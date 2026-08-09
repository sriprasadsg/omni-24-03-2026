"""
Geo Security Detectors — Phase 47 Plan 02 (GSEC-02/GSEC-03).

Pure detector + dedup + config core for agent-scoped impossible-travel
(GSEC-02) and per-tenant country-code geo-fence (GSEC-03). Kept as a
standalone sibling module (47-RESEARCH.md Recommended Project Structure) so
agent_heartbeat_endpoints.py stays under the 500-line cap and this logic is
unit-tested hermetically, without a live DB or a bundled GeoLite2 .mmdb
(47-RESEARCH.md Pitfall 6).

Exports (this module grows across Task 2/3 of 47-02-PLAN.md):
  - evaluate_impossible_travel(...) -> bool  (D-01/D-02/D-08)
  - evaluate_geo_fence(...) -> bool          (D-03)
  - get_geo_security_settings(db, tenant_id) -> dict  (tenant -> global ->
    default resolution, cloned from agent_location_history_service's
    get_track_agent_location / compliance_remediation_sla_service's
    get_sla_at_risk_window)
  - dedup_and_maybe_alert(...) -> bool       (D-05/D-07, shadow field on the
    agents doc: geoSecurityState.<violation_type>.{violating,lastAlertedAt})
  - run_geo_security_detectors(...) -> list[dict]  the orchestrator: RETURNS
    alert payloads for the caller (47-03's heartbeat wiring) to persist via
    ueba_service's public alert-persistence alias. This module never
    imports or calls that alert fan-out itself and performs no connection
    side effects (D-04 alert-only).

Anti-pattern guard (47-RESEARCH.md Pattern 2 / Pitfall 2): impossible-travel
compares against the RAW existing_agent.geo/lastSeen (updated every
heartbeat unconditionally) — never Phase 46's debounced
locationConfirmed/locationPending shadow fields, which solve a different
problem (NAT-flip audit-trail noise).
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from ueba_service import _haversine_km

logger = logging.getLogger(__name__)

# D-01 — fixed max speed (commercial-flight ceiling); not tenant-configurable
# in v3.3 (keep the config surface minimal per CONTEXT.md).
MAX_SPEED_KMH = 1000

# D-08 — noise floor below GeoIP city-level jitter / CGNAT-mobile-carrier IP
# churn at real ~30-60s heartbeat cadence (47-RESEARCH.md Pitfall 4).
MIN_ELAPSED_MINUTES = 15

# D-05 default cooldown; D-07 re-fires once elapsed while still violating
# rather than staying permanently silent after the first alert.
COOLDOWN_WINDOW = timedelta(hours=6)


def evaluate_impossible_travel(
    prev_geo: Optional[Dict[str, Any]],
    prev_last_seen_iso: Optional[str],
    curr_geo: Optional[Dict[str, Any]],
    now: datetime,
    prev_vpn: Optional[bool],
    curr_vpn: Optional[bool],
) -> bool:
    """D-01/D-02/D-08: True iff the implied speed between two RAW consecutive
    check-ins exceeds MAX_SPEED_KMH.

    Guard order (47-RESEARCH.md Pattern 2):
      1. Missing prior state (first-ever check-in) -> False (Pitfall 3).
      2. Missing lat/long on either side -> False.
      3. Either endpoint's vpn_heuristic is True -> False (D-02 full
         suppression; `is True` only — Pitfall 5, a 3-valued signal, never
         truthy/falsy coercion of None).
      4. Clock skew (elapsed <= 0) -> False.
      5. Elapsed < MIN_ELAPSED_MINUTES -> False (D-08 noise floor).
      6. distance_km / elapsed_hours > MAX_SPEED_KMH -> True.
    """
    if not prev_geo or not curr_geo or not prev_last_seen_iso:
        return False  # first-ever check-in — nothing to compare against

    if prev_geo.get("latitude") is None or prev_geo.get("longitude") is None:
        return False
    if curr_geo.get("latitude") is None or curr_geo.get("longitude") is None:
        return False

    if prev_vpn is True or curr_vpn is True:
        return False  # D-02 — full suppression, either endpoint

    try:
        prev_dt = datetime.fromisoformat(str(prev_last_seen_iso).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return False  # malformed timestamp — never crash the heartbeat path

    elapsed_seconds = (now - prev_dt).total_seconds()
    if elapsed_seconds <= 0:
        return False  # clock skew / out-of-order heartbeat

    elapsed_hours = elapsed_seconds / 3600
    if elapsed_hours < (MIN_ELAPSED_MINUTES / 60):
        return False  # D-08 — below the GeoIP-jitter/CGNAT-churn noise floor

    distance_km = _haversine_km(
        prev_geo["latitude"], prev_geo["longitude"],
        curr_geo["latitude"], curr_geo["longitude"],
    )
    return (distance_km / elapsed_hours) > MAX_SPEED_KMH


def evaluate_geo_fence(country_code: Optional[str], allowlist: Optional[List[str]]) -> bool:
    """D-03: True iff country_code is resolved and not in the tenant's
    (case-insensitive, ISO 3166 alpha-2) allowlist. An empty allowlist or a
    missing/empty country_code never fires — callers gate this on
    geo_fence_enabled, which defaults False for exactly this reason (an
    empty allowlist would otherwise alert on every check-in)."""
    if not country_code or not allowlist:
        return False
    normalized = country_code.strip().upper()
    normalized_allowlist = {code.strip().upper() for code in allowlist if code}
    return normalized not in normalized_allowlist


async def get_geo_security_settings(db, tenant_id) -> Dict[str, Any]:
    """Per-tenant geo-security config: tenant doc -> global doc -> hardcoded
    default. Clone of get_track_agent_location / get_sla_at_risk_window's
    3-step resolution (47-RESEARCH.md Pattern 1).

    Args:
        db: TenantIsolatedDatabase (request-scoped) or raw Motor db (sweep).
        tenant_id: tenant identifier string, or None/empty.

    Returns:
        {impossible_travel_enabled, geo_fence_enabled, allowed_country_codes}
    """
    raw = db._db if hasattr(db, "_db") else db
    defaults: Dict[str, Any] = {
        "impossible_travel_enabled": True,
        "geo_fence_enabled": False,  # off by default — see docstring above
        "allowed_country_codes": [],
    }

    if tenant_id:
        doc = await raw.system_settings.find_one(
            {"type": "geo_security_detectors", "tenantId": tenant_id}
        )
        if doc:
            return {**defaults, **{k: v for k, v in doc.items() if k in defaults}}

    doc = await raw.system_settings.find_one(
        {"type": "geo_security_detectors", "tenantId": {"$exists": False}}
    )
    if doc:
        return {**defaults, **{k: v for k, v in doc.items() if k in defaults}}

    return defaults


async def dedup_and_maybe_alert(
    raw_db,
    agent_id: str,
    existing_agent: Optional[Dict[str, Any]],
    violation_type: str,
    violating: bool,
) -> bool:
    """D-05/D-07: returns True iff the caller should fire the alert
    fan-out now.

    Shadow field: geoSecurityState.<violation_type>.{violating, lastAlertedAt}
    on the agents doc — zero extra reads, since existing_agent is already
    fetched by the heartbeat handler before this is called
    (47-RESEARCH.md Pattern 3, deliberately simplified vs. Phase 46's
    4-branch NAT-flip debounce machine — see module docstring).

    Behavior:
      - clean -> violating transition: fires, writes violating=True + now.
      - repeat within COOLDOWN_WINDOW: suppressed, no write.
      - repeat after COOLDOWN_WINDOW elapses, still violating: re-fires
        (D-07), resets lastAlertedAt.
      - violating -> clean: clears violating=False, never fires.
    """
    state = ((existing_agent or {}).get("geoSecurityState") or {}).get(violation_type, {})
    was_violating = state.get("violating", False)
    last_alerted = state.get("lastAlertedAt")
    now = datetime.now(timezone.utc)

    if not violating:
        if was_violating:
            await raw_db.agents.update_one(
                {"id": agent_id},
                {"$set": {f"geoSecurityState.{violation_type}.violating": False}},
            )
        return False

    should_fire = (not was_violating) or (
        last_alerted is None or (now - last_alerted) >= COOLDOWN_WINDOW
    )
    if should_fire:
        await raw_db.agents.update_one(
            {"id": agent_id},
            {"$set": {
                f"geoSecurityState.{violation_type}.violating": True,
                f"geoSecurityState.{violation_type}.lastAlertedAt": now,
            }},
        )
    return should_fire


async def run_geo_security_detectors(
    db,
    existing_agent: Optional[Dict[str, Any]],
    agent_id: str,
    tenant_id: Optional[str],
    curr_geo: Optional[Dict[str, Any]],
    now: datetime,
) -> List[Dict[str, Any]]:
    """Orchestrator: evaluates both detectors (toggle-gated) and RETURNS the
    alert payloads that should be persisted — it does NOT call the alert
    fan-out itself (47-03's heartbeat wiring fires them, keeping this
    module decoupled per the phase's Wave-1 scope). No connection side
    effects (D-04 alert-only).

    Reads the RAW prior heartbeat's geo/lastSeen off existing_agent — never
    the debounced locationConfirmed/locationPending shadow fields (Pitfall 2).
    """
    raw = db._db if hasattr(db, "_db") else db
    existing_agent = existing_agent or {}
    settings = await get_geo_security_settings(raw, tenant_id)
    payloads: List[Dict[str, Any]] = []

    if settings["impossible_travel_enabled"]:
        prev_geo = existing_agent.get("geo")
        prev_last_seen = existing_agent.get("lastSeen")
        prev_vpn = (prev_geo or {}).get("vpn_heuristic")
        curr_vpn = (curr_geo or {}).get("vpn_heuristic")
        violating = evaluate_impossible_travel(
            prev_geo, prev_last_seen, curr_geo, now, prev_vpn, curr_vpn,
        )
        should_fire = await dedup_and_maybe_alert(
            raw, agent_id, existing_agent, "impossible_travel", violating,
        )
        if should_fire:
            payloads.append({
                "alert_type": "impossible_travel",
                "severity": "high",
                "title": f"Impossible travel detected for agent {agent_id}",
                "description": (
                    f"Agent {agent_id} checked in from a location that is physically "
                    "impossible to reach from its previous check-in within the elapsed time."
                ),
                "metadata": {
                    "agent_id": agent_id,
                    "tenant_id": tenant_id,
                    "prev_geo": prev_geo,
                    "curr_geo": curr_geo,
                },
            })

    if settings["geo_fence_enabled"]:
        country_code = (curr_geo or {}).get("country_code")
        violating = evaluate_geo_fence(country_code, settings["allowed_country_codes"])
        should_fire = await dedup_and_maybe_alert(
            raw, agent_id, existing_agent, "geo_fence_violation", violating,
        )
        if should_fire:
            payloads.append({
                "alert_type": "geo_fence_violation",
                "severity": "medium",
                "title": f"Geo-fence violation for agent {agent_id}",
                "description": (
                    f"Agent {agent_id} checked in from country '{country_code}', which is "
                    "outside the tenant's allowed-country allowlist."
                ),
                "metadata": {
                    "agent_id": agent_id,
                    "tenant_id": tenant_id,
                    "country_code": country_code,
                    "allowed_country_codes": settings["allowed_country_codes"],
                },
            })

    return payloads

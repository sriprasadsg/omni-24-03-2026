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
  - dedup_and_maybe_alert(...) / run_geo_security_detectors(...) land in
    Task 3 — the orchestrator RETURNS alert payloads for 47-03's heartbeat
    wiring to persist via ueba_service.persist_security_alert; this module
    never imports or calls persist_security_alert itself (D-04 alert-only,
    no connection side effects).

Anti-pattern guard (47-RESEARCH.md Pattern 2 / Pitfall 2): impossible-travel
compares against the RAW existing_agent.geo/lastSeen (updated every
heartbeat unconditionally) — never Phase 46's debounced
locationConfirmed/locationPending shadow fields, which solve a different
problem (NAT-flip audit-trail noise).
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from ueba_service import _haversine_km

logger = logging.getLogger(__name__)

# D-01 — fixed max speed (commercial-flight ceiling); not tenant-configurable
# in v3.3 (keep the config surface minimal per CONTEXT.md).
MAX_SPEED_KMH = 1000

# D-08 — noise floor below GeoIP city-level jitter / CGNAT-mobile-carrier IP
# churn at real ~30-60s heartbeat cadence (47-RESEARCH.md Pitfall 4).
MIN_ELAPSED_MINUTES = 15


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

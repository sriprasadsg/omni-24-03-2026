"""
Agent Location History Service.

Change-detection + NAT-flip de-noise state machine that decides when a
public-IP/geo change is real enough to append an immutable
agent_location_history row (GAUD-01), plus the per-tenant
track_agent_location toggle lookup (D-02). This is the load-bearing logic
of Phase 46 — called inline from the heartbeat/register handlers (wired in
46-05) with the existing_agent doc already in hand (zero extra reads, D-05).

Exports:
  - get_track_agent_location(db, tenant_id) -> bool — per-tenant toggle,
    tenant-doc -> global-doc -> hardcoded-default(True) lookup, cloned
    verbatim from
    compliance_remediation_sla_service.get_sla_at_risk_window() (renaming
    type -> "track_agent_location", field -> "enabled").
  - record_location_change(db, existing_agent, agent_id, tenant_id,
    public_ip, geo, asn_enrichment, now=None) -> bool — the 4-branch
    NAT-flip de-noise state machine (46-RESEARCH.md "Pitfall 1"). Writes an
    immutable agent_location_history row only on a *confirmed* change (a
    candidate that has either been the agent's location since its very
    first observation, or has been stable for >= DEBOUNCE_WINDOW). Returns
    True iff a row was written.

Anti-pattern guard (46-RESEARCH.md / Pitfall 6): agent_location_history's
timestamp field must always be a native datetime object (a real BSON Date),
never converted to a string representation — required for both the
app-level 365-day retention $lt sweep and any future TTL index.

Append-only guarantee (D-10 backend half, T-46-02-A): this module only ever
issues agent_location_history.insert_one — it never update/delete/replace's
an existing history row. The locationConfirmed/locationPending shadow
fields it maintains live on the *agent* doc, not on any history row.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# NAT-flip de-noise debounce window (D-06) — Claude's Discretion per
# CONTEXT.md; ~10 minutes matches the stated NAT-lease-flip timescale.
DEBOUNCE_WINDOW = timedelta(minutes=10)


async def get_track_agent_location(db, tenant_id) -> bool:
    """Per-tenant track_agent_location toggle (D-02).

    Lookup order:
    1. Per-tenant doc: {type: "track_agent_location", tenantId: <tenant_id>}
    2. Global doc:     {type: "track_agent_location"} (no tenantId field)
    3. Hard-coded default: True

    Args:
        db: TenantIsolatedDatabase (request-scoped) or raw Motor db (sweep).
        tenant_id: tenant identifier string or None/empty.

    Returns:
        bool — True (default ON) unless a resolved doc explicitly sets
        "enabled": False.
    """
    raw = db._db if hasattr(db, "_db") else db

    if tenant_id:
        doc = await raw.system_settings.find_one(
            {"type": "track_agent_location", "tenantId": tenant_id}
        )
        if doc and isinstance(doc.get("enabled"), bool):
            return doc["enabled"]
    doc = await raw.system_settings.find_one(
        {"type": "track_agent_location", "tenantId": {"$exists": False}}
    )
    if doc and isinstance(doc.get("enabled"), bool):
        return doc["enabled"]
    return True  # D-02: default ON


def _geo_key(geo: Optional[Dict[str, Any]]) -> tuple:
    """City/country comparison key (D-05: 'publicIp OR resolved city/country')."""
    if not geo:
        return (None, None)
    return (geo.get("city"), geo.get("country"))


def _candidate_matches(candidate_ip: Optional[str], candidate_geo: Optional[Dict[str, Any]],
                        stored: Optional[Dict[str, Any]]) -> bool:
    """True iff (public_ip, city/country) both match a stored shadow-field value."""
    if not stored:
        return False
    return (
        stored.get("publicIp") == candidate_ip
        and _geo_key(stored.get("geo")) == _geo_key(candidate_geo)
    )


def _location_snapshot(public_ip: str, geo: Optional[Dict[str, Any]], at: datetime, *, confirmed: bool) -> Dict[str, Any]:
    key = "confirmedAt" if confirmed else "firstSeenAt"
    return {"publicIp": public_ip, "geo": geo, key: at}


async def _promote(raw, agent_id: str, tenant_id: Optional[str], public_ip: str,
                    geo: Optional[Dict[str, Any]], asn_enrichment: Optional[Dict[str, Any]],
                    now: datetime) -> None:
    """Write the one immutable agent_location_history row for this confirmed
    change, and update the agent doc's shadow fields accordingly. Never
    mutates/deletes an existing history row — insert_one only."""
    asn_enrichment = asn_enrichment or {}
    await raw.agent_location_history.insert_one({
        "agent_id": agent_id,
        "tenantId": tenant_id,
        "publicIp": public_ip,
        "geo": geo,
        "asn": asn_enrichment.get("asn"),
        "vpn_heuristic": asn_enrichment.get("vpn_heuristic"),
        "timestamp": now,  # native datetime (BSON Date) — never string-formatted
    })
    await raw.agents.update_one(
        {"id": agent_id},
        {
            "$set": {"locationConfirmed": _location_snapshot(public_ip, geo, now, confirmed=True)},
            "$unset": {"locationPending": ""},
        },
    )


async def record_location_change(
    db,
    existing_agent: Optional[Dict[str, Any]],
    agent_id: str,
    tenant_id: Optional[str],
    public_ip: Optional[str],
    geo: Optional[Dict[str, Any]],
    asn_enrichment: Optional[Dict[str, Any]],
    now: Optional[datetime] = None,
) -> bool:
    """4-branch NAT-flip de-noise state machine (46-RESEARCH.md Pitfall 1).

    Branches (evaluated in order):
    1. Candidate equals the confirmed baseline -> no-op (common case, most
       heartbeats hit this branch); any stale locationPending is discarded.
    2. No confirmed baseline exists yet (first-ever observation) -> promote
       immediately, no debounce — there is nothing to de-noise against.
    3. Candidate equals the current pending candidate:
       a. >= DEBOUNCE_WINDOW has elapsed since it first appeared -> promote.
       b. otherwise -> no-op, keep waiting.
    4. A genuinely new candidate (differs from both confirmed and any
       current pending) -> reset locationPending to this candidate,
       discarding whatever was pending before. This is what collapses an
       A->B->A flip-flop: B never accumulates enough dwell time to promote
       before the agent flips back to A, which matches locationConfirmed
       and short-circuits at branch 1 with the stale pending discarded.

    Never blocks/delays the caller's heartbeat response and never mutates
    an already-written agent_location_history row.

    Returns:
        True iff a new agent_location_history row was written.
    """
    if not public_ip:
        return False

    if not await get_track_agent_location(db, tenant_id):
        return False  # D-02: toggle OFF -> enrichment/write both skipped

    raw = db._db if hasattr(db, "_db") else db
    now = now or datetime.now(timezone.utc)
    existing_agent = existing_agent or {}
    confirmed = existing_agent.get("locationConfirmed")
    pending = existing_agent.get("locationPending")

    # Branch 1: candidate matches the confirmed baseline.
    if confirmed and _candidate_matches(public_ip, geo, confirmed):
        if pending:
            # Discard the stale pending candidate — this is the de-noise:
            # a flip back to the confirmed value invalidates any in-flight
            # candidate rather than letting it silently keep accumulating
            # dwell time toward a future, no-longer-accurate promotion.
            await raw.agents.update_one({"id": agent_id}, {"$unset": {"locationPending": ""}})
        return False

    # Branch 2: no confirmed baseline yet — first-ever observation promotes
    # immediately (there is no prior state to de-noise against).
    if confirmed is None:
        await _promote(raw, agent_id, tenant_id, public_ip, geo, asn_enrichment, now)
        return True

    # Branch 3: candidate matches the current pending candidate.
    if pending and _candidate_matches(public_ip, geo, pending):
        first_seen = pending.get("firstSeenAt")
        elapsed_enough = isinstance(first_seen, datetime) and (now - first_seen) >= DEBOUNCE_WINDOW
        if elapsed_enough:
            await _promote(raw, agent_id, tenant_id, public_ip, geo, asn_enrichment, now)
            return True
        return False  # still bouncing within the debounce window

    # Branch 4: a genuinely new candidate — start (or restart) the pending
    # window. Discards any previously-pending, different candidate.
    await raw.agents.update_one(
        {"id": agent_id},
        {"$set": {"locationPending": _location_snapshot(public_ip, geo, now, confirmed=False)}},
    )
    return False

"""Scheduled retention: the type registry and the per-(tenant, type) confirmation gate (phase 82).

The nightly job (``retention_job``) deletes old records of exactly eight routine data types and
nothing else. Before a Super Admin has confirmed the counts, every (tenant, type) only counts
what *would* be deleted (D-18). A tenant that later shortens a period goes back to counting for
that data type only (D-19); lengthening needs no review.

Collections written here (all on the raw handle, explicit tenant field on every filter):

* ``retention_gate``        one document per (tenantId, type): confirmedDays, firstSeenAt (informational:
                            it decides nothing; adoption keys on the tenant's creation time, CR-01)
* ``retention_gate_global`` one document ``{_id: "global"}``: confirmedAt, confirmedBy
* ``retention_counts``      latest count per (tenantId, type): days, count, countedAt, error
* ``retention_job_runs``    one summary per run (written by retention_job)

This module deliberately imports nothing from ``retention_service``: the registry here is the
single source for count, delete, labels and the per-tenant gate flags.
"""
import hashlib
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, List, Optional

from pymongo import ReturnDocument

from autonomous_ops import PROTECTED_COLLECTIONS
from autonomous_ops.scope import raw

logger = logging.getLogger(__name__)

GATE = "retention_gate"
GATE_GLOBAL = "retention_gate_global"
COUNTS = "retention_counts"
RUNS = "retention_job_runs"
GLOBAL_ID = "global"

MIN_DAYS = 1
MAX_DAYS = 3650


@dataclass(frozen=True)
class RetentionType:
    id: str
    collection: str
    tenant_field: str
    time_kind: str          # "iso" (ISO-8601 string), "date" (BSON date) or "objectid" (creation time)
    time_field: Optional[str]
    default_days: int
    label: str


# Registry order is the display order. Tenant fields are the ones the collections actually store:
# agent_uptime_rollups, agent_metrics and asset_metrics use ``tenant_id`` (the tenant wrapper would
# inject ``tenantId``), so every filter goes through the raw handle with the stored field.
RETENTION_TYPES = (
    RetentionType("metrics", "metrics", "tenantId", "iso", "timestamp", 30, "System metrics"),
    RetentionType("notifications", "notifications", "tenantId", "iso", "sent_at", 30, "Notifications"),
    RetentionType("agent_location_history", "agent_location_history", "tenantId", "date", "timestamp",
                  365, "Agent location history"),
    RetentionType("agent_uptime_rollups", "agent_uptime_rollups", "tenant_id", "date", "timestamp",
                  90, "Agent uptime"),
    RetentionType("agent_metrics", "agent_metrics", "tenant_id", "objectid", None, 30, "Agent metrics"),
    RetentionType("asset_metrics", "asset_metrics", "tenant_id", "objectid", None, 30, "Asset metrics"),
    RetentionType("persistence_results", "persistence_results", "tenantId", "objectid", None, 90,
                  "Persistence results"),
    RetentionType("logs", "logs", "tenantId", "objectid", None, 30, "Logs"),
)

TYPE_IDS = tuple(t.id for t in RETENTION_TYPES)
BY_ID: Dict[str, RetentionType] = {t.id: t for t in RETENTION_TYPES}

# Audit evidence, the audit ledger chain, decision records and compliance evidence are never
# deleted by scheduled retention (PROH-82-05, GATE-07).
NEVER_DELETED = frozenset({
    "audit_logs", "audit_chain_heads", "audit_chain_checkpoints",
    "autonomy_actions", "autonomy_settings", "autonomy_never_touch",
    "compliance_evidence",
}) | frozenset(PROTECTED_COLLECTIONS)

assert not ({t.collection for t in RETENTION_TYPES} & NEVER_DELETED), \
    "retention registry must never include a protected collection"
assert len(TYPE_IDS) == 8 and len(set(TYPE_IDS)) == 8


def aware(value: Optional[datetime]) -> Optional[datetime]:
    """Mongo hands back naive UTC datetimes unless the client is tz-aware; make them aware."""
    if value is None:
        return None
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def _read_time(value) -> Optional[datetime]:
    """One stored time as an aware UTC-or-offset datetime, or None when it is absent or unreadable.
    A datetime goes through ``aware`` (naive means UTC); a non-empty ISO-8601 string (a trailing Z
    is accepted) is parsed and then made aware. Nothing is rounded or truncated."""
    if isinstance(value, datetime):
        return aware(value)
    if isinstance(value, str) and value.strip():
        text = value.strip()
        if text.endswith(("Z", "z")):
            text = text[:-1] + "+00:00"
        try:
            return aware(datetime.fromisoformat(text))
        except (ValueError, TypeError, OverflowError):
            return None
    return None


def created_at_of(tenant: Optional[dict]) -> Optional[datetime]:
    """When the tenant was created, from ``createdAt`` and ``created_at`` (the writers disagree on
    the name). Fails closed: None when neither field is readable; when both are, the earlier one."""
    if not isinstance(tenant, dict):
        return None
    found = [t for t in (_read_time(tenant.get("createdAt")), _read_time(tenant.get("created_at")))
             if t is not None]
    return min(found) if found else None


async def tenant_created_at(db, tenant_id: Optional[str]) -> Optional[datetime]:
    """``created_at_of`` the tenant with this id; None for an empty id (a filter on a None id would
    match a document without an id field). A read error propagates: the run records the tenant failed."""
    if not tenant_id:
        return None
    doc = await raw(db).tenants.find_one({"id": tenant_id}, {"_id": 0, "createdAt": 1, "created_at": 1})
    return created_at_of(doc)


def gate_state(policy_days: int, confirmed_days: Optional[int], global_confirmed_at: Optional[datetime],
               tenant_created_at: Optional[datetime]) -> str:
    """first_run | adopt | shortened | confirmed. Only confirmed and adopt delete (D-18, D-19).

    adopt (A-82-A12, narrowed by the CR-01 gap round): never confirmed, and the tenant itself was
    created strictly after the one global confirmation, so a reviewer could not have seen it and it
    holds nothing old. A data type added to the registry later for an existing tenant waits for the
    review. Every other unconfirmed case, an unknown time or an equal one included, is first_run.
    """
    if confirmed_days is None:
        created, confirmed_at = aware(tenant_created_at), aware(global_confirmed_at)
        if confirmed_at is not None and created is not None and created > confirmed_at:
            return "adopt"
        return "first_run"
    return "shortened" if policy_days < confirmed_days else "confirmed"


def valid_days(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and MIN_DAYS <= value <= MAX_DAYS


async def load_policy_days(db, tenant_id: str) -> Dict[str, int]:
    """The tenant's configured days per registry type. Only integer periods of 1..3650 are
    accepted: the retention_tiers writer stores a different document shape in the same
    collection, and a malformed value must fall back to the default rather than delete."""
    out: Dict[str, int] = {}
    cursor = raw(db).retention_policies.find(
        {"tenantId": tenant_id, "collection": {"$in": list(TYPE_IDS)}},
        {"_id": 0, "collection": 1, "retention_days": 1}).sort("_id", 1)
    async for doc in cursor:
        if valid_days(doc.get("retention_days")):
            out[doc["collection"]] = doc["retention_days"]
    return out


def effective_days(policies: Dict[str, int], rtype: RetentionType) -> int:
    return policies.get(rtype.id, rtype.default_days)


async def global_confirmed_at(db) -> Optional[datetime]:
    doc = await raw(db)[GATE_GLOBAL].find_one({"_id": GLOBAL_ID}, {"confirmedAt": 1})
    return aware(doc.get("confirmedAt")) if doc else None


async def mark_seen(db, tenant_id: str, type_id: str, now: datetime) -> dict:
    """The gate row for (tenant, type), created with confirmedDays null on first sight."""
    return await raw(db)[GATE].find_one_and_update(
        {"tenantId": tenant_id, "type": type_id},
        {"$setOnInsert": {"tenantId": tenant_id, "type": type_id, "confirmedDays": None,
                          "firstSeenAt": now}},
        upsert=True, return_document=ReturnDocument.AFTER, projection={"_id": 0})


async def gate_rows(db, tenant_id: str) -> Dict[str, dict]:
    return {d["type"]: d async for d in raw(db)[GATE].find({"tenantId": tenant_id}, {"_id": 0})}


async def set_confirmed_days(db, tenant_id: str, type_id: str, days: int, now: datetime,
                             actor: Optional[str] = None) -> None:
    update = {"confirmedDays": days, "updatedAt": now}
    if actor:
        update.update({"confirmedBy": actor, "confirmedAt": now})
    await raw(db)[GATE].update_one(
        {"tenantId": tenant_id, "type": type_id},
        {"$set": update, "$setOnInsert": {"tenantId": tenant_id, "type": type_id, "firstSeenAt": now}},
        upsert=True)


# ---------------------------------------------------------------------------- review and confirm

class StaleReview(Exception):
    """The waiting rows changed (a recount, a new policy) since the reviewer loaded them."""


class ReviewIncomplete(Exception):
    """The counted set is known to be incomplete (T-82-47); ``gap`` is ``{reason, tenants}``."""

    def __init__(self, gap: dict):
        super().__init__("the retention review is incomplete: " + str(gap.get("reason")))
        self.gap = gap


def _iso(value) -> str:
    value = aware(value) if isinstance(value, datetime) else value
    return value.isoformat() if value is not None else ""


def usable_count(counted: Optional[dict], days: int) -> bool:
    """A stored count the review can show: it exists, did not fail, and is for the current period."""
    return bool(counted) and not counted.get("error") and counted.get("days") == days \
        and isinstance(counted.get("count"), int)


async def review_rows(db) -> List[dict]:
    """The rows waiting for a Super Admin: first_run and shortened, with their latest count.

    ``count`` is None while there is no usable count (never counted, a failed count, or a count
    taken at a different period than the tenant's current policy); such rows are shown but never
    confirmed. ``previousDays`` is the last confirmed period (None for a first run), so shortening
    90 -> 60 -> 30 before confirming still reports 90.
    """
    rdb = raw(db)
    global_at = await global_confirmed_at(db)
    names: Dict[str, str] = {}
    created: Dict[str, Optional[datetime]] = {}
    async for t in rdb.tenants.find({}, {"_id": 0, "id": 1, "name": 1, "createdAt": 1, "created_at": 1}):
        if t.get("id"):
            names[t["id"]] = t.get("name") or t["id"]
            created[t["id"]] = created_at_of(t)
    counts = {(c["tenantId"], c["type"]): c async for c in rdb[COUNTS].find({}, {"_id": 0})}
    policies: Dict[str, Dict[str, int]] = {}
    rows: List[dict] = []
    async for gate in rdb[GATE].find({}, {"_id": 0}):
        rtype = BY_ID.get(gate.get("type"))
        tenant_id = gate.get("tenantId")
        if rtype is None or tenant_id not in names:
            continue
        if tenant_id not in policies:
            policies[tenant_id] = await load_policy_days(db, tenant_id)
        days = effective_days(policies[tenant_id], rtype)
        state = gate_state(days, gate.get("confirmedDays"), global_at, created.get(tenant_id))
        if state not in ("first_run", "shortened"):
            continue
        counted = counts.get((tenant_id, rtype.id)) or {}
        error = counted.get("error")
        usable = usable_count(counted, days)
        rows.append({
            "tenantId": tenant_id, "tenantName": names[tenant_id], "type": rtype.id,
            "label": rtype.label, "collection": rtype.collection, "days": days,
            "previousDays": gate.get("confirmedDays"),
            "count": counted["count"] if usable else None,
            "countError": error or None, "countedAt": counted.get("countedAt"),
            "reason": state,
        })
    rows.sort(key=lambda r: (-(r["count"] or 0), r["tenantName"].lower(), r["type"]))
    return rows


async def incomplete_review(db) -> Optional[dict]:
    """Why a confirmation would speak for organizations nobody counted, or None when it would not.

    ``{"reason": "stopped_early" | "tenant_failed" | "not_reached", "tenants": n}`` where n is the
    number of organizations concerned. The latest *scheduled* run decides stopped_early and
    tenant_failed. A tenant is not reached when it lacks a gate row for any registry type, unless its
    creation time is readable and strictly later than the global confirmation or than that run's start
    (it did not exist when the set was counted). An unreadable time never exempts, and rows made by
    manual runs only ever cover their own tenant. Shared by confirm() and GET /review (CR-01)."""
    rdb = raw(db)
    run = await rdb[RUNS].find_one({"trigger": "scheduled"},
                                   {"_id": 0, "startedAt": 1, "stoppedEarly": 1, "failedTenants": 1},
                                   sort=[("startedAt", -1)])
    run_start = _read_time(run.get("startedAt")) if run else None
    global_at = await global_confirmed_at(db)
    covered: Dict[str, set] = {}
    async for row in rdb[GATE].find({}, {"_id": 0, "tenantId": 1, "type": 1}):
        covered.setdefault(row.get("tenantId"), set()).add(row.get("type"))
    not_reached = set()
    async for tenant in rdb.tenants.find({}, {"_id": 0, "id": 1, "createdAt": 1, "created_at": 1}):
        tenant_id = tenant.get("id")
        if not tenant_id or set(TYPE_IDS) <= covered.get(tenant_id, set()):
            continue
        created = created_at_of(tenant)
        if created is not None and ((global_at is not None and created > global_at)
                                    or (run_start is not None and created > run_start)):
            continue
        not_reached.add(tenant_id)
    failed = {t for t in ((run or {}).get("failedTenants") or []) if isinstance(t, str)}
    gap = {"tenants": len(failed | not_reached)}
    if run and run.get("stoppedEarly"):
        return {"reason": "stopped_early", **gap}
    if failed:
        return {"reason": "tenant_failed", **gap}
    if not_reached:
        return {"reason": "not_reached", **gap}
    return None


def review_token(rows: List[dict]) -> str:
    """Stateless stale-review guard: a hash of the sorted waiting rows."""
    lines = sorted(f"{r['tenantId']}|{r['type']}|{r['days']}|{r['count']}|{_iso(r.get('countedAt'))}"
                   for r in rows)
    return hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest()


def _eligible(row: dict) -> bool:
    return row.get("count") is not None and not row.get("countError")


async def confirm(db, token: str, actor: str, now: datetime) -> dict:
    """Confirm the counted waiting rows the reviewer saw. Raises StaleReview when the waiting
    set no longer matches ``token``, and ReviewIncomplete (before any write) when something would be
    confirmed while ``incomplete_review`` says the counted set is incomplete. Deletes nothing itself:
    the next run deletes."""
    rows = await review_rows(db)
    if token != review_token(rows):
        raise StaleReview("the retention review changed; reload it")
    confirmed = [r for r in rows if _eligible(r)]
    if confirmed:
        gap = await incomplete_review(db)
        if gap is not None:
            raise ReviewIncomplete(gap)
    rdb = raw(db)
    for row in confirmed:
        await set_confirmed_days(db, row["tenantId"], row["type"], row["days"], now, actor=actor)
    if confirmed:
        await rdb[GATE_GLOBAL].update_one(
            {"_id": GLOBAL_ID}, {"$setOnInsert": {"confirmedAt": now, "confirmedBy": actor}}, upsert=True)
    logger.info("retention: %d row(s) confirmed by %s", len(confirmed), actor)
    return {"rows": len(confirmed), "records": sum(r["count"] for r in confirmed),
            "tenants": len({r["tenantId"] for r in confirmed})}


async def tenant_gate_flags(db, tenant_id: str) -> Dict[str, dict]:
    """Per type: is this tenant's data type waiting for a confirmation, and why."""
    global_at = await global_confirmed_at(db)
    created = await tenant_created_at(db, tenant_id)
    policies = await load_policy_days(db, tenant_id)
    gates = await gate_rows(db, tenant_id)
    flags: Dict[str, dict] = {}
    for rtype in RETENTION_TYPES:
        gate = gates.get(rtype.id) or {}
        state = gate_state(effective_days(policies, rtype), gate.get("confirmedDays"), global_at, created)
        waiting = state in ("first_run", "shortened")
        flags[rtype.id] = {"waiting": waiting, "reason": state if waiting else None}
    return flags


async def ensure_indexes(db) -> None:
    rdb = raw(db)
    await rdb[GATE].create_index([("tenantId", 1), ("type", 1)], unique=True, name="retention_gate_tenant_type")
    await rdb[COUNTS].create_index([("tenantId", 1), ("type", 1)], unique=True,
                                   name="retention_counts_tenant_type")
    await rdb[RUNS].create_index([("startedAt", -1)], name="retention_runs_started")

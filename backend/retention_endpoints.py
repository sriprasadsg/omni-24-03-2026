from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from auth_utils import require_auth
from auth_roles import tenant_admin_roles

_RETENTION_ADMIN_ROLES = tenant_admin_roles()
import retention_gate
import retention_job
from database import get_database
from datetime import datetime, timezone

router = APIRouter(prefix="/api/retention", tags=["retention"])


class RetentionPolicyUpdate(BaseModel):
    retention_days: int = Field(90, ge=1, le=3650)

# Seed defaults used only when the DB collection is empty
_POLICY_DEFAULTS = {
    "audit_logs":       {"retention_days": 90,  "description": "Retain audit logs for 90 days"},
    "metrics":          {"retention_days": 30,  "description": "Retain metrics for 30 days"},
    "notifications":    {"retention_days": 30,  "description": "Retain notifications for 30 days"},
    "security_events":  {"retention_days": 180, "description": "Retain security events for 180 days"},
    "alerts":           {"retention_days": 365, "description": "Retain alerts for 365 days"},
    "agent_location_history": {"retention_days": 365, "description": "Retain agent location-history audit records for 365 days"},
}


async def _ensure_seeded(db):
    """Upsert default policies so seeding is idempotent and race-safe."""
    for collection_name, defaults in _POLICY_DEFAULTS.items():
        await db.retention_policies.update_one(
            {"collection": collection_name},
            {"$setOnInsert": {
                "collection": collection_name,
                **defaults,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }},
            upsert=True,
        )


AUDIT_LOGS_NOTE = "Audit logs are kept by the audit ledger's own schedule, not by this cleanup."
RUN_BUSY = "A retention run is in progress. Try again when it finishes."


def _tenant_of(user):
    return getattr(user, "tenant_id", None)


@router.get("/policies")
async def get_policies(user=Depends(require_auth)):
    db = get_database()
    await _ensure_seeded(db)
    docs = await db.retention_policies.find({}, {"_id": 0}).to_list(length=100)
    flags = await retention_gate.tenant_gate_flags(db, _tenant_of(user))
    seen: set = set()
    unique_docs = []
    for doc in docs:
        if doc["collection"] not in seen:
            seen.add(doc["collection"])
            doc["gate"] = flags.get(doc["collection"]) or {"waiting": False, "reason": None}
            if doc["collection"] == "audit_logs":
                doc.update({"managedBy": "audit_ledger", "editable": False})
            else:
                doc["editable"] = True
            unique_docs.append(doc)
    return {"policies": unique_docs}


def _manual_result(summary: dict):
    """The per-type outcome of a manual run: a flat tile map (``<type>_counted`` or ``<type>_deleted``)
    for the existing result card, and a list with the state and the number for each data type."""
    tiles, types = {"status": "completed"}, []
    for type_id in retention_gate.TYPE_IDS:
        info = (summary.get("types") or {}).get(type_id)
        if info is None:
            continue
        rtype = retention_gate.BY_ID[type_id]
        entry = {"type": type_id, "label": rtype.label, "days": info.get("days")}
        if "error" in info and "deleted" not in info:
            entry["state"] = "failed"
        elif info.get("state") in ("confirmed", "adopt"):
            entry.update(state="deleted", deleted=info.get("deleted", 0))
            tiles[f"{type_id}_deleted"] = entry["deleted"]
        else:
            entry.update(state="counted", count=info.get("count"))
            tiles[f"{type_id}_counted"] = info.get("count") or 0
            if info.get("error"):
                entry["countFailed"] = True
        types.append(entry)
    return tiles, types


@router.post("/run")
async def run_cleanup(user=Depends(require_auth)):
    if getattr(user, "role", None) not in _RETENTION_ADMIN_ROLES:
        raise HTTPException(status_code=403, detail="Admin role required")
    tenant_id = _tenant_of(user)
    if not tenant_id:          # a delete path: an empty tenant must never reach the filters
        raise HTTPException(status_code=400, detail="A tenant is required to run retention")
    db = get_database()
    await _ensure_seeded(db)
    summary = await retention_job.run_manual(db, tenant_id)
    if summary is None:
        raise HTTPException(status_code=409, detail=RUN_BUSY)
    result, types = _manual_result(summary)
    ran_at = datetime.now(timezone.utc).isoformat()
    await db.retention_runs.insert_one({"ran_at": ran_at, "result": result, "types": types})
    return {"status": "completed", "ran_at": ran_at, "result": result, "types": types,
            "stoppedEarly": bool(summary.get("stoppedEarly"))}


@router.post("/policies/{collection}")
async def update_policy(collection: str, body: RetentionPolicyUpdate, user=Depends(require_auth)):
    if getattr(user, "role", None) not in _RETENTION_ADMIN_ROLES:
        raise HTTPException(status_code=403, detail="Admin role required")
    if collection == "audit_logs":
        raise HTTPException(status_code=409, detail=AUDIT_LOGS_NOTE)
    db = get_database()
    await _ensure_seeded(db)
    known = set(_POLICY_DEFAULTS.keys())
    existing = {doc["collection"] for doc in await db.retention_policies.find({}, {"collection": 1, "_id": 0}).to_list(length=100)}
    if collection not in known and collection not in existing:
        return {"error": "Unknown collection"}, 404
    days = body.retention_days
    await db.retention_policies.update_one(
        {"collection": collection},
        {"$set": {"retention_days": days, "updated_at": datetime.now(timezone.utc).isoformat()}},
        upsert=True,
    )
    waiting = False
    if collection in retention_gate.BY_ID:
        waiting = (await retention_gate.tenant_gate_flags(db, _tenant_of(user)))[collection]["waiting"]
    return {"collection": collection, "retention_days": days, "updated": True,
            "countOnlyUntilConfirmed": waiting}


@router.get("/stats")
async def get_stats(user=Depends(require_auth)):
    db = get_database()
    await _ensure_seeded(db)
    policies_count = await db.retention_policies.count_documents({})
    collections = [doc["collection"] for doc in await db.retention_policies.find({}, {"collection": 1, "_id": 0}).to_list(length=100)]
    last_run = await db.retention_runs.find_one({}, {"_id": 0}, sort=[("ran_at", -1)])
    return {
        "policies": policies_count,
        "collections": collections,
        "last_cleanup": last_run["ran_at"] if last_run else None,
        "next_scheduled": retention_job.next_scheduled(datetime.now(timezone.utc)).isoformat(),
    }

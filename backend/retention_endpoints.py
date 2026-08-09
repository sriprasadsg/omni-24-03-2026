from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from auth_utils import require_auth

_RETENTION_ADMIN_ROLES = {"Super Admin", "super_admin", "platform-admin", "admin", "Tenant Admin"}
from retention_service import RetentionService
from database import get_db, get_database
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


def get_svc(db=Depends(get_db)):
    return RetentionService(db)


@router.get("/policies")
async def get_policies(user=Depends(require_auth)):
    db = get_database()
    await _ensure_seeded(db)
    docs = await db.retention_policies.find({}, {"_id": 0}).to_list(length=100)
    seen: set = set()
    unique_docs = []
    for doc in docs:
        if doc["collection"] not in seen:
            seen.add(doc["collection"])
            unique_docs.append(doc)
    return {"policies": unique_docs}


@router.post("/run")
async def run_cleanup(user=Depends(require_auth), svc: RetentionService = Depends(get_svc)):
    if getattr(user, "role", None) not in _RETENTION_ADMIN_ROLES:
        raise HTTPException(status_code=403, detail="Admin role required")
    db = get_database()
    await _ensure_seeded(db)
    policies = {
        doc["collection"]: doc["retention_days"]
        for doc in await db.retention_policies.find({}, {"collection": 1, "retention_days": 1, "_id": 0}).to_list(length=100)
    }
    result = await svc.run_cleanup(policies=policies)
    ran_at = datetime.now(timezone.utc).isoformat()
    await db.retention_runs.insert_one({"ran_at": ran_at, "result": result})
    return {"status": "completed", "ran_at": ran_at, "result": result}


@router.post("/policies/{collection}")
async def update_policy(collection: str, body: RetentionPolicyUpdate, user=Depends(require_auth)):
    if getattr(user, "role", None) not in _RETENTION_ADMIN_ROLES:
        raise HTTPException(status_code=403, detail="Admin role required")
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
    return {"collection": collection, "retention_days": days, "updated": True}


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
        "next_scheduled": None,
    }

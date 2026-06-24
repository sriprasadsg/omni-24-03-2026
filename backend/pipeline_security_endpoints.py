"""CI/CD Pipeline Security endpoints."""
from __future__ import annotations
import time
from fastapi import APIRouter, HTTPException, Depends
from auth_utils import get_current_user
from auth_roles import SUPER_ROLES as _PIPELINE_SUPER_ROLES

router = APIRouter(prefix="/api/pipeline-security", tags=["Pipeline Security"])


async def _db():
    from database import get_database
    return get_database()


def _tenant(user):
    return getattr(user, "tenant_id", None)


def _role(user):
    return getattr(user, "role", None)


@router.get("/scans")
async def list_pipeline_scans(db=Depends(_db), current_user=Depends(get_current_user)):
    """List recent pipeline security scan results."""
    tenant_id = _tenant(current_user)
    query = {} if _role(current_user) in _PIPELINE_SUPER_ROLES else {"tenantId": tenant_id}
    cursor = db["pipeline_scans"].find(query, {"_id": 0}).sort("scanned_at", -1).limit(50)
    items = await cursor.to_list(length=50)
    return items


@router.get("/scans/{scan_id}")
async def get_scan(scan_id: str, db=Depends(_db), current_user=Depends(get_current_user)):
    tenant_id = _tenant(current_user)
    scan_filter: dict = {"id": scan_id}
    if tenant_id and _role(current_user) not in _PIPELINE_SUPER_ROLES:
        scan_filter["tenantId"] = tenant_id
    doc = await db["pipeline_scans"].find_one(scan_filter, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Scan not found")
    return doc


@router.post("/scans")
async def trigger_scan(payload: dict, db=Depends(_db), current_user=Depends(get_current_user)):
    """Trigger a pipeline security scan for a repository."""
    tenant_id = _tenant(current_user)
    scan = {
        "id": f"scan-{int(time.time())}",
        "repo": payload.get("repo", "unknown"),
        "branch": payload.get("branch", "main"),
        "pipeline": payload.get("pipeline", "ci"),
        "status": "queued",
        "scanned_at": time.time(),
        "triggered_by": current_user.get("sub"),
        "findings": [],
    }
    if tenant_id:
        scan["tenantId"] = tenant_id
    await db["pipeline_scans"].insert_one(scan)
    scan.pop("_id", None)
    return scan


@router.get("/policies")
async def list_policies(db=Depends(_db), current_user=Depends(get_current_user)):
    """Return pipeline security gate policies."""
    tenant_id = _tenant(current_user)
    query = {} if _role(current_user) in _PIPELINE_SUPER_ROLES else {"tenantId": tenant_id}
    cursor = db["pipeline_policies"].find(query, {"_id": 0})
    items = await cursor.to_list(length=100)
    return items


@router.post("/policies")
async def create_policy(payload: dict, db=Depends(_db), current_user=Depends(get_current_user)):
    tenant_id = _tenant(current_user)
    payload.setdefault("id", f"policy-{int(time.time())}")
    payload.setdefault("created_at", time.time())
    payload.setdefault("created_by", current_user.get("sub"))
    if tenant_id:
        payload["tenantId"] = tenant_id
    await db["pipeline_policies"].insert_one(payload)
    payload.pop("_id", None)
    return payload


@router.get("/stats")
async def pipeline_stats(db=Depends(_db), current_user=Depends(get_current_user)):
    tenant_id = _tenant(current_user)
    base = {} if _role(current_user) in _PIPELINE_SUPER_ROLES else {"tenantId": tenant_id}

    total = await db["pipeline_scans"].count_documents(base)
    passed = await db["pipeline_scans"].count_documents({**base, "status": "passed"})
    failed = await db["pipeline_scans"].count_documents({**base, "status": "failed"})
    blocked = await db["pipeline_scans"].count_documents({**base, "status": "blocked"})

    pipeline_agg = await db["pipeline_scans"].aggregate([
        {"$match": base},
        {"$unwind": {"path": "$findings", "preserveNullAndEmptyArrays": False}},
        {"$group": {"_id": "$findings.type", "count": {"$sum": 1}}},
    ]).to_list(length=20)
    finding_counts = {row["_id"]: row["count"] for row in pipeline_agg}

    return {
        "total_scans": total,
        "passed": passed,
        "failed": failed,
        "blocked": blocked,
        "secret_leaks_blocked": finding_counts.get("secret_leak", 0),
        "iac_violations": finding_counts.get("iac_violation", 0),
        "dependency_risks": finding_counts.get("dependency_risk", 0),
    }

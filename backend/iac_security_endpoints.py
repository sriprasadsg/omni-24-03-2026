"""Infrastructure as Code (IaC) Security scanning endpoints."""
from __future__ import annotations
import time
from fastapi import APIRouter, HTTPException, Depends
from auth_utils import get_current_user

router = APIRouter(prefix="/api/iac-security", tags=["IaC Security"])


async def _db():
    from database import get_database
    return get_database()


@router.get("/scans")
async def list_scans(db=Depends(_db)):
    cursor = db["iac_scans"].find({}, {"_id": 0}).sort("scanned_at", -1).limit(100)
    items = await cursor.to_list(length=100)
    return items


@router.post("/scans")
async def trigger_scan(payload: dict, db=Depends(_db), current_user=Depends(get_current_user)):
    scan = {
        "id": f"iac-{int(time.time())}",
        "repo": payload.get("repo"),
        "branch": payload.get("branch", "main"),
        "tool": payload.get("tool", "checkov"),
        "status": "queued",
        "scanned_at": time.time(),
        "triggered_by": current_user.get("sub"),
    }
    await db["iac_scans"].insert_one(scan)
    scan.pop("_id", None)
    return scan


@router.get("/violations")
async def list_violations(db=Depends(_db)):
    cursor = db["iac_violations"].find({}, {"_id": 0}).sort("detected_at", -1).limit(200)
    items = await cursor.to_list(length=200)
    return items


@router.post("/violations/{violation_id}/suppress")
async def suppress_violation(violation_id: str, payload: dict, db=Depends(_db),
                              current_user=Depends(get_current_user)):
    result = await db["iac_violations"].update_one(
        {"id": violation_id},
        {"$set": {"suppressed": True, "suppressed_by": current_user.get("sub"),
                  "suppress_reason": payload.get("reason"), "suppressed_at": time.time()}}
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Violation not found")
    return {"ok": True}


@router.get("/stats")
async def stats(db=Depends(_db)):
    total_v = await db["iac_violations"].count_documents({})
    critical = await db["iac_violations"].count_documents({"severity": "critical"})
    high = await db["iac_violations"].count_documents({"severity": "high"})
    suppressed = await db["iac_violations"].count_documents({"suppressed": True})
    medium = max(0, total_v - critical - high)
    return {"total_violations": total_v, "critical": critical, "high": high,
            "medium": medium, "suppressed": suppressed,
            "frameworks_checked": ["Terraform", "CloudFormation", "Kubernetes YAML", "Helm"],
            "rules_applied": 312}



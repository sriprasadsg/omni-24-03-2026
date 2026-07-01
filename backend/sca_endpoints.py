"""Security Configuration Assessment (SCA) Endpoints — /api/sca/"""
from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from pydantic import BaseModel
from authentication_service import get_current_user, TokenData
from database import get_database
from datetime import datetime, timezone
from typing import Optional, List
import uuid

router = APIRouter(prefix="/api/sca", tags=["SCA"])

# Built-in CIS policy profiles
SCA_POLICIES = [
    {"id": "cis-windows-10", "name": "CIS Microsoft Windows 10", "version": "1.12.0", "platform": "windows", "total_checks": 241},
    {"id": "cis-windows-11", "name": "CIS Microsoft Windows 11", "version": "1.0.0", "platform": "windows", "total_checks": 228},
    {"id": "cis-windows-server-2022", "name": "CIS Windows Server 2022", "version": "1.0.0", "platform": "windows", "total_checks": 268},
    {"id": "cis-ubuntu-22", "name": "CIS Ubuntu Linux 22.04 LTS", "version": "1.0.0", "platform": "linux", "total_checks": 253},
    {"id": "cis-rhel-8", "name": "CIS Red Hat Enterprise Linux 8", "version": "2.0.0", "platform": "linux", "total_checks": 198},
    {"id": "cis-debian-11", "name": "CIS Debian Linux 11", "version": "1.0.0", "platform": "linux", "total_checks": 211},
    {"id": "cis-macos-13", "name": "CIS Apple macOS 13 Ventura", "version": "1.0.0", "platform": "macos", "total_checks": 177},
    {"id": "pci-dss-linux", "name": "PCI DSS Linux", "version": "3.2.1", "platform": "linux", "total_checks": 142},
    {"id": "nist-800-53-linux", "name": "NIST 800-53 Linux", "version": "5.0", "platform": "linux", "total_checks": 186},
]


def _strip_id(doc: dict) -> dict:
    doc.pop("_id", None)
    return doc


class ScanTrigger(BaseModel):
    policy_id: str


@router.get("/policies")
async def list_policies(
    platform: Optional[str] = Query(None, description="windows|linux|macos"),
    current_user: TokenData = Depends(get_current_user),
):
    """Return available SCA policy profiles."""
    if platform:
        return [p for p in SCA_POLICIES if p["platform"] == platform]
    return SCA_POLICIES


@router.get("/checks")
async def list_checks(
    agent_id: Optional[str] = Query(None),
    policy_id: Optional[str] = Query(None),
    result: Optional[str] = Query(None, description="passed|failed|error|not_applicable"),
    limit: int = Query(100, ge=1, le=1000),
    current_user: TokenData = Depends(get_current_user),
):
    """List SCA check results, optionally filtered by agent or policy."""
    db = get_database()
    query: dict = {"tenantId": current_user.tenant_id}
    if agent_id:
        query["agent_id"] = agent_id
    if policy_id:
        query["policy_id"] = policy_id
    if result:
        query["result"] = result
    results = []
    async for doc in db.sca_checks.find(query).sort("scanned_at", -1).limit(limit):
        _strip_id(doc)
        results.append(doc)
    return results


@router.get("/checks/summary")
async def checks_summary(
    current_user: TokenData = Depends(get_current_user),
):
    """Pass/fail/error counts per agent for the tenant."""
    db = get_database()
    pipeline = [
        {"$match": {"tenantId": current_user.tenant_id}},
        {"$group": {
            "_id": {"agent_id": "$agent_id", "result": "$result"},
            "count": {"$sum": 1},
        }},
        {"$group": {
            "_id": "$_id.agent_id",
            "counts": {"$push": {"result": "$_id.result", "count": "$count"}},
        }},
    ]
    per_agent: dict = {}
    async for row in db.sca_checks.aggregate(pipeline):
        aid = row["_id"]
        per_agent[aid] = {"passed": 0, "failed": 0, "error": 0, "not_applicable": 0}
        for c in row["counts"]:
            per_agent[aid][c["result"]] = c["count"]
    return per_agent


@router.get("/agents/{agent_id}/checks")
async def agent_checks(
    agent_id: str,
    policy_id: Optional[str] = Query(None),
    result: Optional[str] = Query(None),
    limit: int = Query(200, ge=1, le=1000),
    current_user: TokenData = Depends(get_current_user),
):
    """All SCA check results for a specific agent."""
    db = get_database()
    query: dict = {"tenantId": current_user.tenant_id, "agent_id": agent_id}
    if policy_id:
        query["policy_id"] = policy_id
    if result:
        query["result"] = result
    checks = []
    async for doc in db.sca_checks.find(query).sort("result", 1).limit(limit):
        _strip_id(doc)
        checks.append(doc)
    return checks


@router.post("/scan/{agent_id}", status_code=202)
async def trigger_scan(
    agent_id: str,
    body: ScanTrigger,
    background_tasks: BackgroundTasks,
    current_user: TokenData = Depends(get_current_user),
):
    """Queue an SCA scan for the specified agent."""
    db = get_database()
    job = {
        "id": str(uuid.uuid4()),
        "tenantId": current_user.tenant_id,
        "agent_id": agent_id,
        "policy_id": body.policy_id,
        "status": "queued",
        "queued_at": datetime.now(timezone.utc).isoformat(),
        "triggered_by": current_user.email,
    }
    await db.sca_jobs.insert_one(job)
    job.pop("_id", None)
    return {"job_id": job["id"], "status": "queued", "message": "SCA scan queued for agent"}


@router.get("/stats")
async def sca_stats(current_user: TokenData = Depends(get_current_user)):
    """Overall SCA stats for the tenant."""
    db = get_database()
    pipeline = [
        {"$match": {"tenantId": current_user.tenant_id}},
        {"$group": {"_id": "$result", "count": {"$sum": 1}}},
    ]
    counts = {"passed": 0, "failed": 0, "error": 0, "not_applicable": 0}
    async for row in db.sca_checks.aggregate(pipeline):
        if row["_id"] in counts:
            counts[row["_id"]] = row["count"]
    total = sum(counts.values())
    score = round((counts["passed"] / total) * 100, 1) if total > 0 else 0
    agent_count = await db.sca_checks.distinct("agent_id", {"tenantId": current_user.tenant_id})
    return {
        **counts,
        "total": total,
        "compliance_score": score,
        "agents_scanned": len(agent_count),
    }

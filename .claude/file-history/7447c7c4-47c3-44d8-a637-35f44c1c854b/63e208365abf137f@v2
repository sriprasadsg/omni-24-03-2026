from fastapi import APIRouter, Form, BackgroundTasks, Depends, Query
import logging
from datetime import datetime, timezone
from typing import Optional
from database import get_database
from authentication_service import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/api/compliance/{framework_id}/scan")
async def trigger_framework_scan(
    framework_id: str,
    background_tasks: BackgroundTasks,
    current_user=Depends(get_current_user),
):
    """
    Broadcast 'Run Compliance Scan' instruction to all online agents AND
    run server-side admin evidence collection as a background task.
    """
    db = get_database()
    online_agents = await db.agents.find({"status": "Online"}).to_list(length=1000)

    timestamp = datetime.now(timezone.utc).isoformat()
    new_instructions = [
        {
            "agent_id": agent["id"],
            "instruction": "Run Compliance Scan",
            "status": "pending",
            "created_at": timestamp,
            "created_by": "system_broadcast",
            "framework_target": framework_id,
        }
        for agent in online_agents
    ]
    if new_instructions:
        await db.agent_instructions.insert_many(new_instructions)

    count = len(new_instructions)
    logger.info("BROADCAST Run Compliance Scan to %s agents for framework %s", count, framework_id)

    try:
        from admin_evidence_service import run_evidence_collection_for_asset
        hostnames = [a.get("hostname") for a in online_agents if a.get("hostname")]
        if not hostnames:
            async for asset in db.assets.find({}, {"hostname": 1}):
                h = asset.get("hostname")
                if h:
                    hostnames.append(h)
        for hostname in set(hostnames):
            background_tasks.add_task(run_evidence_collection_for_asset, hostname, db)
            logger.info("AdminEvidence: Queued admin evidence collection for: %s", hostname)
    except Exception as e:
        logger.warning("Could not queue admin evidence collection: %s", e)

    return {
        "success": True,
        "message": f"Scan initiated for {max(count, 1)} agent(s). Admin evidence collection running in background.",
        "agent_count": count,
    }


@router.post("/api/agents/{agent_id}/compliance/scan")
async def trigger_agent_scan(agent_id: str, current_user=Depends(get_current_user)):
    """Send 'Run Compliance Scan' instruction to a single agent."""
    db = get_database()
    instruction = {
        "agent_id": agent_id,
        "instruction": "Run Compliance Scan",
        "status": "pending",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "created_by": "user_manual_refresh",
        "priority": "high",
    }
    result = await db.agent_instructions.insert_one(instruction)
    logger.info("Sent 'Run Compliance Scan' to agent %s", agent_id)
    return {
        "success": True,
        "message": "Scan instruction sent to agent",
        "instruction_id": str(result.inserted_id),
    }


@router.post("/api/agents/{agent_id}/compliance/fix")
async def trigger_compliance_fix(
    agent_id: str,
    check_name: str = Form(...),
    current_user=Depends(get_current_user),
):
    """Send a 'Fix Compliance' instruction to a specific agent."""
    db = get_database()
    await db.agent_instructions.insert_one({
        "agent_id": agent_id,
        "instruction": f"Fix Compliance: {check_name}",
        "status": "pending",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "created_by": "user_action",
        "priority": "high",
    })
    logger.info("Sent Fix Instruction to %s: %s", agent_id, check_name)
    return {"success": True, "message": f"Fix instruction sent for {check_name}"}


@router.post("/api/compliance/collect-all")
async def trigger_full_evidence_sweep(
    background_tasks: BackgroundTasks,
    current_user=Depends(get_current_user),
):
    """
    Immediately dispatch a compliance evidence collection sweep to all active agents
    for the calling user's tenant.  Agents will execute their compliance checks and
    include the results in their next heartbeat.
    """
    from compliance_auto_evidence_service import dispatch_collection_sweep
    db = get_database()

    tenant_id = getattr(current_user, "tenant_id", None)
    role = getattr(current_user, "role", "")
    _SUPER = {"Super Admin", "superadmin", "super_admin", "platform-admin"}
    if role in _SUPER:
        tenant_id = None  # super-admin sweeps all tenants

    result = await dispatch_collection_sweep(db, tenant_id=tenant_id)
    return {
        "success": True,
        "message": f"Evidence collection sweep dispatched to {result.get('dispatched', 0)} agent(s). "
                   "Results will appear after agents send their next heartbeat.",
        **result,
    }


@router.get("/api/compliance/evidence-coverage")
async def get_evidence_coverage(
    framework_id: Optional[str] = Query(None, description="Filter by framework ID"),
    since_days: int = Query(30, ge=1, le=365, description="Look-back window in days"),
    current_user=Depends(get_current_user),
):
    """
    Return a coverage report showing which compliance controls have recent evidence
    and which are gaps.  Use `since_days` to adjust the look-back window (default 30 days).
    """
    from compliance_auto_evidence_service import get_coverage_gaps
    db = get_database()

    tenant_id = getattr(current_user, "tenant_id", None)
    role = getattr(current_user, "role", "")
    _SUPER = {"Super Admin", "superadmin", "super_admin", "platform-admin"}
    if role in _SUPER:
        tenant_id = None

    report = await get_coverage_gaps(db, tenant_id=tenant_id, since_days=since_days, framework_id=framework_id)
    return report

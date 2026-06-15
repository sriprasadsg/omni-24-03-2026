"""Active Response Rules Endpoints — /api/active-response/"""
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from authentication_service import get_current_user, TokenData
from database import get_database
from datetime import datetime, timezone
from typing import Optional, List, Any
import uuid

router = APIRouter(prefix="/api/active-response", tags=["Active Response"])

VALID_TRIGGERS = {
    "alert_severity_critical", "alert_severity_high",
    "failed_login_threshold", "malware_detected",
    "fim_change_critical", "port_scan_detected",
    "brute_force_detected", "new_process_suspicious",
    "ransomware_indicator", "lateral_movement_detected",
}

VALID_ACTIONS = {
    "block_ip", "unblock_ip",
    "disable_user", "enable_user",
    "kill_process", "quarantine_host",
    "isolate_agent", "unisolate_agent",
    "run_sca_scan", "collect_forensics",
    "send_alert", "create_ticket",
}

VALID_MODES = {"automatic", "manual", "supervised"}


class RuleCreate(BaseModel):
    name: str
    description: str = ""
    trigger: str
    trigger_threshold: int = 1
    actions: List[str]
    mode: str = "supervised"
    enabled: bool = True
    timeout_seconds: int = 300
    applies_to: List[str] = []  # agent IDs or group IDs; empty = all


class RuleUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    trigger: Optional[str] = None
    trigger_threshold: Optional[int] = None
    actions: Optional[List[str]] = None
    mode: Optional[str] = None
    enabled: Optional[bool] = None
    timeout_seconds: Optional[int] = None
    applies_to: Optional[List[str]] = None


class ExecuteRequest(BaseModel):
    agent_id: str
    action: str
    parameters: dict = {}
    reason: str = ""


def _strip_id(doc: dict) -> dict:
    doc.pop("_id", None)
    return doc


def _validate_rule(trigger: str, actions: List[str], mode: str) -> None:
    if trigger not in VALID_TRIGGERS:
        raise HTTPException(status_code=400, detail=f"Invalid trigger. Valid: {sorted(VALID_TRIGGERS)}")
    invalid_actions = set(actions) - VALID_ACTIONS
    if invalid_actions:
        raise HTTPException(status_code=400, detail=f"Invalid actions: {invalid_actions}")
    if not actions:
        raise HTTPException(status_code=400, detail="At least one action is required")
    if mode not in VALID_MODES:
        raise HTTPException(status_code=400, detail=f"mode must be one of: {sorted(VALID_MODES)}")


@router.get("/rules")
async def list_rules(
    enabled: Optional[bool] = Query(None),
    mode: Optional[str] = Query(None),
    current_user: TokenData = Depends(get_current_user),
):
    """List all active response rules for the tenant."""
    db = get_database()
    query: dict = {"tenantId": current_user.tenant_id}
    if enabled is not None:
        query["enabled"] = enabled
    if mode:
        query["mode"] = mode
    rules = []
    async for doc in db.active_response_rules.find(query).sort("created_at", -1):
        _strip_id(doc)
        # Attach execution count
        doc["execution_count"] = await db.active_response_executions.count_documents(
            {"rule_id": doc["id"], "tenantId": current_user.tenant_id}
        )
        rules.append(doc)
    return rules


@router.post("/rules", status_code=201)
async def create_rule(
    body: RuleCreate,
    current_user: TokenData = Depends(get_current_user),
):
    """Create a new active response rule."""
    _validate_rule(body.trigger, body.actions, body.mode)
    db = get_database()
    exists = await db.active_response_rules.find_one(
        {"name": body.name, "tenantId": current_user.tenant_id}
    )
    if exists:
        raise HTTPException(status_code=409, detail="Rule name already exists")
    now = datetime.now(timezone.utc).isoformat()
    doc = {
        "id": str(uuid.uuid4()),
        "tenantId": current_user.tenant_id,
        "name": body.name,
        "description": body.description,
        "trigger": body.trigger,
        "trigger_threshold": max(1, body.trigger_threshold),
        "actions": body.actions,
        "mode": body.mode,
        "enabled": body.enabled,
        "timeout_seconds": min(3600, max(10, body.timeout_seconds)),
        "applies_to": body.applies_to,
        "created_at": now,
        "updated_at": now,
        "created_by": current_user.email,
    }
    await db.active_response_rules.insert_one(doc)
    _strip_id(doc)
    doc["execution_count"] = 0
    return doc


@router.put("/rules/{rule_id}")
async def update_rule(
    rule_id: str,
    body: RuleUpdate,
    current_user: TokenData = Depends(get_current_user),
):
    """Update an active response rule."""
    db = get_database()
    existing = await db.active_response_rules.find_one(
        {"id": rule_id, "tenantId": current_user.tenant_id}
    )
    if not existing:
        raise HTTPException(status_code=404, detail="Rule not found")
    updates = {k: v for k, v in body.dict().items() if v is not None}
    trigger = updates.get("trigger", existing["trigger"])
    actions = updates.get("actions", existing["actions"])
    mode = updates.get("mode", existing["mode"])
    _validate_rule(trigger, actions, mode)
    updates["updated_at"] = datetime.now(timezone.utc).isoformat()
    await db.active_response_rules.update_one(
        {"id": rule_id, "tenantId": current_user.tenant_id},
        {"$set": updates},
    )
    doc = await db.active_response_rules.find_one({"id": rule_id, "tenantId": current_user.tenant_id})
    _strip_id(doc)
    doc["execution_count"] = await db.active_response_executions.count_documents(
        {"rule_id": rule_id, "tenantId": current_user.tenant_id}
    )
    return doc


@router.delete("/rules/{rule_id}", status_code=204)
async def delete_rule(rule_id: str, current_user: TokenData = Depends(get_current_user)):
    """Delete an active response rule."""
    db = get_database()
    result = await db.active_response_rules.delete_one(
        {"id": rule_id, "tenantId": current_user.tenant_id}
    )
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Rule not found")
    return None


@router.post("/execute", status_code=202)
async def execute_action(
    body: ExecuteRequest,
    current_user: TokenData = Depends(get_current_user),
):
    """Manually execute an active response action against a specific agent."""
    if body.action not in VALID_ACTIONS:
        raise HTTPException(status_code=400, detail=f"Invalid action. Valid: {sorted(VALID_ACTIONS)}")
    db = get_database()
    agent = await db.agents.find_one(
        {"id": body.agent_id, "tenantId": current_user.tenant_id}
    )
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    now = datetime.now(timezone.utc).isoformat()
    execution = {
        "id": str(uuid.uuid4()),
        "tenantId": current_user.tenant_id,
        "rule_id": None,
        "agent_id": body.agent_id,
        "action": body.action,
        "parameters": body.parameters,
        "reason": body.reason,
        "status": "queued",
        "triggered_by": current_user.email,
        "triggered_at": now,
        "mode": "manual",
    }
    await db.active_response_executions.insert_one(execution)
    execution.pop("_id", None)
    return {"execution_id": execution["id"], "status": "queued", "action": body.action, "agent_id": body.agent_id}


@router.get("/executions")
async def list_executions(
    agent_id: Optional[str] = Query(None),
    action: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=500),
    current_user: TokenData = Depends(get_current_user),
):
    """List active response execution history."""
    db = get_database()
    query: dict = {"tenantId": current_user.tenant_id}
    if agent_id:
        query["agent_id"] = agent_id
    if action:
        query["action"] = action
    if status:
        query["status"] = status
    executions = []
    async for doc in db.active_response_executions.find(query).sort("triggered_at", -1).limit(limit):
        _strip_id(doc)
        executions.append(doc)
    return executions


@router.get("/stats")
async def ar_stats(current_user: TokenData = Depends(get_current_user)):
    """Active response statistics for the tenant."""
    db = get_database()
    total_rules = await db.active_response_rules.count_documents(
        {"tenantId": current_user.tenant_id}
    )
    enabled_rules = await db.active_response_rules.count_documents(
        {"tenantId": current_user.tenant_id, "enabled": True}
    )
    total_executions = await db.active_response_executions.count_documents(
        {"tenantId": current_user.tenant_id}
    )
    pipeline = [
        {"$match": {"tenantId": current_user.tenant_id}},
        {"$group": {"_id": "$action", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
        {"$limit": 5},
    ]
    top_actions = []
    async for row in db.active_response_executions.aggregate(pipeline):
        top_actions.append({"action": row["_id"], "count": row["count"]})
    mode_pipeline = [
        {"$match": {"tenantId": current_user.tenant_id}},
        {"$group": {"_id": "$mode", "count": {"$sum": 1}}},
    ]
    by_mode: dict = {}
    async for row in db.active_response_rules.aggregate(mode_pipeline):
        by_mode[row["_id"]] = row["count"]
    return {
        "total_rules": total_rules,
        "enabled_rules": enabled_rules,
        "total_executions": total_executions,
        "top_actions": top_actions,
        "rules_by_mode": by_mode,
    }


@router.get("/triggers")
async def list_valid_triggers(current_user: TokenData = Depends(get_current_user)):
    """Return valid trigger types and action types for the UI."""
    return {
        "triggers": sorted(VALID_TRIGGERS),
        "actions": sorted(VALID_ACTIONS),
        "modes": sorted(VALID_MODES),
    }

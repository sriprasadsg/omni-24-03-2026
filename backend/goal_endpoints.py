"""
Goal System Endpoints — HTTP API for the autonomous agent goal system.
Allows creating high-level objectives, viewing decomposed task plans, and tracking progress.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from database import get_database
from auth_utils import get_current_user

router = APIRouter(prefix="/api/goals", tags=["Goal System"])

import logging as _logging
_log = _logging.getLogger(__name__)

_SUPER_ADMIN_ROLES = {"Super Admin", "superadmin", "super_admin", "platform-admin"}

def _tenant_filter(current_user: Any) -> Dict[str, Any]:
    role = getattr(current_user, "role", "") or ""
    if role in _SUPER_ADMIN_ROLES:
        return {}
    tid = getattr(current_user, "tenant_id", None)
    return {"tenantId": tid} if tid else {"tenantId": {"$exists": False}}


async def _dispatch_goal_tasks(db, goal: Dict[str, Any], goal_id: str) -> None:
    """Fire-and-forget: insert each goal task into agent_tasks for an available online agent."""
    try:
        agents = await db.agents.find(
            {"status": "Online"}, {"_id": 0, "id": 1, "hostname": 1}
        ).limit(5).to_list(length=5)

        if not agents:
            _log.warning("[Goals] No online agents found to dispatch tasks for goal %s", goal_id)
            return

        tasks = goal.get("tasks", [])
        agent_cycle = len(agents)
        for idx, task in enumerate(tasks):
            agent = agents[idx % agent_cycle]
            await db.agent_tasks.insert_one({
                "id": f"goal-{goal_id}-{task['task_id']}",
                "goal_id": goal_id,
                "task_id": task["task_id"],
                "description": task.get("description", ""),
                "capability": task.get("capability", ""),
                "agentId": agent["id"],
                "agentHostname": agent.get("hostname", ""),
                "status": "pending",
                "created_at": datetime.now(timezone.utc).isoformat(),
            })
        _log.info("[Goals] Dispatched %d tasks for goal %s to %d agents", len(tasks), goal_id, agent_cycle)
    except Exception as exc:
        _log.error("[Goals] Failed to dispatch tasks for goal %s: %s", goal_id, exc)

# ── Pydantic models ────────────────────────────────────────────────────────────

class GoalCreate(BaseModel):
    objective: str = Field(..., max_length=2000)
    priority: int = 5          # 1 (critical) – 10 (low)
    deadline_hours: Optional[int] = None
    category: str = Field("security", max_length=100)
    auto_approve: bool = False


class GoalApprove(BaseModel):
    approved: bool
    reviewer_note: str = Field("", max_length=2000)


# ── Predefined goal templates ──────────────────────────────────────────────────

GOAL_TEMPLATES = [
    {
        "template_id": "reduce_attack_surface",
        "name": "Reduce Cloud Attack Surface",
        "description": "Identify and remediate exposed resources, open ports, and misconfigured cloud services",
        "category": "security",
        "default_priority": 2,
        "suggested_tasks": [
            "Run network discovery scan on all subnets",
            "Identify publicly accessible storage buckets",
            "Enumerate open security groups and firewall rules",
            "Detect unused/orphaned cloud resources",
            "Generate remediation playbook for each finding",
        ],
    },
    {
        "template_id": "soc2_readiness",
        "name": "Achieve SOC2 Type II Readiness",
        "description": "Automate evidence collection and control validation for SOC2 audit",
        "category": "compliance",
        "default_priority": 2,
        "suggested_tasks": [
            "Map all systems to Trust Service Criteria",
            "Enable continuous control monitoring",
            "Generate access review reports for CC6.1–CC6.7",
            "Validate encryption controls for CC9.1",
            "Package audit evidence bundle",
        ],
    },
    {
        "template_id": "patch_critical_cves",
        "name": "Patch All Critical CVEs",
        "description": "Identify, prioritize, and remediate all CVSS 9.0+ vulnerabilities in the environment",
        "category": "security",
        "default_priority": 1,
        "suggested_tasks": [
            "Sync NVD CVE database",
            "Correlate CVEs against installed software inventory",
            "Rank by CVSS score and exploitability",
            "Deploy patches to critical systems first",
            "Re-scan to validate remediation",
        ],
    },
    {
        "template_id": "zero_trust_migration",
        "name": "Zero Trust Network Migration",
        "description": "Replace implicit trust model with per-request context-aware authorization",
        "category": "infrastructure",
        "default_priority": 3,
        "suggested_tasks": [
            "Inventory all service-to-service communications",
            "Deploy mTLS between all internal services",
            "Migrate privileged access to JIT model",
            "Implement device posture checks",
            "Validate microsegmentation policies",
        ],
    },
    {
        "template_id": "reduce_cloud_spend",
        "name": "Reduce Cloud Costs by 20%",
        "description": "Identify waste, rightsize resources, and optimize reserved instance coverage",
        "category": "cost",
        "default_priority": 4,
        "suggested_tasks": [
            "Identify idle and underutilized instances",
            "Generate rightsizing recommendations",
            "Analyze reserved instance coverage gaps",
            "Detect orphaned EBS volumes and snapshots",
            "Implement auto-shutdown for dev/test environments",
        ],
    },
]


def _decompose_goal(objective: str, category: str) -> List[Dict[str, Any]]:
    """
    Decompose a high-level objective into concrete agent tasks.
    In production this calls the LLM engine; here we match against templates
    and generate a structured task list.
    """
    # Try template match first
    objective_lower = objective.lower()
    for tmpl in GOAL_TEMPLATES:
        if any(kw in objective_lower for kw in tmpl["name"].lower().split()):
            return [
                {
                    "task_id": str(uuid.uuid4()),
                    "description": task,
                    "capability": _map_capability(task),
                    "status": "pending",
                    "estimated_minutes": 5,
                    "order": idx,
                }
                for idx, task in enumerate(tmpl["suggested_tasks"])
            ]

    # Generic decomposition fallback
    generic_tasks = [
        {"description": "Assess current state and baseline metrics", "capability": "metrics"},
        {"description": "Identify gaps and risks", "capability": "risk_assessment"},
        {"description": "Generate remediation action plan", "capability": "ai_remediation"},
        {"description": "Execute top-priority remediations", "capability": "autonomous_response"},
        {"description": "Validate outcomes and measure improvement", "capability": "compliance"},
    ]
    return [
        {
            "task_id": str(uuid.uuid4()),
            "description": t["description"],
            "capability": t["capability"],
            "status": "pending",
            "estimated_minutes": 5,
            "order": idx,
        }
        for idx, t in enumerate(generic_tasks)
    ]


def _map_capability(task_desc: str) -> str:
    lower = task_desc.lower()
    if "scan" in lower or "discover" in lower:
        return "network_discovery"
    if "patch" in lower or "deploy" in lower:
        return "software_management"
    if "compliance" in lower or "audit" in lower or "evidence" in lower:
        return "compliance"
    if "cost" in lower or "rightsize" in lower or "idle" in lower:
        return "finops"
    if "threat" in lower or "cve" in lower or "vulnerability" in lower:
        return "fim"
    if "remediat" in lower:
        return "autonomous_response"
    return "general"


def _goal_doc(goal_id: str, data: GoalCreate, tasks: List[Dict], tenant_id: str = "") -> Dict[str, Any]:
    deadline = None
    if data.deadline_hours:
        from datetime import timedelta
        deadline = (datetime.now(timezone.utc) + timedelta(hours=data.deadline_hours)).isoformat()

    return {
        "id": goal_id,
        "tenantId": tenant_id,
        "objective": data.objective,
        "priority": data.priority,
        "category": data.category,
        "status": "active" if data.auto_approve else "pending_approval",
        "auto_approve": data.auto_approve,
        "deadline": deadline,
        "tasks": tasks,
        "progress_pct": 0.0,
        "completed_tasks": 0,
        "total_tasks": len(tasks),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "approved_by": None,
        "approved_at": None,
    }


def _compute_progress(goal: Dict[str, Any]) -> float:
    tasks = goal.get("tasks", [])
    if not tasks:
        return 0.0
    done = sum(1 for t in tasks if t.get("status") == "completed")
    return round(done / len(tasks) * 100, 1)


# ── Endpoints ──────────────────────────────────────────────────────────────────

@router.get("")
async def list_goals(status: Optional[str] = None, current_user: Dict[str, Any] = Depends(get_current_user)):
    """List all goals, optionally filtered by status."""
    db = get_database()
    query: Dict[str, Any] = {**_tenant_filter(current_user)}
    if status:
        query["status"] = status
    try:
        goals = await db.agent_goals.find(query).sort("priority", 1).limit(100).to_list(length=100)
        for g in goals:
            g.pop("_id", None)
            g["progress_pct"] = _compute_progress(g)
        return {"goals": goals, "total": len(goals)}
    except Exception as exc:
        _log.error("Failed to list goals: %s", exc)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("")
async def create_goal(data: GoalCreate, current_user: Dict[str, Any] = Depends(get_current_user)):
    """Create a new goal and decompose it into tasks."""
    tasks = _decompose_goal(data.objective, data.category)
    goal_id = str(uuid.uuid4())
    tenant_id = getattr(current_user, "tenant_id", "") or ""
    doc = _goal_doc(goal_id, data, tasks, tenant_id=tenant_id)

    db = get_database()
    try:
        await db.agent_goals.insert_one({**doc, "_id": goal_id})
    except Exception as e:
        import logging
        logging.getLogger(__name__).error("Failed to persist goal %s: %s", goal_id, e)
        raise HTTPException(status_code=500, detail="Internal server error")

    return doc


@router.get("/templates")
async def list_templates(current_user: Dict[str, Any] = Depends(get_current_user)):
    """Return predefined goal templates."""
    return {"templates": GOAL_TEMPLATES}


@router.get("/{goal_id}")
async def get_goal(goal_id: str, current_user: Dict[str, Any] = Depends(get_current_user)):
    """Get a single goal with current progress."""
    db = get_database()
    goal = await db.agent_goals.find_one({"id": goal_id, **_tenant_filter(current_user)})
    if not goal:
        raise HTTPException(status_code=404, detail="Goal not found")
    goal.pop("_id", None)
    goal["progress_pct"] = _compute_progress(goal)
    return goal


@router.post("/{goal_id}/approve")
async def approve_goal(goal_id: str, body: GoalApprove, current_user: Dict[str, Any] = Depends(get_current_user)):
    """Approve or reject the decomposed task plan for a goal."""
    db = get_database()
    goal = await db.agent_goals.find_one({"id": goal_id, **_tenant_filter(current_user)})
    if not goal:
        raise HTTPException(status_code=404, detail="Goal not found")

    update: Dict[str, Any] = {
        "status": "active" if body.approved else "rejected",
        "approved_at": datetime.now(timezone.utc).isoformat(),
        "reviewer_note": body.reviewer_note,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.agent_goals.update_one({"id": goal_id}, {"$set": update})

    # Auto-dispatch tasks to online agents when approved
    if body.approved:
        import asyncio
        asyncio.create_task(_dispatch_goal_tasks(db, goal, goal_id))

    return {"status": update["status"], "goal_id": goal_id}


@router.post("/{goal_id}/tasks/{task_id}/complete")
async def complete_task(goal_id: str, task_id: str, current_user: Dict[str, Any] = Depends(get_current_user)):
    """Mark a specific task within a goal as completed."""
    db = get_database()
    goal = await db.agent_goals.find_one({"id": goal_id, **_tenant_filter(current_user)})
    if not goal:
        raise HTTPException(status_code=404, detail="Goal not found")

    tasks = goal.get("tasks", [])
    updated = False
    for t in tasks:
        if t["task_id"] == task_id:
            t["status"] = "completed"
            t["completed_at"] = datetime.now(timezone.utc).isoformat()
            updated = True
            break

    if not updated:
        raise HTTPException(status_code=404, detail="Task not found")

    completed_count = sum(1 for t in tasks if t.get("status") == "completed")
    goal_status = "completed" if completed_count == len(tasks) else "active"

    await db.agent_goals.update_one(
        {"id": goal_id},
        {"$set": {
            "tasks": tasks,
            "completed_tasks": completed_count,
            "status": goal_status,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }},
    )
    return {"goal_id": goal_id, "task_id": task_id, "goal_status": goal_status,
            "progress_pct": _compute_progress({**goal, "tasks": tasks})}


@router.delete("/{goal_id}")
async def delete_goal(goal_id: str, current_user: Dict[str, Any] = Depends(get_current_user)):
    """Delete a goal."""
    db = get_database()
    result = await db.agent_goals.delete_one({"id": goal_id, **_tenant_filter(current_user)})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Goal not found")
    return {"deleted": True, "goal_id": goal_id}

"""Agentic AI task endpoints — GET /api/agents/{agent_id}/agentic-tasks and related routes.

Rust agent polls GET agentic-tasks every 60 s; the endpoint runs AgenticService.run()
inline and returns the AI-selected tool as a queued task. The agent POST result back.

Route ordering: static suffixes (/decisions, /trigger) registered before /{task_id}/result
to avoid FastAPI path collision (F-03 Pitfall 1 from RESEARCH.md).
"""
import logging
import uuid
from datetime import datetime, timezone
from typing import Dict, Any, List

from fastapi import APIRouter, Depends, Body, HTTPException

from agent_auth import verify_agent_key
from authentication_service import get_current_user
from database import get_database

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/agents", tags=["Agentic AI"])

_AGENTIC_TOOL_NAMES = {
    "run_compliance_check",
    "run_vulnerability_scan",
    "run_threat_hunt",
    "run_persistence_scan",
    "collect_processes",
}


# ── GET  /{agent_id}/agentic-tasks  (Rust agent polls this) ──────────────────

@router.get("/{agent_id}/agentic-tasks")
async def get_agentic_tasks(
    agent_id: str,
    _tenant: Dict[str, Any] = Depends(verify_agent_key),
):
    """Return an AI-selected agentic task for the Rust agent to execute.

    Runs AgenticService.run() inline with the agent's live security context.
    Falls back to rule-based selection (collect_processes) if the Claude API is
    unreachable — circuit-breaker handled inside AgenticService (AI-04).
    """
    try:
        from agentic_service import get_agentic_service
        db = get_database()
        tenant_id = _tenant.get("tenant_id") or _tenant.get("tenantId") or ""

        # Assemble a lightweight security context from existing collections
        agent_doc = await db.agents.find_one({"id": agent_id, "tenantId": tenant_id})
        findings = await db.compliance_findings.find(
            {"agent_id": agent_id, "tenantId": tenant_id}
        ).to_list(length=30) if db else []
        alerts = await db.alerts.find(
            {"agent_id": agent_id, "tenantId": tenant_id}
        ).sort("created_at", -1).to_list(length=10) if db else []
        processes = await db.process_snapshots.find(
            {"agent_id": agent_id, "tenantId": tenant_id}
        ).sort("collected_at", -1).to_list(length=30) if db else []

        security_context: dict = {
            "agent_id": agent_id,
            "findings": findings,
            "alerts": alerts,
            "processes": processes,
            "capabilities": list(_AGENTIC_TOOL_NAMES),
        }
        if agent_doc:
            security_context["last_compliance_run"] = agent_doc.get("last_compliance_run")
            security_context["last_vuln_scan"] = agent_doc.get("last_vuln_scan")

        svc = get_agentic_service()
        result = await svc.run(agent_id, security_context)

        # Create a pending agent_tasks record so the result POST can link back
        task_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        decision_id = result.get("decision_id")
        task_doc = {
            "id": task_id,
            "type": result["tool_name"],
            "agent_id": agent_id,
            "tenantId": tenant_id,
            "status": "pending",
            "created_at": now,
            "context": result.get("tool_input", {}),
            "decision_id": decision_id,
        }
        await db.agent_tasks.insert_one(task_doc)

        # Correlate the audit record with this task so the result POST can
        # find it (see CR-03 — agent_ai_decisions.task_id must be set here).
        if decision_id:
            await db.agent_ai_decisions.update_one(
                {"_id": decision_id}, {"$set": {"task_id": task_id}}
            )

        return [
            {
                "id": task_id,
                "type": result["tool_name"],
                "context": result.get("tool_input", {}),
            }
        ]

    except RuntimeError as exc:
        # ANTHROPIC_API_KEY not set — return empty list (agent skips this cycle)
        logger.warning("[AgenticTasks] Agentic service unavailable: %s", exc)
        return []
    except Exception as exc:
        logger.error("[AgenticTasks] Unexpected error for agent %s: %s", agent_id, exc)
        return []


# ── GET  /{agent_id}/agentic-tasks/decisions  (dashboard read) ───────────────

@router.get("/{agent_id}/agentic-tasks/decisions")
async def get_agentic_decisions(
    agent_id: str,
    current_user=Depends(get_current_user),
):
    """Return the last 50 agentic AI decisions for an agent (per-tenant)."""
    try:
        db = get_database()
        docs = await db.agent_ai_decisions.find(
            {"agent_id": agent_id}
        ).sort("started_at", -1).to_list(length=50)
        for d in docs:
            d.pop("_id", None)
        return {"decisions": docs}
    except Exception as exc:
        logger.error("[AgenticTasks] Could not fetch decisions for %s: %s", agent_id, exc)
        return {"decisions": []}


# ── POST /{agent_id}/agentic-tasks/trigger  (manual trigger from UI) ─────────

@router.post("/{agent_id}/agentic-tasks/trigger")
async def trigger_agentic_task(
    agent_id: str,
    current_user=Depends(get_current_user),
):
    """Manually trigger an agentic decision cycle for the given agent."""
    try:
        from agentic_service import get_agentic_service
        db = get_database()
        tenant_id = getattr(current_user, "tenant_id", "") or ""

        security_context = {
            "agent_id": agent_id,
            "findings": [],
            "alerts": [],
            "processes": [],
            "capabilities": list(_AGENTIC_TOOL_NAMES),
        }

        svc = get_agentic_service()
        result = await svc.run(agent_id, security_context)
        result.pop("tool_result", None)  # strip internal queue status from response
        return result

    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except Exception as exc:
        logger.error("[AgenticTasks] Trigger failed for agent %s: %s", agent_id, exc)
        raise HTTPException(status_code=500, detail="Internal server error")


# ── POST /{agent_id}/agentic-tasks/{task_id}/result  (Rust agent result) ─────

@router.post("/{agent_id}/agentic-tasks/{task_id}/result")
async def report_agentic_task_result(
    agent_id: str,
    task_id: str,
    result: Dict[str, Any] = Body(...),
    _tenant: Dict[str, Any] = Depends(verify_agent_key),
):
    """Rust agent reports the outcome of an agentic task.

    Updates the agent_ai_decisions document linked to this task with the
    agent's actual execution result and outcome timestamp.
    """
    try:
        db = get_database()
        now = datetime.now(timezone.utc).isoformat()

        # Update the agent_tasks record
        await db.agent_tasks.update_one(
            {"id": task_id, "agent_id": agent_id},
            {"$set": {"status": "completed", "result": result, "completed_at": now}},
        )

        # Update the agent_ai_decisions document if linked
        await db.agent_ai_decisions.update_one(
            {"agent_id": agent_id, "task_id": task_id},
            {"$set": {"agent_result": result, "result_at": now}},
        )

        logger.info(
            "[AgenticTasks] Task %s result received from agent %s: success=%s",
            task_id,
            agent_id,
            result.get("success"),
        )
        return {"status": "ok"}

    except Exception as exc:
        logger.error(
            "[AgenticTasks] Result update failed for task %s / agent %s: %s",
            task_id, agent_id, exc,
        )
        raise HTTPException(status_code=500, detail="Internal server error")

"""
Chaos Engineering Service
Creates experiments in MongoDB and dispatches real agent instructions
to execute chaos injections (CPU stress, latency, process kill).
"""

import re
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

_TARGET_RE = re.compile(r'^[\w\-\.]+$')

from database import get_database
from authentication_service import get_current_user
from auth_types import TokenData

router = APIRouter(prefix="/api/chaos", tags=["Chaos Engineering"])

# Experiment types → agent instruction templates
_CHAOS_INSTRUCTIONS = {
    "CPU Hog": {
        "type": "chaos_cpu_hog",
        "instruction": "Run CPU stress test: stress --cpu 4 --timeout 60s",
        "description": "Saturates all CPU cores for 60 seconds to test auto-scaling and alerting.",
    },
    "Latency Injection": {
        "type": "chaos_latency",
        "instruction": "Inject 200ms network latency: tc qdisc add dev eth0 root netem delay 200ms",
        "description": "Adds artificial network latency to test timeout and retry logic.",
    },
    "Pod Failure": {
        "type": "chaos_process_kill",
        "instruction": "Kill target process: kill -9 $(pgrep -f {target})",
        "description": "Terminates the target process to test restart and failover behaviour.",
    },
    "Disk Fill": {
        "type": "chaos_disk_fill",
        "instruction": "Fill disk: dd if=/dev/zero of=/tmp/chaos_fill bs=1M count=512",
        "description": "Fills 512 MB of disk space to test low-disk alerting and cleanup.",
    },
    "Memory Leak": {
        "type": "chaos_memory",
        "instruction": "Allocate memory: python3 -c \"x=[bytearray(1024*1024) for _ in range(256)]; import time; time.sleep(60)\"",
        "description": "Allocates 256 MB of RAM for 60 seconds to test OOM alerting.",
    },
}


class ChaosExperiment(BaseModel):
    id: str
    tenantId: str
    name: str
    type: str
    target: str
    status: str
    lastRun: str
    instructionsDispatched: int = 0
    result: Optional[str] = None


_CHAOS_SUPER_ROLES = {"Super Admin", "super_admin", "platform-admin"}

class NewExperiment(BaseModel):
    name: str
    type: str
    target: str


@router.get("/experiments", response_model=List[ChaosExperiment])
async def get_experiments(current_user: TokenData = Depends(get_current_user)):
    db = get_database()
    user_role = getattr(current_user, "role", "")
    if user_role in _CHAOS_SUPER_ROLES:
        query: dict = {}
    else:
        tenant_id = getattr(current_user, "tenant_id", None) or None
        if not tenant_id:
            raise HTTPException(status_code=403, detail="Tenant context required")
        query = {"tenantId": tenant_id}
    exps = await db.chaos_experiments.find(query, {"_id": 0}).to_list(length=100)
    return [ChaosExperiment(**e) for e in exps] if exps else []


@router.post("/experiments", response_model=ChaosExperiment)
async def create_experiment(
    data: NewExperiment,
    current_user: TokenData = Depends(get_current_user),
):
    db = get_database()
    tenant_id = getattr(current_user, "tenant_id", None) or None
    if not tenant_id:
        raise HTTPException(status_code=403, detail="Tenant context required")
    exp = ChaosExperiment(
        id=f"chaos-{uuid.uuid4().hex[:8]}",
        tenantId=tenant_id,
        name=data.name,
        type=data.type,
        target=data.target,
        status="Scheduled",
        lastRun=datetime.now(timezone.utc).isoformat(),
    )
    await db.chaos_experiments.insert_one(exp.dict())
    return exp


@router.post("/experiments/{experiment_id}/run")
async def run_experiment(
    experiment_id: str,
    current_user: TokenData = Depends(get_current_user),
):
    """
    Execute a chaos experiment by dispatching real agent instructions to
    matching agents in the experiment's tenant.
    """
    db = get_database()

    experiment = await db.chaos_experiments.find_one({"id": experiment_id}, {"_id": 0})
    if not experiment:
        raise HTTPException(status_code=404, detail="Experiment not found")

    exp_type = experiment.get("type", "")
    template = _CHAOS_INSTRUCTIONS.get(exp_type)

    now = datetime.now(timezone.utc).isoformat()
    tenant_id = experiment.get("tenantId") or getattr(current_user, "tenant_id", None) or None
    target = experiment.get("target", "")

    dispatched = 0

    if template:
        # Validate target before using in regex query or instruction template
        if target and target.lower() not in ("all", "*", "") and not _TARGET_RE.match(target):
            raise HTTPException(status_code=400, detail="Invalid target: only alphanumeric, dash, dot allowed")

        # Find agents in the tenant that match the target (by name, hostname, or "all")
        query: dict = {"tenantId": tenant_id, "status": "Online"}
        if target.lower() not in ("all", "*", ""):
            safe_target = re.escape(target)
            query["$or"] = [
                {"hostname": {"$regex": safe_target, "$options": "i"}},
                {"name": {"$regex": safe_target, "$options": "i"}},
                {"id": target},
            ]

        agents = await db.agents.find(query, {"id": 1}).to_list(length=50)

        instruction_text = template["instruction"].replace("{target}", target)

        for agent in agents:
            await db.agent_instructions.insert_one({
                "agent_id": agent["id"],
                "instruction": instruction_text,
                "type": template["type"],
                "status": "pending",
                "created_at": now,
                "job_id": experiment_id,
                "metadata": {
                    "chaos_type": exp_type,
                    "experiment_id": experiment_id,
                    "target": target,
                    "description": template["description"],
                },
                "payload": {},
            })
            dispatched += 1

    status = "Running" if dispatched > 0 else "Completed"
    result_msg = (
        f"Dispatched to {dispatched} agent(s)." if dispatched > 0
        else "No matching online agents found — experiment recorded but not executed."
    )

    await db.chaos_experiments.update_one(
        {"id": experiment_id},
        {"$set": {
            "status": status,
            "lastRun": now,
            "instructionsDispatched": dispatched,
            "result": result_msg,
        }},
    )

    return {
        "message": f"Experiment {experiment_id} {'started' if dispatched else 'recorded'}",
        "status": status,
        "dispatched_to": dispatched,
        "result": result_msg,
    }


@router.get("/experiments/{experiment_id}/result")
async def get_experiment_result(
    experiment_id: str,
    _current_user: TokenData = Depends(get_current_user),
):
    """Poll experiment execution results from agent instruction completions."""
    db = get_database()

    experiment = await db.chaos_experiments.find_one({"id": experiment_id}, {"_id": 0})
    if not experiment:
        raise HTTPException(status_code=404, detail="Experiment not found")

    instructions = await db.agent_instructions.find(
        {"job_id": experiment_id},
        {"_id": 0, "agent_id": 1, "status": 1, "result": 1},
    ).to_list(length=100)

    completed = sum(1 for i in instructions if i.get("status") in ("completed", "delivered"))
    total = len(instructions)

    if total > 0 and completed == total:
        await db.chaos_experiments.update_one(
            {"id": experiment_id},
            {"$set": {"status": "Completed"}},
        )

    return {
        "experiment_id": experiment_id,
        "status": experiment.get("status"),
        "total_agents": total,
        "completed_agents": completed,
        "instructions": instructions,
    }

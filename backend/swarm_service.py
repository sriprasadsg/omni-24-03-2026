"""
Supplementary swarm routes not covered by swarm_endpoints.py.
The main swarm lifecycle (start/status/list/topology/peers/report) lives in swarm_endpoints.py.
"""
from fastapi import APIRouter, BackgroundTasks, Depends
from typing import Dict, Any
import uuid
from datetime import datetime, timezone
from authentication_service import get_current_user

router = APIRouter(prefix="/api/swarm", tags=["Swarm"])


@router.post("/propagate-antibody")
async def propagate_antibody(
    threat_data: Dict[str, Any],
    background_tasks: BackgroundTasks,
    current_user=Depends(get_current_user),
):
    """
    Digital Immune System: Dispatches a block rule (antibody) to all online agents
    in the tenant via the instructions collection.
    """
    tenant_id = getattr(current_user, "tenant_id", None) or getattr(current_user, "tenantId", "default")
    antibody_id = f"antibody-{uuid.uuid4().hex[:8]}"
    threat_type = threat_data.get("threat_type", "Unknown")
    indicator = threat_data.get("indicator") or threat_data.get("ip") or threat_data.get("hash", "")

    async def distribute():
        from database import mongodb
        db = mongodb.db
        agents = await db.agents.find(
            {"tenantId": tenant_id, "status": {"$in": ["Online", "Active", "online", "active"]}},
            {"id": 1}
        ).to_list(length=1000)
        now = datetime.now(timezone.utc).isoformat()
        instructions = [
            {
                "id": str(uuid.uuid4()),
                "agent_id": a["id"],
                "tenant_id": tenant_id,
                "type": "apply_block_rule",
                "parameters": {"antibody_id": antibody_id, "threat_type": threat_type, "indicator": indicator},
                "status": "pending",
                "created_at": now,
                "source": "immune_system"
            }
            for a in agents if a.get("id")
        ]
        if instructions:
            await db.instructions.insert_many(instructions)
        print(f"[IMMUNE] Antibody {antibody_id} dispatched to {len(instructions)} agents.")

    background_tasks.add_task(distribute)
    return {
        "status": "Propagating",
        "antibody_id": antibody_id,
        "threat_type": threat_type,
        "indicator": indicator,
        "action": f"Distributed block rule for threat: {threat_type}",
    }

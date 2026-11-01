"""
Supplementary swarm routes not covered by swarm_endpoints.py.
The main swarm lifecycle (start/status/list/topology/peers/report) lives in swarm_endpoints.py.
"""
from fastapi import APIRouter, Depends, HTTPException
from typing import Dict, Any
import uuid
from authentication_service import get_current_user
from rbac_utils import require_permission
from autonomous_ops.response_messages import FENCE

router = APIRouter(prefix="/api/swarm", tags=["Swarm"])


@router.post("/propagate-antibody")
async def propagate_antibody(
    threat_data: Dict[str, Any],
    current_user=Depends(require_permission("remediate:agents")),
):
    """
    Antibody propagation used to queue a block rule for every online agent. That
    path skipped the Autonomous Ops gate (stop, limits, protected targets, the audit
    ledger), so it now sends nothing and says so (RESP-11, D-18). Containment is
    decided in Autonomous Ops. Rows an earlier version left in the old queue stay put.
    """
    tenant_id = getattr(current_user, "tenant_id", None) or None
    if not tenant_id:
        raise HTTPException(status_code=403, detail="Tenant context required")
    antibody_id = f"antibody-{uuid.uuid4().hex[:8]}"
    threat_type = threat_data.get("threat_type", "Unknown")
    indicator = threat_data.get("indicator") or threat_data.get("ip") or threat_data.get("hash", "")
    return {
        "status": "not_sent",
        "dispatched": 0,
        "antibody_id": antibody_id,
        "threat_type": threat_type,
        "indicator": indicator,
        "message": FENCE["swarm"],
    }

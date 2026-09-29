"""Agent self-credential rotation (Phase 63, promoted from backlog 999.2,
extends AUTO-02's ACTION_MAP). Scope is deliberately narrow: an agent's own
bearer token only — never broader managed-secret rotation (cloud/SaaS
credentials), which was explicitly out of scope when this backlog item was
promoted.

Two endpoints, two very different callers:

  - POST /{agent_id}/rotate-key — operator-triggered. Goes through the exact
    same select_playbook -> pending_approval -> approve/deny -> dispatch
    pipeline as kill_process/restore_file/block_ip (Phase 53), since the
    rotate_key playbook step is marked destructive: true. No code here
    handles approval — that's remediation_control_endpoints.py, unchanged.

  - POST /{hostname}/rotate-key/confirm — agent-called only, never by an
    operator, once the agent receives the dispatched "rotate_key"
    instruction. Must mint the new token and revoke the old one in the same
    request/response: the backend is the only party that can mint a valid
    token (it alone holds SECRET_KEY), and revoking the agent's current
    token before it has the replacement in hand would permanently lock it
    out — it could never poll for instructions again to receive a new one.
    Doing both atomically means either the swap fully succeeds or nothing
    changes; there is no half-rotated state.
"""
import logging
import uuid
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, Optional

import jwt as pyjwt
from fastapi import APIRouter, Depends, Header, HTTPException

from agent_auth import verify_agent_key
from authentication_service import (
    ALGORITHM,
    SECRET_KEY,
    _revoked_jti_cache,
    create_access_token,
    get_current_user,
)
from autonomous_remediation_service import AutonomousRemediationService, RemediationFinding
from database import get_database
from rbac_utils import verify_permission

logger = logging.getLogger("agent_key_rotation")
router = APIRouter(prefix="/api/agents", tags=["Agents"])


async def _require_ops_permission(current_user=Depends(get_current_user)):
    if not await verify_permission(current_user, "manage:active_response"):
        raise HTTPException(status_code=403, detail="Permission denied")
    return current_user


@router.post("/{agent_id}/rotate-key")
async def request_agent_key_rotation(agent_id: str, current_user=Depends(_require_ops_permission)):
    """Operator-triggered: queue a rotate_key remediation for approval,
    exactly like kill_process/restore_file/block_ip (Phase 53). Never
    rotates anything directly — the approval gate and dispatch happen
    through the existing autonomous remediation pipeline."""
    tenant_id = getattr(current_user, "tenant_id", None)
    db = get_database()
    query: Dict[str, Any] = {"id": agent_id}
    if tenant_id:
        query["tenantId"] = tenant_id
    agent = await db.agents.find_one(query)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    finding = RemediationFinding(
        finding_id=f"credential-rotation-{agent_id}-{uuid.uuid4().hex[:8]}",
        finding_type="agent_credential",
        severity="medium",
        tenant_id=tenant_id or agent.get("tenantId"),
        agent_id=agent_id,
        resource_id=agent_id,
        details={"requested_by": getattr(current_user, "id", None) or getattr(current_user, "email", None)},
    )
    return await AutonomousRemediationService().remediate(finding)


@router.post("/{hostname}/rotate-key/confirm")
async def confirm_agent_key_rotation(
    hostname: str,
    authorization: Optional[str] = Header(None),
    _tenant: Dict[str, Any] = Depends(verify_agent_key),
):
    """Called by the agent itself, using its own current token as proof of
    identity. Mints a replacement token and revokes the presented one's jti
    in the same call — there is no other server-side record of "this
    agent's current token" to look up (agent tokens are stateless JWTs, see
    authentication_service.verify_token_async), so the token the agent
    presents here IS the one being rotated."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Bearer token required to rotate a credential")
    old_token = authorization.split(" ", 1)[1]
    try:
        payload = pyjwt.decode(old_token, SECRET_KEY, algorithms=[ALGORITHM])
    except pyjwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid agent token")

    tenant_id = payload.get("tenant_id")
    old_jti = payload.get("jti")
    old_exp = payload.get("exp")

    db = get_database()
    agent = await db.agents.find_one({"hostname": hostname, "tenantId": tenant_id})
    agent_id = agent["id"] if agent else hostname

    new_token = create_access_token(
        data={"sub": agent_id, "role": "agent", "tenant_id": tenant_id},
        expires_delta=timedelta(days=90),
    )

    if old_jti:
        _revoked_jti_cache.add(old_jti)  # block in-process immediately, even if the DB write below fails
        try:
            await db.revoked_tokens.insert_one({
                "jti": old_jti,
                "exp": old_exp,
                "revoked_at": datetime.now(timezone.utc).isoformat(),
                "reason": "agent_key_rotation",
            })
        except Exception as db_err:
            logger.warning("Rotation revocation DB write failed for agent %s — blocked in-process cache only: %s", agent_id, db_err)

    logger.info("Agent %s (%s) rotated its credential", agent_id, hostname)
    return {"token": new_token}

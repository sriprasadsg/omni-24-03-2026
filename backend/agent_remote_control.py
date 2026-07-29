from fastapi import APIRouter, HTTPException, Depends
import logging
import re
import uuid
from datetime import datetime, timezone

from authentication_service import get_current_user
from database import get_database
from auth_types import TokenData
from rbac_utils import require_permission, is_super_admin
import websocket_manager

_RC_SUPER_ROLES = {"Super Admin", "super_admin", "admin", "platform-admin"}
# Roles that may issue remote shell commands — elevated privilege required
_RC_EXECUTE_ROLES = {"Super Admin", "super_admin", "admin", "platform-admin", "Tenant Admin", "tenant_admin"}

# Allowlist of permitted executables for remote execution
_ALLOWED_COMMANDS = {
    "ls", "ps", "whoami", "hostname", "netstat", "ss", "df", "uptime",
    "date", "ping", "ifconfig", "ip", "cat", "head", "tail", "grep",
    "find", "systemctl", "service", "journalctl", "dmesg", "id",
    "uname", "env", "which", "pwd", "lsof", "top", "free",
}
# Shell metacharacters that must not appear in arguments
_SHELL_META_RE = re.compile(r'[;&|`$()<>\\\n\r]')


def _assert_may_execute(role: str) -> None:
    """Defense-in-depth role gate for remote command/control endpoints.

    `manage:agents` permission alone is not sufficient — the caller must also
    hold an elevated role. Super Admins (all variants) bypass; Tenant Admins and
    platform admins are explicitly allowed via _RC_EXECUTE_ROLES.
    """
    if is_super_admin(role) or role in _RC_EXECUTE_ROLES:
        return
    raise HTTPException(status_code=403, detail="Your role is not permitted to issue remote commands")


router = APIRouter(prefix="/api/agents/remote", tags=["agent-remote-control"])
logger = logging.getLogger(__name__)

# --- REST Endpoints for Remote Control ---

@router.post("/{agent_id}/execute")
async def execute_command(
    agent_id: str,
    command: dict,
    current_user: TokenData = Depends(require_permission("manage:agents"))
):
    """Execute a shell command on the agent"""
    # Check if agent is connected
    if not await websocket_manager.is_agent_connected(agent_id):
        raise HTTPException(status_code=503, detail="Agent is not connected via WebSocket")
    
    # Verify agent exists and belongs to user's tenant
    db = get_database()
    _caller_role = getattr(current_user, "role", "")
    _assert_may_execute(_caller_role)
    _caller_tenant = getattr(current_user, "tenant_id", None)
    _agent_filter: dict = {"id": agent_id}
    if _caller_role not in _RC_SUPER_ROLES:
        _agent_filter["tenantId"] = _caller_tenant
    agent = await db.agents.find_one(_agent_filter)

    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    cmd = (command.get("command") or "").strip()
    args = command.get("args", []) or []
    if cmd not in _ALLOWED_COMMANDS:
        raise HTTPException(status_code=400, detail=f"Command '{cmd}' is not permitted. Allowed: {sorted(_ALLOWED_COMMANDS)}")
    for arg in args:
        if _SHELL_META_RE.search(str(arg)):
            raise HTTPException(status_code=400, detail="Shell metacharacters are not permitted in command arguments")

    command_id = str(uuid.uuid4())
    command_payload = {
        "type": "execute",
        "command_id": command_id,
        "command": cmd,
        "args": args,
        "user_id": current_user.username  # This is actually the email/sub
    }
    
    # Send via Socket.IO
    success = await websocket_manager.send_to_agent(agent_id, command_payload)
    
    if not success:
        raise HTTPException(status_code=503, detail="Failed to send command to agent")
    
    # Log the command
    await db.agent_commands.insert_one({
        "id": command_id,
        "agent_id": agent_id,
        "user_id": current_user.username,
        "command": command.get("command"),
        "status": "pending",
        "created_at": datetime.now(timezone.utc).isoformat()
    })
    
    # PAM: Log to Immutable Ledger (Async)
    try:
        from audit_service import get_audit_service
        audit_service = get_audit_service()
        await audit_service.log_action_async(
            user_name=current_user.username,
            action="remote_command.execute",
            resource_type="agent",
            resource_id=agent_id,
            details=f"Executed command: {command.get('command')} {command.get('args', [])}",
            tenant_id=current_user.tenant_id
        )
    except Exception as e:
        logger.error(f"Failed to log PAM audit event: {e}")
    
    return {
        "success": True,
        "command_id": command_id,
        "status": "sent"
    }

@router.post("/{agent_id}/restart")
async def restart_agent(
    agent_id: str,
    current_user: TokenData = Depends(require_permission("manage:agents"))
):
    """Restart the agent"""
    if not await websocket_manager.is_agent_connected(agent_id):
        raise HTTPException(status_code=503, detail="Agent is not connected via WebSocket")
    
    db = get_database()
    _caller_role = getattr(current_user, "role", "")
    _assert_may_execute(_caller_role)
    _caller_tenant = getattr(current_user, "tenant_id", None)
    _agent_filter: dict = {"id": agent_id}
    if _caller_role not in _RC_SUPER_ROLES:
        _agent_filter["tenantId"] = _caller_tenant
    agent = await db.agents.find_one(_agent_filter)

    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    command_id = str(uuid.uuid4())
    command_payload = {
        "type": "restart",
        "command_id": command_id,
        "user_id": current_user.username
    }
    
    # Send via Socket.IO
    success = await websocket_manager.send_to_agent(agent_id, command_payload)
    
    if not success:
        raise HTTPException(status_code=503, detail="Failed to send restart command")
    
    await db.agent_commands.insert_one({
        "id": command_id,
        "agent_id": agent_id,
        "user_id": current_user.username,
        "command": "RESTART",
        "status": "pending",
        "created_at": datetime.now(timezone.utc).isoformat()
    })
    
    return {"success": True, "status": "restart_initiated", "command_id": command_id}

@router.get("/{agent_id}/status")
async def get_agent_connection_status(
    agent_id: str,
    _current_user: TokenData = Depends(get_current_user),
):
    """Check if agent is connected to WebSocket"""
    is_connected = await websocket_manager.is_agent_connected(agent_id)
    # connected_agents = await websocket_manager.get_connected_agents()
    
    return {
        "agent_id": agent_id,
        "websocket_connected": is_connected
    }

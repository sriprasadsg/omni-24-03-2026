from fastapi import APIRouter, HTTPException, Depends
from typing import Dict
import logging
import asyncio
import uuid
from datetime import datetime
import json

from authentication_service import get_current_user
from database import get_database
from auth_types import TokenData
import websocket_manager 

router = APIRouter(prefix="/api/agents/remote", tags=["agent-remote-control"])
logger = logging.getLogger(__name__)

# --- REST Endpoints for Remote Control ---

@router.post("/{agent_id}/execute")
async def execute_command(
    agent_id: str,
    command: dict,
    current_user: TokenData = Depends(get_current_user)
):
    """Execute a shell command on the agent"""
    # Check if agent is connected
    if not await websocket_manager.is_agent_connected(agent_id):
        raise HTTPException(status_code=503, detail="Agent is not connected via WebSocket")
    
    # Verify agent exists and belongs to user's tenant
    db = get_database()
    agent = await db.agents.find_one({"id": agent_id})
    
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    
    # For non-super admins, verify tenant access
    if current_user.role != "Super Admin" and agent.get("tenantId") != current_user.tenant_id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    command_id = str(uuid.uuid4())
    command_payload = {
        "type": "execute",
        "command_id": command_id,
        "command": command.get("command"),
        "args": command.get("args", []),
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
        "created_at": datetime.utcnow().isoformat()
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
    current_user: TokenData = Depends(get_current_user)
):
    """Restart the agent"""
    if not await websocket_manager.is_agent_connected(agent_id):
        raise HTTPException(status_code=503, detail="Agent is not connected via WebSocket")
    
    db = get_database()
    agent = await db.agents.find_one({"id": agent_id})
    
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    
    if current_user.role != "Super Admin" and agent.get("tenantId") != current_user.tenant_id:
        raise HTTPException(status_code=403, detail="Access denied")
    
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
        "created_at": datetime.utcnow().isoformat()
    })
    
    return {"success": True, "status": "restart_initiated", "command_id": command_id}

@router.get("/{agent_id}/status")
async def get_agent_connection_status(agent_id: str):
    """Check if agent is connected to WebSocket"""
    is_connected = await websocket_manager.is_agent_connected(agent_id)
    # connected_agents = await websocket_manager.get_connected_agents()
    
    return {
        "agent_id": agent_id,
        "websocket_connected": is_connected
    }

"""
Enhanced SOAR Playbook Template, Analytics, and Integration Endpoints
"""

import logging
from fastapi import APIRouter, HTTPException, Depends
from typing import List, Optional, Dict, Any
from motor.motor_asyncio import AsyncIOMotorDatabase
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

from database import get_database
from soar_integrations import get_integration_manager
from rbac_utils import require_permission

router = APIRouter(prefix="/api/playbooks/enhanced", tags=["Enhanced SOAR"])

_KEY_ALIASES = {"tenantId": "tenant_id", "email": "username"}


def _get(user, key, default=None):
    if isinstance(user, dict):
        return user.get(key, default)
    attr = _KEY_ALIASES.get(key, key)
    return getattr(user, attr, default)


def _get_connector_actions(connector_name: str) -> List[str]:
    action_map = {
        "slack": ["send_message", "request_approval"],
        "jira": ["create_ticket", "update_ticket", "add_comment"],
        "firewall": ["block_ip", "unblock_ip", "create_rule"],
        "edr": ["isolate_endpoint", "release_endpoint", "quarantine_file", "scan_endpoint"],
        "email_gateway": ["block_sender", "quarantine_email", "release_email"],
        "cloud_provider": ["quarantine_instance", "snapshot_instance", "revoke_credentials"]
    }
    return action_map.get(connector_name, [])


@router.get("/templates")
async def get_playbook_templates(
    category: Optional[str] = None,
    db: AsyncIOMotorDatabase = Depends(get_database),
    _current_user: dict = Depends(require_permission("view:playbooks"))
):
    """Get playbook templates filtered by optional category."""
    query = {"is_template": True}
    if category:
        query["category"] = category

    templates = []
    async for template in db.playbooks.find(query):
        template["id"] = str(template.pop("_id"))
        templates.append(template)

    return templates


@router.post("/templates")
async def create_playbook_from_template(
    template_id: str,
    name: str,
    customizations: Optional[Dict[str, Any]] = None,
    db: AsyncIOMotorDatabase = Depends(get_database),
    current_user: dict = Depends(require_permission("manage:playbooks"))
):
    """Create a new playbook from a template with optional customizations."""
    template = await db.playbooks.find_one({"_id": template_id, "is_template": True})
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")

    playbook = {
        "name": name,
        "description": template.get("description"),
        "trigger": template.get("trigger"),
        "steps": template.get("steps"),
        "tenantId": _get(current_user, "tenantId"),
        "created_by": _get(current_user, "email"),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "template_id": template_id,
        "is_template": False,
    }
    if customizations:
        playbook.update(customizations)

    result = await db.playbooks.insert_one(playbook)
    return {"message": "Playbook created from template", "playbook_id": str(result.inserted_id)}


@router.get("/analytics")
async def get_playbook_analytics(
    _days: int = 30,
    db: AsyncIOMotorDatabase = Depends(get_database),
    current_user: dict = Depends(require_permission("view:playbooks"))
):
    """Get playbook execution analytics including success rates and timing."""
    tenant_id = _get(current_user, "tenantId")

    pipeline = [
        {"$match": {"tenant_id": tenant_id}},
        {
            "$group": {
                "_id": "$playbook_id",
                "playbook_name": {"$first": "$playbook_name"},
                "total_executions": {"$sum": 1},
                "successful": {
                    "$sum": {"$cond": [{"$eq": ["$status", "completed"]}, 1, 0]}
                },
                "failed": {
                    "$sum": {"$cond": [{"$eq": ["$status", "failed"]}, 1, 0]}
                },
                "avg_duration": {"$avg": "$duration_ms"}
            }
        },
        {"$sort": {"total_executions": -1}}
    ]

    playbook_stats = []
    total_executions = 0
    total_successful = 0

    async for stat in db.playbook_executions.aggregate(pipeline):
        success_rate = (stat["successful"] / stat["total_executions"] * 100) if stat["total_executions"] > 0 else 0
        playbook_stats.append({
            "playbook_id": stat["_id"],
            "playbook_name": stat["playbook_name"],
            "total_executions": stat["total_executions"],
            "success_rate": round(success_rate, 2),
            "avg_duration_ms": round(stat.get("avg_duration", 0), 2)
        })
        total_executions += stat["total_executions"]
        total_successful += stat["successful"]

    overall_success_rate = (total_successful / total_executions * 100) if total_executions > 0 else 0
    return {
        "total_executions": total_executions,
        "overall_success_rate": round(overall_success_rate, 2),
        "playbook_stats": playbook_stats,
    }


@router.get("/integrations")
async def get_available_integrations(
    _current_user: dict = Depends(require_permission("view:playbooks"))
):
    """Get list of available integration connectors with their connection status."""
    integration_manager = get_integration_manager()
    connection_status = await integration_manager.test_all_connections()

    return [
        {
            "name": name,
            "type": connector.__class__.__name__,
            "available": connection_status.get(name, False),
            "actions": _get_connector_actions(name),
        }
        for name, connector in integration_manager.connectors.items()
    ]


@router.post("/integrations/test")
async def test_integration(
    connector_name: str,
    action: str,
    params: Dict[str, Any],
    _current_user: dict = Depends(require_permission("manage:playbooks"))
):
    """Test an integration connector action to validate configuration."""
    integration_manager = get_integration_manager()
    try:
        result = await integration_manager.execute_action(
            connector_name=connector_name,
            action=action,
            params=params,
        )
        return {"message": "Integration test successful", "result": result}
    except ValueError:
        raise HTTPException(status_code=404, detail="Not found")
    except Exception as e:
        logger.error("Integration test failed: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error")

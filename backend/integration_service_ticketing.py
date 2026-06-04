"""
IntegrationService ticketing and CMDB mixin: Jira, ServiceNow, Zoho Desk, CMDB sync.
"""

import aiohttp
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional
import logging

_log = logging.getLogger(__name__)

_JIRA_PRIORITY = {"critical": "Highest", "high": "High", "medium": "Medium", "low": "Low"}
_SNOW_PRIORITY = {"critical": "1", "high": "2", "medium": "3", "low": "4"}


class IntegrationServiceTicketingMixin:
    """Ticketing system and CMDB integrations."""

    async def sync_assets_to_cmdb(
        self,
        platform: str = "servicenow",
        tenant_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Sync assets to a CMDB platform (servicenow)."""
        config = await self._get_integration_config("cmdb", platform)
        if not config or not config.get("enabled"):
            return {"success": False, "error": f"CMDB {platform} not configured"}

        query = {}
        if tenant_id:
            query["tenantId"] = tenant_id
        assets = await self.db.assets.find(query, {"_id": 0}).to_list(length=1000)

        if platform == "servicenow":
            return await self._sync_to_servicenow(assets, config)
        return {"success": False, "error": f"Unsupported CMDB platform: {platform}"}

    async def _sync_to_servicenow(
        self, assets: List[Dict[str, Any]], config: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Sync assets to ServiceNow CMDB."""
        url = f"{config['instance_url']}/api/now/table/cmdb_ci_server"
        headers = {"Authorization": f"Basic {config['auth_token']}",
                   "Content-Type": "application/json"}
        synced = failed = 0
        for asset in assets[:10]:
            payload = {
                "name": asset.get("name"), "ip_address": asset.get("ipAddress"),
                "os": asset.get("os"), "os_version": asset.get("osVersion"),
                "serial_number": asset.get("id"), "asset_tag": asset.get("id"),
            }
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.post(
                        url, json=payload, headers=headers,
                        timeout=aiohttp.ClientTimeout(total=10)
                    ) as resp:
                        if resp.status in (200, 201):
                            synced += 1
                        else:
                            failed += 1
            except Exception:
                failed += 1
        return {"success": True, "platform": "servicenow",
                "synced_assets": synced, "failed_assets": failed, "total_assets": len(assets)}

    async def create_ticket(
        self,
        title: str,
        description: str,
        priority: str,
        platform: str = "jira",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Create ticket in a ticketing system (jira, servicenow, zohodesk)."""
        config = await self._get_integration_config("ticketing", platform)
        if not config or not config.get("enabled"):
            return {"success": False, "error": f"Ticketing {platform} not configured"}

        if platform == "jira":
            return await self._create_jira_ticket(title, description, priority, config, metadata)
        if platform == "servicenow":
            return await self._create_servicenow_ticket(title, description, priority, config, metadata)
        if platform == "zohodesk":
            return await self._create_zoho_ticket(title, description, priority, config, metadata)
        return {"success": False, "error": f"Unsupported ticketing platform: {platform}"}

    async def _create_jira_ticket(
        self,
        title: str,
        description: str,
        priority: str,
        config: Dict[str, Any],
        metadata: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Create a Jira issue."""
        url = f"{config['instance_url']}/rest/api/2/issue"
        payload = {
            "fields": {
                "project": {"key": config.get("project_key", "PATCH")},
                "summary": title,
                "description": description,
                "issuetype": {"name": "Task"},
                "priority": {"name": _JIRA_PRIORITY.get(priority, "Medium")},
            }
        }
        headers = {"Authorization": f"Basic {config['auth_token']}",
                   "Content-Type": "application/json"}
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url, json=payload, headers=headers, timeout=aiohttp.ClientTimeout(total=10)
                ) as resp:
                    if resp.status in (200, 201):
                        data = await resp.json()
                        return {"success": True, "platform": "jira",
                                "ticket_id": data.get("key"),
                                "url": f"{config['instance_url']}/browse/{data.get('key')}"}
                    return {"success": False, "error": f"JIRA API returned {resp.status}"}
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    async def _create_servicenow_ticket(
        self,
        title: str,
        description: str,
        priority: str,
        config: Dict[str, Any],
        metadata: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Create a ServiceNow incident."""
        url = f"{config['instance_url']}/api/now/table/incident"
        payload = {
            "short_description": title, "description": description,
            "priority": _SNOW_PRIORITY.get(priority, "3"), "category": "Software",
        }
        headers = {"Authorization": f"Basic {config['auth_token']}",
                   "Content-Type": "application/json"}
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url, json=payload, headers=headers, timeout=aiohttp.ClientTimeout(total=10)
                ) as resp:
                    if resp.status in (200, 201):
                        data = await resp.json()
                        result = data.get("result", {})
                        return {
                            "success": True, "platform": "servicenow",
                            "ticket_id": result.get("number"),
                            "url": (
                                f"{config['instance_url']}/nav_to.do"
                                f"?uri=incident.do?sys_id={result.get('sys_id')}"
                            ),
                        }
                    return {"success": False, "error": f"ServiceNow API returned {resp.status}"}
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    async def _create_zoho_ticket(
        self,
        title: str,
        description: str,
        priority: str,
        config: Dict[str, Any],
        metadata: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Simulation: Create Zoho Desk ticket."""
        _log.info("[TICKETING][ZOHO] Creating ticket: %s", title)
        return {
            "success": True, "platform": "zohodesk",
            "ticket_id": f"ZD-{datetime.now(timezone.utc).timestamp()}",
            "url": "https://desk.zoho.com/mock",
        }

    async def comment_on_ticket(
        self, ticket_id: str, comment: str, platform: str = "jira"
    ) -> Dict[str, Any]:
        """Post a comment on an existing ticket."""
        config = await self._get_integration_config("ticketing", platform)
        if not config or not config.get("enabled"):
            return {"success": False, "error": f"Ticketing {platform} not configured"}

        if platform == "jira":
            return await self._comment_on_jira_ticket(ticket_id, comment, config)
        if platform == "zohodesk":
            return await self._comment_on_zoho_ticket(ticket_id, comment, config)
        return {"success": False, "error": f"Commenting not implemented for {platform}"}

    async def _comment_on_jira_ticket(
        self, ticket_id: str, comment: str, config: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Post a comment to a Jira issue."""
        url = f"{config['instance_url']}/rest/api/2/issue/{ticket_id}/comment"
        headers = {"Authorization": f"Basic {config['auth_token']}",
                   "Content-Type": "application/json"}
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url, json={"body": comment}, headers=headers,
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as resp:
                    return {"success": resp.status in (200, 201)}
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    async def _comment_on_zoho_ticket(
        self, ticket_id: str, comment: str, config: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Simulation: Post a comment to Zoho Desk."""
        _log.info("[TICKETING][ZOHO] Adding comment to %s", ticket_id)
        return {"success": True, "platform": "zohodesk"}

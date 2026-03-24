"""
Integration Service - External Platform Integrations
SIEM, CMDB, Ticketing, EDR/XDR integrations
"""

from datetime import datetime, timezone
from typing import Dict, List, Optional, Any
import aiohttp


class IntegrationService:
    """External platform integration service"""
    
    def __init__(self, db):
        self.db = db
    
    async def send_to_siem(
        self,
        event_type: str,
        severity: str,
        details: Dict[str, Any],
        platform: str = "splunk"
    ) -> Dict[str, Any]:
        """
        Send security event to SIEM platform
        
        Supported platforms: splunk, wazuh, qradar, sentinel
        """
        config = await self._get_integration_config("siem", platform)
        
        if not config or not config.get("enabled"):
            return {"success": False, "error": f"SIEM {platform} not configured"}
        
        # Format event based on platform
        if platform == "splunk":
            return await self._send_to_splunk(event_type, severity, details, config)
        elif platform == "wazuh":
            return await self._send_to_wazuh(event_type, severity, details, config)
        elif platform == "elk":
            return await self._send_to_elk(event_type, severity, details, config)
        elif platform == "qradar":
            return await self._send_to_qradar(event_type, severity, details, config)
        else:
            return {"success": False, "error": f"Unsupported SIEM platform: {platform}"}
    
    async def _send_to_splunk(
        self,
        event_type: str,
        severity: str,
        details: Dict[str, Any],
        config: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Send event to Splunk HEC (HTTP Event Collector)"""
        url = f"{config['endpoint']}/services/collector/event"
        
        payload = {
            "time": datetime.now(timezone.utc).timestamp(),
            "sourcetype": "patch_management",
            "event": {
                "event_type": event_type,
                "severity": severity,
                **details
            }
        }
        
        headers = {
            "Authorization": f"Splunk {config['token']}",
            "Content-Type": "application/json"
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload, headers=headers, ssl=False) as response:
                    if response.status == 200:
                        return {"success": True, "details": await response.json()}
                    else:
                        return {"success": False, "error": f"Splunk returned {response.status}", "details": await response.text()}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    async def _send_to_elk(
        self,
        event_type: str,
        severity: str,
        details: Dict[str, Any],
        config: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Send event to Elasticsearch/Logstash"""
        url = f"{config['endpoint']}/{config.get('index', 'security-events')}/_doc"
        
        payload = {
            "@timestamp": datetime.now(timezone.utc).isoformat(),
            "event_type": event_type,
            "severity": severity,
            **details
        }
        
        headers = {
            "Content-Type": "application/json"
        }
        
        if config.get("api_key"):
            headers["Authorization"] = f"ApiKey {config['api_key']}"
        elif config.get("username") and config.get("password"):
            auth = aiohttp.BasicAuth(config["username"], config["password"])
            headers["Authorization"] = auth.encode()
            
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as response:
                    return {
                        "success": response.status in [200, 201],
                        "platform": "elk",
                        "status_code": response.status
                    }
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    async def _send_to_wazuh(
        self,
        event_type: str,
        severity: str,
        details: Dict[str, Any],
        config: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Simulation: Send event to Wazuh manager"""
        # In production, this would use Wazuh API or Syslog
        print(f"[SIEM][WAZUH] Sending {event_type} (Severity: {severity}) to {config.get('endpoint', 'N/A')}")
        
        return {
            "success": True,
            "platform": "wazuh",
            "status": "simulated",
            "transmission_id": f"wz-{datetime.now(timezone.utc).timestamp()}",
            "details": {
                "event_type": event_type,
                "endpoint": config.get("endpoint"),
                "agent_id": details.get("agent_id", "global")
            }
        }
    
    async def _send_to_qradar(
        self,
        event_type: str,
        severity: str,
        details: Dict[str, Any],
        config: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Simulation: Send event to IBM QRadar"""
        # In production, this would use QRadar REST API or LEEF logs
        print(f"[SIEM][QRADAR] Sending {event_type} (Severity: {severity}) to {config.get('endpoint', 'N/A')}")
        
        return {
            "success": True,
            "platform": "qradar",
            "status": "simulated",
            "transmission_id": f"qr-{datetime.now(timezone.utc).timestamp()}",
            "details": {
                "event_type": event_type,
                "leef_version": "2.0"
            }
        }
    
    async def sync_assets_to_cmdb(
        self,
        platform: str = "servicenow",
        tenant_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Sync assets to CMDB platform
        
        Supported: servicenow, device42
        """
        config = await self._get_integration_config("cmdb", platform)
        
        if not config or not config.get("enabled"):
            return {"success": False, "error": f"CMDB {platform} not configured"}
        
        # Get assets
        query = {}
        if tenant_id:
            query["tenantId"] = tenant_id
        
        assets = await self.db.assets.find(query, {"_id": 0}).to_list(length=None)
        
        if platform == "servicenow":
            return await self._sync_to_servicenow(assets, config)
        else:
            return {"success": False, "error": f"Unsupported CMDB platform: {platform}"}
    
    async def _sync_to_servicenow(
        self,
        assets: List[Dict[str, Any]],
        config: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Sync assets to ServiceNow CMDB"""
        url = f"{config['instance_url']}/api/now/table/cmdb_ci_server"
        
        headers = {
            "Authorization": f"Basic {config['auth_token']}",
            "Content-Type": "application/json"
        }
        
        synced = 0
        failed = 0
        
        for asset in assets[:10]:  # Limit for demo
            payload = {
                "name": asset.get("name"),
                "ip_address": asset.get("ipAddress"),
                "os": asset.get("os"),
                "os_version": asset.get("osVersion"),
                "serial_number": asset.get("id"),
                "asset_tag": asset.get("id")
            }
            
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.post(url, json=payload, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as response:
                        if response.status in [200, 201]:
                            synced += 1
                        else:
                            failed += 1
            except Exception:
                failed += 1
        
        return {
            "success": True,
            "platform": "servicenow",
            "synced_assets": synced,
            "failed_assets": failed,
            "total_assets": len(assets)
        }
    
    async def create_ticket(
        self,
        title: str,
        description: str,
        priority: str,
        platform: str = "jira",
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Create ticket in ticketing system
        
        Supported: jira, servicenow, zohodesk
        """
        config = await self._get_integration_config("ticketing", platform)
        
        if not config or not config.get("enabled"):
            return {"success": False, "error": f"Ticketing {platform} not configured"}
        
        if platform == "jira":
            return await self._create_jira_ticket(title, description, priority, config, metadata)
        elif platform == "servicenow":
            return await self._create_servicenow_ticket(title, description, priority, config, metadata)
        elif platform == "zohodesk":
            return await self._create_zoho_ticket(title, description, priority, config, metadata)
        else:
            return {"success": False, "error": f"Unsupported ticketing platform: {platform}"}
    
    async def _create_jira_ticket(
        self,
        title: str,
        description: str,
        priority: str,
        config: Dict[str, Any],
        metadata: Optional[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Create JIRA ticket"""
        url = f"{config['instance_url']}/rest/api/2/issue"
        
        # Map priority
        priority_map = {
            "critical": "Highest",
            "high": "High",
            "medium": "Medium",
            "low": "Low"
        }
        
        payload = {
            "fields": {
                "project": {"key": config.get("project_key", "PATCH")},
                "summary": title,
                "description": description,
                "issuetype": {"name": "Task"},
                "priority": {"name": priority_map.get(priority, "Medium")}
            }
        }
        
        headers = {
            "Authorization": f"Basic {config['auth_token']}",
            "Content-Type": "application/json"
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as response:
                    if response.status in [200, 201]:
                        data = await response.json()
                        return {
                            "success": True,
                            "platform": "jira",
                            "ticket_id": data.get("key"),
                            "url": f"{config['instance_url']}/browse/{data.get('key')}"
                        }
                    else:
                        return {
                            "success": False,
                            "error": f"JIRA API returned {response.status}"
                        }
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    async def _create_servicenow_ticket(
        self,
        title: str,
        description: str,
        priority: str,
        config: Dict[str, Any],
        metadata: Optional[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Create ServiceNow incident"""
        url = f"{config['instance_url']}/api/now/table/incident"
        
        # Map priority (ServiceNow uses 1-5)
        priority_map = {
            "critical": "1",
            "high": "2",
            "medium": "3",
            "low": "4"
        }
        
        payload = {
            "short_description": title,
            "description": description,
            "priority": priority_map.get(priority, "3"),
            "category": "Software"
        }
        
        headers = {
            "Authorization": f"Basic {config['auth_token']}",
            "Content-Type": "application/json"
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as response:
                    if response.status in [200, 201]:
                        data = await response.json()
                        return {
                            "success": True,
                            "platform": "servicenow",
                            "ticket_id": data.get("result", {}).get("number"),
                            "url": f"{config['instance_url']}/nav_to.do?uri=incident.do?sys_id={data.get('result', {}).get('sys_id')}"
                        }
                    else:
                        return {
                            "success": False,
                            "error": f"ServiceNow API returned {response.status}"
                        }
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    async def send_to_edr(
        self,
        asset_id: str,
        action: str,
        platform: str = "crowdstrike"
    ) -> Dict[str, Any]:
        """
        Send action to EDR/XDR platform
        
        Supported: crowdstrike, sentinelone, microsoft_defender
        Actions: isolate, scan, update
        """
        config = await self._get_integration_config("edr", platform)
        
        if not config or not config.get("enabled"):
            return {"success": False, "error": f"EDR {platform} not configured"}
        
        return {
            "success": True,
            "platform": platform,
            "asset_id": asset_id,
            "action": action,
            "message": f"{platform} integration placeholder"
        }
    
    async def _get_integration_config(
        self,
        integration_type: str,
        platform: str
    ) -> Optional[Dict[str, Any]]:
        """Get integration configuration"""
        config = await self.db.integration_configs.find_one(
            {"type": integration_type, "platform": platform},
            {"_id": 0}
        )
        return config

    async def get_all_configs(self, tenant_id: str) -> List[Dict[str, Any]]:
        """Get all integration configurations for a tenant"""
        configs = await self.db.integration_configs.find(
            {"tenantId": tenant_id},
            {"_id": 0}
        ).to_list(length=None)
        return configs

    async def save_config(self, tenant_id: str, config_data: Dict[str, Any]) -> Dict[str, Any]:
        """Save or update integration configuration"""
        integration_type = config_data.get("type")
        platform = config_data.get("platform")
        
        if not integration_type or not platform:
            return {"success": False, "error": "Missing type or platform"}
            
        await self.db.integration_configs.update_one(
            {"tenantId": tenant_id, "type": integration_type, "platform": platform},
            {"$set": {**config_data, "tenantId": tenant_id, "updatedAt": datetime.now(timezone.utc)}},
            upsert=True
        )
        
        return {"success": True, "message": f"Configuration for {platform} saved"}

    async def test_siem_connection(self, platform: str, config: Dict[str, Any]) -> Dict[str, Any]:
        """Test SIEM connection with provided configuration"""
        # For testing, we send a heartbeat event
        test_details = {
            "message": "SIEM Connection Test Heartbeat",
            "test_time": datetime.now(timezone.utc).isoformat()
        }
        
        if platform == "splunk":
            return await self._send_to_splunk("test_heartbeat", "info", test_details, config)
        elif platform == "elk":
            return await self._send_to_elk("test_heartbeat", "info", test_details, config)
        elif platform == "slack":
            return await self._send_to_slack("Test Heartbeat", "Testing Slack connection from Omni-Agent Platform.", "info", config)
        elif platform == "teams":
            return await self._send_to_teams("Test Heartbeat", "Testing Teams connection from Omni-Agent Platform.", "info", config)
        else:
            return {"success": False, "error": f"Testing not implemented for {platform}"}

    async def send_to_chatops(
        self,
        title: str,
        message: str,
        severity: str,
        platform: str = "slack"
    ) -> Dict[str, Any]:
        """
        Send notification to ChatOps platform (Slack, Teams)
        """
        config = await self._get_integration_config("chatops", platform)
        
        if not config or not config.get("enabled"):
            return {"success": False, "error": f"ChatOps {platform} not configured"}
            
        if platform == "slack":
            return await self._send_to_slack(title, message, severity, config)
        elif platform == "teams":
            return await self._send_to_teams(title, message, severity, config)
        else:
            return {"success": False, "error": f"Unsupported ChatOps platform: {platform}"}

    async def _send_to_slack(
        self,
        title: str,
        message: str,
        severity: str,
        config: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Send message to Slack Webhook"""
        url = config.get("webhook_url")
        if not url:
            return {"success": False, "error": "Missing Webhook URL"}

        color_map = {
            "critical": "#FF0000",
            "high": "#FF9900",
            "medium": "#FFFF00",
            "low": "#00FF00",
            "info": "#0000FF"
        }

        payload = {
            "attachments": [
                {
                    "color": color_map.get(severity, "#CCCCCC"),
                    "title": title,
                    "text": message,
                    "footer": "Omni-Agent AI Platform",
                    "ts": datetime.now(timezone.utc).timestamp()
                }
            ]
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=10)) as response:
                    return {
                        "success": response.status == 200,
                        "platform": "slack",
                        "status_code": response.status
                    }
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def _send_to_teams(
        self,
        title: str,
        message: str,
        severity: str,
        config: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Send message to Microsoft Teams Webhook"""
        url = config.get("webhook_url")
        if not url:
            return {"success": False, "error": "Missing Webhook URL"}
            
        # Teams Card payload
        payload = {
            "@type": "MessageCard",
            "@context": "http://schema.org/extensions",
            "themeColor": "0076D7",
            "summary": title,
            "sections": [{
                "activityTitle": title,
                "activitySubtitle": f"Severity: {severity.upper()}",
                "text": message,
                "markdown": True
            }]
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=10)) as response:
                    return {
                        "success": response.status == 200,
                        "platform": "teams",
                        "status_code": response.status
                    }
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def _create_zoho_ticket(
        self,
        title: str,
        description: str,
        priority: str,
        config: Dict[str, Any],
        metadata: Optional[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Simulation: Create Zoho Desk ticket"""
        print(f"[TICKETING][ZOHO] Creating ticket: {title}")
        return {
            "success": True,
            "platform": "zohodesk",
            "ticket_id": f"ZD-{datetime.now(timezone.utc).timestamp()}",
            "url": "https://desk.zoho.com/mock"
        }

    async def comment_on_ticket(
        self,
        ticket_id: str,
        comment: str,
        platform: str = "jira"
    ) -> Dict[str, Any]:
        """Post a comment on an existing ticket"""
        config = await self._get_integration_config("ticketing", platform)
        
        if not config or not config.get("enabled"):
            return {"success": False, "error": f"Ticketing {platform} not configured"}
            
        if platform == "jira":
            return await self._comment_on_jira_ticket(ticket_id, comment, config)
        elif platform == "zohodesk":
            return await self._comment_on_zoho_ticket(ticket_id, comment, config)
        else:
            return {"success": False, "error": f"Commenting not implemented for {platform}"}

    async def _comment_on_jira_ticket(
        self,
        ticket_id: str,
        comment: str,
        config: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Post a comment to JIRA"""
        url = f"{config['instance_url']}/rest/api/2/issue/{ticket_id}/comment"
        payload = {"body": comment}
        headers = {
            "Authorization": f"Basic {config['auth_token']}",
            "Content-Type": "application/json"
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as response:
                    return {"success": response.status in [200, 201]}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def _comment_on_zoho_ticket(
        self,
        ticket_id: str,
        comment: str,
        config: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Simulation: Post a comment to Zoho Desk"""
        print(f"[TICKETING][ZOHO] Adding comment to {ticket_id}: {comment}")
        return {"success": True, "platform": "zohodesk"}


def get_integration_service(db):
    """Get integration service instance"""
    return IntegrationService(db)

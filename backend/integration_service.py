"""
Integration Service - External Platform Integrations
SIEM, CMDB, Ticketing, EDR/XDR integrations
"""

import logging
import os as _os
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any
import aiohttp

_SSL_VERIFY = True  # SSL verification is always enforced; never disable globally
if _os.getenv("DISABLE_SSL_VERIFY", "").lower() in ("1", "true", "yes"):
    import logging as _warn_log
    _warn_log.getLogger(__name__).warning(
        "DISABLE_SSL_VERIFY is set but ignored — SSL certificate validation is enforced. "
        "Use per-integration verify_ssl config for self-signed cert environments."
    )

_log = logging.getLogger(__name__)


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
                async with session.post(url, json=payload, headers=headers, ssl=_SSL_VERIFY) as response:
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
        """Send event to Wazuh manager via REST API (Wazuh 4.4+)."""
        base = config.get("endpoint", "").rstrip("/")
        username = config.get("username", "wazuh")
        password = config.get("password", "")

        try:
            timeout = aiohttp.ClientTimeout(total=10)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                # Authenticate
                auth_resp = await session.post(
                    f"{base}/security/user/authenticate",
                    auth=aiohttp.BasicAuth(username, password),
                    ssl=_SSL_VERIFY,
                )
                if auth_resp.status != 200:
                    return {"success": False, "platform": "wazuh", "error": f"Auth failed: {auth_resp.status}"}
                token = (await auth_resp.json())["data"]["token"]

                # Inject event
                payload = {
                    "events": [
                        {
                            "log": {
                                "full_log": f"event_type={event_type} severity={severity} "
                                            + " ".join(f"{k}={v}" for k, v in details.items())
                            }
                        }
                    ]
                }
                resp = await session.post(
                    f"{base}/events",
                    json=payload,
                    headers={"Authorization": f"Bearer {token}"},
                    ssl=_SSL_VERIFY,
                )
                body = await resp.json()
                return {
                    "success": resp.status in (200, 201),
                    "platform": "wazuh",
                    "status_code": resp.status,
                    "details": body,
                }
        except Exception as exc:
            return {"success": False, "platform": "wazuh", "error": str(exc)}

    async def _send_to_qradar(
        self,
        event_type: str,
        severity: str,
        details: Dict[str, Any],
        config: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Send event to IBM QRadar via REST API using a reference-data set."""
        base = config.get("endpoint", "").rstrip("/")
        api_token = config.get("api_token", "")
        set_name = config.get("ref_set", "omni_agent_events")

        payload = {
            "event_type": event_type,
            "severity": severity,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            **{k: str(v) for k, v in details.items()},
        }

        headers = {
            "SEC": api_token,
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Version": "17.0",
        }

        try:
            timeout = aiohttp.ClientTimeout(total=10)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                # Ensure the reference set exists (ignore 409 Conflict = already exists)
                await session.post(
                    f"{base}/api/reference_data/sets",
                    params={"name": set_name, "element_type": "ALN"},
                    headers=headers,
                    ssl=_SSL_VERIFY,
                )
                # Add the event entry
                resp = await session.post(
                    f"{base}/api/reference_data/sets/{set_name}",
                    params={"value": str(payload)},
                    headers=headers,
                    ssl=_SSL_VERIFY,
                )
                return {
                    "success": resp.status in (200, 201),
                    "platform": "qradar",
                    "status_code": resp.status,
                    "ref_set": set_name,
                }
        except Exception as exc:
            return {"success": False, "platform": "qradar", "error": str(exc)}
    
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
        
        assets = await self.db.assets.find(query, {"_id": 0}).to_list(length=1000)

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
        Send action to EDR/XDR platform.
        Supported platforms: crowdstrike, sentinelone, microsoft_defender
        Actions: isolate, scan, update
        """
        config = await self._get_integration_config("edr", platform)

        if not config or not config.get("enabled"):
            return {"success": False, "error": f"EDR {platform} not configured"}

        if platform == "crowdstrike":
            return await self._crowdstrike_action(asset_id, action, config)
        elif platform == "sentinelone":
            return await self._sentinelone_action(asset_id, action, config)
        elif platform == "microsoft_defender":
            return await self._defender_action(asset_id, action, config)
        else:
            return {"success": False, "error": f"Unsupported EDR platform: {platform}"}

    async def _crowdstrike_action(
        self, asset_id: str, action: str, config: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Execute action via CrowdStrike Falcon REST API (OAuth2)."""
        base = config.get("endpoint", "https://api.crowdstrike.com").rstrip("/")
        client_id = config.get("client_id", "")
        client_secret = config.get("client_secret", "")

        cs_action_map = {"isolate": "contain", "scan": "hide_host", "update": "lift_containment"}
        cs_action = cs_action_map.get(action, action)

        try:
            timeout = aiohttp.ClientTimeout(total=15)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                # Get OAuth2 token
                token_resp = await session.post(
                    f"{base}/oauth2/token",
                    data={"client_id": client_id, "client_secret": client_secret},
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                    ssl=_SSL_VERIFY,
                )
                if token_resp.status != 201:
                    return {"success": False, "platform": "crowdstrike",
                            "error": f"Auth failed: {token_resp.status}"}
                token = (await token_resp.json())["access_token"]

                # Execute action
                resp = await session.post(
                    f"{base}/devices/entities/responses/v1",
                    params={"action_name": cs_action},
                    json={"ids": [asset_id]},
                    headers={"Authorization": f"Bearer {token}"},
                    ssl=_SSL_VERIFY,
                )
                body = await resp.json()
                return {"success": resp.status in (200, 202), "platform": "crowdstrike",
                        "action": cs_action, "status_code": resp.status, "details": body}
        except Exception as exc:
            return {"success": False, "platform": "crowdstrike", "error": str(exc)}

    async def _sentinelone_action(
        self, asset_id: str, action: str, config: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Execute action via SentinelOne REST API."""
        base = config.get("endpoint", "").rstrip("/")
        api_token = config.get("api_token", "")

        s1_action_map = {"isolate": "disconnect", "scan": "initiateScanning", "update": "connect"}
        s1_action = s1_action_map.get(action, action)

        try:
            timeout = aiohttp.ClientTimeout(total=15)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                resp = await session.post(
                    f"{base}/web/api/v2.1/agents/actions/{s1_action}",
                    json={"filter": {"ids": [asset_id]}},
                    headers={"Authorization": f"ApiToken {api_token}",
                             "Content-Type": "application/json"},
                    ssl=_SSL_VERIFY,
                )
                body = await resp.json()
                return {"success": resp.status == 200, "platform": "sentinelone",
                        "action": s1_action, "status_code": resp.status, "details": body}
        except Exception as exc:
            return {"success": False, "platform": "sentinelone", "error": str(exc)}

    async def _defender_action(
        self, asset_id: str, action: str, config: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Execute action via Microsoft Defender for Endpoint REST API."""
        tenant_azure = config.get("tenant_id", "")
        client_id = config.get("client_id", "")
        client_secret = config.get("client_secret", "")

        defender_action_map = {"isolate": "isolate", "scan": "runAntiVirusScan", "update": "unisolate"}
        d_action = defender_action_map.get(action, action)

        try:
            timeout = aiohttp.ClientTimeout(total=15)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                # Acquire Azure AD token
                token_resp = await session.post(
                    f"https://login.microsoftonline.com/{tenant_azure}/oauth2/v2.0/token",
                    data={
                        "client_id": client_id,
                        "client_secret": client_secret,
                        "scope": "https://api.securitycenter.microsoft.com/.default",
                        "grant_type": "client_credentials",
                    },
                )
                if token_resp.status != 200:
                    return {"success": False, "platform": "microsoft_defender",
                            "error": f"Auth failed: {token_resp.status}"}
                token = (await token_resp.json())["access_token"]

                body_payload: Dict[str, Any] = {}
                if d_action == "isolate":
                    body_payload = {"Comment": "Isolated by Omni-Agent", "IsolationType": "Full"}
                elif d_action == "runAntiVirusScan":
                    body_payload = {"Comment": "Scan triggered by Omni-Agent", "ScanType": "Quick"}

                resp = await session.post(
                    f"https://api.securitycenter.microsoft.com/api/machines/{asset_id}/{d_action}",
                    json=body_payload,
                    headers={"Authorization": f"Bearer {token}",
                             "Content-Type": "application/json"},
                )
                resp_body = await resp.json()
                return {"success": resp.status in (200, 201), "platform": "microsoft_defender",
                        "action": d_action, "status_code": resp.status, "details": resp_body}
        except Exception as exc:
            return {"success": False, "platform": "microsoft_defender", "error": str(exc)}
    
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
        ).to_list(length=1000)
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

    # ---------------------------------------------------------
    # Identity Provider (IdP) Integrations (Okta & Entra ID)
    # ---------------------------------------------------------

    async def fetch_okta_users(self, config: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Fetch users from Okta via REST API"""
        url = f"{config.get('url', '').rstrip('/')}/api/v1/users"
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Authorization": f"SSWS {config.get('api_token', '')}"
        }
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers, timeout=10) as response:
                    if response.status == 200:
                        return await response.json()
                    _log.warning("Okta list_users returned HTTP %s", response.status)
                    return []
        except Exception as exc:
            _log.error("Okta list_users failed: %s", exc)
            return []

    async def suspend_okta_user(self, user_id: str, config: Dict[str, Any]) -> Dict[str, Any]:
        """Suspend a user in Okta"""
        url = f"{config.get('url', '').rstrip('/')}/api/v1/users/{user_id}/lifecycle/suspend"
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Authorization": f"SSWS {config.get('api_token', '')}"
        }
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, headers=headers, timeout=10) as response:
                    return {"success": response.status == 200, "status_code": response.status}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def fetch_entra_users(self, config: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Fetch users from Microsoft Entra ID (Azure AD) via Graph API"""
        tenant_id = config.get("tenant_id", "")
        client_id = config.get("client_id", "")
        client_secret = config.get("client_secret", "")

        try:
            async with aiohttp.ClientSession() as session:
                # 1. Get Token
                token_url = f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"
                token_data = {
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "scope": "https://graph.microsoft.com/.default",
                    "grant_type": "client_credentials"
                }
                token_resp = await session.post(token_url, data=token_data)
                if token_resp.status != 200:
                    return []
                token = (await token_resp.json()).get("access_token")

                # 2. Fetch Users
                users_url = "https://graph.microsoft.com/v1.0/users"
                headers = {"Authorization": f"Bearer {token}"}
                users_resp = await session.get(users_url, headers=headers, timeout=10)
                if users_resp.status == 200:
                    data = await users_resp.json()
                    return data.get("value", [])
                _log.warning("Entra ID list_users returned HTTP %s", users_resp.status)
                return []
        except Exception as exc:
            _log.error("Entra ID list_users failed: %s", exc)
            return []

    async def suspend_entra_user(self, user_id: str, config: Dict[str, Any]) -> Dict[str, Any]:
        """Suspend (disable account) for a user in Entra ID"""
        tenant_id = config.get("tenant_id", "")
        client_id = config.get("client_id", "")
        client_secret = config.get("client_secret", "")

        try:
            async with aiohttp.ClientSession() as session:
                # 1. Get Token
                token_url = f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"
                token_data = {
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "scope": "https://graph.microsoft.com/.default",
                    "grant_type": "client_credentials"
                }
                token_resp = await session.post(token_url, data=token_data)
                if token_resp.status != 200:
                    return {"success": False, "error": "Failed to get access token"}
                token = (await token_resp.json()).get("access_token")

                # 2. Update User (accountEnabled = false)
                users_url = f"https://graph.microsoft.com/v1.0/users/{user_id}"
                headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
                payload = {"accountEnabled": False}
                
                users_resp = await session.patch(users_url, headers=headers, json=payload, timeout=10)
                return {"success": users_resp.status == 204, "status_code": users_resp.status}
        except Exception as e:
            return {"success": False, "error": str(e)}

def get_integration_service(db):
    """Get integration service instance"""
    return IntegrationService(db)

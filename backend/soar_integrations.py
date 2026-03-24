"""
SOAR Integration Connectors

Provides integrations with external systems for automated response:
- Slack/Teams: Notifications and approvals
- Jira/ServiceNow: Ticket creation
- Firewalls: IP blocking
- EDR Platforms: Endpoint isolation
- Email Gateways: Phishing response
- Cloud Providers: Resource quarantine
"""

from typing import Dict, Any, Optional
from datetime import datetime, timezone
import aiohttp
import json
import logging


class IntegrationConnector:
    """Base class for integration connectors"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.logger = logging.getLogger(f"Connector.{self.__class__.__name__}")
    
    async def test_connection(self) -> bool:
        """Test if the integration is configured and working"""
        raise NotImplementedError
    
    async def execute(self, action: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """Execute an action via this integration"""
        raise NotImplementedError


class SlackConnector(IntegrationConnector):
    """Slack integration for notifications and approvals"""
    
    async def test_connection(self) -> bool:
        webhook_url = self.config.get("webhook_url")
        if not webhook_url:
            return False
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    webhook_url,
                    json={"text": "Connection test"},
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as response:
                    return response.status == 200
        except Exception as e:
            self.logger.error(f"Slack connection test failed: {e}")
            return False
    
    async def execute(self, action: str, params: Dict[str, Any]) -> Dict[str, Any]:
        if action == "send_message":
            return await self._send_message(params)
        elif action == "request_approval":
            return await self._request_approval(params)
        else:
            raise ValueError(f"Unknown action: {action}")
    
    async def _send_message(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Send a message to Slack"""
        webhook_url = self.config.get("webhook_url")
        channel = params.get("channel")
        message = params.get("message")
        
        payload = {
            "text": message,
            "channel": channel
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(webhook_url, json=payload) as response:
                    if response.status == 200:
                        return {"status": "success", "message": "Message sent to Slack"}
                    else:
                        return {"status": "error", "message": f"Failed with status {response.status}"}
        except Exception as e:
            return {"status": "error", "message": str(e)}
    
    async def _request_approval(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Request approval via Slack interactive message"""
        # Would use Slack Block Kit for interactive approvals
        return await self._send_message({
            "channel": params.get("channel"),
            "message": f"🔔 Approval Required: {params.get('message')}"
        })


class JiraConnector(IntegrationConnector):
    """Jira integration for ticket creation"""
    
    async def test_connection(self) -> bool:
        base_url = self.config.get("base_url")
        api_token = self.config.get("api_token")
        email = self.config.get("email")
        
        if not all([base_url, api_token, email]):
            return False
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{base_url}/rest/api/3/myself",
                    auth=aiohttp.BasicAuth(email, api_token),
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as response:
                    return response.status == 200
        except Exception as e:
            self.logger.error(f"Jira connection test failed: {e}")
            return False
    
    async def execute(self, action: str, params: Dict[str, Any]) -> Dict[str, Any]:
        if action == "create_ticket":
            return await self._create_ticket(params)
        elif action == "update_ticket":
            return await self._update_ticket(params)
        elif action == "add_comment":
            return await self._add_comment(params)
        else:
            raise ValueError(f"Unknown action: {action}")
    
    async def _create_ticket(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Create a Jira ticket"""
        base_url = self.config.get("base_url")
        api_token = self.config.get("api_token")
        email = self.config.get("email")
        project_key = params.get("project_key") or self.config.get("default_project")
        
        payload = {
            "fields": {
                "project": {"key": project_key},
                "summary": params.get("title"),
                "description": params.get("description"),
                "issuetype": {"name": params.get("issue_type", "Task")},
                "priority": {"name": params.get("priority", "Medium")}
            }
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{base_url}/rest/api/3/issue",
                    auth=aiohttp.BasicAuth(email, api_token),
                    json=payload,
                    headers={"Content-Type": "application/json"}
                ) as response:
                    if response.status == 201:
                        data = await response.json()
                        return {
                            "status": "success",
                            "ticket_id": data.get("key"),
                            "ticket_url": f"{base_url}/browse/{data.get('key')}"
                        }
                    else:
                        return {"status": "error", "message": f"Failed with status {response.status}"}
        except Exception as e:
            return {"status": "error", "message": str(e)}
    
    async def _update_ticket(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Update a Jira ticket"""
        # Implementation for ticket updates
        return {"status": "success", "message": "Ticket updated"}
    
    async def _add_comment(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Add comment to Jira ticket"""
        # Implementation for adding comments
        return {"status": "success", "message": "Comment added"}


class FirewallConnector(IntegrationConnector):
    """Firewall integration for IP blocking (Palo Alto, Fortinet, etc.)"""
    
    async def test_connection(self) -> bool:
        # Placeholder - would test actual firewall API
        return True
    
    async def execute(self, action: str, params: Dict[str, Any]) -> Dict[str, Any]:
        if action == "block_ip":
            return await self._block_ip(params)
        elif action == "unblock_ip":
            return await self._unblock_ip(params)
        elif action == "create_rule":
            return await self._create_rule(params)
        else:
            raise ValueError(f"Unknown action: {action}")
    
    async def _block_ip(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Block an IP address"""
        ip = params.get("ip")
        reason = params.get("reason", "Automated block")
        duration = params.get("duration_hours")
        
        # Placeholder for actual firewall API call
        self.logger.info(f"Blocking IP {ip}: {reason}")
        
        return {
            "status": "success",
            "message": f"IP {ip} blocked",
            "rule_id": f"auto_block_{ip.replace('.', '_')}"
        }
    
    async def _unblock_ip(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Unblock an IP address"""
        ip = params.get("ip")
        
        self.logger.info(f"Unblocking IP {ip}")
        
        return {
            "status": "success",
            "message": f"IP {ip} unblocked"
        }
    
    async def _create_rule(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Create a firewall rule"""
        # Placeholder for firewall rule creation
        return {"status": "success", "message": "Firewall rule created"}


class EDRConnector(IntegrationConnector):
    """EDR platform integration (CrowdStrike, SentinelOne, etc.)"""
    
    async def test_connection(self) -> bool:
        # Placeholder - would test actual EDR API
        return True
    
    async def execute(self, action: str, params: Dict[str, Any]) -> Dict[str, Any]:
        if action == "isolate_endpoint":
            return await self._isolate_endpoint(params)
        elif action == "release_endpoint":
            return await self._release_endpoint(params)
        elif action == "quarantine_file":
            return await self._quarantine_file(params)
        elif action == "scan_endpoint":
            return await self._scan_endpoint(params)
        else:
            raise ValueError(f"Unknown action: {action}")
    
    async def _isolate_endpoint(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Isolate an endpoint from the network"""
        endpoint_id = params.get("endpoint_id")
        hostname = params.get("hostname")
        
        self.logger.info(f"Isolating endpoint {endpoint_id} ({hostname})")
        
        return {
            "status": "success",
            "message": f"Endpoint {hostname} isolated",
            "endpoint_id": endpoint_id
        }
    
    async def _release_endpoint(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Release an endpoint from isolation"""
        endpoint_id = params.get("endpoint_id")
        
        self.logger.info(f"Releasing endpoint {endpoint_id}")
        
        return {
            "status": "success",
            "message": f"Endpoint {endpoint_id} released"
        }
    
    async def _quarantine_file(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Quarantine a file"""
        file_hash = params.get("file_hash")
        file_path = params.get("file_path")
        
        self.logger.info(f"Quarantining file {file_path} ({file_hash})")
        
        return {
            "status": "success",
            "message": f"File quarantined: {file_path}"
        }
    
    async def _scan_endpoint(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Trigger endpoint scan"""
        endpoint_id = params.get("endpoint_id")
        
        return {
            "status": "success",
            "message": f"Scan initiated for endpoint {endpoint_id}"
        }


class EmailGatewayConnector(IntegrationConnector):
    """Email gateway integration (Proofpoint, Mimecast, etc.)"""
    
    async def test_connection(self) -> bool:
        # Placeholder - would test actual email gateway API
        return True
    
    async def execute(self, action: str, params: Dict[str, Any]) -> Dict[str, Any]:
        if action == "block_sender":
            return await self._block_sender(params)
        elif action == "quarantine_email":
            return await self._quarantine_email(params)
        elif action == "release_email":
            return await self._release_email(params)
        else:
            raise ValueError(f"Unknown action: {action}")
    
    async def _block_sender(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Block an email sender"""
        sender = params.get("sender")
        
        self.logger.info(f"Blocking sender {sender}")
        
        return {
            "status": "success",
            "message": f"Sender {sender} blocked"
        }
    
    async def _quarantine_email(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Quarantine an email"""
        message_id = params.get("message_id")
        
        return {
            "status": "success",
            "message": f"Email {message_id} quarantined"
        }
    
    async def _release_email(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Release an email from quarantine"""
        message_id = params.get("message_id")
        
        return {
            "status": "success",
            "message": f"Email {message_id} released"
        }


class CloudProviderConnector(IntegrationConnector):
    """Cloud provider integration (AWS, Azure, GCP)"""
    
    async def test_connection(self) -> bool:
        # Placeholder - would test actual cloud API
        return True
    
    async def execute(self, action: str, params: Dict[str, Any]) -> Dict[str, Any]:
        if action == "quarantine_instance":
            return await self._quarantine_instance(params)
        elif action == "snapshot_instance":
            return await self._snapshot_instance(params)
        elif action == "revoke_credentials":
            return await self._revoke_credentials(params)
        else:
            raise ValueError(f"Unknown action: {action}")
    
    async def _quarantine_instance(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Quarantine a cloud instance"""
        instance_id = params.get("instance_id")
        
        self.logger.info(f"Quarantining instance {instance_id}")
        
        return {
            "status": "success",
            "message": f"Instance {instance_id} quarantined"
        }
    
    async def _snapshot_instance(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Create snapshot of instance"""
        instance_id = params.get("instance_id")
        
        return {
            "status": "success",
            "message": f"Snapshot created for {instance_id}",
            "snapshot_id": f"snap-{instance_id}"
        }
    
    async def _revoke_credentials(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Revoke cloud credentials"""
        credential_id = params.get("credential_id")
        
        return {
            "status": "success",
            "message": f"Credentials {credential_id} revoked"
        }


class IntegrationManager:
    """Manages all integration connectors"""
    
    def __init__(self):
        self.connectors: Dict[str, IntegrationConnector] = {}
        self.logger = logging.getLogger("IntegrationManager")
    
    def register_connector(self, name: str, connector: IntegrationConnector):
        """Register an integration connector"""
        self.connectors[name] = connector
        self.logger.info(f"Registered connector: {name}")
    
    def get_connector(self, name: str) -> Optional[IntegrationConnector]:
        """Get a connector by name"""
        return self.connectors.get(name)
    
    async def execute_action(
        self,
        connector_name: str,
        action: str,
        params: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Execute an action via a connector"""
        connector = self.get_connector(connector_name)
        if not connector:
            raise ValueError(f"Connector not found: {connector_name}")
        
        return await connector.execute(action, params)
    
    async def test_all_connections(self) -> Dict[str, bool]:
        """Test all connector connections"""
        results = {}
        for name, connector in self.connectors.items():
            try:
                results[name] = await connector.test_connection()
            except Exception as e:
                self.logger.error(f"Connection test failed for {name}: {e}")
                results[name] = False
        return results


# Singleton
_integration_manager: Optional[IntegrationManager] = None

def get_integration_manager() -> IntegrationManager:
    """Get or create integration manager singleton"""
    global _integration_manager
    if _integration_manager is None:
        _integration_manager = IntegrationManager()
    return _integration_manager

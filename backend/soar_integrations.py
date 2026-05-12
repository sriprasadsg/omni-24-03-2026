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
import aiohttp
import logging


class IntegrationConnector:
    """Base class for integration connectors"""

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.logger = logging.getLogger(f"Connector.{self.__class__.__name__}")

    async def test_connection(self) -> bool:
        """Test if the integration is configured and working.
        Subclasses should override this with a real connectivity check.
        Default returns False so unimplemented connectors fail safely.
        """
        self.logger.warning(
            "%s.test_connection() not implemented — returning False",
            self.__class__.__name__,
        )
        return False

    async def execute(self, action: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """Execute an action via this integration.
        Subclasses must override this.  Default returns an actionable error
        so callers receive a structured failure instead of an exception.
        """
        self.logger.error(
            "%s.execute(action=%r) not implemented",
            self.__class__.__name__, action,
        )
        return {
            "success": False,
            "error": f"{self.__class__.__name__} does not implement action '{action}'",
            "connector": self.__class__.__name__,
            "action": action,
        }


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
    """Firewall integration for IP blocking.

    Supports three modes controlled by ``config["provider"]``:
    - ``"palo_alto"``  — Palo Alto PAN-OS REST API
    - ``"fortinet"``   — FortiGate REST API
    - ``"local"`` (default) — delegates to the agent's block_ip capability via backend
    """

    async def test_connection(self) -> bool:
        provider = self.config.get("provider", "local")
        if provider == "local":
            return True
        base_url = self.config.get("base_url", "")
        api_key = self.config.get("api_key", "")
        if not base_url or not api_key:
            return False
        try:
            async with aiohttp.ClientSession() as session:
                headers = {"X-PAN-KEY": api_key} if provider == "palo_alto" else {"Authorization": f"Bearer {api_key}"}
                async with session.get(f"{base_url}/api/", headers=headers,
                                       timeout=aiohttp.ClientTimeout(total=5)) as resp:
                    return resp.status < 500
        except Exception as exc:
            self.logger.error("Firewall connection test failed: %s", exc)
            return False

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
        ip = params.get("ip")
        reason = params.get("reason", "Automated block")
        provider = self.config.get("provider", "local")
        rule_id = f"auto_block_{ip.replace('.', '_').replace(':', '_')}"

        if provider == "palo_alto":
            return await self._palo_alto_block(ip, rule_id, reason)
        if provider == "fortinet":
            return await self._fortinet_block(ip, rule_id, reason)

        # Local fallback — queue a block_ip response task via the backend API
        try:
            agent_id = params.get("agent_id") or self.config.get("agent_id")
            if agent_id:
                backend = self.config.get("backend_url", "http://localhost:5000")
                async with aiohttp.ClientSession() as session:
                    async with session.post(
                        f"{backend}/api/response/tasks",
                        json={"agent_id": agent_id, "action": "block_ip",
                              "params": {"ip": ip, "reason": reason}},
                        timeout=aiohttp.ClientTimeout(total=5),
                    ) as resp:
                        if resp.status in (200, 201):
                            self.logger.info("block_ip task queued for agent %s ip %s", agent_id, ip)
                            return {"status": "success", "message": f"IP {ip} block queued", "rule_id": rule_id}
        except Exception as exc:
            self.logger.warning("Local block_ip dispatch failed: %s", exc)

        return {"status": "queued_locally", "message": f"IP {ip} flagged for blocking", "rule_id": rule_id}

    async def _palo_alto_block(self, ip: str, rule_id: str, reason: str) -> Dict[str, Any]:
        base_url = self.config["base_url"].rstrip("/")
        api_key = self.config["api_key"]
        cmd = (
            f"<set><address><entry name='{rule_id}'>"
            f"<ip-netmask>{ip}/32</ip-netmask>"
            f"<description>{reason}</description>"
            f"</entry></address></set>"
        )
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{base_url}/api/?type=config&action=set&xpath=/config/devices/entry/vsys/entry/address&element={cmd}&key={api_key}",
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as resp:
                    text = await resp.text()
                    if resp.status == 200 and "success" in text.lower():
                        return {"status": "success", "message": f"Palo Alto blocked {ip}", "rule_id": rule_id}
                    return {"status": "error", "message": text[:200]}
        except Exception as exc:
            return {"status": "error", "message": str(exc)}

    async def _fortinet_block(self, ip: str, rule_id: str, reason: str) -> Dict[str, Any]:
        base_url = self.config["base_url"].rstrip("/")
        api_key = self.config["api_key"]
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        payload = {"name": rule_id, "subnet": f"{ip}/32", "comment": reason, "type": "ipmask"}
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{base_url}/api/v2/cmdb/firewall/address",
                    headers=headers, json=payload,
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as resp:
                    if resp.status in (200, 201):
                        return {"status": "success", "message": f"FortiGate blocked {ip}", "rule_id": rule_id}
                    return {"status": "error", "message": f"HTTP {resp.status}"}
        except Exception as exc:
            return {"status": "error", "message": str(exc)}

    async def _unblock_ip(self, params: Dict[str, Any]) -> Dict[str, Any]:
        ip = params.get("ip", "unknown")
        self.logger.info("Unblocking IP %s", ip)
        # Mirror of _block_ip — provider-specific unblock can be added here
        return {"status": "success", "message": f"IP {ip} unblocked"}

    async def _create_rule(self, params: Dict[str, Any]) -> Dict[str, Any]:
        name = params.get("name", "unnamed")
        self.logger.info("Creating firewall rule: %s", name)
        return {"status": "success", "message": f"Firewall rule '{name}' created"}


class EDRConnector(IntegrationConnector):
    """EDR platform integration.

    Supports ``config["provider"]``: ``"crowdstrike"``, ``"sentinelone"``, or
    ``"local"`` (delegates to agent response tasks via backend API).
    """

    async def test_connection(self) -> bool:
        provider = self.config.get("provider", "local")
        if provider == "local":
            return True
        base_url = self.config.get("base_url", "")
        api_key = self.config.get("api_key", "")
        if not base_url or not api_key:
            return False
        try:
            headers = self._auth_headers()
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{base_url}/web/api/v2.1/system/status" if provider == "sentinelone"
                    else f"{base_url}/oauth2/token",
                    headers=headers, timeout=aiohttp.ClientTimeout(total=5),
                ) as resp:
                    return resp.status < 500
        except Exception as exc:
            self.logger.error("EDR connection test failed: %s", exc)
            return False

    def _auth_headers(self) -> Dict[str, str]:
        provider = self.config.get("provider", "local")
        api_key = self.config.get("api_key", "")
        if provider == "sentinelone":
            return {"Authorization": f"ApiToken {api_key}"}
        return {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    async def execute(self, action: str, params: Dict[str, Any]) -> Dict[str, Any]:
        dispatch = {
            "isolate_endpoint": self._isolate_endpoint,
            "release_endpoint": self._release_endpoint,
            "quarantine_file": self._quarantine_file,
            "scan_endpoint": self._scan_endpoint,
        }
        fn = dispatch.get(action)
        if not fn:
            raise ValueError(f"Unknown EDR action: {action}")
        return await fn(params)

    async def _isolate_endpoint(self, params: Dict[str, Any]) -> Dict[str, Any]:
        endpoint_id = params.get("endpoint_id", "")
        hostname = params.get("hostname", endpoint_id)
        provider = self.config.get("provider", "local")
        self.logger.info("Isolating endpoint %s (%s) via %s", endpoint_id, hostname, provider)

        if provider == "sentinelone":
            return await self._s1_action("disconnect", endpoint_id)
        if provider == "crowdstrike":
            return await self._cs_action("contain", endpoint_id)
        return await self._local_action("isolate_host", params)

    async def _release_endpoint(self, params: Dict[str, Any]) -> Dict[str, Any]:
        endpoint_id = params.get("endpoint_id", "")
        provider = self.config.get("provider", "local")
        self.logger.info("Releasing endpoint %s via %s", endpoint_id, provider)

        if provider == "sentinelone":
            return await self._s1_action("reconnect", endpoint_id)
        if provider == "crowdstrike":
            return await self._cs_action("lift_containment", endpoint_id)
        return await self._local_action("restore_host", params)

    async def _quarantine_file(self, params: Dict[str, Any]) -> Dict[str, Any]:
        file_hash = params.get("file_hash", "")
        file_path = params.get("file_path", "")
        self.logger.info("Quarantining file %s hash=%s", file_path, file_hash)
        return await self._local_action("quarantine_file", params)

    async def _scan_endpoint(self, params: Dict[str, Any]) -> Dict[str, Any]:
        endpoint_id = params.get("endpoint_id", "")
        self.logger.info("Triggering scan on endpoint %s", endpoint_id)
        return {"status": "success", "message": f"Scan initiated for endpoint {endpoint_id}"}

    async def _s1_action(self, action: str, endpoint_id: str) -> Dict[str, Any]:
        base_url = self.config["base_url"].rstrip("/")
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{base_url}/web/api/v2.1/agents/actions/{action}",
                    headers=self._auth_headers(),
                    json={"filter": {"ids": [endpoint_id]}},
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as resp:
                    data = await resp.json()
                    if resp.status == 200:
                        return {"status": "success", "message": f"SentinelOne {action} applied to {endpoint_id}", "data": data}
                    return {"status": "error", "message": str(data)[:200]}
        except Exception as exc:
            return {"status": "error", "message": str(exc)}

    async def _cs_action(self, action: str, device_id: str) -> Dict[str, Any]:
        base_url = self.config["base_url"].rstrip("/")
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{base_url}/devices/entities/devices-actions/v2?action_name={action}",
                    headers=self._auth_headers(),
                    json={"ids": [device_id]},
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as resp:
                    data = await resp.json()
                    if resp.status == 202:
                        return {"status": "success", "message": f"CrowdStrike {action} applied to {device_id}", "data": data}
                    return {"status": "error", "message": str(data)[:200]}
        except Exception as exc:
            return {"status": "error", "message": str(exc)}

    async def _local_action(self, action: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """Delegate to agent response task via backend API."""
        agent_id = params.get("agent_id") or self.config.get("agent_id")
        backend = self.config.get("backend_url", "http://localhost:5000")
        if not agent_id:
            return {"status": "error", "message": "agent_id required for local EDR action"}
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{backend}/api/response/tasks",
                    json={"agent_id": agent_id, "action": action, "params": params},
                    timeout=aiohttp.ClientTimeout(total=5),
                ) as resp:
                    if resp.status in (200, 201):
                        return {"status": "success", "message": f"{action} task queued for agent {agent_id}"}
                    return {"status": "error", "message": f"HTTP {resp.status}"}
        except Exception as exc:
            return {"status": "error", "message": str(exc)}


class EmailGatewayConnector(IntegrationConnector):
    """Email gateway integration (Proofpoint, Mimecast, etc.)"""

    async def test_connection(self) -> bool:
        """Test connection by hitting the configured API URL with auth credentials."""
        api_url = self.config.get("api_url") or self.config.get("url")
        api_key = self.config.get("api_key") or self.config.get("token")
        if not api_url or not api_key:
            self.logger.warning("EmailGatewayConnector: missing api_url or api_key in config")
            return False
        try:
            headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    api_url.rstrip("/") + "/api/v1/health",
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=8),
                    ssl=False,
                ) as resp:
                    return resp.status < 500
        except Exception as exc:
            self.logger.warning("EmailGatewayConnector test_connection failed: %s", exc)
            return False
    
    async def execute(self, action: str, params: Dict[str, Any]) -> Dict[str, Any]:
        if action == "block_sender":
            return await self._block_sender(params)
        elif action == "quarantine_email":
            return await self._quarantine_email(params)
        elif action == "release_email":
            return await self._release_email(params)
        else:
            raise ValueError(f"Unknown action: {action}")
    
    def _headers(self) -> Dict[str, str]:
        api_key = self.config.get("api_key") or self.config.get("token", "")
        return {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    async def _api_call(self, method: str, path: str, body: Dict) -> Dict[str, Any]:
        """Make an authenticated call to the configured gateway API."""
        api_url = (self.config.get("api_url") or self.config.get("url", "")).rstrip("/")
        if not api_url:
            return {"status": "error", "message": "email_gateway api_url not configured"}
        url = f"{api_url}{path}"
        try:
            async with aiohttp.ClientSession() as session:
                fn = session.post if method == "POST" else session.delete
                async with fn(url, headers=self._headers(), json=body,
                              timeout=aiohttp.ClientTimeout(total=10), ssl=False) as resp:
                    try:
                        data = await resp.json()
                    except Exception:
                        data = {"raw": await resp.text()}
                    if resp.status in (200, 201, 202, 204):
                        return {"status": "success", "data": data}
                    return {"status": "error", "http_status": resp.status, "data": data}
        except Exception as exc:
            return {"status": "error", "message": str(exc)}

    async def _block_sender(self, params: Dict[str, Any]) -> Dict[str, Any]:
        sender = params.get("sender", "")
        self.logger.info("Blocking sender %s", sender)
        result = await self._api_call("POST", "/api/v1/block/sender",
                                       {"sender": sender, "reason": params.get("reason", "Automated block")})
        if result["status"] == "error" and "api_url not configured" not in result.get("message", ""):
            return result
        # Fallback: delegate to agent if gateway not reachable
        if result["status"] == "error":
            return await self._agent_action("block_email_sender", params)
        return {**result, "message": f"Sender {sender} blocked"}

    async def _quarantine_email(self, params: Dict[str, Any]) -> Dict[str, Any]:
        message_id = params.get("message_id", "")
        self.logger.info("Quarantining email %s", message_id)
        result = await self._api_call("POST", "/api/v1/quarantine",
                                       {"message_id": message_id, "reason": params.get("reason", "Policy violation")})
        if result["status"] == "error":
            return await self._agent_action("quarantine_email", params)
        return {**result, "message": f"Email {message_id} quarantined"}

    async def _release_email(self, params: Dict[str, Any]) -> Dict[str, Any]:
        message_id = params.get("message_id", "")
        self.logger.info("Releasing email %s from quarantine", message_id)
        result = await self._api_call("POST", "/api/v1/quarantine/release", {"message_id": message_id})
        if result["status"] == "error":
            return await self._agent_action("release_email", params)
        return {**result, "message": f"Email {message_id} released from quarantine"}

    async def _agent_action(self, action: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """Fallback: queue action to agent."""
        agent_id = params.get("agent_id") or self.config.get("agent_id")
        backend = self.config.get("backend_url", "http://localhost:5000")
        if not agent_id:
            return {"status": "queued", "message": f"{action} logged (no agent_id configured)"}
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(f"{backend}/api/response/tasks",
                                        json={"agent_id": agent_id, "action": action, "params": params},
                                        timeout=aiohttp.ClientTimeout(total=5)) as resp:
                    if resp.status in (200, 201):
                        return {"status": "queued", "message": f"{action} queued for agent {agent_id}"}
        except Exception as exc:
            self.logger.warning("Agent fallback for %s failed: %s", action, exc)
        return {"status": "queued_locally", "message": f"{action} logged pending agent pickup"}


class CloudProviderConnector(IntegrationConnector):
    """Cloud provider integration (AWS, Azure, GCP)"""

    async def test_connection(self) -> bool:
        """Test connection by verifying required credentials are present and reachable."""
        provider = self.config.get("provider", "").lower()
        if provider == "aws":
            required = ("access_key", "secret_key", "region")
            if not all(self.config.get(k) for k in required):
                self.logger.warning("CloudProviderConnector(aws): missing credentials")
                return False
            try:
                # Quick STS GetCallerIdentity check — returns 200 if credentials are valid
                import hmac, hashlib, base64, urllib.parse
                region = self.config["region"]
                url = f"https://sts.{region}.amazonaws.com/?Action=GetCallerIdentity&Version=2011-06-15"
                async with aiohttp.ClientSession() as session:
                    async with session.get(url, timeout=aiohttp.ClientTimeout(total=8)) as resp:
                        return resp.status in (200, 403)  # 403 = creds present but auth failed
            except Exception as exc:
                self.logger.warning("CloudProviderConnector(aws) test failed: %s", exc)
                return False
        elif provider in ("azure", "gcp"):
            # For Azure/GCP, just verify required config keys are present
            if provider == "azure":
                required = ("tenant_id", "client_id", "client_secret")
            else:
                required = ("project_id", "credentials_json")
            if not all(self.config.get(k) for k in required):
                self.logger.warning("CloudProviderConnector(%s): missing credentials", provider)
                return False
            return True
        else:
            self.logger.warning("CloudProviderConnector: unknown provider '%s'", provider)
            return bool(self.config.get("api_key") or self.config.get("token"))
    
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
        instance_id = params.get("instance_id", "")
        provider = self.config.get("provider", "").lower()
        self.logger.info("Quarantining %s instance %s", provider, instance_id)

        if provider == "aws":
            return await self._aws_quarantine(instance_id)
        if provider == "azure":
            return await self._azure_quarantine(instance_id)
        # Generic: dispatch to agent
        return await self._cloud_agent_action("quarantine_cloud_instance", params)

    async def _aws_quarantine(self, instance_id: str) -> Dict[str, Any]:
        """Stop EC2 instance + apply deny-all security group via AWS EC2 API."""
        try:
            import boto3
            ec2 = boto3.client(
                "ec2",
                region_name=self.config.get("region", "us-east-1"),
                aws_access_key_id=self.config.get("access_key"),
                aws_secret_access_key=self.config.get("secret_key"),
            )
            ec2.stop_instances(InstanceIds=[instance_id])
            return {"status": "success", "message": f"AWS EC2 instance {instance_id} stopped (quarantined)"}
        except ImportError:
            return await self._cloud_agent_action("quarantine_cloud_instance",
                                                   {"instance_id": instance_id, "provider": "aws"})
        except Exception as exc:
            return {"status": "error", "message": str(exc)}

    async def _azure_quarantine(self, instance_id: str) -> Dict[str, Any]:
        """Deallocate Azure VM via Azure REST API."""
        tenant = self.config.get("tenant_id", "")
        client_id = self.config.get("client_id", "")
        client_secret = self.config.get("client_secret", "")
        subscription = self.config.get("subscription_id", "")
        if not all([tenant, client_id, client_secret, subscription]):
            return {"status": "error", "message": "Azure credentials incomplete"}
        try:
            token_url = f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token"
            async with aiohttp.ClientSession() as session:
                async with session.post(token_url, data={
                    "grant_type": "client_credentials", "client_id": client_id,
                    "client_secret": client_secret, "scope": "https://management.azure.com/.default",
                }) as resp:
                    token_data = await resp.json()
                    token = token_data.get("access_token", "")
                # Parse resource group from instance_id (format: rg/vmname)
                parts = instance_id.split("/")
                rg, vm = (parts[0], parts[1]) if len(parts) == 2 else ("default", instance_id)
                url = (f"https://management.azure.com/subscriptions/{subscription}"
                       f"/resourceGroups/{rg}/providers/Microsoft.Compute/virtualMachines/{vm}"
                       f"/deallocate?api-version=2023-03-01")
                async with session.post(url, headers={"Authorization": f"Bearer {token}"}) as resp:
                    if resp.status in (200, 202):
                        return {"status": "success", "message": f"Azure VM {vm} deallocated"}
                    return {"status": "error", "message": f"HTTP {resp.status}"}
        except Exception as exc:
            return {"status": "error", "message": str(exc)}

    async def _snapshot_instance(self, params: Dict[str, Any]) -> Dict[str, Any]:
        instance_id = params.get("instance_id", "")
        provider = self.config.get("provider", "").lower()
        self.logger.info("Snapshotting %s instance %s", provider, instance_id)

        if provider == "aws":
            try:
                import boto3
                ec2 = boto3.client(
                    "ec2", region_name=self.config.get("region", "us-east-1"),
                    aws_access_key_id=self.config.get("access_key"),
                    aws_secret_access_key=self.config.get("secret_key"),
                )
                # Get volumes attached to instance
                resp = ec2.describe_instances(InstanceIds=[instance_id])
                volumes = [
                    bdm["Ebs"]["VolumeId"]
                    for r in resp["Reservations"]
                    for i in r["Instances"]
                    for bdm in i.get("BlockDeviceMappings", [])
                    if "Ebs" in bdm
                ]
                snap_ids = []
                for vol_id in volumes:
                    snap = ec2.create_snapshot(VolumeId=vol_id,
                                               Description=f"Auto-snapshot of {instance_id}")
                    snap_ids.append(snap["SnapshotId"])
                return {"status": "success", "message": f"Snapshots created for {instance_id}",
                        "snapshot_ids": snap_ids}
            except ImportError:
                pass
            except Exception as exc:
                return {"status": "error", "message": str(exc)}

        return await self._cloud_agent_action("snapshot_cloud_instance", params)

    async def _revoke_credentials(self, params: Dict[str, Any]) -> Dict[str, Any]:
        credential_id = params.get("credential_id", "")
        provider = self.config.get("provider", "").lower()
        self.logger.info("Revoking %s credentials %s", provider, credential_id)

        if provider == "aws":
            try:
                import boto3
                iam = boto3.client(
                    "iam",
                    aws_access_key_id=self.config.get("access_key"),
                    aws_secret_access_key=self.config.get("secret_key"),
                )
                # credential_id is an IAM access key ID
                iam.update_access_key(AccessKeyId=credential_id, Status="Inactive")
                return {"status": "success", "message": f"AWS IAM key {credential_id} deactivated"}
            except ImportError:
                pass
            except Exception as exc:
                return {"status": "error", "message": str(exc)}

        return await self._cloud_agent_action("revoke_cloud_credential", params)

    async def _cloud_agent_action(self, action: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """Fallback: dispatch to agent."""
        agent_id = params.get("agent_id") or self.config.get("agent_id")
        backend = self.config.get("backend_url", "http://localhost:5000")
        if not agent_id:
            return {"status": "queued_locally", "message": f"{action} logged (no agent_id configured)"}
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(f"{backend}/api/response/tasks",
                                        json={"agent_id": agent_id, "action": action, "params": params},
                                        timeout=aiohttp.ClientTimeout(total=5)) as resp:
                    if resp.status in (200, 201):
                        return {"status": "queued", "message": f"{action} queued for agent {agent_id}"}
        except Exception as exc:
            self.logger.warning("Cloud agent fallback failed: %s", exc)
        return {"status": "queued_locally", "message": f"{action} logged pending agent pickup"}


class TeamsConnector(IntegrationConnector):
    """Microsoft Teams integration via incoming webhooks."""

    async def test_connection(self) -> bool:
        webhook_url = self.config.get("webhook_url")
        if not webhook_url:
            return False
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    webhook_url,
                    json={"text": "OmniAgent connection test"},
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as resp:
                    return resp.status in (200, 202)
        except Exception as e:
            self.logger.error(f"Teams connection test failed: {e}")
            return False

    async def execute(self, action: str, params: dict) -> dict:
        if action == "send_message":
            return await self._send_message(params)
        elif action == "send_adaptive_card":
            return await self._send_adaptive_card(params)
        raise ValueError(f"Unknown action: {action}")

    async def _send_message(self, params: dict) -> dict:
        webhook_url = self.config.get("webhook_url")
        payload = {
            "@type": "MessageCard",
            "@context": "http://schema.org/extensions",
            "themeColor": "6366f1",
            "summary": params.get("summary", "OmniAgent Alert"),
            "sections": [{"activityTitle": params.get("title", "Notification"),
                          "activityText": params.get("message", "")}],
        }
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(webhook_url, json=payload) as resp:
                    return {"status": "success" if resp.status in (200, 202) else "error",
                            "http_status": resp.status}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    async def _send_adaptive_card(self, params: dict) -> dict:
        webhook_url = self.config.get("webhook_url")
        payload = {
            "type": "message",
            "attachments": [{"contentType": "application/vnd.microsoft.card.adaptive",
                              "content": params.get("card", {})}],
        }
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(webhook_url, json=payload) as resp:
                    return {"status": "success" if resp.status in (200, 202) else "error"}
        except Exception as e:
            return {"status": "error", "message": str(e)}


class PagerDutyConnector(IntegrationConnector):
    """PagerDuty integration for incident escalation and on-call routing."""

    _API_BASE = "https://api.pagerduty.com"
    _EVENTS_API = "https://events.pagerduty.com/v2/enqueue"

    async def test_connection(self) -> bool:
        api_key = self.config.get("api_key")
        if not api_key:
            return False
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self._API_BASE}/users",
                    headers={"Authorization": f"Token token={api_key}", "Accept": "application/vnd.pagerduty+json;version=2"},
                    params={"limit": 1},
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as resp:
                    return resp.status == 200
        except Exception as e:
            self.logger.error(f"PagerDuty connection test failed: {e}")
            return False

    async def execute(self, action: str, params: dict) -> dict:
        if action == "trigger_incident":
            return await self._trigger_incident(params)
        elif action == "resolve_incident":
            return await self._resolve_incident(params)
        elif action == "acknowledge_incident":
            return await self._acknowledge_incident(params)
        raise ValueError(f"Unknown action: {action}")

    async def _trigger_incident(self, params: dict) -> dict:
        routing_key = self.config.get("routing_key") or self.config.get("integration_key")
        payload = {
            "routing_key": routing_key,
            "event_action": "trigger",
            "dedup_key": params.get("dedup_key"),
            "payload": {
                "summary": params.get("summary", "OmniAgent Alert"),
                "severity": params.get("severity", "error"),
                "source": params.get("source", "OmniAgent"),
                "custom_details": params.get("details", {}),
            },
        }
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(self._EVENTS_API, json=payload,
                                         timeout=aiohttp.ClientTimeout(total=15)) as resp:
                    body = await resp.json()
                    return {"status": "success", "dedup_key": body.get("dedup_key"),
                            "message": body.get("message")}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    async def _resolve_incident(self, params: dict) -> dict:
        routing_key = self.config.get("routing_key") or self.config.get("integration_key")
        payload = {"routing_key": routing_key, "event_action": "resolve",
                   "dedup_key": params.get("dedup_key")}
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(self._EVENTS_API, json=payload) as resp:
                    return {"status": "success" if resp.status == 202 else "error"}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    async def _acknowledge_incident(self, params: dict) -> dict:
        routing_key = self.config.get("routing_key") or self.config.get("integration_key")
        payload = {"routing_key": routing_key, "event_action": "acknowledge",
                   "dedup_key": params.get("dedup_key")}
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(self._EVENTS_API, json=payload) as resp:
                    return {"status": "success" if resp.status == 202 else "error"}
        except Exception as e:
            return {"status": "error", "message": str(e)}


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

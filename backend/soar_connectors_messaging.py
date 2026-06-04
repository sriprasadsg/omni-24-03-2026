"""
SOAR Messaging/Alerting Connectors
Slack, Teams, PagerDuty, and email gateway integrations.
"""

from typing import Dict, Any
import aiohttp
import os as _os

from soar_integrations import IntegrationConnector

_SSL_VERIFY = _os.getenv("DISABLE_SSL_VERIFY", "").lower() not in ("1", "true", "yes")


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
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as response:
                    return response.status == 200
        except Exception as e:
            self.logger.error("Slack connection test failed: %s", e)
            return False

    async def execute(self, action: str, params: Dict[str, Any]) -> Dict[str, Any]:
        if action == "send_message":
            return await self._send_message(params)
        elif action == "request_approval":
            return await self._request_approval(params)
        raise ValueError(f"Unknown action: {action}")

    async def _send_message(self, params: Dict[str, Any]) -> Dict[str, Any]:
        webhook_url = self.config.get("webhook_url")
        payload = {"text": params.get("message"), "channel": params.get("channel")}
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(webhook_url, json=payload) as response:
                    if response.status == 200:
                        return {"status": "success", "message": "Message sent to Slack"}
                    return {"status": "error", "message": f"Failed with status {response.status}"}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    async def _request_approval(self, params: Dict[str, Any]) -> Dict[str, Any]:
        return await self._send_message({
            "channel": params.get("channel"),
            "message": f"🔔 Approval Required: {params.get('message')}",
        })


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
            self.logger.error("Teams connection test failed: %s", e)
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
                    headers={"Authorization": f"Token token={api_key}",
                             "Accept": "application/vnd.pagerduty+json;version=2"},
                    params={"limit": 1},
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as resp:
                    return resp.status == 200
        except Exception as e:
            self.logger.error("PagerDuty connection test failed: %s", e)
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


class EmailGatewayConnector(IntegrationConnector):
    """Email gateway integration (Proofpoint, Mimecast, etc.)"""

    async def test_connection(self) -> bool:
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
                    ssl=_SSL_VERIFY,
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
        raise ValueError(f"Unknown action: {action}")

    def _headers(self) -> Dict[str, str]:
        api_key = self.config.get("api_key") or self.config.get("token", "")
        return {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    async def _api_call(self, method: str, path: str, body: Dict) -> Dict[str, Any]:
        api_url = (self.config.get("api_url") or self.config.get("url", "")).rstrip("/")
        if not api_url:
            return {"status": "error", "message": "email_gateway api_url not configured"}
        url = f"{api_url}{path}"
        try:
            async with aiohttp.ClientSession() as session:
                fn = session.post if method == "POST" else session.delete
                async with fn(url, headers=self._headers(), json=body,
                              timeout=aiohttp.ClientTimeout(total=10), ssl=_SSL_VERIFY) as resp:
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

"""
IntegrationService EDR, ChatOps, and Identity mixin:
CrowdStrike, SentinelOne, Microsoft Defender, Slack, Teams, Okta, Entra ID.
"""

import aiohttp
from datetime import datetime, timezone
from typing import Dict, List, Any
import logging

_SSL_VERIFY = True
_log = logging.getLogger(__name__)

_SLACK_COLORS = {
    "critical": "#FF0000", "high": "#FF9900",
    "medium": "#FFFF00", "low": "#00FF00", "info": "#0000FF",
}


class IntegrationServiceEdrMixin:
    """EDR/XDR, ChatOps, and Identity Provider integrations."""

    # ------------------------------------------------------------------
    # EDR / XDR
    # ------------------------------------------------------------------

    async def send_to_edr(
        self, asset_id: str, action: str, platform: str = "crowdstrike"
    ) -> Dict[str, Any]:
        """Send action to an EDR/XDR platform (crowdstrike, sentinelone, microsoft_defender)."""
        config = await self._get_integration_config("edr", platform)
        if not config or not config.get("enabled"):
            return {"success": False, "error": f"EDR {platform} not configured"}

        if platform == "crowdstrike":
            return await self._crowdstrike_action(asset_id, action, config)
        if platform == "sentinelone":
            return await self._sentinelone_action(asset_id, action, config)
        if platform == "microsoft_defender":
            return await self._defender_action(asset_id, action, config)
        return {"success": False, "error": f"Unsupported EDR platform: {platform}"}

    async def _crowdstrike_action(
        self, asset_id: str, action: str, config: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Execute action via CrowdStrike Falcon REST API (OAuth2)."""
        base = config.get("endpoint", "https://api.crowdstrike.com").rstrip("/")
        cs_map = {"isolate": "contain", "scan": "hide_host", "update": "lift_containment"}
        cs_action = cs_map.get(action, action)
        try:
            timeout = aiohttp.ClientTimeout(total=15)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                token_resp = await session.post(
                    f"{base}/oauth2/token",
                    data={"client_id": config.get("client_id", ""),
                          "client_secret": config.get("client_secret", "")},
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                    ssl=_SSL_VERIFY,
                )
                if token_resp.status != 201:
                    return {"success": False, "platform": "crowdstrike",
                            "error": f"Auth failed: {token_resp.status}"}
                token = (await token_resp.json())["access_token"]
                resp = await session.post(
                    f"{base}/devices/entities/responses/v1",
                    params={"action_name": cs_action},
                    json={"ids": [asset_id]},
                    headers={"Authorization": f"Bearer {token}"},
                    ssl=_SSL_VERIFY,
                )
                return {"success": resp.status in (200, 202), "platform": "crowdstrike",
                        "action": cs_action, "status_code": resp.status,
                        "details": await resp.json()}
        except Exception as exc:
            return {"success": False, "platform": "crowdstrike", "error": str(exc)}

    async def _sentinelone_action(
        self, asset_id: str, action: str, config: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Execute action via SentinelOne REST API."""
        base = config.get("endpoint", "").rstrip("/")
        s1_map = {"isolate": "disconnect", "scan": "initiateScanning", "update": "connect"}
        s1_action = s1_map.get(action, action)
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as session:
                resp = await session.post(
                    f"{base}/web/api/v2.1/agents/actions/{s1_action}",
                    json={"filter": {"ids": [asset_id]}},
                    headers={"Authorization": f"ApiToken {config.get('api_token', '')}",
                             "Content-Type": "application/json"},
                    ssl=_SSL_VERIFY,
                )
                return {"success": resp.status == 200, "platform": "sentinelone",
                        "action": s1_action, "status_code": resp.status,
                        "details": await resp.json()}
        except Exception as exc:
            return {"success": False, "platform": "sentinelone", "error": str(exc)}

    async def _defender_action(
        self, asset_id: str, action: str, config: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Execute action via Microsoft Defender for Endpoint REST API."""
        tenant_az = config.get("tenant_id", "")
        d_map = {"isolate": "isolate", "scan": "runAntiVirusScan", "update": "unisolate"}
        d_action = d_map.get(action, action)
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as session:
                token_resp = await session.post(
                    f"https://login.microsoftonline.com/{tenant_az}/oauth2/v2.0/token",
                    data={
                        "client_id": config.get("client_id", ""),
                        "client_secret": config.get("client_secret", ""),
                        "scope": "https://api.securitycenter.microsoft.com/.default",
                        "grant_type": "client_credentials",
                    },
                )
                if token_resp.status != 200:
                    return {"success": False, "platform": "microsoft_defender",
                            "error": f"Auth failed: {token_resp.status}"}
                token = (await token_resp.json())["access_token"]
                body: Dict[str, Any] = {}
                if d_action == "isolate":
                    body = {"Comment": "Isolated by Omni-Agent", "IsolationType": "Full"}
                elif d_action == "runAntiVirusScan":
                    body = {"Comment": "Scan triggered by Omni-Agent", "ScanType": "Quick"}
                resp = await session.post(
                    f"https://api.securitycenter.microsoft.com/api/machines/{asset_id}/{d_action}",
                    json=body,
                    headers={"Authorization": f"Bearer {token}",
                             "Content-Type": "application/json"},
                )
                return {"success": resp.status in (200, 201), "platform": "microsoft_defender",
                        "action": d_action, "status_code": resp.status,
                        "details": await resp.json()}
        except Exception as exc:
            return {"success": False, "platform": "microsoft_defender", "error": str(exc)}

    # ------------------------------------------------------------------
    # ChatOps
    # ------------------------------------------------------------------

    async def send_to_chatops(
        self, title: str, message: str, severity: str, platform: str = "slack"
    ) -> Dict[str, Any]:
        """Send notification to a ChatOps platform (slack, teams)."""
        config = await self._get_integration_config("chatops", platform)
        if not config or not config.get("enabled"):
            return {"success": False, "error": f"ChatOps {platform} not configured"}

        if platform == "slack":
            return await self._send_to_slack(title, message, severity, config)
        if platform == "teams":
            return await self._send_to_teams(title, message, severity, config)
        return {"success": False, "error": f"Unsupported ChatOps platform: {platform}"}

    async def _send_to_slack(
        self, title: str, message: str, severity: str, config: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Send message to a Slack incoming webhook."""
        url = config.get("webhook_url")
        if not url:
            return {"success": False, "error": "Missing Webhook URL"}
        payload = {
            "attachments": [{
                "color": _SLACK_COLORS.get(severity, "#CCCCCC"),
                "title": title, "text": message,
                "footer": "Omni-Agent AI Platform",
                "ts": datetime.now(timezone.utc).timestamp(),
            }]
        }
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    return {"success": resp.status == 200, "platform": "slack",
                            "status_code": resp.status}
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    async def _send_to_teams(
        self, title: str, message: str, severity: str, config: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Send message to a Microsoft Teams incoming webhook."""
        url = config.get("webhook_url")
        if not url:
            return {"success": False, "error": "Missing Webhook URL"}
        payload = {
            "@type": "MessageCard", "@context": "http://schema.org/extensions",
            "themeColor": "0076D7", "summary": title,
            "sections": [{
                "activityTitle": title,
                "activitySubtitle": f"Severity: {severity.upper()}",
                "text": message, "markdown": True,
            }],
        }
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    return {"success": resp.status == 200, "platform": "teams",
                            "status_code": resp.status}
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    # ------------------------------------------------------------------
    # Identity Providers
    # ------------------------------------------------------------------

    async def fetch_okta_users(self, config: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Fetch users from Okta via REST API."""
        url = f"{config.get('url', '').rstrip('/')}/api/v1/users"
        headers = {"Accept": "application/json", "Content-Type": "application/json",
                   "Authorization": f"SSWS {config.get('api_token', '')}"}
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers, timeout=10) as resp:
                    if resp.status == 200:
                        return await resp.json()
                    _log.warning("Okta list_users returned HTTP %s", resp.status)
                    return []
        except Exception as exc:
            _log.error("Okta list_users failed: %s", exc)
            return []

    async def suspend_okta_user(self, user_id: str, config: Dict[str, Any]) -> Dict[str, Any]:
        """Suspend a user in Okta."""
        url = f"{config.get('url', '').rstrip('/')}/api/v1/users/{user_id}/lifecycle/suspend"
        headers = {"Accept": "application/json", "Content-Type": "application/json",
                   "Authorization": f"SSWS {config.get('api_token', '')}"}
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, headers=headers, timeout=10) as resp:
                    return {"success": resp.status == 200, "status_code": resp.status}
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    async def fetch_entra_users(self, config: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Fetch users from Microsoft Entra ID via Graph API."""
        tenant_id = config.get("tenant_id", "")
        try:
            async with aiohttp.ClientSession() as session:
                token_resp = await session.post(
                    f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token",
                    data={"client_id": config.get("client_id", ""),
                          "client_secret": config.get("client_secret", ""),
                          "scope": "https://graph.microsoft.com/.default",
                          "grant_type": "client_credentials"},
                )
                if token_resp.status != 200:
                    return []
                token = (await token_resp.json()).get("access_token")
                users_resp = await session.get(
                    "https://graph.microsoft.com/v1.0/users",
                    headers={"Authorization": f"Bearer {token}"},
                    timeout=10,
                )
                if users_resp.status == 200:
                    return (await users_resp.json()).get("value", [])
                _log.warning("Entra ID list_users returned HTTP %s", users_resp.status)
                return []
        except Exception as exc:
            _log.error("Entra ID list_users failed: %s", exc)
            return []

    async def suspend_entra_user(self, user_id: str, config: Dict[str, Any]) -> Dict[str, Any]:
        """Disable an account in Entra ID (Azure AD)."""
        tenant_id = config.get("tenant_id", "")
        try:
            async with aiohttp.ClientSession() as session:
                token_resp = await session.post(
                    f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token",
                    data={"client_id": config.get("client_id", ""),
                          "client_secret": config.get("client_secret", ""),
                          "scope": "https://graph.microsoft.com/.default",
                          "grant_type": "client_credentials"},
                )
                if token_resp.status != 200:
                    return {"success": False, "error": "Failed to get access token"}
                token = (await token_resp.json()).get("access_token")
                resp = await session.patch(
                    f"https://graph.microsoft.com/v1.0/users/{user_id}",
                    headers={"Authorization": f"Bearer {token}",
                             "Content-Type": "application/json"},
                    json={"accountEnabled": False},
                    timeout=10,
                )
                return {"success": resp.status == 204, "status_code": resp.status}
        except Exception as exc:
            return {"success": False, "error": str(exc)}

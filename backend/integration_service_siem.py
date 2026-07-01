"""
IntegrationService SIEM mixin: Splunk, ELK, Wazuh, QRadar.
"""

import aiohttp
from datetime import datetime, timezone
from typing import Dict, Any
import logging

_SSL_VERIFY = True
_log = logging.getLogger(__name__)


class IntegrationServiceSiemMixin:
    """SIEM platform integrations."""

    async def send_to_siem(
        self,
        event_type: str,
        severity: str,
        details: Dict[str, Any],
        platform: str = "splunk",
    ) -> Dict[str, Any]:
        """Send security event to a SIEM platform (splunk, wazuh, elk, qradar)."""
        config = await self._get_integration_config("siem", platform)
        if not config or not config.get("enabled"):
            return {"success": False, "error": f"SIEM {platform} not configured"}

        if platform == "splunk":
            return await self._send_to_splunk(event_type, severity, details, config)
        if platform == "wazuh":
            return await self._send_to_wazuh(event_type, severity, details, config)
        if platform == "elk":
            return await self._send_to_elk(event_type, severity, details, config)
        if platform == "qradar":
            return await self._send_to_qradar(event_type, severity, details, config)
        return {"success": False, "error": f"Unsupported SIEM platform: {platform}"}

    async def test_siem_connection(self, platform: str, config: Dict[str, Any]) -> Dict[str, Any]:
        """Test SIEM connection by sending a heartbeat event."""
        test_details = {
            "message": "SIEM Connection Test Heartbeat",
            "test_time": datetime.now(timezone.utc).isoformat(),
        }
        if platform == "splunk":
            return await self._send_to_splunk("test_heartbeat", "info", test_details, config)
        if platform == "elk":
            return await self._send_to_elk("test_heartbeat", "info", test_details, config)
        if platform == "slack":
            return await self._send_to_slack(
                "Test Heartbeat", "Testing Slack connection from Omni-Agent Platform.", "info", config
            )
        if platform == "teams":
            return await self._send_to_teams(
                "Test Heartbeat", "Testing Teams connection from Omni-Agent Platform.", "info", config
            )
        return {"success": False, "error": f"Testing not implemented for {platform}"}

    async def _send_to_splunk(
        self,
        event_type: str,
        severity: str,
        details: Dict[str, Any],
        config: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Send event to Splunk HEC (HTTP Event Collector)."""
        url = f"{config['endpoint']}/services/collector/event"
        payload = {
            "time": datetime.now(timezone.utc).timestamp(),
            "sourcetype": "patch_management",
            "event": {"event_type": event_type, "severity": severity, **details},
        }
        headers = {"Authorization": f"Splunk {config['token']}", "Content-Type": "application/json"}
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload, headers=headers, ssl=_SSL_VERIFY) as resp:
                    if resp.status == 200:
                        return {"success": True, "details": await resp.json()}
                    return {"success": False, "error": f"Splunk returned {resp.status}",
                            "details": await resp.text()}
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    async def _send_to_elk(
        self,
        event_type: str,
        severity: str,
        details: Dict[str, Any],
        config: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Send event to Elasticsearch/Logstash."""
        url = f"{config['endpoint']}/{config.get('index', 'security-events')}/_doc"
        payload = {"@timestamp": datetime.now(timezone.utc).isoformat(),
                   "event_type": event_type, "severity": severity, **details}
        headers: Dict[str, str] = {"Content-Type": "application/json"}
        if config.get("api_key"):
            headers["Authorization"] = f"ApiKey {config['api_key']}"
        elif config.get("username") and config.get("password"):
            headers["Authorization"] = aiohttp.BasicAuth(
                config["username"], config["password"]
            ).encode()
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url, json=payload, headers=headers, timeout=aiohttp.ClientTimeout(total=10)
                ) as resp:
                    return {"success": resp.status in (200, 201), "platform": "elk",
                            "status_code": resp.status}
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    async def _send_to_wazuh(
        self,
        event_type: str,
        severity: str,
        details: Dict[str, Any],
        config: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Send event to Wazuh manager via REST API (Wazuh 4.4+)."""
        base = config.get("endpoint", "").rstrip("/")
        username = config.get("username", "wazuh")
        password = config.get("password", "")
        try:
            timeout = aiohttp.ClientTimeout(total=10)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                auth_resp = await session.post(
                    f"{base}/security/user/authenticate",
                    auth=aiohttp.BasicAuth(username, password),
                    ssl=_SSL_VERIFY,
                )
                if auth_resp.status != 200:
                    return {"success": False, "platform": "wazuh",
                            "error": f"Auth failed: {auth_resp.status}"}
                token = (await auth_resp.json())["data"]["token"]
                payload = {
                    "events": [{
                        "log": {
                            "full_log": (
                                f"event_type={event_type} severity={severity} "
                                + " ".join(f"{k}={v}" for k, v in details.items())
                            )
                        }
                    }]
                }
                resp = await session.post(
                    f"{base}/events",
                    json=payload,
                    headers={"Authorization": f"Bearer {token}"},
                    ssl=_SSL_VERIFY,
                )
                return {"success": resp.status in (200, 201), "platform": "wazuh",
                        "status_code": resp.status, "details": await resp.json()}
        except Exception as exc:
            return {"success": False, "platform": "wazuh", "error": str(exc)}

    async def _send_to_qradar(
        self,
        event_type: str,
        severity: str,
        details: Dict[str, Any],
        config: Dict[str, Any],
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
        headers = {"SEC": api_token, "Content-Type": "application/json",
                   "Accept": "application/json", "Version": "17.0"}
        try:
            timeout = aiohttp.ClientTimeout(total=10)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                await session.post(
                    f"{base}/api/reference_data/sets",
                    params={"name": set_name, "element_type": "ALN"},
                    headers=headers, ssl=_SSL_VERIFY,
                )
                resp = await session.post(
                    f"{base}/api/reference_data/sets/{set_name}",
                    params={"value": str(payload)},
                    headers=headers, ssl=_SSL_VERIFY,
                )
                return {"success": resp.status in (200, 201), "platform": "qradar",
                        "status_code": resp.status, "ref_set": set_name}
        except Exception as exc:
            return {"success": False, "platform": "qradar", "error": str(exc)}

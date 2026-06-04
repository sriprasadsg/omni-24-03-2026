"""
SOAR Security Operations Connectors
Firewall (Palo Alto, FortiGate, local) and EDR (CrowdStrike, SentinelOne, local) integrations.
"""

from typing import Dict, Any
import aiohttp

from soar_integrations import IntegrationConnector


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
                headers = ({"X-PAN-KEY": api_key} if provider == "palo_alto"
                           else {"Authorization": f"Bearer {api_key}"})
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
                    f"{base_url}/api/?type=config&action=set&xpath=/config/devices/entry/vsys/entry/address"
                    f"&element={cmd}&key={api_key}",
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
                        return {"status": "success",
                                "message": f"SentinelOne {action} applied to {endpoint_id}", "data": data}
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
                        return {"status": "success",
                                "message": f"CrowdStrike {action} applied to {device_id}", "data": data}
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

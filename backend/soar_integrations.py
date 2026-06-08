"""
SOAR Integration Connectors — base class, Jira ticketing, and manager.

Connector implementations live in dedicated modules:
  soar_connectors_messaging  — Slack, Teams, PagerDuty, EmailGateway
  soar_connectors_security   — Firewall, EDR
  soar_connectors_cloud      — CloudProvider
"""

from typing import Dict, Any, Optional
import aiohttp
import logging
import os as _os

_SSL_VERIFY = _os.getenv("DISABLE_SSL_VERIFY", "").lower() not in ("1", "true", "yes")


class IntegrationConnector:
    """Base class for all integration connectors."""

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.logger = logging.getLogger(f"Connector.{self.__class__.__name__}")

    async def test_connection(self) -> bool:
        """Test connectivity. Subclasses should override with a real check."""
        self.logger.warning(
            "%s.test_connection() not implemented — returning False",
            self.__class__.__name__,
        )
        return False

    async def execute(self, action: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """Execute an action. Subclasses must override."""
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


class JiraConnector(IntegrationConnector):
    """Jira integration for ticket creation and management."""

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
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as response:
                    return response.status == 200
        except Exception as e:
            self.logger.error("Jira connection test failed: %s", e)
            return False

    async def execute(self, action: str, params: Dict[str, Any]) -> Dict[str, Any]:
        if action == "create_ticket":
            return await self._create_ticket(params)
        elif action == "update_ticket":
            return await self._update_ticket(params)
        elif action == "add_comment":
            return await self._add_comment(params)
        raise ValueError(f"Unknown action: {action}")

    async def _create_ticket(self, params: Dict[str, Any]) -> Dict[str, Any]:
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
                "priority": {"name": params.get("priority", "Medium")},
            }
        }
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{base_url}/rest/api/3/issue",
                    auth=aiohttp.BasicAuth(email, api_token),
                    json=payload,
                    headers={"Content-Type": "application/json"},
                ) as response:
                    if response.status == 201:
                        data = await response.json()
                        return {
                            "status": "success",
                            "ticket_id": data.get("key"),
                            "ticket_url": f"{base_url}/browse/{data.get('key')}",
                        }
                    return {"status": "error", "message": f"Failed with status {response.status}"}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    async def _update_ticket(self, params: Dict[str, Any]) -> Dict[str, Any]:
        base_url = self.config.get("base_url")
        api_token = self.config.get("api_token")
        email = self.config.get("email")
        issue_key = params.get("issue_key")
        if not all([base_url, api_token, email, issue_key]):
            return {"status": "error", "message": "Missing required config or issue_key param"}
        payload = {"fields": params.get("fields", {})}
        try:
            async with aiohttp.ClientSession() as session:
                async with session.put(
                    f"{base_url}/rest/api/3/issue/{issue_key}",
                    auth=aiohttp.BasicAuth(email, api_token),
                    json=payload,
                    headers={"Content-Type": "application/json"},
                    ssl=_SSL_VERIFY,
                ) as response:
                    if response.status in (200, 204):
                        return {"status": "success", "issue_key": issue_key}
                    return {"status": "error", "message": f"Jira returned {response.status}"}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    async def _add_comment(self, params: Dict[str, Any]) -> Dict[str, Any]:
        base_url = self.config.get("base_url")
        api_token = self.config.get("api_token")
        email = self.config.get("email")
        issue_key = params.get("issue_key")
        if not all([base_url, api_token, email, issue_key]):
            return {"status": "error", "message": "Missing required config or issue_key param"}
        comment_text = params.get("comment", "")
        payload = {
            "body": {
                "version": 1,
                "type": "doc",
                "content": [{"type": "paragraph", "content": [{"type": "text", "text": comment_text}]}],
            }
        }
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{base_url}/rest/api/3/issue/{issue_key}/comment",
                    auth=aiohttp.BasicAuth(email, api_token),
                    json=payload,
                    headers={"Content-Type": "application/json"},
                    ssl=_SSL_VERIFY,
                ) as response:
                    if response.status == 201:
                        data = await response.json()
                        return {"status": "success", "comment_id": data.get("id")}
                    return {"status": "error", "message": f"Jira returned {response.status}"}
        except Exception as e:
            return {"status": "error", "message": str(e)}


class IntegrationManager:
    """Manages all integration connectors."""

    def __init__(self):
        self.connectors: Dict[str, IntegrationConnector] = {}
        self.logger = logging.getLogger("IntegrationManager")

    def register_connector(self, name: str, connector: IntegrationConnector):
        self.connectors[name] = connector
        self.logger.info("Registered connector: %s", name)

    def get_connector(self, name: str) -> Optional[IntegrationConnector]:
        return self.connectors.get(name)

    async def execute_action(
        self,
        connector_name: str,
        action: str,
        params: Dict[str, Any],
    ) -> Dict[str, Any]:
        connector = self.get_connector(connector_name)
        if not connector:
            raise ValueError(f"Connector not found: {connector_name}")
        return await connector.execute(action, params)

    async def test_all_connections(self) -> Dict[str, bool]:
        results = {}
        for name, connector in self.connectors.items():
            try:
                results[name] = await connector.test_connection()
            except Exception as e:
                self.logger.error("Connection test failed for %s: %s", name, e)
                results[name] = False
        return results


_integration_manager: Optional[IntegrationManager] = None


def get_integration_manager() -> IntegrationManager:
    global _integration_manager
    if _integration_manager is None:
        _integration_manager = IntegrationManager()
    return _integration_manager

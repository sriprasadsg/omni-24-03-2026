"""
Integration Service aggregator.

Logic is split across three mixin modules:
  integration_service_siem.py      — Splunk, ELK, Wazuh, QRadar
  integration_service_ticketing.py — Jira, ServiceNow, Zoho Desk, CMDB sync
  integration_service_edr.py       — CrowdStrike, SentinelOne, Defender, ChatOps, Okta, Entra ID
"""

import os as _os
import logging
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional

from integration_service_siem import IntegrationServiceSiemMixin
from integration_service_ticketing import IntegrationServiceTicketingMixin
from integration_service_edr import IntegrationServiceEdrMixin

_log = logging.getLogger(__name__)

if _os.getenv("DISABLE_SSL_VERIFY", "").lower() in ("1", "true", "yes"):
    _log.warning(
        "DISABLE_SSL_VERIFY is set but ignored — SSL certificate validation is enforced. "
        "Use per-integration verify_ssl config for self-signed cert environments."
    )


class IntegrationService(
    IntegrationServiceSiemMixin,
    IntegrationServiceTicketingMixin,
    IntegrationServiceEdrMixin,
):
    """External platform integration service."""

    def __init__(self, db):
        self.db = db

    async def _get_integration_config(
        self, integration_type: str, platform: str
    ) -> Optional[Dict[str, Any]]:
        """Fetch integration configuration from the database."""
        return await self.db.integration_configs.find_one(
            {"type": integration_type, "platform": platform}, {"_id": 0}
        )

    async def get_all_configs(self, tenant_id: str) -> List[Dict[str, Any]]:
        """Get all integration configurations for a tenant."""
        return await self.db.integration_configs.find(
            {"tenantId": tenant_id}, {"_id": 0}
        ).to_list(length=1000)

    async def save_config(
        self, tenant_id: str, config_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Save or update an integration configuration."""
        integration_type = config_data.get("type")
        platform = config_data.get("platform")
        if not integration_type or not platform:
            return {"success": False, "error": "Missing type or platform"}
        await self.db.integration_configs.update_one(
            {"tenantId": tenant_id, "type": integration_type, "platform": platform},
            {"$set": {**config_data, "tenantId": tenant_id,
                      "updatedAt": datetime.now(timezone.utc)}},
            upsert=True,
        )
        return {"success": True, "message": f"Configuration for {platform} saved"}


def get_integration_service(db) -> IntegrationService:
    """Get an integration service instance."""
    return IntegrationService(db)

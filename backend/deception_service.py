"""
Deception Technology Service
Manages honeytokens, canary tokens, and deception alerts platform-side.
"""

import uuid
import logging
import secrets
import hashlib
from datetime import datetime, timezone
from typing import Any, Dict, List

from database import get_database

logger = logging.getLogger(__name__)

HONEYTOKEN_TYPES = {
    "aws_key": {
        "name": "Fake AWS Access Key",
        "description": "AWS-format access key that triggers alert when used",
        "template": "AKIA{random16}",
    },
    "api_key": {
        "name": "Fake API Key",
        "description": "API key that triggers alert when included in a request",
        "template": "sk-{random32}",
    },
    "url_token": {
        "name": "Canary URL Token",
        "description": "Unique URL that triggers alert when fetched",
        "template": "https://{domain}/canary/{token}",
    },
    "dns_token": {
        "name": "DNS Canary Token",
        "description": "Subdomain that triggers alert on DNS lookup",
        "template": "{token}.canary.{domain}",
    },
    "document_token": {
        "name": "Canary Document",
        "description": "Document with embedded beacon that triggers on open",
        "template": "decoy_document_{token}",
    },
}


def _generate_token() -> str:
    return secrets.token_urlsafe(24)


def _generate_aws_key() -> str:
    chars = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567"
    return "AKIA" + "".join(secrets.choice(chars) for _ in range(16))


async def create_honeytoken(tenant_id: str, created_by: str, data: Dict[str, Any]) -> Dict[str, Any]:
    db = get_database()
    token_type = data.get("type", "api_key")
    label = data.get("label", f"Honeytoken {token_type}")

    token_value = _generate_aws_key() if token_type == "aws_key" else _generate_token()

    doc = {
        "id": str(uuid.uuid4()),
        "tenant_id": tenant_id,
        "created_by": created_by,
        "type": token_type,
        "label": label,
        "description": data.get("description", HONEYTOKEN_TYPES.get(token_type, {}).get("description", "")),
        "token_value": token_value,
        "token_hash": hashlib.sha256(token_value.encode()).hexdigest(),
        "deploy_location": data.get("deploy_location", ""),
        "tags": data.get("tags", []),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "last_triggered": None,
        "trigger_count": 0,
        "active": True,
        "alert_on_trigger": True,
    }

    await db.honeytokens.insert_one(doc)
    logger.info("[Deception] Created %s honeytoken '%s' for tenant %s", token_type, label, tenant_id)
    return doc


async def list_honeytokens(tenant_id: str, role: str) -> List[Dict[str, Any]]:
    db = get_database()
    query = {} if role == "super_admin" else {"tenant_id": tenant_id}
    tokens = await db.honeytokens.find(query).sort("created_at", -1).to_list(length=500)
    for t in tokens:
        t["_id"] = str(t["_id"])
        # Mask token value in list response
        if t.get("token_value"):
            t["token_value"] = t["token_value"][:8] + "***"
    return tokens


async def record_trigger(token_id: str, source_ip: str, user_agent: str = "", extra: Dict = None) -> bool:
    """Called when a honeytoken is triggered (e.g. via webhook or API check)."""
    db = get_database()
    # Only accept triggers for tokens that exist AND are currently active
    token = await db.honeytokens.find_one({"id": token_id, "status": "Active"})
    if not token:
        return False

    now = datetime.now(timezone.utc).isoformat()
    await db.honeytokens.update_one(
        {"id": token_id},
        {"$set": {"last_triggered": now}, "$inc": {"trigger_count": 1}},
    )

    alert = {
        "id": str(uuid.uuid4()),
        "tenant_id": token.get("tenant_id", ""),
        "honeytoken_id": token_id,
        "honeytoken_type": token.get("type", ""),
        "honeytoken_label": token.get("label", ""),
        "source_ip": source_ip,
        "user_agent": user_agent,
        "extra": extra or {},
        "triggered_at": now,
        "severity": "Critical",
        "description": f"Honeytoken '{token.get('label', token_id)}' was triggered from {source_ip}",
        "status": "open",
    }
    await db.deception_alerts.insert_one(alert)

    # Also create a high-severity security event
    await db.security_events.insert_one({
        "id": str(uuid.uuid4()),
        "tenant_id": token.get("tenant_id", ""),
        "timestamp": now,
        "log_type": "honeytoken_trigger",
        "title": f"Honeytoken Triggered: {token.get('label', '')}",
        "description": alert["description"],
        "severity": "Critical",
        "source": "deception_technology",
        "source_ip": source_ip,
        "raw_message": f"[Deception] {alert['description']}",
    })

    logger.critical("[Deception] HONEYTOKEN TRIGGERED: %s from %s", token.get("label"), source_ip)
    return True


async def list_deception_alerts(tenant_id: str, role: str, limit: int = 100) -> List[Dict[str, Any]]:
    db = get_database()
    query = {} if role == "super_admin" else {"tenant_id": tenant_id}
    alerts = await db.deception_alerts.find(query).sort("triggered_at", -1).to_list(length=limit)
    for a in alerts:
        a["_id"] = str(a["_id"])
    return alerts


async def get_deception_summary(tenant_id: str, role: str) -> Dict[str, Any]:
    db = get_database()
    query = {} if role == "super_admin" else {"tenant_id": tenant_id}

    total_tokens = await db.honeytokens.count_documents(query)
    active_tokens = await db.honeytokens.count_documents({**query, "active": True})
    total_alerts = await db.deception_alerts.count_documents(query)
    open_alerts = await db.deception_alerts.count_documents({**query, "status": "open"})

    # Ingest deception events from agents
    agent_hits = await db.compliance_evidence.find(
        {"tenant_id": tenant_id if role != "super_admin" else {"$exists": True}},
        {"data.deception_monitor": 1}
    ).to_list(length=50)

    agent_total_hits = 0
    for ev in agent_hits:
        hits = ev.get("data", {}).get("deception_monitor", {}).get("hits_this_cycle", 0)
        agent_total_hits += hits

    return {
        "total_honeytokens": total_tokens,
        "active_honeytokens": active_tokens,
        "total_alerts": total_alerts,
        "open_alerts": open_alerts,
        "agent_hits_detected": agent_total_hits,
        "honeytoken_types": list(HONEYTOKEN_TYPES.keys()),
    }


async def deactivate_honeytoken(token_id: str, tenant_id: str, role: str) -> bool:
    db = get_database()
    query = {"id": token_id}
    if role != "super_admin":
        query["tenant_id"] = tenant_id
    result = await db.honeytokens.update_one(query, {"$set": {"active": False}})
    return result.modified_count > 0


async def delete_honeytoken(token_id: str, tenant_id: str, role: str) -> bool:
    db = get_database()
    query = {"id": token_id}
    if role != "super_admin":
        query["tenant_id"] = tenant_id
    result = await db.honeytokens.delete_one(query)
    return result.deleted_count > 0

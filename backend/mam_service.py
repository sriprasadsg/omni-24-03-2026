"""
Mobile Application Management (MAM) Service.
Manages App Protection Policies, App Configuration Policies,
and corporate data wipe for managed mobile apps.
"""

import uuid
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from database import get_database

logger = logging.getLogger(__name__)


async def list_protection_policies(tenant_id: str) -> List[Dict[str, Any]]:
    db = get_database()
    cursor = db._db.mam_protection_policies.find({"tenantId": tenant_id}).sort("created_at", -1)
    docs = await cursor.to_list(length=500)
    for d in docs:
        d.pop("_id", None)
    return docs


async def get_protection_policy(tenant_id: str, policy_id: str) -> Optional[Dict[str, Any]]:
    db = get_database()
    doc = await db._db.mam_protection_policies.find_one({"tenantId": tenant_id, "id": policy_id})
    if doc:
        doc.pop("_id", None)
    return doc


async def create_protection_policy(tenant_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
    name = (data.get("name") or "").strip()
    if not name:
        raise ValueError("Policy name is required")
    now = datetime.now(timezone.utc).isoformat()
    doc = {
        "id": str(uuid.uuid4()),
        "tenantId": tenant_id,
        "name": name,
        "description": data.get("description", ""),
        "platform": data.get("platform", "all"),
        "require_pin": bool(data.get("require_pin", True)),
        "pin_length": int(data.get("pin_length", 6)),
        "block_copy_paste": bool(data.get("block_copy_paste", False)),
        "block_screenshots": bool(data.get("block_screenshots", False)),
        "block_backup": bool(data.get("block_backup", False)),
        "require_managed_browser": bool(data.get("require_managed_browser", False)),
        "wipe_on_jailbreak": bool(data.get("wipe_on_jailbreak", True)),
        "wipe_after_failed_pins": int(data.get("wipe_after_failed_pins", 10)),
        "offline_grace_period_days": int(data.get("offline_grace_period_days", 30)),
        "assigned_groups": data.get("assigned_groups", []),
        "assigned_apps": data.get("assigned_apps", []),
        "enabled": True,
        "created_at": now,
        "updated_at": now,
    }
    db = get_database()
    await db._db.mam_protection_policies.insert_one(doc)
    doc.pop("_id", None)
    return doc


async def update_protection_policy(tenant_id: str, policy_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
    existing = await get_protection_policy(tenant_id, policy_id)
    if not existing:
        raise ValueError(f"Policy {policy_id} not found")
    allowed = {
        "name", "description", "platform", "require_pin", "pin_length",
        "block_copy_paste", "block_screenshots", "block_backup",
        "require_managed_browser", "wipe_on_jailbreak", "wipe_after_failed_pins",
        "offline_grace_period_days", "assigned_groups", "assigned_apps", "enabled",
    }
    updates = {k: v for k, v in data.items() if k in allowed}
    updates["updated_at"] = datetime.now(timezone.utc).isoformat()
    db = get_database()
    await db._db.mam_protection_policies.update_one(
        {"tenantId": tenant_id, "id": policy_id}, {"$set": updates}
    )
    return {**existing, **updates}


async def delete_protection_policy(tenant_id: str, policy_id: str) -> None:
    db = get_database()
    await db._db.mam_protection_policies.delete_one({"tenantId": tenant_id, "id": policy_id})


async def list_config_policies(tenant_id: str) -> List[Dict[str, Any]]:
    db = get_database()
    cursor = db._db.mam_config_policies.find({"tenantId": tenant_id}).sort("created_at", -1)
    docs = await cursor.to_list(length=500)
    for d in docs:
        d.pop("_id", None)
    return docs


async def get_config_policy(tenant_id: str, policy_id: str) -> Optional[Dict[str, Any]]:
    db = get_database()
    doc = await db._db.mam_config_policies.find_one({"tenantId": tenant_id, "id": policy_id})
    if doc:
        doc.pop("_id", None)
    return doc


async def create_config_policy(tenant_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
    name = (data.get("name") or "").strip()
    if not name:
        raise ValueError("Policy name is required")
    now = datetime.now(timezone.utc).isoformat()
    doc = {
        "id": str(uuid.uuid4()),
        "tenantId": tenant_id,
        "name": name,
        "description": data.get("description", ""),
        "platform": data.get("platform", "all"),
        "target_app": data.get("target_app", ""),
        "config_items": data.get("config_items", []),  # [{key, value, value_type}]
        "assigned_groups": data.get("assigned_groups", []),
        "enabled": True,
        "created_at": now,
        "updated_at": now,
    }
    db = get_database()
    await db._db.mam_config_policies.insert_one(doc)
    doc.pop("_id", None)
    return doc


async def update_config_policy(tenant_id: str, policy_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
    existing = await get_config_policy(tenant_id, policy_id)
    if not existing:
        raise ValueError(f"Config policy {policy_id} not found")
    allowed = {"name", "description", "platform", "target_app", "config_items", "assigned_groups", "enabled"}
    updates = {k: v for k, v in data.items() if k in allowed}
    updates["updated_at"] = datetime.now(timezone.utc).isoformat()
    db = get_database()
    await db._db.mam_config_policies.update_one(
        {"tenantId": tenant_id, "id": policy_id}, {"$set": updates}
    )
    return {**existing, **updates}


async def delete_config_policy(tenant_id: str, policy_id: str) -> None:
    db = get_database()
    await db._db.mam_config_policies.delete_one({"tenantId": tenant_id, "id": policy_id})


async def list_managed_apps(tenant_id: str) -> List[Dict[str, Any]]:
    db = get_database()
    cursor = db._db.mam_managed_apps.find({"tenantId": tenant_id}).sort("app_name", 1)
    docs = await cursor.to_list(length=1000)
    for d in docs:
        d.pop("_id", None)
    return docs


async def selective_wipe(tenant_id: str, app_id: str) -> Dict[str, Any]:
    db = get_database()
    now = datetime.now(timezone.utc).isoformat()
    await db._db.mam_managed_apps.update_one(
        {"tenantId": tenant_id, "id": app_id},
        {"$set": {"wipe_pending": True, "wipe_requested_at": now}},
    )
    return {"app_id": app_id, "wipe_pending": True, "wipe_requested_at": now}

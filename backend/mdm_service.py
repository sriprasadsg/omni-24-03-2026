"""
Mobile Device Management (MDM) Service
Manages iOS and Android device enrollment, compliance, and remote actions.
"""

import uuid
import secrets
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from database import get_database

logger = logging.getLogger(__name__)

PLATFORMS = ("ios", "android", "windows", "macos")
ENROLLMENT_STATUSES = ("pending", "enrolled", "non_compliant", "wiped", "unenrolled")
REMOTE_ACTIONS = ("wipe", "lock", "reset_passcode", "sync", "retire")


async def get_summary(tenant_id: str) -> Dict[str, Any]:
    db = get_database()
    total = await db._db.mdm_devices.count_documents({"tenantId": tenant_id})
    enrolled = await db._db.mdm_devices.count_documents({"tenantId": tenant_id, "enrollment_status": "enrolled"})
    non_compliant = await db._db.mdm_devices.count_documents({"tenantId": tenant_id, "compliance_status": "non_compliant"})
    ios_count = await db._db.mdm_devices.count_documents({"tenantId": tenant_id, "platform": "ios"})
    android_count = await db._db.mdm_devices.count_documents({"tenantId": tenant_id, "platform": "android"})
    return {
        "total": total,
        "enrolled": enrolled,
        "non_compliant": non_compliant,
        "ios": ios_count,
        "android": android_count,
        "other": total - ios_count - android_count,
    }


async def list_devices(tenant_id: str, platform: Optional[str] = None, status: Optional[str] = None, limit: int = 100) -> List[Dict]:
    db = get_database()
    filt: Dict[str, Any] = {"tenantId": tenant_id}
    if platform:
        filt["platform"] = platform
    if status:
        filt["enrollment_status"] = status
    cursor = db._db.mdm_devices.find(filt).sort("enrolled_at", -1).limit(limit)
    docs = await cursor.to_list(length=limit)
    for d in docs:
        d.pop("_id", None)
    return docs


async def enroll_device(tenant_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
    db = get_database()
    platform = data.get("platform", "").lower()
    if platform not in PLATFORMS:
        raise ValueError(f"platform must be one of {PLATFORMS}")

    udid = data.get("udid", "").strip()
    if not udid:
        raise ValueError("udid (unique device identifier) is required")

    existing = await db._db.mdm_devices.find_one({"tenantId": tenant_id, "udid": udid})
    if existing:
        raise ValueError(f"Device with UDID '{udid}' is already enrolled")

    now = datetime.now(timezone.utc).isoformat()
    doc = {
        "id": str(uuid.uuid4()),
        "tenantId": tenant_id,
        "udid": udid,
        "name": data.get("name", ""),
        "platform": platform,
        "os_version": data.get("os_version", ""),
        "model": data.get("model", ""),
        "manufacturer": data.get("manufacturer", ""),
        "serial_number": data.get("serial_number", ""),
        "assigned_user": data.get("assigned_user", ""),
        "phone_number": data.get("phone_number", ""),
        "enrollment_status": "enrolled",
        "compliance_status": "pending",
        "last_seen": now,
        "enrolled_at": now,
        "updated_at": now,
        "policy_id": data.get("policy_id"),
        "management_token": secrets.token_urlsafe(32),
        "compliance_details": {},
        "installed_apps": [],
        "notes": data.get("notes", ""),
    }
    await db._db.mdm_devices.insert_one(doc)
    doc.pop("_id", None)
    doc.pop("management_token", None)
    return doc


async def get_device(device_id: str, tenant_id: str) -> Optional[Dict]:
    db = get_database()
    doc = await db._db.mdm_devices.find_one({"id": device_id, "tenantId": tenant_id})
    if doc:
        doc.pop("_id", None)
        doc.pop("management_token", None)
    return doc


async def update_device(device_id: str, tenant_id: str, data: Dict[str, Any]) -> Optional[Dict]:
    db = get_database()
    allowed = {"name", "assigned_user", "phone_number", "policy_id", "notes", "os_version", "compliance_status"}
    update = {k: v for k, v in data.items() if k in allowed}
    if not update:
        raise ValueError("No updatable fields provided")
    update["updated_at"] = datetime.now(timezone.utc).isoformat()
    await db._db.mdm_devices.update_one(
        {"id": device_id, "tenantId": tenant_id},
        {"$set": update},
    )
    return await get_device(device_id, tenant_id)


async def unenroll_device(device_id: str, tenant_id: str) -> bool:
    db = get_database()
    result = await db._db.mdm_devices.update_one(
        {"id": device_id, "tenantId": tenant_id},
        {"$set": {"enrollment_status": "unenrolled", "updated_at": datetime.now(timezone.utc).isoformat()}},
    )
    return result.modified_count > 0


async def remote_action(device_id: str, tenant_id: str, action: str, actor: str) -> Dict[str, Any]:
    if action not in REMOTE_ACTIONS:
        raise ValueError(f"action must be one of {REMOTE_ACTIONS}")
    db = get_database()
    device = await get_device(device_id, tenant_id)
    if not device:
        raise ValueError("Device not found")

    now = datetime.now(timezone.utc).isoformat()
    log_entry = {"action": action, "actor": actor, "timestamp": now, "status": "queued"}

    update: Dict[str, Any] = {"updated_at": now}
    if action == "wipe":
        update["enrollment_status"] = "wiped"
    elif action == "retire":
        update["enrollment_status"] = "unenrolled"

    await db._db.mdm_devices.update_one(
        {"id": device_id, "tenantId": tenant_id},
        {"$set": update, "$push": {"action_log": log_entry}},
    )
    return {"device_id": device_id, "action": action, "status": "queued", "timestamp": now}


# ── MDM Policies ──────────────────────────────────────────────────────────────

async def list_policies(tenant_id: str) -> List[Dict]:
    db = get_database()
    cursor = db._db.mdm_policies.find({"tenantId": tenant_id}).sort("created_at", -1)
    docs = await cursor.to_list(length=100)
    for d in docs:
        d.pop("_id", None)
    return docs


async def create_policy(tenant_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
    db = get_database()
    name = data.get("name", "").strip()
    if not name:
        raise ValueError("Policy name is required")

    now = datetime.now(timezone.utc).isoformat()
    doc = {
        "id": str(uuid.uuid4()),
        "tenantId": tenant_id,
        "name": name,
        "description": data.get("description", ""),
        "platforms": data.get("platforms", ["ios", "android"]),
        "require_pin": bool(data.get("require_pin", True)),
        "min_pin_length": int(data.get("min_pin_length", 6)),
        "require_encryption": bool(data.get("require_encryption", True)),
        "min_os_version_ios": data.get("min_os_version_ios", ""),
        "min_os_version_android": data.get("min_os_version_android", ""),
        "block_rooted_jailbroken": bool(data.get("block_rooted_jailbroken", True)),
        "max_inactivity_minutes": int(data.get("max_inactivity_minutes", 15)),
        "assigned_devices_count": 0,
        "created_at": now,
        "updated_at": now,
        "created_by": data.get("created_by", ""),
    }
    await db._db.mdm_policies.insert_one(doc)
    doc.pop("_id", None)
    return doc


async def get_policy(policy_id: str, tenant_id: str) -> Optional[Dict]:
    db = get_database()
    doc = await db._db.mdm_policies.find_one({"id": policy_id, "tenantId": tenant_id})
    if doc:
        doc.pop("_id", None)
    return doc


async def delete_policy(policy_id: str, tenant_id: str) -> bool:
    db = get_database()
    result = await db._db.mdm_policies.delete_one({"id": policy_id, "tenantId": tenant_id})
    return result.deleted_count > 0


async def generate_enrollment_url(tenant_id: str, platform: str) -> Dict[str, Any]:
    """Generate a one-time enrollment token/URL for mobile device registration."""
    if platform not in ("ios", "android"):
        raise ValueError("platform must be 'ios' or 'android'")
    token = secrets.token_urlsafe(24)
    db = get_database()
    now = datetime.now(timezone.utc).isoformat()
    await db._db.mdm_enrollment_tokens.insert_one({
        "token": token,
        "tenantId": tenant_id,
        "platform": platform,
        "used": False,
        "created_at": now,
    })
    return {
        "enrollment_url": f"/enroll/mdm/{platform}?token={token}",
        "token": token,
        "platform": platform,
        "qr_hint": f"Scan to enroll {platform.upper()} device",
        "expires_in_hours": 24,
    }

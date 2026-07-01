"""
Android Enterprise and Samsung Knox Integration Service.
Manages Android Enterprise enrollment profiles (Work Profile, Fully Managed,
Dedicated Device) and Samsung Knox license/KME enrollment.
"""

import uuid
import secrets
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from database import get_database

logger = logging.getLogger(__name__)

ENROLLMENT_MODES = [
    "work_profile",
    "fully_managed",
    "dedicated_device",
    "corporate_owned_work_profile",
]


async def list_profiles(tenant_id: str) -> List[Dict[str, Any]]:
    db = get_database()
    cursor = db._db.android_enterprise_profiles.find({"tenantId": tenant_id}).sort("created_at", -1)
    docs = await cursor.to_list(length=500)
    for d in docs:
        d.pop("_id", None)
    return docs


async def get_profile(tenant_id: str, profile_id: str) -> Optional[Dict[str, Any]]:
    db = get_database()
    doc = await db._db.android_enterprise_profiles.find_one({"tenantId": tenant_id, "id": profile_id})
    if doc:
        doc.pop("_id", None)
    return doc


async def create_profile(tenant_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
    name = (data.get("name") or "").strip()
    if not name:
        raise ValueError("Profile name is required")
    mode = data.get("enrollment_mode", "work_profile")
    if mode not in ENROLLMENT_MODES:
        raise ValueError(f"Invalid enrollment_mode. Must be one of: {ENROLLMENT_MODES}")
    now = datetime.now(timezone.utc).isoformat()
    token = secrets.token_urlsafe(32)
    doc = {
        "id": str(uuid.uuid4()),
        "tenantId": tenant_id,
        "name": name,
        "description": data.get("description", ""),
        "enrollment_mode": mode,
        "enrollment_token": token,
        "enrollment_url": f"https://enterprise.google.com/android/enroll?et={token}",
        "allowed_apps": data.get("allowed_apps", []),
        "blocked_apps": data.get("blocked_apps", []),
        "work_profile_password_required": bool(data.get("work_profile_password_required", True)),
        "camera_disabled": bool(data.get("camera_disabled", False)),
        "screen_capture_disabled": bool(data.get("screen_capture_disabled", False)),
        "play_store_mode": data.get("play_store_mode", "whitelist"),  # whitelist | blacklist | all
        "enabled": True,
        "device_count": 0,
        "created_at": now,
        "updated_at": now,
    }
    db = get_database()
    await db._db.android_enterprise_profiles.insert_one(doc)
    doc.pop("_id", None)
    return doc


async def update_profile(tenant_id: str, profile_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
    existing = await get_profile(tenant_id, profile_id)
    if not existing:
        raise ValueError(f"Profile {profile_id} not found")
    allowed = {
        "name", "description", "allowed_apps", "blocked_apps",
        "work_profile_password_required", "camera_disabled",
        "screen_capture_disabled", "play_store_mode", "enabled",
    }
    updates = {k: v for k, v in data.items() if k in allowed}
    updates["updated_at"] = datetime.now(timezone.utc).isoformat()
    db = get_database()
    await db._db.android_enterprise_profiles.update_one(
        {"tenantId": tenant_id, "id": profile_id}, {"$set": updates}
    )
    return {**existing, **updates}


async def delete_profile(tenant_id: str, profile_id: str) -> None:
    db = get_database()
    await db._db.android_enterprise_profiles.delete_one({"tenantId": tenant_id, "id": profile_id})


async def get_enrollment_url(tenant_id: str, profile_id: str) -> Dict[str, Any]:
    profile = await get_profile(tenant_id, profile_id)
    if not profile:
        raise ValueError(f"Profile {profile_id} not found")
    return {
        "profile_id": profile_id,
        "enrollment_url": profile["enrollment_url"],
        "enrollment_token": profile["enrollment_token"],
        "enrollment_mode": profile["enrollment_mode"],
        "qr_payload": f"ANDROIDENTERP:T:{profile['enrollment_token']};MODE:{profile['enrollment_mode']}",
    }


async def set_knox_license(tenant_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
    license_key = (data.get("license_key") or "").strip()
    if not license_key:
        raise ValueError("license_key is required")
    now = datetime.now(timezone.utc).isoformat()
    db = get_database()
    doc = {
        "tenantId": tenant_id,
        "license_key_masked": f"****-****-{license_key[-8:]}",
        "license_key": license_key,
        "kme_enabled": bool(data.get("kme_enabled", False)),
        "kme_server": data.get("kme_server", "https://kme.samsungknox.com"),
        "status": "active",
        "activated_at": now,
        "updated_at": now,
    }
    await db._db.knox_settings.update_one(
        {"tenantId": tenant_id},
        {"$set": doc},
        upsert=True,
    )
    safe = {k: v for k, v in doc.items() if k != "license_key"}
    return safe


async def get_knox_status(tenant_id: str) -> Dict[str, Any]:
    db = get_database()
    doc = await db._db.knox_settings.find_one({"tenantId": tenant_id})
    if not doc:
        return {"configured": False}
    doc.pop("_id", None)
    doc.pop("license_key", None)
    doc["configured"] = True
    return doc


async def configure_dedicated_device(tenant_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
    profile_id = data.get("profile_id", "")
    if not profile_id:
        raise ValueError("profile_id is required")
    now = datetime.now(timezone.utc).isoformat()
    config = {
        "tenantId": tenant_id,
        "profile_id": profile_id,
        "kiosk_app": data.get("kiosk_app", ""),
        "kiosk_url": data.get("kiosk_url", ""),
        "auto_launch": bool(data.get("auto_launch", True)),
        "hide_status_bar": bool(data.get("hide_status_bar", False)),
        "hide_navigation_bar": bool(data.get("hide_navigation_bar", False)),
        "lock_task_mode": bool(data.get("lock_task_mode", True)),
        "allowed_apps": data.get("allowed_apps", []),
        "updated_at": now,
    }
    db = get_database()
    await db._db.dedicated_device_configs.update_one(
        {"tenantId": tenant_id, "profile_id": profile_id},
        {"$set": config},
        upsert=True,
    )
    return config


async def list_dedicated_device_configs(tenant_id: str) -> List[Dict[str, Any]]:
    db = get_database()
    cursor = db._db.dedicated_device_configs.find({"tenantId": tenant_id})
    docs = await cursor.to_list(length=200)
    for d in docs:
        d.pop("_id", None)
    return docs

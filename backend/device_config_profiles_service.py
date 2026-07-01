"""
Device Configuration Profiles Service.
Manages Browser, USB, Wi-Fi, VPN, and Kiosk configuration profiles
that are pushed to managed devices.
"""

import uuid
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from database import get_database

logger = logging.getLogger(__name__)

PROFILE_TYPES = ["browser", "usb", "wifi", "vpn", "kiosk"]

PROFILE_TYPE_META = {
    "browser": {"label": "Browser Configuration", "platforms": ["windows", "macos", "linux"]},
    "usb": {"label": "USB Device Control", "platforms": ["windows", "macos"]},
    "wifi": {"label": "Wi-Fi Profile", "platforms": ["windows", "macos", "ios", "android"]},
    "vpn": {"label": "VPN Profile", "platforms": ["windows", "macos", "ios", "android"]},
    "kiosk": {"label": "Kiosk / Shared Device", "platforms": ["windows", "android", "ios"]},
}


def _validate_settings(profile_type: str, settings: Dict[str, Any]) -> Dict[str, Any]:
    if profile_type == "browser":
        return {
            "homepage": settings.get("homepage", ""),
            "force_safe_search": bool(settings.get("force_safe_search", False)),
            "allowed_urls": settings.get("allowed_urls", []),
            "blocked_urls": settings.get("blocked_urls", []),
            "extensions_policy": settings.get("extensions_policy", "allow_all"),
            "incognito_mode": settings.get("incognito_mode", "allow"),
            "password_manager_enabled": bool(settings.get("password_manager_enabled", True)),
        }
    if profile_type == "usb":
        return {
            "block_mass_storage": bool(settings.get("block_mass_storage", False)),
            "block_removable_media": bool(settings.get("block_removable_media", False)),
            "allowed_device_ids": settings.get("allowed_device_ids", []),
            "blocked_device_classes": settings.get("blocked_device_classes", []),
            "read_only_mode": bool(settings.get("read_only_mode", False)),
        }
    if profile_type == "wifi":
        return {
            "ssid": settings.get("ssid", ""),
            "security_type": settings.get("security_type", "WPA2"),
            "passphrase": settings.get("passphrase", ""),
            "hidden_network": bool(settings.get("hidden_network", False)),
            "auto_connect": bool(settings.get("auto_connect", True)),
            "proxy_type": settings.get("proxy_type", "none"),
            "proxy_server": settings.get("proxy_server", ""),
            "proxy_port": settings.get("proxy_port", 0),
            "eap_type": settings.get("eap_type", ""),
            "certificate_id": settings.get("certificate_id", ""),
        }
    if profile_type == "vpn":
        return {
            "vpn_type": settings.get("vpn_type", "IKEv2"),
            "server_address": settings.get("server_address", ""),
            "username": settings.get("username", ""),
            "auth_type": settings.get("auth_type", "password"),
            "certificate_id": settings.get("certificate_id", ""),
            "always_on": bool(settings.get("always_on", False)),
            "per_app_vpn": bool(settings.get("per_app_vpn", False)),
            "split_tunneling": bool(settings.get("split_tunneling", False)),
            "excluded_domains": settings.get("excluded_domains", []),
        }
    if profile_type == "kiosk":
        return {
            "kiosk_mode": settings.get("kiosk_mode", "single_app"),
            "allowed_apps": settings.get("allowed_apps", []),
            "auto_launch_app": settings.get("auto_launch_app", ""),
            "allow_settings": bool(settings.get("allow_settings", False)),
            "show_status_bar": bool(settings.get("show_status_bar", True)),
            "show_navigation_bar": bool(settings.get("show_navigation_bar", True)),
            "allowed_urls": settings.get("allowed_urls", []),
            "idle_timeout_minutes": int(settings.get("idle_timeout_minutes", 0)),
        }
    return settings


async def list_profiles(tenant_id: str, profile_type: Optional[str] = None) -> List[Dict[str, Any]]:
    db = get_database()
    filt: Dict[str, Any] = {"tenantId": tenant_id}
    if profile_type:
        filt["profile_type"] = profile_type
    cursor = db._db.device_config_profiles.find(filt).sort("created_at", -1)
    docs = await cursor.to_list(length=500)
    for d in docs:
        d.pop("_id", None)
    return docs


async def get_profile(tenant_id: str, profile_id: str) -> Optional[Dict[str, Any]]:
    db = get_database()
    doc = await db._db.device_config_profiles.find_one({"tenantId": tenant_id, "id": profile_id})
    if doc:
        doc.pop("_id", None)
    return doc


async def create_profile(tenant_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
    name = (data.get("name") or "").strip()
    if not name:
        raise ValueError("Profile name is required")
    profile_type = data.get("profile_type", "")
    if profile_type not in PROFILE_TYPES:
        raise ValueError(f"profile_type must be one of: {PROFILE_TYPES}")
    now = datetime.now(timezone.utc).isoformat()
    settings = _validate_settings(profile_type, data.get("settings", {}))
    doc = {
        "id": str(uuid.uuid4()),
        "tenantId": tenant_id,
        "name": name,
        "description": data.get("description", ""),
        "profile_type": profile_type,
        "platforms": data.get("platforms", PROFILE_TYPE_META[profile_type]["platforms"]),
        "settings": settings,
        "assigned_groups": data.get("assigned_groups", []),
        "assigned_devices": [],
        "enabled": True,
        "created_at": now,
        "updated_at": now,
    }
    db = get_database()
    await db._db.device_config_profiles.insert_one(doc)
    doc.pop("_id", None)
    return doc


async def update_profile(tenant_id: str, profile_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
    existing = await get_profile(tenant_id, profile_id)
    if not existing:
        raise ValueError(f"Profile {profile_id} not found")
    updates: Dict[str, Any] = {}
    if "name" in data:
        updates["name"] = data["name"]
    if "description" in data:
        updates["description"] = data["description"]
    if "platforms" in data:
        updates["platforms"] = data["platforms"]
    if "enabled" in data:
        updates["enabled"] = data["enabled"]
    if "settings" in data:
        updates["settings"] = _validate_settings(existing["profile_type"], data["settings"])
    if "assigned_groups" in data:
        updates["assigned_groups"] = data["assigned_groups"]
    updates["updated_at"] = datetime.now(timezone.utc).isoformat()
    db = get_database()
    await db._db.device_config_profiles.update_one(
        {"tenantId": tenant_id, "id": profile_id}, {"$set": updates}
    )
    return {**existing, **updates}


async def delete_profile(tenant_id: str, profile_id: str) -> None:
    db = get_database()
    await db._db.device_config_profiles.delete_one({"tenantId": tenant_id, "id": profile_id})


async def assign_profile(tenant_id: str, profile_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
    existing = await get_profile(tenant_id, profile_id)
    if not existing:
        raise ValueError(f"Profile {profile_id} not found")
    groups = data.get("groups", [])
    devices = data.get("devices", [])
    db = get_database()
    await db._db.device_config_profiles.update_one(
        {"tenantId": tenant_id, "id": profile_id},
        {
            "$addToSet": {
                "assigned_groups": {"$each": groups},
                "assigned_devices": {"$each": devices},
            },
            "$set": {"updated_at": datetime.now(timezone.utc).isoformat()},
        },
    )
    return {"profile_id": profile_id, "assigned_groups": groups, "assigned_devices": devices}


async def get_profile_types() -> List[Dict[str, Any]]:
    return [
        {"type": t, **meta}
        for t, meta in PROFILE_TYPE_META.items()
    ]

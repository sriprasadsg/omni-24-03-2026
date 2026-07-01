"""
Windows Autopilot Service
Manages device registration, deployment profiles, and enrollment status tracking.
"""

import uuid
import csv
import io
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from database import get_database

logger = logging.getLogger(__name__)

PROFILE_TYPES = ("user_driven", "self_deploying", "pre_provisioning", "white_glove")
DEPLOYMENT_MODES = ("azure_ad_join", "hybrid_azure_ad_join", "azure_ad_join_intune")
ESP_STAGES = ("device_preparation", "device_setup", "account_setup", "completed", "failed")


async def get_summary(tenant_id: str) -> Dict[str, Any]:
    db = get_database()
    total = await db._db.autopilot_devices.count_documents({"tenantId": tenant_id})
    enrolled = await db._db.autopilot_devices.count_documents({"tenantId": tenant_id, "status": "enrolled"})
    deploying = await db._db.autopilot_devices.count_documents({"tenantId": tenant_id, "status": "deploying"})
    failed = await db._db.autopilot_devices.count_documents({"tenantId": tenant_id, "status": "failed"})
    profiles = await db._db.autopilot_profiles.count_documents({"tenantId": tenant_id})
    return {
        "total_devices": total,
        "enrolled": enrolled,
        "deploying": deploying,
        "failed": failed,
        "registered": max(0, total - enrolled - deploying - failed),
        "total_profiles": profiles,
    }


async def list_devices(tenant_id: str, status: Optional[str] = None, limit: int = 100) -> List[Dict]:
    db = get_database()
    filt: Dict[str, Any] = {"tenantId": tenant_id}
    if status:
        filt["status"] = status
    cursor = db._db.autopilot_devices.find(filt).sort("registered_at", -1).limit(limit)
    docs = await cursor.to_list(length=limit)
    for d in docs:
        d.pop("_id", None)
    return docs


async def register_device(tenant_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
    db = get_database()
    serial = data.get("serial_number", "").strip()
    if not serial:
        raise ValueError("serial_number is required")

    existing = await db._db.autopilot_devices.find_one({"tenantId": tenant_id, "serial_number": serial})
    if existing:
        raise ValueError(f"Device with serial '{serial}' is already registered")

    now = datetime.now(timezone.utc).isoformat()
    doc = {
        "id": str(uuid.uuid4()),
        "tenantId": tenant_id,
        "serial_number": serial,
        "hardware_hash": data.get("hardware_hash", ""),
        "manufacturer": data.get("manufacturer", ""),
        "model": data.get("model", ""),
        "product_key": data.get("product_key", ""),
        "group_tag": data.get("group_tag", ""),
        "assigned_user": data.get("assigned_user", ""),
        "profile_id": data.get("profile_id") or None,
        "status": "registered",
        "esp_stage": None,
        "esp_progress": 0,
        "esp_error": None,
        "last_contact": None,
        "enrolled_at": None,
        "registered_at": now,
        "updated_at": now,
        "notes": data.get("notes", ""),
    }
    await db._db.autopilot_devices.insert_one(doc)
    doc.pop("_id", None)
    return doc


async def import_devices_csv(tenant_id: str, csv_content: str) -> Dict[str, Any]:
    """Parse Microsoft hardware hash CSV format and bulk-register devices."""
    reader = csv.DictReader(io.StringIO(csv_content))
    imported, skipped, errors = 0, 0, []

    for row in reader:
        serial = (row.get("Device Serial Number") or row.get("serial_number") or "").strip()
        if not serial:
            continue
        try:
            await register_device(tenant_id, {
                "serial_number": serial,
                "hardware_hash": row.get("Hardware Hash") or row.get("hardware_hash") or "",
                "manufacturer": row.get("Manufacturer") or row.get("manufacturer") or "",
                "model": row.get("Model") or row.get("model") or "",
                "product_key": row.get("Windows Product ID") or row.get("product_key") or "",
                "group_tag": row.get("Group Tag") or row.get("group_tag") or "",
                "assigned_user": row.get("Assigned User") or row.get("assigned_user") or "",
            })
            imported += 1
        except ValueError:
            skipped += 1
        except Exception as exc:
            errors.append(f"{serial}: {exc}")

    return {"imported": imported, "skipped": skipped, "errors": errors}


async def get_device(device_id: str, tenant_id: str) -> Optional[Dict]:
    db = get_database()
    doc = await db._db.autopilot_devices.find_one({"id": device_id, "tenantId": tenant_id})
    if doc:
        doc.pop("_id", None)
    return doc


async def update_device(device_id: str, tenant_id: str, data: Dict[str, Any]) -> Optional[Dict]:
    db = get_database()
    allowed = {"group_tag", "assigned_user", "profile_id", "notes", "status"}
    update = {k: v for k, v in data.items() if k in allowed}
    if not update:
        raise ValueError("No updatable fields provided")
    update["updated_at"] = datetime.now(timezone.utc).isoformat()
    await db._db.autopilot_devices.update_one(
        {"id": device_id, "tenantId": tenant_id},
        {"$set": update},
    )
    return await get_device(device_id, tenant_id)


async def delete_device(device_id: str, tenant_id: str) -> bool:
    db = get_database()
    result = await db._db.autopilot_devices.delete_one({"id": device_id, "tenantId": tenant_id})
    return result.deleted_count > 0


# ── Deployment Profiles ───────────────────────────────────────────────────────

async def list_profiles(tenant_id: str) -> List[Dict]:
    db = get_database()
    cursor = db._db.autopilot_profiles.find({"tenantId": tenant_id}).sort("created_at", -1)
    docs = await cursor.to_list(length=200)
    for d in docs:
        d.pop("_id", None)
    return docs


async def create_profile(tenant_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
    db = get_database()
    name = data.get("name", "").strip()
    if not name:
        raise ValueError("Profile name is required")
    if data.get("profile_type", "user_driven") not in PROFILE_TYPES:
        raise ValueError(f"profile_type must be one of {PROFILE_TYPES}")
    if data.get("deployment_mode", "azure_ad_join") not in DEPLOYMENT_MODES:
        raise ValueError(f"deployment_mode must be one of {DEPLOYMENT_MODES}")

    now = datetime.now(timezone.utc).isoformat()
    doc = {
        "id": str(uuid.uuid4()),
        "tenantId": tenant_id,
        "name": name,
        "description": data.get("description", ""),
        "profile_type": data.get("profile_type", "user_driven"),
        "deployment_mode": data.get("deployment_mode", "azure_ad_join"),
        "language": data.get("language", "os_default"),
        "keyboard": data.get("keyboard", "os_default"),
        "skip_keyboard_selection": bool(data.get("skip_keyboard_selection", False)),
        "hide_privacy_settings": bool(data.get("hide_privacy_settings", True)),
        "hide_eula": bool(data.get("hide_eula", True)),
        "skip_account_setup": bool(data.get("skip_account_setup", False)),
        "auto_enroll_mdm": bool(data.get("auto_enroll_mdm", True)),
        "apply_device_name_template": data.get("apply_device_name_template", ""),
        "allowed_group": data.get("allowed_group", ""),
        "assigned_devices_count": 0,
        "created_at": now,
        "updated_at": now,
        "created_by": data.get("created_by", ""),
    }
    await db._db.autopilot_profiles.insert_one(doc)
    doc.pop("_id", None)
    return doc


async def get_profile(profile_id: str, tenant_id: str) -> Optional[Dict]:
    db = get_database()
    doc = await db._db.autopilot_profiles.find_one({"id": profile_id, "tenantId": tenant_id})
    if doc:
        doc.pop("_id", None)
    return doc


async def update_profile(profile_id: str, tenant_id: str, data: Dict[str, Any]) -> Optional[Dict]:
    db = get_database()
    allowed = {
        "name", "description", "profile_type", "deployment_mode", "language", "keyboard",
        "skip_keyboard_selection", "hide_privacy_settings", "hide_eula",
        "skip_account_setup", "auto_enroll_mdm", "apply_device_name_template", "allowed_group",
    }
    update = {k: v for k, v in data.items() if k in allowed}
    if not update:
        raise ValueError("No updatable fields provided")
    update["updated_at"] = datetime.now(timezone.utc).isoformat()
    await db._db.autopilot_profiles.update_one(
        {"id": profile_id, "tenantId": tenant_id},
        {"$set": update},
    )
    return await get_profile(profile_id, tenant_id)


async def delete_profile(profile_id: str, tenant_id: str) -> bool:
    db = get_database()
    count = await db._db.autopilot_devices.count_documents({"tenantId": tenant_id, "profile_id": profile_id})
    if count > 0:
        raise ValueError(f"Cannot delete: {count} device(s) still assigned to this profile")
    result = await db._db.autopilot_profiles.delete_one({"id": profile_id, "tenantId": tenant_id})
    return result.deleted_count > 0


async def assign_profile(profile_id: str, device_ids: List[str], tenant_id: str) -> Dict[str, Any]:
    db = get_database()
    if not await get_profile(profile_id, tenant_id):
        raise ValueError("Profile not found")

    updated = 0
    now = datetime.now(timezone.utc).isoformat()
    for device_id in device_ids:
        result = await db._db.autopilot_devices.update_one(
            {"id": device_id, "tenantId": tenant_id},
            {"$set": {"profile_id": profile_id, "status": "assigned", "updated_at": now}},
        )
        if result.modified_count:
            updated += 1

    total_assigned = await db._db.autopilot_devices.count_documents({"tenantId": tenant_id, "profile_id": profile_id})
    await db._db.autopilot_profiles.update_one(
        {"id": profile_id, "tenantId": tenant_id},
        {"$set": {"assigned_devices_count": total_assigned}},
    )
    return {"updated": updated, "total_assigned": total_assigned}


# ── ESP (Enrollment Status Page) ─────────────────────────────────────────────

async def update_esp_status(
    device_id: str,
    tenant_id: str,
    stage: str,
    progress: int,
    error: Optional[str] = None,
) -> Optional[Dict]:
    """Update ESP progress — called by the Windows agent during enrollment."""
    if stage not in ESP_STAGES:
        raise ValueError(f"stage must be one of {ESP_STAGES}")

    db = get_database()
    new_status = "enrolled" if stage == "completed" else ("failed" if stage == "failed" else "deploying")
    now = datetime.now(timezone.utc).isoformat()

    update: Dict[str, Any] = {
        "esp_stage": stage,
        "esp_progress": min(max(progress, 0), 100),
        "status": new_status,
        "last_contact": now,
        "updated_at": now,
    }
    if stage == "completed":
        update["enrolled_at"] = now
    if error:
        update["esp_error"] = error

    await db._db.autopilot_devices.update_one(
        {"id": device_id, "tenantId": tenant_id},
        {"$set": update},
    )
    return await get_device(device_id, tenant_id)


async def list_esp_events(tenant_id: str, limit: int = 50) -> List[Dict]:
    db = get_database()
    cursor = db._db.autopilot_devices.find(
        {"tenantId": tenant_id, "esp_stage": {"$ne": None}},
        projection={
            "id": 1, "serial_number": 1, "model": 1, "manufacturer": 1,
            "esp_stage": 1, "esp_progress": 1, "esp_error": 1,
            "status": 1, "last_contact": 1, "enrolled_at": 1,
        },
    ).sort("last_contact", -1).limit(limit)
    docs = await cursor.to_list(length=limit)
    for d in docs:
        d.pop("_id", None)
    return docs

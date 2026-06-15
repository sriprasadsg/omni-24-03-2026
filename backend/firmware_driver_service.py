"""
Firmware and Driver Update Management Service.
Tracks driver inventory, firmware (BIOS/UEFI) versions per asset,
provides available update catalog, and manages deployment jobs.
"""

import uuid
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from database import get_database

logger = logging.getLogger(__name__)

# Mock update catalog — in production this comes from vendor APIs (Windows Update, Dell OMSA, etc.)
DRIVER_UPDATE_CATALOG: List[Dict[str, Any]] = [
    {
        "id": "drv-upd-001",
        "type": "driver",
        "component": "Intel Network Adapter",
        "current_version": "12.18.9.1",
        "available_version": "12.19.0.23",
        "manufacturer": "Intel",
        "severity": "optional",
        "release_date": "2024-03-15",
        "kb_article": "KB5034766",
    },
    {
        "id": "drv-upd-002",
        "type": "driver",
        "component": "NVIDIA Display Adapter",
        "current_version": "551.23",
        "available_version": "555.85",
        "manufacturer": "NVIDIA",
        "severity": "recommended",
        "release_date": "2024-04-01",
        "kb_article": "",
    },
    {
        "id": "drv-upd-003",
        "type": "driver",
        "component": "Realtek Audio",
        "current_version": "6.0.9235.1",
        "available_version": "6.0.9440.1",
        "manufacturer": "Realtek",
        "severity": "optional",
        "release_date": "2024-02-20",
        "kb_article": "",
    },
    {
        "id": "drv-upd-004",
        "type": "firmware",
        "component": "Dell BIOS",
        "current_version": "1.12.0",
        "available_version": "1.15.1",
        "manufacturer": "Dell",
        "severity": "critical",
        "release_date": "2024-05-10",
        "kb_article": "DSA-2024-108",
    },
    {
        "id": "drv-upd-005",
        "type": "firmware",
        "component": "HP System BIOS",
        "current_version": "Q76 Ver. 02.18.00",
        "available_version": "Q76 Ver. 02.21.00",
        "manufacturer": "HP",
        "severity": "recommended",
        "release_date": "2024-04-22",
        "kb_article": "HPSBHF03898",
    },
    {
        "id": "drv-upd-006",
        "type": "firmware",
        "component": "Intel ME Firmware",
        "current_version": "16.0.15.1845",
        "available_version": "16.1.25.2024",
        "manufacturer": "Intel",
        "severity": "critical",
        "release_date": "2024-05-01",
        "kb_article": "INTEL-SA-00999",
    },
]

MOCK_DRIVER_INVENTORY: List[Dict[str, Any]] = [
    {"component": "Intel Network Adapter", "type": "driver", "version": "12.18.9.1", "manufacturer": "Intel", "date": "2022-11-14", "status": "outdated"},
    {"component": "NVIDIA Display Adapter", "type": "driver", "version": "551.23", "manufacturer": "NVIDIA", "date": "2024-01-10", "status": "outdated"},
    {"component": "Realtek Audio", "type": "driver", "version": "6.0.9235.1", "manufacturer": "Realtek", "date": "2023-03-05", "status": "outdated"},
    {"component": "USB 3.0 Host Controller", "type": "driver", "version": "3.0.210.0", "manufacturer": "Intel", "date": "2023-06-20", "status": "current"},
    {"component": "Bluetooth Device", "type": "driver", "version": "22.110.0", "manufacturer": "Intel", "date": "2023-09-15", "status": "current"},
]

MOCK_FIRMWARE_INVENTORY: List[Dict[str, Any]] = [
    {"component": "System BIOS", "type": "firmware", "version": "1.12.0", "manufacturer": "Dell", "date": "2022-08-10", "status": "outdated"},
    {"component": "Intel ME Firmware", "type": "firmware", "version": "16.0.15.1845", "manufacturer": "Intel", "date": "2023-01-05", "status": "outdated"},
    {"component": "EC Firmware", "type": "firmware", "version": "1.08.0", "manufacturer": "Dell", "date": "2023-06-01", "status": "current"},
    {"component": "NVMe SSD Firmware", "type": "firmware", "version": "CN5.3", "manufacturer": "Samsung", "date": "2023-04-12", "status": "current"},
]


async def get_inventory(tenant_id: str) -> Dict[str, Any]:
    db = get_database()
    cursor = db._db.assets.find({"tenantId": tenant_id}).limit(50)
    assets = await cursor.to_list(length=50)
    records = []
    for asset in assets:
        asset_id = str(asset.get("_id", asset.get("id", "")))
        for item in MOCK_DRIVER_INVENTORY:
            records.append({
                "asset_id": asset_id,
                "asset_name": asset.get("name", asset.get("hostname", "Unknown")),
                **item,
            })
        for item in MOCK_FIRMWARE_INVENTORY:
            records.append({
                "asset_id": asset_id,
                "asset_name": asset.get("name", asset.get("hostname", "Unknown")),
                **item,
            })
    return {
        "total": len(records),
        "outdated": sum(1 for r in records if r["status"] == "outdated"),
        "current": sum(1 for r in records if r["status"] == "current"),
        "items": records[:200],
    }


async def get_asset_inventory(tenant_id: str, asset_id: str) -> Dict[str, Any]:
    items = [*MOCK_DRIVER_INVENTORY, *MOCK_FIRMWARE_INVENTORY]
    return {
        "asset_id": asset_id,
        "drivers": [i for i in items if i["type"] == "driver"],
        "firmware": [i for i in items if i["type"] == "firmware"],
    }


async def get_available_updates(tenant_id: str, update_type: Optional[str] = None) -> List[Dict[str, Any]]:
    catalog = DRIVER_UPDATE_CATALOG
    if update_type in ("driver", "firmware"):
        catalog = [u for u in catalog if u["type"] == update_type]
    return catalog


async def create_deployment_job(tenant_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
    update_ids = data.get("update_ids", [])
    target_devices = data.get("target_devices", [])
    if not update_ids:
        raise ValueError("update_ids is required")
    now = datetime.now(timezone.utc).isoformat()
    job = {
        "id": str(uuid.uuid4()),
        "tenantId": tenant_id,
        "name": data.get("name", f"Firmware/Driver Update Job {now[:10]}"),
        "update_ids": update_ids,
        "target_devices": target_devices,
        "target_groups": data.get("target_groups", []),
        "schedule": data.get("schedule", "immediate"),
        "status": "pending",
        "created_at": now,
        "updated_at": now,
        "completed_at": None,
        "success_count": 0,
        "failure_count": 0,
    }
    db = get_database()
    await db._db.firmware_driver_jobs.insert_one(job)
    job.pop("_id", None)
    return job


async def list_deployment_jobs(tenant_id: str) -> List[Dict[str, Any]]:
    db = get_database()
    cursor = db._db.firmware_driver_jobs.find({"tenantId": tenant_id}).sort("created_at", -1).limit(100)
    docs = await cursor.to_list(length=100)
    for d in docs:
        d.pop("_id", None)
    return docs


async def get_compliance_report(tenant_id: str) -> Dict[str, Any]:
    db = get_database()
    total_assets = await db._db.assets.count_documents({"tenantId": tenant_id})
    outdated_drivers = len([i for i in MOCK_DRIVER_INVENTORY if i["status"] == "outdated"])
    outdated_firmware = len([i for i in MOCK_FIRMWARE_INVENTORY if i["status"] == "outdated"])
    return {
        "total_assets": total_assets,
        "assets_with_outdated_drivers": min(total_assets, outdated_drivers),
        "assets_with_outdated_firmware": min(total_assets, outdated_firmware),
        "critical_updates_pending": sum(1 for u in DRIVER_UPDATE_CATALOG if u["severity"] == "critical"),
        "driver_compliance_pct": max(0, round(100 - (outdated_drivers / max(len(MOCK_DRIVER_INVENTORY), 1)) * 100, 1)),
        "firmware_compliance_pct": max(0, round(100 - (outdated_firmware / max(len(MOCK_FIRMWARE_INVENTORY), 1)) * 100, 1)),
    }

"""
End-of-Life Asset Detection and Rogue Asset Detection Service.
Identifies assets running EOL operating systems/software and detects unauthorized devices.
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from database import get_database

logger = logging.getLogger(__name__)

# EOL database: platform -> {version_prefix -> eol_date ISO string}
EOL_DATABASE: Dict[str, Dict[str, str]] = {
    "windows": {
        "Windows 7": "2020-01-14",
        "Windows 8": "2016-01-12",
        "Windows 8.1": "2023-01-10",
        "Windows 10 1507": "2017-05-09",
        "Windows 10 1511": "2017-10-10",
        "Windows 10 1607": "2018-04-10",
        "Windows 10 1703": "2018-10-09",
        "Windows 10 1709": "2019-04-09",
        "Windows 10 1803": "2019-11-12",
        "Windows 10 1809": "2021-05-11",
        "Windows 10 1903": "2020-12-08",
        "Windows 10 1909": "2021-05-11",
        "Windows 10 2004": "2021-12-14",
        "Windows 10 20H2": "2022-05-10",
        "Windows 10 21H1": "2022-12-13",
        "Windows 10 21H2": "2023-06-13",
        "Windows Server 2008": "2020-01-14",
        "Windows Server 2012": "2023-10-10",
        "Windows Server 2012 R2": "2023-10-10",
        "Windows Server 2016": "2027-01-12",
    },
    "linux": {
        "Ubuntu 14.04": "2019-04-30",
        "Ubuntu 16.04": "2021-04-30",
        "Ubuntu 18.04": "2023-04-30",
        "Ubuntu 20.04": "2025-04-30",
        "CentOS 6": "2020-11-30",
        "CentOS 7": "2024-06-30",
        "CentOS 8": "2021-12-31",
        "Debian 8": "2020-06-30",
        "Debian 9": "2022-06-30",
        "Debian 10": "2024-06-30",
        "RHEL 6": "2020-11-30",
        "RHEL 7": "2024-06-30",
    },
    "macos": {
        "macOS 10.13": "2022-11-30",
        "macOS 10.14": "2023-11-30",
        "macOS 10.15": "2022-11-30",
        "macOS 11": "2023-09-26",
        "macOS 12": "2024-09-16",
    },
}


def _days_since_eol(eol_date_str: str) -> int:
    eol = datetime.fromisoformat(eol_date_str).replace(tzinfo=timezone.utc)
    now = datetime.now(timezone.utc)
    return (now - eol).days


def _eol_severity(days_past: int) -> str:
    if days_past > 730:
        return "critical"
    if days_past > 365:
        return "high"
    if days_past > 90:
        return "medium"
    return "low"


def _match_eol(os_name: str) -> Optional[str]:
    for _platform, versions in EOL_DATABASE.items():
        for prefix, eol_date in versions.items():
            if os_name.startswith(prefix):
                return eol_date
    return None


async def get_eol_assets(tenant_id: str) -> List[Dict[str, Any]]:
    db = get_database()
    cursor = db._db.assets.find({"tenantId": tenant_id, "os": {"$exists": True, "$ne": ""}})
    assets = await cursor.to_list(length=2000)
    results = []
    for asset in assets:
        os_name = asset.get("os", "")
        eol_date = _match_eol(os_name)
        if eol_date:
            days_past = _days_since_eol(eol_date)
            results.append({
                "id": str(asset.get("_id", asset.get("id", ""))),
                "name": asset.get("name", asset.get("hostname", "Unknown")),
                "ip": asset.get("ip", asset.get("ipAddress", "")),
                "os": os_name,
                "eol_date": eol_date,
                "days_past_eol": days_past,
                "severity": _eol_severity(days_past),
                "last_seen": asset.get("lastSeen", asset.get("last_seen", "")),
            })
    results.sort(key=lambda x: x["days_past_eol"], reverse=True)
    return results


async def get_eol_summary(tenant_id: str) -> Dict[str, Any]:
    items = await get_eol_assets(tenant_id)
    counts: Dict[str, int] = {"critical": 0, "high": 0, "medium": 0, "low": 0}
    for item in items:
        counts[item["severity"]] += 1
    return {
        "total": len(items),
        "by_severity": counts,
    }


async def get_rogue_assets(tenant_id: str) -> List[Dict[str, Any]]:
    db = get_database()
    cursor = db._db.assets.find({
        "tenantId": tenant_id,
        "$or": [
            {"authorized": False},
            {"authorized": {"$exists": False}},
        ],
        "source": {"$in": ["discovery", "network_scan", "arp_scan"]},
    })
    assets = await cursor.to_list(length=2000)
    results = []
    for asset in assets:
        results.append({
            "id": str(asset.get("_id", asset.get("id", ""))),
            "name": asset.get("name", asset.get("hostname", "Unknown")),
            "ip": asset.get("ip", asset.get("ipAddress", "")),
            "mac": asset.get("mac", asset.get("macAddress", "")),
            "os": asset.get("os", ""),
            "first_seen": asset.get("createdAt", asset.get("created_at", "")),
            "last_seen": asset.get("lastSeen", asset.get("last_seen", "")),
            "source": asset.get("source", "discovery"),
            "authorized": asset.get("authorized", False),
        })
    return results


async def get_rogue_summary(tenant_id: str) -> Dict[str, Any]:
    items = await get_rogue_assets(tenant_id)
    return {
        "total": len(items),
        "unauthorized": sum(1 for i in items if not i.get("authorized")),
    }


async def authorize_asset(tenant_id: str, asset_id: str) -> Dict[str, Any]:
    db = get_database()
    from bson import ObjectId
    try:
        filt: Dict[str, Any] = {"tenantId": tenant_id}
        try:
            filt["_id"] = ObjectId(asset_id)
        except Exception:
            filt["id"] = asset_id
        result = await db._db.assets.update_one(
            filt,
            {"$set": {"authorized": True, "authorizedAt": datetime.now(timezone.utc).isoformat()}},
        )
        if result.matched_count == 0:
            raise ValueError(f"Asset {asset_id} not found")
        return {"asset_id": asset_id, "authorized": True}
    except ValueError:
        raise
    except Exception as exc:
        logger.error("[EolRogue] authorize_asset error: %s", exc)
        raise

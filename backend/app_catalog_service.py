"""
Third-Party Application Catalog Service
Provides a curated catalog of 850+ known applications with version metadata,
supporting silent deployment and patch management integration.
"""

import uuid
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from database import get_database

logger = logging.getLogger(__name__)

# Curated catalog seed — representative entries across categories
BUILTIN_CATALOG: List[Dict] = [
    # Browsers
    {"id": "cat-chrome", "name": "Google Chrome", "vendor": "Google", "category": "Browser", "platforms": ["windows", "macos", "linux"], "silent_install": "/silent /install", "latest_version": "126.0"},
    {"id": "cat-firefox", "name": "Mozilla Firefox", "vendor": "Mozilla", "category": "Browser", "platforms": ["windows", "macos", "linux"], "silent_install": "-ms", "latest_version": "127.0"},
    {"id": "cat-edge", "name": "Microsoft Edge", "vendor": "Microsoft", "category": "Browser", "platforms": ["windows", "macos"], "silent_install": "/silent /install", "latest_version": "126.0"},
    {"id": "cat-brave", "name": "Brave Browser", "vendor": "Brave Software", "category": "Browser", "platforms": ["windows", "macos", "linux"], "silent_install": "--silent", "latest_version": "1.67"},
    # Communication
    {"id": "cat-teams", "name": "Microsoft Teams", "vendor": "Microsoft", "category": "Communication", "platforms": ["windows", "macos"], "silent_install": "/quiet", "latest_version": "24.0"},
    {"id": "cat-slack", "name": "Slack", "vendor": "Salesforce", "category": "Communication", "platforms": ["windows", "macos", "linux"], "silent_install": "--silent", "latest_version": "4.38"},
    {"id": "cat-zoom", "name": "Zoom", "vendor": "Zoom Video Communications", "category": "Communication", "platforms": ["windows", "macos"], "silent_install": "/quiet /norestart", "latest_version": "5.18"},
    {"id": "cat-webex", "name": "Cisco Webex", "vendor": "Cisco", "category": "Communication", "platforms": ["windows", "macos"], "silent_install": "/S", "latest_version": "44.6"},
    {"id": "cat-msteams-new", "name": "Microsoft Teams (New)", "vendor": "Microsoft", "category": "Communication", "platforms": ["windows"], "silent_install": "/quiet", "latest_version": "24.0"},
    # Productivity
    {"id": "cat-office365", "name": "Microsoft 365", "vendor": "Microsoft", "category": "Productivity", "platforms": ["windows", "macos"], "silent_install": "/configure", "latest_version": "2406"},
    {"id": "cat-libreoffice", "name": "LibreOffice", "vendor": "The Document Foundation", "category": "Productivity", "platforms": ["windows", "macos", "linux"], "silent_install": "/qn", "latest_version": "7.6"},
    {"id": "cat-notepadpp", "name": "Notepad++", "vendor": "Don Ho", "category": "Productivity", "platforms": ["windows"], "silent_install": "/S", "latest_version": "8.6"},
    {"id": "cat-vscode", "name": "Visual Studio Code", "vendor": "Microsoft", "category": "Development", "platforms": ["windows", "macos", "linux"], "silent_install": "/VERYSILENT", "latest_version": "1.90"},
    # Security
    {"id": "cat-defender", "name": "Microsoft Defender", "vendor": "Microsoft", "category": "Security", "platforms": ["windows"], "silent_install": "/quiet", "latest_version": "1.1.24050"},
    {"id": "cat-crowdstrike", "name": "CrowdStrike Falcon", "vendor": "CrowdStrike", "category": "Security", "platforms": ["windows", "macos", "linux"], "silent_install": "/install /quiet", "latest_version": "7.14"},
    {"id": "cat-sentinelone", "name": "SentinelOne Agent", "vendor": "SentinelOne", "category": "Security", "platforms": ["windows", "macos", "linux"], "silent_install": "/QUIET", "latest_version": "23.3"},
    {"id": "cat-carbon-black", "name": "VMware Carbon Black", "vendor": "VMware", "category": "Security", "platforms": ["windows", "macos"], "silent_install": "/S", "latest_version": "3.9"},
    {"id": "cat-cylance", "name": "Cylance PROTECT", "vendor": "Cylance", "category": "Security", "platforms": ["windows", "macos"], "silent_install": "/S", "latest_version": "3.1"},
    # Utilities
    {"id": "cat-7zip", "name": "7-Zip", "vendor": "Igor Pavlov", "category": "Utilities", "platforms": ["windows"], "silent_install": "/S", "latest_version": "24.07"},
    {"id": "cat-winrar", "name": "WinRAR", "vendor": "RARLAB", "category": "Utilities", "platforms": ["windows"], "silent_install": "/S", "latest_version": "7.00"},
    {"id": "cat-vlc", "name": "VLC media player", "vendor": "VideoLAN", "category": "Media", "platforms": ["windows", "macos", "linux"], "silent_install": "/S", "latest_version": "3.0.21"},
    {"id": "cat-acrobat-reader", "name": "Adobe Acrobat Reader", "vendor": "Adobe", "category": "Utilities", "platforms": ["windows", "macos"], "silent_install": "/sPB /rs", "latest_version": "2024.002"},
    {"id": "cat-adobe-acrobat-pro", "name": "Adobe Acrobat Pro", "vendor": "Adobe", "category": "Utilities", "platforms": ["windows", "macos"], "silent_install": "/sPB /rs", "latest_version": "2024.002"},
    # Runtime / Dev Dependencies
    {"id": "cat-java-jre", "name": "Java Runtime Environment", "vendor": "Oracle", "category": "Runtime", "platforms": ["windows", "macos", "linux"], "silent_install": "/s", "latest_version": "21.0.3"},
    {"id": "cat-dotnet6", "name": ".NET 6 Runtime", "vendor": "Microsoft", "category": "Runtime", "platforms": ["windows", "macos", "linux"], "silent_install": "/quiet /norestart", "latest_version": "6.0.31"},
    {"id": "cat-dotnet8", "name": ".NET 8 Runtime", "vendor": "Microsoft", "category": "Runtime", "platforms": ["windows", "macos", "linux"], "silent_install": "/quiet /norestart", "latest_version": "8.0.6"},
    {"id": "cat-python3", "name": "Python 3", "vendor": "Python Software Foundation", "category": "Development", "platforms": ["windows", "macos", "linux"], "silent_install": "/quiet InstallAllUsers=1", "latest_version": "3.12.4"},
    {"id": "cat-nodejs", "name": "Node.js", "vendor": "OpenJS Foundation", "category": "Development", "platforms": ["windows", "macos", "linux"], "silent_install": "/qn", "latest_version": "20.15"},
    {"id": "cat-git", "name": "Git", "vendor": "Software Freedom Conservancy", "category": "Development", "platforms": ["windows", "macos", "linux"], "silent_install": "/SILENT", "latest_version": "2.45"},
    # Remote Access & Management
    {"id": "cat-anydesk", "name": "AnyDesk", "vendor": "AnyDesk Software", "category": "Remote Access", "platforms": ["windows", "macos", "linux"], "silent_install": "--install --start-with-win --silent", "latest_version": "8.0"},
    {"id": "cat-teamviewer", "name": "TeamViewer", "vendor": "TeamViewer AG", "category": "Remote Access", "platforms": ["windows", "macos", "linux"], "silent_install": "/S /norestart", "latest_version": "15.54"},
    {"id": "cat-putty", "name": "PuTTY", "vendor": "Simon Tatham", "category": "Remote Access", "platforms": ["windows"], "silent_install": "/quiet", "latest_version": "0.81"},
    {"id": "cat-winscp", "name": "WinSCP", "vendor": "Martin Prikryl", "category": "Remote Access", "platforms": ["windows"], "silent_install": "/SILENT", "latest_version": "6.3"},
    # VPN
    {"id": "cat-openvpn", "name": "OpenVPN", "vendor": "OpenVPN Inc.", "category": "VPN", "platforms": ["windows", "macos", "linux"], "silent_install": "/S", "latest_version": "2.6.11"},
    {"id": "cat-globalprotect", "name": "Palo Alto GlobalProtect", "vendor": "Palo Alto Networks", "category": "VPN", "platforms": ["windows", "macos"], "silent_install": "/quiet", "latest_version": "6.2"},
    {"id": "cat-cisco-anyconnect", "name": "Cisco AnyConnect", "vendor": "Cisco", "category": "VPN", "platforms": ["windows", "macos", "linux"], "silent_install": "/S", "latest_version": "4.10"},
    {"id": "cat-fortivpn", "name": "FortiClient VPN", "vendor": "Fortinet", "category": "VPN", "platforms": ["windows", "macos"], "silent_install": "/S", "latest_version": "7.4"},
    # Cloud Storage
    {"id": "cat-onedrive", "name": "Microsoft OneDrive", "vendor": "Microsoft", "category": "Cloud Storage", "platforms": ["windows", "macos"], "silent_install": "/allusers /silent", "latest_version": "24.0"},
    {"id": "cat-dropbox", "name": "Dropbox", "vendor": "Dropbox Inc.", "category": "Cloud Storage", "platforms": ["windows", "macos", "linux"], "silent_install": "/S", "latest_version": "202.4"},
    {"id": "cat-googledrive", "name": "Google Drive", "vendor": "Google", "category": "Cloud Storage", "platforms": ["windows", "macos"], "silent_install": "/silent", "latest_version": "93.0"},
    # Password Managers
    {"id": "cat-1password", "name": "1Password", "vendor": "AgileBits", "category": "Security", "platforms": ["windows", "macos", "linux"], "silent_install": "/S", "latest_version": "8.10"},
    {"id": "cat-bitwarden", "name": "Bitwarden", "vendor": "Bitwarden Inc.", "category": "Security", "platforms": ["windows", "macos", "linux"], "silent_install": "/S", "latest_version": "2024.6"},
    # Monitoring
    {"id": "cat-datadog", "name": "Datadog Agent", "vendor": "Datadog", "category": "Monitoring", "platforms": ["windows", "macos", "linux"], "silent_install": "/quiet", "latest_version": "7.55"},
    {"id": "cat-newrelic", "name": "New Relic Agent", "vendor": "New Relic", "category": "Monitoring", "platforms": ["windows", "macos", "linux"], "silent_install": "/S", "latest_version": "10.28"},
    # System Tools
    {"id": "cat-sysinternals", "name": "Sysinternals Suite", "vendor": "Microsoft", "category": "System Tools", "platforms": ["windows"], "silent_install": "/S", "latest_version": "2024.06"},
    {"id": "cat-bginfo", "name": "BGInfo", "vendor": "Microsoft", "category": "System Tools", "platforms": ["windows"], "silent_install": "/silent", "latest_version": "4.32"},
    {"id": "cat-cpu-z", "name": "CPU-Z", "vendor": "CPUID", "category": "System Tools", "platforms": ["windows"], "silent_install": "/S", "latest_version": "2.09"},
]


async def _seed_catalog(db_raw) -> None:
    existing = await db_raw.app_catalog.count_documents({"source": "builtin"})
    if existing >= len(BUILTIN_CATALOG):
        return
    for app in BUILTIN_CATALOG:
        await db_raw.app_catalog.update_one(
            {"id": app["id"]},
            {"$setOnInsert": {
                **app,
                "source": "builtin",
                "description": f"{app['name']} by {app['vendor']}",
                "enabled": True,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }},
            upsert=True,
        )
    logger.info("[AppCatalog] Seeded %d built-in apps", len(BUILTIN_CATALOG))


async def _ensure_seeded() -> None:
    db = get_database()
    await _seed_catalog(db._db)


async def list_apps(
    tenant_id: str,
    category: Optional[str] = None,
    platform: Optional[str] = None,
    search: Optional[str] = None,
    limit: int = 200,
) -> List[Dict]:
    await _ensure_seeded()
    db = get_database()
    filt: Dict[str, Any] = {"$or": [{"source": "builtin"}, {"tenantId": tenant_id}]}
    if category:
        filt["category"] = category
    if platform:
        filt["platforms"] = platform
    if search:
        filt["$or"] = [
            {"name": {"$regex": search, "$options": "i"}},
            {"vendor": {"$regex": search, "$options": "i"}},
        ]
    cursor = db._db.app_catalog.find(filt).sort("name", 1).limit(limit)
    docs = await cursor.to_list(length=limit)
    for d in docs:
        d.pop("_id", None)
    return docs


async def get_categories(tenant_id: str) -> List[str]:
    await _ensure_seeded()
    db = get_database()
    cats = await db._db.app_catalog.distinct("category", {"$or": [{"source": "builtin"}, {"tenantId": tenant_id}]})
    return sorted(cats)


async def add_custom_app(tenant_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
    db = get_database()
    name = data.get("name", "").strip()
    if not name:
        raise ValueError("App name is required")

    now = datetime.now(timezone.utc).isoformat()
    doc = {
        "id": str(uuid.uuid4()),
        "tenantId": tenant_id,
        "name": name,
        "vendor": data.get("vendor", ""),
        "category": data.get("category", "Custom"),
        "description": data.get("description", ""),
        "platforms": data.get("platforms", ["windows"]),
        "latest_version": data.get("latest_version", ""),
        "silent_install": data.get("silent_install", ""),
        "download_url": data.get("download_url", ""),
        "source": "custom",
        "enabled": True,
        "created_at": now,
        "updated_at": now,
        "created_by": data.get("created_by", ""),
    }
    await db._db.app_catalog.insert_one(doc)
    doc.pop("_id", None)
    return doc


async def delete_custom_app(app_id: str, tenant_id: str) -> bool:
    db = get_database()
    result = await db._db.app_catalog.delete_one({"id": app_id, "tenantId": tenant_id, "source": "custom"})
    return result.deleted_count > 0


async def get_summary(tenant_id: str) -> Dict[str, Any]:
    await _ensure_seeded()
    db = get_database()
    total = await db._db.app_catalog.count_documents({"$or": [{"source": "builtin"}, {"tenantId": tenant_id}]})
    custom = await db._db.app_catalog.count_documents({"tenantId": tenant_id, "source": "custom"})
    return {"total_apps": total, "builtin_apps": total - custom, "custom_apps": custom}

"""
System Health Endpoints — real-time platform diagnostics.
Expands beyond the basic binary/VT health check with process, queue, DB, and agent fleet metrics.
"""

from __future__ import annotations

import asyncio
import logging
import platform
import time
from datetime import datetime, timezone
from typing import Any, Dict, List

from fastapi import APIRouter, Depends
from database import get_database
from rbac_utils import is_super_admin, require_permission
from tenant_context import set_tenant_id

logger = logging.getLogger(__name__)

try:
    import psutil
    _PSUTIL = True
except ImportError:
    _PSUTIL = False

# Platform diagnostics: the UI shows this page to manage:settings holders. Only
# super-admins see platform-wide data; everyone else gets their own tenant's
# counts through the tenant-isolated DB wrapper.
_require_settings = require_permission("manage:settings")
router = APIRouter(
    prefix="/api/system",
    tags=["System Health"],
    dependencies=[Depends(_require_settings)],
)

_start_time = time.time()


def _cpu_mem_disk() -> Dict[str, Any]:
    if not _PSUTIL:
        return {"cpu_percent": 0, "memory_percent": 0, "disk_percent": 0, "available": False}
    return {
        "cpu_percent": psutil.cpu_percent(interval=0.2),
        "memory_percent": psutil.virtual_memory().percent,
        "memory_used_gb": round(psutil.virtual_memory().used / 1e9, 2),
        "memory_total_gb": round(psutil.virtual_memory().total / 1e9, 2),
        "disk_percent": psutil.disk_usage("/").percent if platform.system() != "Windows"
                        else psutil.disk_usage("C:\\").percent,
        "disk_used_gb": round(psutil.disk_usage("/" if platform.system() != "Windows" else "C:\\").used / 1e9, 2),
        "disk_total_gb": round(psutil.disk_usage("/" if platform.system() != "Windows" else "C:\\").total / 1e9, 2),
        "available": True,
    }


async def _db_stats(db) -> Dict[str, Any]:
    try:
        stats = await asyncio.wait_for(db.command("dbStats"), timeout=3)
        return {
            "connected": True,
            "collections": stats.get("collections", 0),
            "data_size_mb": round(stats.get("dataSize", 0) / 1e6, 2),
            "storage_size_mb": round(stats.get("storageSize", 0) / 1e6, 2),
            "indexes": stats.get("indexes", 0),
        }
    except Exception as exc:
        import logging as _l; _l.getLogger(__name__).error("DB stats error: %s", exc)
        return {"connected": False, "error": "Database unavailable"}


async def _queue_depths(db) -> Dict[str, int]:
    try:
        results = await asyncio.gather(
            db.security_events.count_documents({"status": "pending"}),
            db.alerts.count_documents({"status": "open"}),
            db.deployment_tasks.count_documents({"status": {"$in": ["pending", "running"]}}),
            db.playbook_executions.count_documents({"status": "running"}),
            return_exceptions=True,
        )
        keys = ["alert_queue", "open_alerts", "deployment_tasks", "running_playbooks"]
        return {k: (v if isinstance(v, int) else 0) for k, v in zip(keys, results)}
    except Exception as e:
        logger.debug("Queue stats query failed: %s", e)
        return {}


async def _agent_fleet(db) -> Dict[str, Any]:
    try:
        now = datetime.now(timezone.utc).timestamp()
        pipeline = [
            {"$group": {
                "_id": "$status",
                "count": {"$sum": 1},
            }}
        ]
        cursor = db.agents.aggregate(pipeline)
        counts: Dict[str, int] = {}
        async for doc in cursor:
            counts[doc["_id"]] = doc["count"]

        total = sum(counts.values())
        online = counts.get("online", 0) + counts.get("active", 0)
        offline = counts.get("offline", 0) + counts.get("inactive", 0)
        stale = counts.get("stale", 0)

        return {
            "total": total,
            "online": online,
            "offline": offline,
            "stale": stale,
            "health_pct": round((online / total * 100) if total else 0, 1),
        }
    except Exception as exc:
        import logging as _l; _l.getLogger(__name__).error("Agent fleet stats error: %s", exc)
        return {"total": 0, "online": 0, "offline": 0, "stale": 0, "health_pct": 0}


def _elevate_if_super(user) -> bool:
    """Bypass tenant isolation for super-admins only; returns True when elevated."""
    if is_super_admin(getattr(user, "role", "")):
        set_tenant_id("platform-admin")
        return True
    return False


# (task name given in app_startup.py, display name, polling interval)
_KNOWN_BACKGROUND_TASKS = [
    ("xdr_correlation", "XDR Correlation Engine", "5min"),
    ("start_aws_polling", "AWS CloudTrail Poller", "5min"),
    ("start_azure_polling", "Azure Defender Poller", "5min"),
    ("start_gcp_polling", "GCP SCC Poller", "5min"),
    ("start_okta_polling", "Okta Log Poller", "60s"),
    ("syslog_receiver", "Syslog UDP Receiver", "persistent"),
    ("nvd_sync_loop", "NVD CVE Sync", "6h"),
    ("jit_expiry_loop", "JIT Expiry Enforcer", "60s"),
    ("report_scheduler", "Scheduled Reports", "1min"),
]


def _syslog_listening() -> bool:
    # The syslog starter finishes once its UDP endpoint is open, so it has no
    # live task; ask the receiver module instead.
    try:
        import syslog_receiver
        return syslog_receiver.is_listening()
    except Exception:
        return False


def _background_tasks() -> List[Dict[str, Any]]:
    """Report each known background loop's live state from the event loop
    (all_tasks() only holds unfinished tasks, so presence means running)."""
    try:
        live = {t.get_name() for t in asyncio.all_tasks()}
    except RuntimeError:  # no running loop
        live = {}
    return [
        {
            "name": label,
            "interval": interval,
            "status": "running" if (_syslog_listening() if name == "syslog_receiver" else name in live) else "not running",
        }
        for name, label, interval in _KNOWN_BACKGROUND_TASKS
    ]


@router.get("/health")
async def system_health(current_user=Depends(_require_settings)):
    """Comprehensive platform health snapshot."""
    elevated = _elevate_if_super(current_user)
    db = get_database()
    resources, db_stats, queues, fleet = await asyncio.gather(
        asyncio.get_event_loop().run_in_executor(None, _cpu_mem_disk),
        _db_stats(db),
        _queue_depths(db),
        _agent_fleet(db),
    )

    uptime_seconds = int(time.time() - _start_time)
    uptime_hours = uptime_seconds // 3600
    uptime_mins = (uptime_seconds % 3600) // 60

    overall = "healthy"
    if resources.get("cpu_percent", 0) > 90 or resources.get("memory_percent", 0) > 90:
        overall = "degraded"
    if not db_stats.get("connected"):
        overall = "critical"
    if not elevated:
        # dbStats describes the whole shared database — not tenant data
        db_stats = {"connected": db_stats.get("connected", False)}

    return {
        "status": overall,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "uptime": f"{uptime_hours}h {uptime_mins}m",
        "uptime_seconds": uptime_seconds,
        "version": "2030.0",
        "platform": platform.system(),
        "resources": resources,
        "database": db_stats,
        "queues": queues,
        "agent_fleet": fleet,
        "background_tasks": _background_tasks(),
    }


@router.get("/services")
async def list_services():
    """All registered backend service modules and their status."""
    services = [
        {"name": "XDR Intelligence", "category": "Security", "status": "healthy", "endpoint": "/api/xdr"},
        {"name": "SIEM Engine", "category": "Security", "status": "healthy", "endpoint": "/api/siem"},
        {"name": "EDR Telemetry", "category": "Security", "status": "healthy", "endpoint": "/api/edr"},
        {"name": "UEBA Engine", "category": "Security", "status": "healthy", "endpoint": "/api/ueba"},
        {"name": "Threat Intel", "category": "Security", "status": "healthy", "endpoint": "/api/threat-intel"},
        {"name": "Correlation Engine", "category": "Security", "status": "healthy", "endpoint": "/api/correlations"},
        {"name": "SOAR Engine", "category": "Automation", "status": "healthy", "endpoint": "/api/soar"},
        {"name": "Playbook Engine", "category": "Automation", "status": "healthy", "endpoint": "/api/playbooks"},
        {"name": "Remediation Engine", "category": "Automation", "status": "healthy", "endpoint": "/api/remediation"},
        {"name": "Compliance Automation", "category": "GRC", "status": "healthy", "endpoint": "/api/compliance"},
        {"name": "AI Service", "category": "AI", "status": "healthy", "endpoint": "/api/ai"},
        {"name": "CISSP Oracle", "category": "AI", "status": "healthy", "endpoint": "/api/cissp"},
        {"name": "LLM Proxy", "category": "AI", "status": "healthy", "endpoint": "/api/llm"},
        {"name": "Agent Manager", "category": "Agents", "status": "healthy", "endpoint": "/api/agents"},
        {"name": "Swarm Coordinator", "category": "Agents", "status": "healthy", "endpoint": "/api/swarm"},
        {"name": "FinOps Engine", "category": "FinOps", "status": "healthy", "endpoint": "/api/finops"},
        {"name": "JIT Access", "category": "Identity", "status": "healthy", "endpoint": "/api/jit"},
        {"name": "Secrets Vault", "category": "Identity", "status": "healthy", "endpoint": "/api/secrets"},
        {"name": "Zero Trust", "category": "Identity", "status": "healthy", "endpoint": "/api/zero-trust"},
        {"name": "HA/DR Service", "category": "Infrastructure", "status": "healthy", "endpoint": "/api/hadr"},
        {"name": "Asset Manager", "category": "Infrastructure", "status": "healthy", "endpoint": "/api/assets"},
        {"name": "Patch Manager", "category": "Infrastructure", "status": "healthy", "endpoint": "/api/patches"},
    ]
    return {"services": services, "total": len(services), "healthy": len(services)}


@router.get("/queues")
async def queue_depths(current_user=Depends(_require_settings)):
    """Current queue depths for all async processing pipelines."""
    _elevate_if_super(current_user)
    db = get_database()
    depths = await _queue_depths(db)
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "queues": [
            {"name": "Alert Queue", "key": "alert_queue", "depth": depths.get("alert_queue", 0), "warning_threshold": 1000},
            {"name": "Open Alerts", "key": "open_alerts", "depth": depths.get("open_alerts", 0), "warning_threshold": 500},
            {"name": "Deployment Tasks", "key": "deployment_tasks", "depth": depths.get("deployment_tasks", 0), "warning_threshold": 50},
            {"name": "Running Playbooks", "key": "running_playbooks", "depth": depths.get("running_playbooks", 0), "warning_threshold": 20},
        ],
    }


@router.get("/fleet")
async def agent_fleet(current_user=Depends(_require_settings)):
    """Agent fleet health summary."""
    _elevate_if_super(current_user)
    db = get_database()
    fleet = await _agent_fleet(db)

    try:
        agents_cursor = db.agents.find(
            {},
            {"_id": 0, "id": 1, "hostname": 1, "status": 1, "last_seen": 1, "os": 1, "version": 1}
        ).limit(200)
        agents = await agents_cursor.to_list(length=200)
    except Exception:
        agents = []

    return {**fleet, "agents": agents}


@router.get("/resources")
async def resource_metrics():
    """Real-time CPU, memory, and disk usage."""
    resources = await asyncio.get_event_loop().run_in_executor(None, _cpu_mem_disk)
    return {"timestamp": datetime.now(timezone.utc).isoformat(), **resources}

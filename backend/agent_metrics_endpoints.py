"""
Agent Metrics Endpoints — Phase 9
Real system metrics collection using psutil.
Agents call POST /api/agents/{id}/metrics to report CPU, RAM, disk, network.
Frontend calls GET /api/agents/{id}/metrics/history for charts.
"""
import logging
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks
from pydantic import BaseModel
from typing import Dict, Any, Optional, List
from database import get_database
from authentication_service import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/agents", tags=["Agent Metrics"])


class SystemMetrics(BaseModel):
    cpu_percent: float = 0.0
    memory_percent: float = 0.0
    memory_used_mb: float = 0.0
    memory_total_mb: float = 0.0
    disk_percent: float = 0.0
    disk_used_gb: float = 0.0
    disk_total_gb: float = 0.0
    network_bytes_sent_mb: float = 0.0
    network_bytes_recv_mb: float = 0.0
    load_avg_1m: Optional[float] = None
    process_count: Optional[int] = None
    uptime_seconds: Optional[float] = None
    top_processes: Optional[List[Dict[str, Any]]] = []


@router.post("/{agent_id}/metrics")
async def record_agent_metrics(
    agent_id: str,
    metrics: SystemMetrics,
    current_user=Depends(get_current_user)
):
    """
    Record real-time system metrics from an agent.
    Called by the agent every 30 seconds.
    """
    db = get_database()

    # Verify agent exists and belongs to this tenant
    agent = await db.agents.find_one({"id": agent_id})
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    timestamp = datetime.now(timezone.utc).isoformat()
    metric_doc = {
        "agent_id": agent_id,
        "tenant_id": agent.get("tenantId"),
        "timestamp": timestamp,
        **metrics.dict()
    }

    # Store time-series metric
    await db.agent_metrics.insert_one(metric_doc)

    # Update agent's current metrics summary
    await db.agents.update_one(
        {"id": agent_id},
        {"$set": {
            "current_metrics": metrics.dict(),
            "metrics_updated_at": timestamp,
            "lastSeen": timestamp,
            "status": "Online",
        }}
    )

    # Alert if CPU or memory is critically high
    if metrics.cpu_percent > 90 or metrics.memory_percent > 90:
        from notification_manager import notification_manager
        resource = "CPU" if metrics.cpu_percent > 90 else "Memory"
        value = metrics.cpu_percent if resource == "CPU" else metrics.memory_percent
        await notification_manager.send_notification(
            "agent.high_resource",
            {
                "agent_id": agent_id,
                "hostname": agent.get("hostname", agent_id),
                "resource": resource,
                "value": value,
            },
            agent.get("tenantId", "platform-admin")
        )

    return {"success": True, "timestamp": timestamp}


@router.get("/{agent_id}/metrics/history")
async def get_agent_metrics_history(
    agent_id: str,
    hours: int = 24,
    current_user=Depends(get_current_user)
):
    """
    Get historical system metrics for an agent for the last N hours.
    Returns time-series data suitable for charting.
    """
    db = get_database()

    since = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
    metrics = await db.agent_metrics.find(
        {"agent_id": agent_id, "timestamp": {"$gte": since}},
        {"_id": 0}
    ).sort("timestamp", 1).to_list(length=2880)  # max 48h at 1-min intervals

    if not metrics:
        return {"agent_id": agent_id, "hours": hours, "metrics": [], "summary": {}}

    # Compute summary stats
    cpu_values = [m["cpu_percent"] for m in metrics]
    mem_values = [m["memory_percent"] for m in metrics]
    disk_values = [m["disk_percent"] for m in metrics]

    summary = {
        "cpu_avg": round(sum(cpu_values) / len(cpu_values), 1),
        "cpu_max": round(max(cpu_values), 1),
        "memory_avg": round(sum(mem_values) / len(mem_values), 1),
        "memory_max": round(max(mem_values), 1),
        "disk_avg": round(sum(disk_values) / len(disk_values), 1),
        "sample_count": len(metrics),
        "period_hours": hours,
    }

    return {"agent_id": agent_id, "hours": hours, "metrics": metrics, "summary": summary}


@router.get("/{agent_id}/metrics/current")
async def get_current_agent_metrics(agent_id: str, current_user=Depends(get_current_user)):
    """Get the most recent metrics snapshot for an agent."""
    db = get_database()
    agent = await db.agents.find_one({"id": agent_id}, {"_id": 0})
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    return {
        "agent_id": agent_id,
        "hostname": agent.get("hostname"),
        "metrics": agent.get("current_metrics", {}),
        "updated_at": agent.get("metrics_updated_at"),
        "status": agent.get("status"),
    }


def collect_local_metrics() -> Dict[str, Any]:
    """
    Collect system metrics from the local machine using psutil.
    Call this from the agent script to get real metrics to report.
    """
    try:
        import psutil
        net = psutil.net_io_counters()
        cpu_freq = psutil.cpu_freq()
        uptime = (datetime.now() - datetime.fromtimestamp(psutil.boot_time())).total_seconds()

        top_procs = []
        for proc in sorted(psutil.process_iter(["pid", "name", "cpu_percent", "memory_percent"]),
                           key=lambda p: p.info["cpu_percent"] or 0, reverse=True)[:5]:
            top_procs.append({
                "pid": proc.info["pid"],
                "name": proc.info["name"],
                "cpu_percent": proc.info["cpu_percent"],
                "memory_percent": proc.info["memory_percent"],
            })

        disk = psutil.disk_usage("/")
        mem = psutil.virtual_memory()

        return {
            "cpu_percent": psutil.cpu_percent(interval=1),
            "memory_percent": mem.percent,
            "memory_used_mb": round(mem.used / 1024 / 1024, 1),
            "memory_total_mb": round(mem.total / 1024 / 1024, 1),
            "disk_percent": disk.percent,
            "disk_used_gb": round(disk.used / 1024 ** 3, 2),
            "disk_total_gb": round(disk.total / 1024 ** 3, 2),
            "network_bytes_sent_mb": round(net.bytes_sent / 1024 / 1024, 2),
            "network_bytes_recv_mb": round(net.bytes_recv / 1024 / 1024, 2),
            "process_count": len(psutil.pids()),
            "uptime_seconds": uptime,
            "top_processes": top_procs,
        }
    except ImportError:
        return {"error": "psutil not installed. Run: pip install psutil"}
    except Exception as e:
        return {"error": str(e)}

"""
MDR Service — Managed Detection & Response business logic.

Handles:
  - SLA tracking (MTTD / MTTR calculations)
  - Managed threat hunt lifecycle
  - Escalation management
  - Asset coverage assessment
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

from database import get_database

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# SLA thresholds (hours)
# ---------------------------------------------------------------------------
SLA_DETECT_CRITICAL = 1.0
SLA_DETECT_HIGH = 4.0
SLA_DETECT_MEDIUM = 12.0
SLA_DETECT_LOW = 24.0

SLA_RESPOND_CRITICAL = 2.0
SLA_RESPOND_HIGH = 8.0
SLA_RESPOND_MEDIUM = 24.0
SLA_RESPOND_LOW = 72.0


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _hours_between(start: str, end: Optional[str]) -> Optional[float]:
    """Return hours between two ISO timestamps, or None if either is missing."""
    if not start or not end:
        return None
    try:
        t0 = datetime.fromisoformat(start.replace("Z", "+00:00"))
        t1 = datetime.fromisoformat(end.replace("Z", "+00:00"))
        return max(0.0, (t1 - t0).total_seconds() / 3600)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# SLA metrics
# ---------------------------------------------------------------------------

async def compute_sla_metrics(tenant_filter: dict, window_hours: int = 168) -> Dict[str, Any]:
    """Compute MTTD / MTTR and SLA breach counts over the last *window_hours*."""
    db = get_database()
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=window_hours)).isoformat()

    # Pull security events detected in the window
    events = await db.security_events.find(
        {"timestamp": {"$gte": cutoff}, **tenant_filter}, {"_id": 0}
    ).to_list(length=2000)

    # Pull response tasks completed in the window
    tasks = await db.response_tasks.find(
        {"created_at": {"$gte": cutoff}, "status": "executed", **tenant_filter}, {"_id": 0}
    ).to_list(length=2000)

    # MTTD: time from event creation to case creation (approx from first response task)
    detect_times: List[float] = []
    respond_times: List[float] = []

    for task in tasks:
        h = _hours_between(task.get("created_at"), task.get("executed_at"))
        if h is not None:
            respond_times.append(h)

    # Derive MTTD from correlation events that produced cases
    cases = await db.security_cases.find(
        {"created_at": {"$gte": cutoff}, **tenant_filter}, {"_id": 0}
    ).to_list(length=2000)

    for case in cases:
        # Compare first related event timestamp to case creation
        related = case.get("relatedEvents") or []
        if related:
            first_event = await db.security_events.find_one(
                {"id": {"$in": related[:1]}}, {"_id": 0, "timestamp": 1}
            )
            if first_event:
                h = _hours_between(first_event.get("timestamp"), case.get("created_at"))
                if h is not None:
                    detect_times.append(h)

    mttd = round(sum(detect_times) / len(detect_times), 2) if detect_times else None
    mttr = round(sum(respond_times) / len(respond_times), 2) if respond_times else None

    # SLA breach counts by severity
    sla_breaches = {"critical": 0, "high": 0, "medium": 0, "low": 0}
    thresholds = {
        "critical": SLA_RESPOND_CRITICAL,
        "high": SLA_RESPOND_HIGH,
        "medium": SLA_RESPOND_MEDIUM,
        "low": SLA_RESPOND_LOW,
    }
    for task in tasks:
        sev = (task.get("severity") or "medium").lower()
        h = _hours_between(task.get("created_at"), task.get("executed_at"))
        if h is not None and sev in thresholds and h > thresholds[sev]:
            sla_breaches[sev] += 1

    return {
        "window_hours": window_hours,
        "mttd_hours": mttd,
        "mttr_hours": mttr,
        "total_events": len(events),
        "total_cases": len(cases),
        "total_responses": len(tasks),
        "sla_breaches": sla_breaches,
        "sla_thresholds_hours": {
            "detect": {
                "critical": SLA_DETECT_CRITICAL,
                "high": SLA_DETECT_HIGH,
                "medium": SLA_DETECT_MEDIUM,
                "low": SLA_DETECT_LOW,
            },
            "respond": {
                "critical": SLA_RESPOND_CRITICAL,
                "high": SLA_RESPOND_HIGH,
                "medium": SLA_RESPOND_MEDIUM,
                "low": SLA_RESPOND_LOW,
            },
        },
    }


# ---------------------------------------------------------------------------
# Dashboard summary
# ---------------------------------------------------------------------------

async def get_dashboard_summary(tenant_filter: dict) -> Dict[str, Any]:
    """Return top-level MDR KPIs for the dashboard."""
    db = get_database()
    cutoff_24h = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
    cutoff_7d = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()

    active_hunts = await db.mdr_hunts.count_documents({"status": "active", **tenant_filter})
    open_escalations = await db.mdr_escalations.count_documents({"status": "open", **tenant_filter})
    threats_24h = await db.response_tasks.count_documents(
        {"status": "executed", "created_at": {"$gte": cutoff_24h}, **tenant_filter}
    )
    cases_7d = await db.security_cases.count_documents(
        {"created_at": {"$gte": cutoff_7d}, **tenant_filter}
    )
    resolved_7d = await db.security_cases.count_documents(
        {"created_at": {"$gte": cutoff_7d}, "status": "Resolved", **tenant_filter}
    )
    total_assets = await db.assets.count_documents({**tenant_filter})
    monitored_assets = await db.agents.count_documents({"status": "Online", **tenant_filter})

    coverage_pct = round((monitored_assets / total_assets * 100), 1) if total_assets > 0 else 0.0

    return {
        "active_hunts": active_hunts,
        "open_escalations": open_escalations,
        "threats_neutralized_24h": threats_24h,
        "cases_opened_7d": cases_7d,
        "cases_resolved_7d": resolved_7d,
        "resolution_rate_pct": round(resolved_7d / cases_7d * 100, 1) if cases_7d > 0 else 0.0,
        "total_assets": total_assets,
        "monitored_assets": monitored_assets,
        "coverage_pct": coverage_pct,
    }


# ---------------------------------------------------------------------------
# Managed Threat Hunts
# ---------------------------------------------------------------------------

async def list_hunts(tenant_filter: dict, status: Optional[str] = None) -> List[Dict]:
    db = get_database()
    query = {**tenant_filter}
    if status:
        query["status"] = status
    return await db.mdr_hunts.find(query, {"_id": 0}).sort("started_at", -1).to_list(length=200)


async def create_hunt(data: dict, tenant_filter: dict, created_by: str) -> Dict:
    db = get_database()
    hunt_id = f"HUNT-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}"
    doc = {
        "hunt_id": hunt_id,
        "title": data["title"],
        "hypothesis": data.get("hypothesis", ""),
        "severity": data.get("severity", "medium"),
        "assigned_to": data.get("assigned_to", ""),
        "status": "active",
        "findings": [],
        "notes": "",
        "started_at": _now(),
        "completed_at": None,
        "created_by": created_by,
        **{k: v for k, v in tenant_filter.items()},
    }
    await db.mdr_hunts.insert_one(doc)
    doc.pop("_id", None)
    return doc


async def update_hunt(hunt_id: str, updates: dict, tenant_filter: dict) -> Optional[Dict]:
    db = get_database()
    hunt = await db.mdr_hunts.find_one({"hunt_id": hunt_id, **tenant_filter})
    if not hunt:
        return None
    allowed = {"status", "findings", "notes", "assigned_to", "severity"}
    patch = {k: v for k, v in updates.items() if k in allowed}
    if patch.get("status") == "completed" and not hunt.get("completed_at"):
        patch["completed_at"] = _now()
    if patch:
        patch["updated_at"] = _now()
        await db.mdr_hunts.update_one(
            {"hunt_id": hunt_id, **tenant_filter}, {"$set": patch}
        )
    return await db.mdr_hunts.find_one({"hunt_id": hunt_id, **tenant_filter}, {"_id": 0})


# ---------------------------------------------------------------------------
# Escalations
# ---------------------------------------------------------------------------

async def list_escalations(tenant_filter: dict, status: Optional[str] = None) -> List[Dict]:
    db = get_database()
    query = {**tenant_filter}
    if status:
        query["status"] = status
    return await db.mdr_escalations.find(query, {"_id": 0}).sort("escalated_at", -1).to_list(length=200)


async def create_escalation(data: dict, tenant_filter: dict, escalated_by: str) -> Dict:
    db = get_database()
    esc_id = f"ESC-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}"
    doc = {
        "escalation_id": esc_id,
        "title": data["title"],
        "severity": data.get("severity", "high"),
        "incident_id": data.get("incident_id"),
        "case_id": data.get("case_id"),
        "description": data.get("description", ""),
        "status": "open",
        "escalated_by": escalated_by,
        "escalated_at": _now(),
        "acknowledged_at": None,
        "resolved_at": None,
        "resolution_notes": "",
        **{k: v for k, v in tenant_filter.items()},
    }
    await db.mdr_escalations.insert_one(doc)
    doc.pop("_id", None)
    return doc


async def update_escalation(esc_id: str, updates: dict, tenant_filter: dict) -> Optional[Dict]:
    db = get_database()
    esc = await db.mdr_escalations.find_one({"escalation_id": esc_id, **tenant_filter})
    if not esc:
        return None
    patch: Dict[str, Any] = {}
    new_status = updates.get("status")
    if new_status == "acknowledged" and esc.get("status") == "open":
        patch["status"] = "acknowledged"
        patch["acknowledged_at"] = _now()
    elif new_status == "resolved":
        patch["status"] = "resolved"
        patch["resolved_at"] = _now()
        patch["resolution_notes"] = updates.get("resolution_notes", "")
    if patch:
        patch["updated_at"] = _now()
        await db.mdr_escalations.update_one(
            {"escalation_id": esc_id, **tenant_filter}, {"$set": patch}
        )
    return await db.mdr_escalations.find_one({"escalation_id": esc_id, **tenant_filter}, {"_id": 0})


# ---------------------------------------------------------------------------
# Coverage report
# ---------------------------------------------------------------------------

async def get_coverage(tenant_filter: dict) -> Dict[str, Any]:
    """Return a breakdown of asset coverage by platform and capability."""
    db = get_database()
    all_assets = await db.assets.find({**tenant_filter}, {"_id": 0, "platform": 1, "id": 1}).to_list(length=5000)
    online_agents = await db.agents.find(
        {"status": "Online", **tenant_filter},
        {"_id": 0, "assetId": 1, "capabilities": 1, "platform": 1}
    ).to_list(length=5000)

    monitored_ids = {a.get("assetId") for a in online_agents if a.get("assetId")}
    asset_ids = {a.get("id") for a in all_assets}

    # Capability coverage
    capability_counts: Dict[str, int] = {}
    for agent in online_agents:
        for cap in (agent.get("capabilities") or []):
            capability_counts[cap] = capability_counts.get(cap, 0) + 1

    # Platform breakdown
    platform_totals: Dict[str, int] = {}
    platform_monitored: Dict[str, int] = {}
    for asset in all_assets:
        p = asset.get("platform", "Unknown")
        platform_totals[p] = platform_totals.get(p, 0) + 1
        if asset.get("id") in monitored_ids:
            platform_monitored[p] = platform_monitored.get(p, 0) + 1

    total = len(asset_ids)
    covered = len(monitored_ids & asset_ids)
    return {
        "total_assets": total,
        "covered_assets": covered,
        "uncovered_assets": total - covered,
        "coverage_pct": round(covered / total * 100, 1) if total > 0 else 0.0,
        "by_platform": [
            {
                "platform": p,
                "total": platform_totals[p],
                "monitored": platform_monitored.get(p, 0),
                "coverage_pct": round(platform_monitored.get(p, 0) / platform_totals[p] * 100, 1)
                if platform_totals[p] > 0 else 0.0,
            }
            for p in sorted(platform_totals)
        ],
        "capabilities_deployed": capability_counts,
    }

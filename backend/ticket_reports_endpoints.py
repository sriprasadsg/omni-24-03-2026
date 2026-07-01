"""
Ticket Reports & Export API
===========================
Provides aggregate reporting data for the ticketing system:
  GET /api/tickets/reports/summary    — top-level KPIs
  GET /api/tickets/reports/trends     — volume over time
  GET /api/tickets/reports/sla        — SLA compliance breakdown
  GET /api/tickets/reports/resolution — resolution-time metrics
  GET /api/tickets/reports/assignee   — per-assignee workload
  GET /api/tickets/reports/ageing     — open ticket age buckets
  GET /api/tickets/export/csv         — download tickets as CSV
"""
from __future__ import annotations

import csv
import io
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Query, Request, Response
from fastapi.responses import StreamingResponse

from authentication_service import get_current_user
from database import get_database
from rate_limiter import limiter
from rbac_utils import require_permission

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/tickets", tags=["Ticket Reports"])

COL = "tickets"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _tenant(user) -> str:
    return getattr(user, "tenant_id", "") or ""


# ── Shared filter builder ──────────────────────────────────────────────────────

def _base_filter(tenant_id: str, from_date: Optional[str], to_date: Optional[str]) -> Dict[str, Any]:
    f: Dict[str, Any] = {}
    if tenant_id:
        f["tenantId"] = tenant_id
    date_range: Dict[str, str] = {}
    if from_date:
        date_range["$gte"] = from_date
    if to_date:
        date_range["$lte"] = to_date
    if date_range:
        f["created_at"] = date_range
    return f


# ── Summary KPIs ──────────────────────────────────────────────────────────────

@router.get("/reports/summary")
@limiter.limit("30/minute")
async def get_summary(
    request: Request,
    response: Response,
    from_date: Optional[str] = Query(None, description="ISO date e.g. 2026-01-01"),
    to_date:   Optional[str] = Query(None),
    current_user=Depends(require_permission("view:dashboard")),
) -> Dict[str, Any]:
    """Top-level KPIs: totals, open/closed split, SLA compliance rate, avg resolution."""
    db  = get_database()
    tid = _tenant(current_user)
    bf  = _base_filter(tid, from_date, to_date)

    total   = await db[COL].count_documents(bf)
    open_c  = await db[COL].count_documents({**bf, "status": {"$nin": ["resolved", "closed"]}})
    closed  = await db[COL].count_documents({**bf, "status": {"$in": ["resolved", "closed"]}})
    overdue = await db[COL].count_documents({
        **bf,
        "due_date": {"$lt": _now().isoformat(), "$ne": None},
        "status": {"$nin": ["resolved", "closed"]},
    })
    escalated = await db[COL].count_documents({**bf, "escalated": True})

    # SLA counts
    sla_met      = await db[COL].count_documents({**bf, "sla_status": "met"})
    sla_breached = await db[COL].count_documents({**bf, "sla_status": "breached"})
    sla_total    = sla_met + sla_breached
    sla_rate     = round(sla_met / sla_total * 100, 1) if sla_total else None

    # Avg resolution time via server-side $avg — no documents transferred to Python
    avg_pipeline = [
        {"$match": {**bf, "status": {"$in": ["resolved", "closed"]},
                    "resolved_at": {"$exists": True}, "created_at": {"$exists": True}}},
        {"$project": {
            "resolution_ms": {"$subtract": [
                {"$dateFromString": {"dateString": "$resolved_at"}},
                {"$dateFromString": {"dateString": "$created_at"}},
            ]}
        }},
        {"$group": {"_id": None, "avg_ms": {"$avg": "$resolution_ms"}}},
    ]
    avg_resolution_hours: Optional[float] = None
    async for doc in db[COL].aggregate(avg_pipeline):
        if doc.get("avg_ms") is not None:
            avg_resolution_hours = round(doc["avg_ms"] / 3_600_000, 1)

    return {
        "total":                total,
        "open":                 open_c,
        "closed":               closed,
        "overdue":              overdue,
        "escalated":            escalated,
        "sla_met":              sla_met,
        "sla_breached":         sla_breached,
        "sla_compliance_rate":  sla_rate,
        "avg_resolution_hours": avg_resolution_hours,
    }


# ── Volume Trends ─────────────────────────────────────────────────────────────

@router.get("/reports/trends")
@limiter.limit("20/minute")
async def get_trends(
    request: Request,
    response: Response,
    days:   int = Query(30, ge=7, le=365, description="Number of days to look back"),
    period: str = Query("daily", description="daily | weekly"),
    current_user=Depends(require_permission("view:dashboard")),
) -> Dict[str, Any]:
    """
    Returns daily or weekly ticket-opened and ticket-closed counts.
    Output shape: [{date, opened, closed, net}, ...]
    """
    db  = get_database()
    tid = _tenant(current_user)
    since = (_now() - timedelta(days=days)).isoformat()
    base  = {"tenantId": tid} if tid else {}

    # Group format depends on period
    date_fmt = "%Y-%m-%d" if period == "daily" else "%Y-W%V"

    async def _count_by_date(extra_filter: Dict[str, Any], date_field: str) -> Dict[str, int]:
        out: Dict[str, int] = {}
        pipeline = [
            {"$match": {**base, **extra_filter, date_field: {"$gte": since}}},
            {"$group": {
                "_id": {
                    "$dateToString": {
                        "format": "%Y-%m-%d" if period == "daily" else "%Y-%V",
                        "date": {"$dateFromString": {"dateString": f"${date_field}"}},
                    }
                },
                "count": {"$sum": 1},
            }},
            {"$sort": {"_id": 1}},
        ]
        async for doc in db[COL].aggregate(pipeline):
            if doc["_id"]:
                out[doc["_id"]] = doc["count"]
        return out

    opened = await _count_by_date({}, "created_at")
    closed = await _count_by_date(
        {"status": {"$in": ["resolved", "closed"]}, "resolved_at": {"$exists": True}},
        "resolved_at",
    )

    # Build a complete date spine
    all_dates: List[str] = []
    cur = _now() - timedelta(days=days)
    step = timedelta(days=1) if period == "daily" else timedelta(weeks=1)
    while cur <= _now():
        key = cur.strftime(date_fmt).replace("-W0", "-W").replace("-W", "-W")
        if period == "daily":
            key = cur.strftime("%Y-%m-%d")
        else:
            key = cur.strftime("%Y-%V")
        if key not in all_dates:
            all_dates.append(key)
        cur += step

    data = []
    for d in all_dates:
        o = opened.get(d, 0)
        c = closed.get(d, 0)
        data.append({"date": d, "opened": o, "closed": c, "net": o - c})

    return {"period": period, "days": days, "data": data}


# ── SLA Compliance ────────────────────────────────────────────────────────────

@router.get("/reports/sla")
@limiter.limit("20/minute")
async def get_sla_report(
    request: Request,
    response: Response,
    from_date: Optional[str] = Query(None),
    to_date:   Optional[str] = Query(None),
    current_user=Depends(require_permission("view:dashboard")),
) -> Dict[str, Any]:
    """SLA compliance breakdown by priority."""
    db  = get_database()
    tid = _tenant(current_user)
    bf  = _base_filter(tid, from_date, to_date)

    sla_met      = await db[COL].count_documents({**bf, "sla_status": "met"})
    sla_breached = await db[COL].count_documents({**bf, "sla_status": "breached"})
    sla_pending  = await db[COL].count_documents({
        **bf,
        "sla_status": {"$nin": ["met", "breached"], "$exists": True},
    })
    sla_none     = await db[COL].count_documents({**bf, "sla_hours": {"$exists": False}})
    sla_total    = sla_met + sla_breached
    compliance   = round(sla_met / sla_total * 100, 1) if sla_total else None

    # SLA breakdown by priority
    by_priority: List[Dict[str, Any]] = []
    for priority in ["critical", "high", "medium", "low"]:
        pf = {**bf, "priority": priority}
        m = await db[COL].count_documents({**pf, "sla_status": "met"})
        b = await db[COL].count_documents({**pf, "sla_status": "breached"})
        t = m + b
        by_priority.append({
            "priority": priority,
            "met":      m,
            "breached": b,
            "rate":     round(m / t * 100, 1) if t else None,
        })

    return {
        "sla_met":         sla_met,
        "sla_breached":    sla_breached,
        "sla_pending":     sla_pending,
        "sla_none":        sla_none,
        "compliance_rate": compliance,
        "by_priority":     by_priority,
    }


# ── Resolution Time ───────────────────────────────────────────────────────────

@router.get("/reports/resolution")
@limiter.limit("20/minute")
async def get_resolution_report(
    request: Request,
    response: Response,
    from_date: Optional[str] = Query(None),
    to_date:   Optional[str] = Query(None),
    current_user=Depends(require_permission("view:dashboard")),
) -> Dict[str, Any]:
    """Average, median, and p90 resolution time in hours, broken down by priority and type."""
    db  = get_database()
    tid = _tenant(current_user)
    bf  = _base_filter(tid, from_date, to_date)

    closed_filter = {
        **bf,
        "status": {"$in": ["resolved", "closed"]},
        "resolved_at": {"$exists": True},
        "created_at":  {"$exists": True},
    }

    # Single aggregation — server computes avg + per-priority avg, transfers only summary rows
    resolution_pipeline = [
        {"$match": closed_filter},
        {"$project": {
            "priority": 1,
            "type": 1,
            "hours": {"$divide": [
                {"$subtract": [
                    {"$dateFromString": {"dateString": "$resolved_at"}},
                    {"$dateFromString": {"dateString": "$created_at"}},
                ]},
                3_600_000,  # ms → hours
            ]},
        }},
        {"$facet": {
            "overall": [
                {"$group": {"_id": None, "avg": {"$avg": "$hours"}, "count": {"$sum": 1}}},
            ],
            "by_priority": [
                {"$group": {"_id": "$priority", "avg": {"$avg": "$hours"}, "count": {"$sum": 1}}},
            ],
            "by_type": [
                {"$group": {"_id": "$type", "avg": {"$avg": "$hours"}, "count": {"$sum": 1}}},
            ],
        }},
    ]

    facet: Dict[str, Any] = {}
    async for doc in db[COL].aggregate(resolution_pipeline):
        facet = doc

    def _row(avg_val: Optional[float], cnt: int) -> Dict[str, Any]:
        return {"avg": round(avg_val, 1) if avg_val is not None else None,
                "p50": None, "p90": None, "count": cnt}

    overall_list = facet.get("overall", [])
    overall_row  = overall_list[0] if overall_list else {}
    overall = _row(overall_row.get("avg"), overall_row.get("count", 0))

    by_priority: Dict[str, Any] = {}
    for row in facet.get("by_priority", []):
        if row.get("_id"):
            by_priority[row["_id"]] = _row(row.get("avg"), row.get("count", 0))
    for p in ("critical", "high", "medium", "low"):
        by_priority.setdefault(p, _row(None, 0))

    by_type: Dict[str, Any] = {}
    for row in facet.get("by_type", []):
        if row.get("_id"):
            by_type[row["_id"]] = _row(row.get("avg"), row.get("count", 0))

    # p50 / p90 via cursor skip — reads exactly 2 documents per stat (overall only)
    total_resolved = overall["count"]
    if total_resolved > 0:
        base_sort = [
            {"$match": closed_filter},
            {"$project": {"hours": {"$divide": [
                {"$subtract": [
                    {"$dateFromString": {"dateString": "$resolved_at"}},
                    {"$dateFromString": {"dateString": "$created_at"}},
                ]}, 3_600_000]}}},
            {"$sort": {"hours": 1}},
        ]
        for offset, key in ((total_resolved // 2, "p50"), (int(total_resolved * 0.9), "p90")):
            docs = await db[COL].aggregate(base_sort + [{"$skip": offset}, {"$limit": 1}]).to_list(1)
            if docs:
                overall[key] = round(docs[0]["hours"], 1)

    return {
        "overall":     overall,
        "by_priority": by_priority,
        "by_type":     by_type,
    }


# ── Assignee Workload ─────────────────────────────────────────────────────────

@router.get("/reports/assignee")
@limiter.limit("20/minute")
async def get_assignee_report(
    request: Request,
    response: Response,
    from_date: Optional[str] = Query(None),
    to_date:   Optional[str] = Query(None),
    current_user=Depends(require_permission("view:dashboard")),
) -> Dict[str, Any]:
    """Per-assignee open, resolved, overdue, and average resolution time."""
    db  = get_database()
    tid = _tenant(current_user)
    bf  = _base_filter(tid, from_date, to_date)
    now = _now().isoformat()

    # Single pipeline: group, compute open/resolved/overdue/avg all server-side
    is_closed = {"$in": ["$status", ["resolved", "closed"]]}
    is_overdue = {"$and": [
        {"$lt": ["$due_date", now]},
        {"$ne": ["$due_date", None]},
        {"$not": is_closed},
    ]}
    has_resolution = {"$and": [
        {"$ne": ["$resolved_at", None]},
        {"$ne": ["$created_at", None]},
    ]}

    pipeline = [
        {"$match": {**bf, "assignee": {"$exists": True, "$nin": [None, ""]}}},
        {"$group": {
            "_id": "$assignee",
            "total":    {"$sum": 1},
            "open":     {"$sum": {"$cond": [{"$not": [is_closed]}, 1, 0]}},
            "resolved": {"$sum": {"$cond": [is_closed, 1, 0]}},
            "overdue":  {"$sum": {"$cond": [is_overdue, 1, 0]}},
            "avg_resolution_ms": {"$avg": {
                "$cond": [
                    {"$and": [is_closed, has_resolution]},
                    {"$subtract": [
                        {"$dateFromString": {"dateString": "$resolved_at"}},
                        {"$dateFromString": {"dateString": "$created_at"}},
                    ]},
                    None,
                ]
            }},
        }},
        {"$sort": {"total": -1}},
        {"$limit": 20},
    ]

    rows: List[Dict[str, Any]] = []
    async for doc in db[COL].aggregate(pipeline):
        avg_ms = doc.get("avg_resolution_ms")
        rows.append({
            "assignee":             doc["_id"],
            "total":                doc["total"],
            "open":                 doc["open"],
            "resolved":             doc["resolved"],
            "overdue":              doc["overdue"],
            "avg_resolution_hours": round(avg_ms / 3_600_000, 1) if avg_ms else None,
        })

    return {"assignees": rows}


# ── Backlog Ageing ────────────────────────────────────────────────────────────

@router.get("/reports/ageing")
@limiter.limit("20/minute")
async def get_ageing_report(
    request: Request,
    response: Response,
    current_user=Depends(require_permission("view:dashboard")),
) -> Dict[str, Any]:
    """Open ticket count bucketed by age (how long they've been open)."""
    db  = get_database()
    tid = _tenant(current_user)
    base = {"tenantId": tid} if tid else {}
    now  = _now()

    open_tickets = await db[COL].find(
        {**base, "status": {"$nin": ["resolved", "closed"]}, "created_at": {"$exists": True}},
        {"created_at": 1, "priority": 1, "_id": 0},
    ).to_list(10000)

    buckets = [
        {"label": "0–1 day",   "min": 0,   "max": 1},
        {"label": "1–3 days",  "min": 1,   "max": 3},
        {"label": "3–7 days",  "min": 3,   "max": 7},
        {"label": "1–2 weeks", "min": 7,   "max": 14},
        {"label": "2–4 weeks", "min": 14,  "max": 28},
        {"label": "> 4 weeks", "min": 28,  "max": 9999},
    ]

    result: List[Dict[str, Any]] = []
    for bucket in buckets:
        count    = 0
        critical = 0
        for t in open_tickets:
            try:
                age_days = (now - datetime.fromisoformat(t["created_at"].replace("Z", "+00:00"))).days
                if bucket["min"] <= age_days < bucket["max"]:
                    count += 1
                    if t.get("priority") == "critical":
                        critical += 1
            except Exception:
                pass
        result.append({"label": bucket["label"], "count": count, "critical": critical})

    total_open = sum(b["count"] for b in result)
    return {"buckets": result, "total_open": total_open}


# ── CSV Export ────────────────────────────────────────────────────────────────

@router.get("/export/csv")
@limiter.limit("5/minute")
async def export_tickets_csv(
    request: Request,
    response: Response,
    from_date:  Optional[str] = Query(None),
    to_date:    Optional[str] = Query(None),
    status:     Optional[str] = Query(None),
    priority:   Optional[str] = Query(None),
    assignee:   Optional[str] = Query(None),
    current_user=Depends(require_permission("view:dashboard")),
) -> StreamingResponse:
    """Download filtered tickets as a CSV file."""
    db  = get_database()
    tid = _tenant(current_user)
    bf  = _base_filter(tid, from_date, to_date)
    if status:
        bf["status"] = status
    if priority:
        bf["priority"] = priority
    if assignee:
        bf["assignee"] = assignee

    tickets = await db[COL].find(bf, {"_id": 0}).sort("created_at", -1).to_list(10000)

    FIELDS = [
        "ticket_number", "title", "type", "status", "priority",
        "assignee", "assignee_group", "reporter",
        "created_at", "updated_at", "due_date", "resolved_at",
        "sla_status", "sla_hours", "sla_remaining_minutes",
        "escalated", "tags",
    ]

    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=FIELDS, extrasaction="ignore")
    writer.writeheader()
    for t in tickets:
        row = {k: t.get(k, "") for k in FIELDS}
        if isinstance(row.get("tags"), list):
            row["tags"] = ", ".join(row["tags"])
        writer.writerow(row)

    output.seek(0)
    filename = f"tickets_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )

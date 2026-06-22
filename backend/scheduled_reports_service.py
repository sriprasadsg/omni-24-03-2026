"""
Scheduled Report Delivery Service
Schedules and delivers compliance, security, and executive reports via email and webhook.
"""

import os
import uuid
import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

from database import get_database
from tenant_context import set_tenant_id
import compliance_reporting_pdf
from compliance_reports_endpoints import _REPORTS_DIR
from email_service import email_service

logger = logging.getLogger(__name__)

REPORT_TYPES = {
    "compliance_summary": {
        "name": "Compliance Summary Report",
        "description": "Overall compliance posture across all frameworks",
        "fields": ["framework_scores", "failing_controls", "upcoming_deadlines"],
    },
    "security_posture": {
        "name": "Security Posture Report",
        "description": "Asset inventory, vulnerability counts, and open alerts",
        "fields": ["alert_summary", "vuln_counts", "asset_count"],
    },
    "executive_dashboard": {
        "name": "Executive Dashboard Report",
        "description": "High-level KPIs for executive and board briefings",
        "fields": ["risk_score", "compliance_score", "incident_count", "trend"],
    },
    "incident_summary": {
        "name": "Incident Summary Report",
        "description": "Incidents opened, closed, and MTTR over period",
        "fields": ["incident_counts", "mttr", "severity_breakdown"],
    },
    "agent_health": {
        "name": "Agent Health Report",
        "description": "Agent connectivity, capability status, and anomalies",
        "fields": ["online_agents", "offline_agents", "capability_errors"],
    },
    "vendor_risk_summary": {
        "name": "Vendor Risk Summary",
        "description": "Third-party vendor connections, TLS expiry, and risk scores",
        "fields": ["vendor_count", "high_risk_vendors", "expiring_certs"],
    },
    "custom_framework": {
        "name": "Custom Framework Report",
        "description": "Per-domain and control scores for custom frameworks",
        "fields": ["domain_scores", "failing_controls", "passing_controls"],
    },
}

SCHEDULE_FREQUENCIES = ["daily", "weekly", "monthly", "quarterly"]

DELIVERY_CHANNELS = ["email", "webhook", "slack", "teams"]


async def create_schedule(tenant_id: str, created_by: str, data: Dict[str, Any]) -> Dict[str, Any]:
    set_tenant_id(tenant_id)
    db = get_database()

    report_type = data.get("report_type", "compliance_summary")
    if report_type not in REPORT_TYPES:
        raise ValueError(f"Invalid report type. Choose from: {list(REPORT_TYPES.keys())}")

    frequency = data.get("frequency", "weekly")
    if frequency not in SCHEDULE_FREQUENCIES:
        raise ValueError(f"Invalid frequency. Choose from: {SCHEDULE_FREQUENCIES}")

    delivery_channel = data.get("delivery_channel", "email")
    if delivery_channel not in DELIVERY_CHANNELS:
        raise ValueError(f"Invalid delivery channel. Choose from: {DELIVERY_CHANNELS}")

    if delivery_channel == "email" and not data.get("recipients"):
        raise ValueError("Email delivery requires at least one recipient")

    if delivery_channel == "email":
        smtp_cfg = await db.smtp_config.find_one({})
        if not smtp_cfg:
            raise ValueError("SMTP not configured")

    now = datetime.now(timezone.utc)
    next_run = _calculate_next_run(frequency, data.get("send_at_hour", 8))

    schedule = {
        "id": str(uuid.uuid4()),
        "tenant_id": tenant_id,
        "created_by": created_by,
        "name": data.get("name", REPORT_TYPES[report_type]["name"]),
        "report_type": report_type,
        "report_type_name": REPORT_TYPES[report_type]["name"],
        "frequency": frequency,
        "send_at_hour": int(data.get("send_at_hour", 8)),
        "day_of_week": data.get("day_of_week", 1),  # Monday = 1
        "day_of_month": data.get("day_of_month", 1),
        "delivery_channel": delivery_channel,
        "recipients": data.get("recipients", []),
        "webhook_url": data.get("webhook_url", ""),
        "slack_webhook": data.get("slack_webhook", ""),
        "teams_webhook": data.get("teams_webhook", ""),
        "include_charts": data.get("include_charts", True),
        "format": data.get("format", "pdf"),  # pdf, html, json
        "filters": data.get("filters", {}),
        "framework_id": data.get("framework_id") or None,
        "framework_name": data.get("framework_name") or None,
        "enabled": True,
        "created_at": now.isoformat(),
        "updated_at": now.isoformat(),
        "last_run": None,
        "next_run": next_run.isoformat(),
        "run_count": 0,
        "last_error": None,
    }

    await db.report_schedules.insert_one(schedule)
    logger.info("[Reports] Schedule created: %s for tenant %s", schedule["name"], tenant_id)
    return schedule


def _calculate_next_run(frequency: str, hour: int = 8) -> datetime:
    now = datetime.now(timezone.utc)
    base = now.replace(minute=0, second=0, microsecond=0)

    if frequency == "daily":
        next_dt = base.replace(hour=hour)
        if next_dt <= now:
            next_dt += timedelta(days=1)
        return next_dt

    elif frequency == "weekly":
        days_ahead = 7 - now.weekday()
        return (base + timedelta(days=days_ahead)).replace(hour=hour)

    elif frequency == "monthly":
        if now.month == 12:
            return base.replace(year=now.year + 1, month=1, day=1, hour=hour)
        return base.replace(month=now.month + 1, day=1, hour=hour)

    else:  # quarterly
        quarter_starts = [1, 4, 7, 10]
        next_month = next((m for m in quarter_starts if m > now.month), 1)
        next_year = now.year if next_month > now.month else now.year + 1
        return base.replace(year=next_year, month=next_month, day=1, hour=hour)


async def _generate_pdf_for_schedule(schedule: Dict[str, Any], tenant_id: str, framework_id: str) -> Optional[bytes]:
    """Call compliance_reporting_pdf._generate_pdf and return file bytes (ephemeral)."""
    result = await compliance_reporting_pdf._generate_pdf(framework_id, _REPORTS_DIR, tenant_id)
    filepath = os.path.join(_REPORTS_DIR, result["filename"])
    try:
        with open(filepath, "rb") as fh:
            pdf_bytes = fh.read()
    finally:
        try:
            os.remove(filepath)
        except OSError:
            pass
    return pdf_bytes


async def _write_delivery_log(
    db,
    schedule: Dict[str, Any],
    status: str,
    error: Optional[str],
    filename: Optional[str],
) -> None:
    """Insert one delivery log entry into report_delivery_logs."""
    await db.report_delivery_logs.insert_one({
        "id": str(uuid.uuid4()),
        "schedule_id": schedule.get("id"),
        "tenant_id": schedule.get("tenant_id"),
        "framework_id": schedule.get("framework_id"),
        "run_at": datetime.now(timezone.utc).isoformat(),
        "recipients": schedule.get("recipients", []),
        "status": status,
        "error": error,
        "format": schedule.get("format"),
        "filename": filename,
    })


async def get_delivery_history(
    schedule_id: str,
    tenant_id: str,
    role: str,
    limit: int = 50,
) -> List[Dict[str, Any]]:
    """Return delivery log entries for a schedule, newest first."""
    db = get_database()
    query: Dict[str, Any] = {"schedule_id": schedule_id}
    if role != "super_admin":
        query["tenant_id"] = tenant_id
    logs = await db.report_delivery_logs.find(query).sort("run_at", -1).to_list(length=limit)
    for log in logs:
        log.pop("_id", None)
    return logs


async def list_schedules(tenant_id: str, role: str) -> List[Dict[str, Any]]:
    set_tenant_id(tenant_id)
    db = get_database()
    query = {} if role == "super_admin" else {"tenant_id": tenant_id}
    schedules = await db.report_schedules.find(query).sort("created_at", -1).to_list(length=200)
    for s in schedules:
        s["_id"] = str(s["_id"])
    return schedules


async def update_schedule(schedule_id: str, tenant_id: str, role: str, data: Dict[str, Any]) -> bool:
    set_tenant_id(tenant_id)
    db = get_database()
    query = {"id": schedule_id}
    if role != "super_admin":
        query["tenant_id"] = tenant_id

    update = {"updated_at": datetime.now(timezone.utc).isoformat()}
    for field in ("name", "frequency", "send_at_hour", "recipients", "webhook_url",
                  "slack_webhook", "teams_webhook", "include_charts", "format", "enabled",
                  "filters", "framework_id", "framework_name"):
        if field in data:
            update[field] = data[field]

    if "frequency" in data:
        update["next_run"] = _calculate_next_run(data["frequency"], data.get("send_at_hour", 8)).isoformat()

    result = await db.report_schedules.update_one(query, {"$set": update})
    return result.modified_count > 0


async def delete_schedule(schedule_id: str, tenant_id: str, role: str) -> bool:
    set_tenant_id(tenant_id)
    db = get_database()
    query = {"id": schedule_id}
    if role != "super_admin":
        query["tenant_id"] = tenant_id
    result = await db.report_schedules.delete_one(query)
    return result.deleted_count > 0


async def run_report_now(schedule_id: str, tenant_id: str, role: str) -> Dict[str, Any]:
    """Generate and deliver report on-demand for the given schedule."""
    set_tenant_id(tenant_id)
    db = get_database()
    query = {"id": schedule_id}
    if role != "super_admin":
        query["tenant_id"] = tenant_id

    schedule = await db.report_schedules.find_one(query)
    if not schedule:
        raise ValueError("Schedule not found")

    eff_tenant_id = schedule.get("tenant_id", tenant_id)
    report_data = await _generate_report(schedule, eff_tenant_id)
    try:
        filename = await _deliver_report(schedule, report_data, eff_tenant_id)
        await _write_delivery_log(db, schedule, "success", None, filename)
    except Exception as exc:
        await _write_delivery_log(db, schedule, "failure", str(exc), None)
        raise

    now = datetime.now(timezone.utc).isoformat()
    next_run = _calculate_next_run(schedule.get("frequency", "weekly"), schedule.get("send_at_hour", 8))
    await db.report_schedules.update_one(
        query,
        {"$set": {"last_run": now, "next_run": next_run.isoformat()}, "$inc": {"run_count": 1}},
    )

    return {"status": "delivered", "delivered_at": now, "report_type": schedule.get("report_type")}


async def _generate_report(schedule: Dict[str, Any], tenant_id: str) -> Dict[str, Any]:
    set_tenant_id(tenant_id)
    db = get_database()
    report_type = schedule.get("report_type", "compliance_summary")
    now = datetime.now(timezone.utc)

    data: Dict[str, Any] = {
        "report_type": report_type,
        "report_name": schedule.get("name", ""),
        "generated_at": now.isoformat(),
        "tenant_id": tenant_id,
        "period_start": (now - timedelta(days=7)).isoformat(),
        "period_end": now.isoformat(),
    }

    if report_type == "compliance_summary":
        frameworks = await db.compliance_frameworks.find({"tenant_id": tenant_id}).to_list(length=20)
        data["frameworks"] = [{"name": f.get("name"), "score": f.get("compliance_score", 0)} for f in frameworks]

    elif report_type == "security_posture":
        alert_count = await db.alerts.count_documents({"tenant_id": tenant_id, "status": "open"})
        asset_count = await db.assets.count_documents({"tenantId": tenant_id})
        data.update({"open_alerts": alert_count, "asset_count": asset_count})

    elif report_type == "executive_dashboard":
        incident_count = await db.incidents.count_documents({"tenant_id": tenant_id, "status": {"$in": ["open", "investigating"]}})
        data.update({"open_incidents": incident_count})

    elif report_type == "agent_health":
        online = await db.agents.count_documents({"tenantId": tenant_id, "status": "Online"})
        offline = await db.agents.count_documents({"tenantId": tenant_id, "status": "Offline"})
        data.update({"online_agents": online, "offline_agents": offline})

    return data


def _build_pdf(report_data: Dict[str, Any]) -> Optional[bytes]:
    """Generate a simple PDF summary of report_data using reportlab. Returns None on failure."""
    try:
        from io import BytesIO
        from reportlab.lib.pagesizes import A4
        from reportlab.lib import colors
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
        from reportlab.lib.styles import getSampleStyleSheet

        buf = BytesIO()
        doc = SimpleDocTemplate(buf, pagesize=A4, rightMargin=40, leftMargin=40, topMargin=60, bottomMargin=40)
        styles = getSampleStyleSheet()
        story = []

        title = report_data.get("report_name", "Security Report")
        story.append(Paragraph(title, styles["Title"]))
        story.append(Spacer(1, 12))
        story.append(Paragraph(f"Generated: {report_data.get('generated_at', '')}", styles["Normal"]))
        story.append(Paragraph(
            f"Period: {report_data.get('period_start', '')} — {report_data.get('period_end', '')}",
            styles["Normal"],
        ))
        story.append(Spacer(1, 24))

        skip = {"report_type", "report_name", "generated_at", "tenant_id", "period_start", "period_end"}
        rows = [["Metric", "Value"]]
        for key, value in report_data.items():
            if key not in skip:
                rows.append([key.replace("_", " ").title(), str(value)])

        if len(rows) > 1:
            tbl = Table(rows, colWidths=[220, 280])
            tbl.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#667eea")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f3f4f6")]),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e5e7eb")),
                ("FONTSIZE", (0, 0), (-1, -1), 10),
                ("PADDING", (0, 0), (-1, -1), 8),
            ]))
            story.append(tbl)

        doc.build(story)
        return buf.getvalue()
    except Exception as exc:
        logger.warning("[Reports] PDF generation failed: %s", exc)
        return None


def _build_html(report_data: Dict[str, Any]) -> str:
    """Generate a self-contained HTML report from report_data."""
    title = report_data.get("report_name", "Security Report")
    generated_at = report_data.get("generated_at", "")
    period_start = report_data.get("period_start", "")
    period_end = report_data.get("period_end", "")
    skip = {"report_type", "report_name", "generated_at", "tenant_id", "period_start", "period_end"}
    rows_html = "".join(
        f"<tr><td>{k.replace('_', ' ').title()}</td><td>{v}</td></tr>"
        for k, v in report_data.items() if k not in skip
    )
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>{title}</title>
<style>
  body {{font-family:Arial,sans-serif;margin:40px;color:#333;}}
  h1 {{color:#667eea;}} p.meta {{color:#666;font-size:.9em;}}
  table {{border-collapse:collapse;width:100%;margin-top:20px;}}
  th {{background:#667eea;color:#fff;padding:10px;text-align:left;}}
  td {{padding:8px 10px;border:1px solid #ddd;}}
  tr:nth-child(even) {{background:#f3f4f6;}}
</style>
</head>
<body>
<h1>{title}</h1>
<p class="meta">Generated: {generated_at} &nbsp;|&nbsp; Period: {period_start} — {period_end}</p>
<table>
  <thead><tr><th>Metric</th><th>Value</th></tr></thead>
  <tbody>{rows_html}</tbody>
</table>
</body>
</html>"""


async def _deliver_report(
    schedule: Dict[str, Any],
    report_data: Dict[str, Any],
    tenant_id: str = "",
) -> Optional[str]:
    """Deliver report via the configured channel. Returns filename or None."""
    channel = schedule.get("delivery_channel", "email")
    logger.info("[Reports] Delivering %s report via %s", schedule.get("report_type"), channel)
    delivered_filename: Optional[str] = None

    if channel == "email":
        fmt = schedule.get("format", "pdf")
        report_type = schedule.get("report_type", "")
        attachments = None
        if fmt == "pdf":
            framework_id = schedule.get("framework_id")
            if framework_id and report_type in ("compliance_summary", "custom_framework"):
                pdf_bytes = await _generate_pdf_for_schedule(schedule, tenant_id, framework_id=framework_id)
                attach_name = f"{schedule.get('name', 'report')}.pdf"
            else:
                pdf_bytes = _build_pdf(report_data)
                attach_name = f"{schedule.get('name', 'report')}.pdf"
            if pdf_bytes:
                attachments = [{"filename": attach_name, "data": pdf_bytes}]
                delivered_filename = attach_name
        elif fmt == "html":
            html_bytes = _build_html(report_data).encode("utf-8")
            attach_name = f"{schedule.get('name', 'report')}.html"
            attachments = [{"filename": attach_name, "data": html_bytes}]
            delivered_filename = attach_name
        elif fmt == "json":
            import json as _json
            json_bytes = _json.dumps(report_data, indent=2).encode("utf-8")
            attach_name = f"{schedule.get('name', 'report')}.json"
            attachments = [{"filename": attach_name, "data": json_bytes}]
            delivered_filename = attach_name
        for recipient in schedule.get("recipients", []):
            await email_service.send_report(
                recipient, schedule.get("name", "Report"), report_data, attachments=attachments
            )

    elif channel in ("webhook", "slack", "teams"):
        webhook_url = schedule.get(f"{channel}_webhook" if channel != "webhook" else "webhook_url", "")
        if webhook_url:
            try:
                import aiohttp
                async with aiohttp.ClientSession() as session:
                    await session.post(webhook_url, json=report_data, timeout=aiohttp.ClientTimeout(total=10))
            except Exception as exc:
                logger.warning("[Reports] Webhook delivery failed: %s", exc)

    return delivered_filename


# ── Background scheduler loop ──────────────────────────────────────────────────

async def start_report_scheduler():
    """Background loop: check every 5 minutes for due reports."""
    logger.info("[Reports] Scheduler loop started")
    while True:
        try:
            await asyncio.sleep(300)
            db = get_database()
            now = datetime.now(timezone.utc).isoformat()
            due_schedules = await db.report_schedules.find(
                {"enabled": True, "next_run": {"$lte": now}}
            ).to_list(length=50)

            for schedule in due_schedules:
                try:
                    sched_tenant_id = schedule.get("tenant_id", "")
                    report_data = await _generate_report(schedule, sched_tenant_id)
                    filename = await _deliver_report(schedule, report_data, sched_tenant_id)
                    await _write_delivery_log(db, schedule, "success", None, filename)
                    next_run = _calculate_next_run(schedule.get("frequency", "weekly"), schedule.get("send_at_hour", 8))
                    await db.report_schedules.update_one(
                        {"id": schedule["id"]},
                        {
                            "$set": {
                                "last_run": now,
                                "next_run": next_run.isoformat(),
                                "last_error": None,
                            },
                            "$inc": {"run_count": 1},
                        },
                    )
                    logger.info("[Reports] Delivered scheduled report '%s' for tenant %s", schedule.get("name"), sched_tenant_id)
                except Exception as exc:
                    logger.error("[Reports] Failed to deliver %s: %s", schedule.get("id"), exc)
                    await _write_delivery_log(db, schedule, "failure", str(exc), None)
                    await db.report_schedules.update_one(
                        {"id": schedule["id"]},
                        {"$set": {"last_error": str(exc)}},
                    )

        except Exception as exc:
            logger.error("[Reports] Scheduler loop error: %s", exc)

"""
Scheduled Report Delivery Service
Schedules and delivers compliance, security, and executive reports via email and webhook.
"""

import os
import re
import uuid
import socket
import asyncio
import calendar
import ipaddress
import logging
import html as _html
from urllib.parse import urlsplit
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

from database import get_database
from tenant_context import set_tenant_id
import compliance_reporting_pdf
from compliance_reports_endpoints import _REPORTS_DIR
from email_service import email_service
try:
    from compliance_narrative_service import enrich_report_data, _render_narratives
except ImportError:  # pragma: no cover — safety fallback if narrative service fails to load
    async def enrich_report_data(*_a, **_kw): pass  # type: ignore[assignment]
    def _render_narratives(*_a, **_kw): pass  # type: ignore[assignment]

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
_EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
_WEBHOOK_FIELD_BY_CHANNEL = {"webhook": "webhook_url", "slack": "slack_webhook", "teams": "teams_webhook"}

def _validate_recipients(recipients: list) -> None:
    """Raise ValueError if any recipient is not a valid email address."""
    for r in recipients:
        if not isinstance(r, str) or not _EMAIL_RE.match(r):
            raise ValueError(f"Invalid email recipient: {r!r}")

def _is_disallowed_ip(ip_str: str) -> bool:
    """Return True for loopback/private/link-local/reserved/multicast addresses (SSRF surface)."""
    try:
        ip = ipaddress.ip_address(ip_str)
    except ValueError:
        return True  # unparsable — fail closed
    return (
        ip.is_private or ip.is_loopback or ip.is_link_local
        or ip.is_multicast or ip.is_reserved or ip.is_unspecified
    )

async def _validate_webhook_url(url: str) -> None:
    """Raise ValueError unless url is https:// and resolves only to public addresses.

    Guards against SSRF via webhook/Slack/Teams delivery URLs pointed at internal
    services (cloud metadata endpoints, internal admin APIs, loopback, etc).
    """
    if not url:
        raise ValueError("Webhook URL must not be empty")
    parsed = urlsplit(url)
    if parsed.scheme != "https":
        raise ValueError(f"Webhook URL must use https:// (got {parsed.scheme or 'no scheme'!r})")
    host = parsed.hostname
    if not host:
        raise ValueError("Webhook URL must include a hostname")
    try:
        ipaddress.ip_address(host)
        is_literal_ip = True
    except ValueError:
        is_literal_ip = False
    if is_literal_ip:
        if _is_disallowed_ip(host):
            raise ValueError(f"Webhook URL resolves to a disallowed address: {host}")
        return
    loop = asyncio.get_event_loop()
    try:
        infos = await loop.run_in_executor(None, socket.getaddrinfo, host, None)
    except socket.gaierror as exc:
        raise ValueError(f"Webhook URL hostname could not be resolved: {host}") from exc
    for info in infos:
        addr = info[4][0]
        if _is_disallowed_ip(addr):
            raise ValueError(f"Webhook URL hostname '{host}' resolves to a disallowed address: {addr}")

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

    if delivery_channel == "email":
        if not data.get("recipients"):
            raise ValueError("Email delivery requires at least one recipient")
        _validate_recipients(data.get("recipients", []))
        smtp_cfg = await db.smtp_config.find_one({})
        if not smtp_cfg:
            raise ValueError("SMTP not configured")
    elif delivery_channel in _WEBHOOK_FIELD_BY_CHANNEL:
        field = _WEBHOOK_FIELD_BY_CHANNEL[delivery_channel]
        await _validate_webhook_url(data.get(field, ""))

    try:
        send_at_hour = int(data.get("send_at_hour", 8))
    except (TypeError, ValueError):
        raise ValueError("send_at_hour must be an integer")
    if not 0 <= send_at_hour <= 23:
        raise ValueError("send_at_hour must be 0-23")

    now = datetime.now(timezone.utc)
    next_run = _calculate_next_run(
        frequency, send_at_hour, data.get("day_of_week", 1), data.get("day_of_month", 1)
    )

    schedule = {
        "id": str(uuid.uuid4()),
        "tenant_id": tenant_id,
        "created_by": created_by,
        "name": data.get("name", REPORT_TYPES[report_type]["name"]),
        "report_type": report_type,
        "report_type_name": REPORT_TYPES[report_type]["name"],
        "frequency": frequency,
        "send_at_hour": send_at_hour,
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

def _calculate_next_run(
    frequency: str, hour: int = 8, day_of_week: int = 1, day_of_month: int = 1,
) -> datetime:
    now = datetime.now(timezone.utc)
    base = now.replace(minute=0, second=0, microsecond=0)

    if frequency == "daily":
        next_dt = base.replace(hour=hour)
        if next_dt <= now:
            next_dt += timedelta(days=1)
        return next_dt

    elif frequency == "weekly":
        # Schedule storage convention: day_of_week 1=Monday ... 7=Sunday.
        # Python's datetime.weekday(): Monday=0 ... Sunday=6.
        target_weekday = (int(day_of_week) - 1) % 7
        days_ahead = (target_weekday - now.weekday()) % 7
        next_dt = (base + timedelta(days=days_ahead)).replace(hour=hour)
        if next_dt <= now:
            next_dt += timedelta(days=7)
        return next_dt

    elif frequency == "monthly":
        target_month = 1 if now.month == 12 else now.month + 1
        target_year = now.year + 1 if now.month == 12 else now.year
        last_day = calendar.monthrange(target_year, target_month)[1]
        target_day = max(1, min(int(day_of_month), last_day))
        return base.replace(year=target_year, month=target_month, day=target_day, hour=hour)

    else:  # quarterly
        quarter_starts = [1, 4, 7, 10]
        next_month = next((m for m in quarter_starts if m > now.month), 1)
        next_year = now.year if next_month > now.month else now.year + 1
        last_day = calendar.monthrange(next_year, next_month)[1]
        target_day = max(1, min(int(day_of_month), last_day))
        return base.replace(year=next_year, month=next_month, day=target_day, hour=hour)

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

async def _write_delivery_log(db, schedule: Dict[str, Any], status: str, error: Optional[str], filename: Optional[str]) -> None:
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

async def get_delivery_history(schedule_id: str, tenant_id: str, role: str, limit: int = 50) -> List[Dict[str, Any]]:
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

    if "recipients" in data:
        _validate_recipients(data["recipients"])

    for field in _WEBHOOK_FIELD_BY_CHANNEL.values():
        if data.get(field):
            await _validate_webhook_url(data[field])

    update = {"updated_at": datetime.now(timezone.utc).isoformat()}
    for field in ("name", "frequency", "send_at_hour", "day_of_week", "day_of_month", "recipients",
                  "webhook_url", "slack_webhook", "teams_webhook", "include_charts", "format",
                  "enabled", "filters", "framework_id", "framework_name"):
        if field in data:
            update[field] = data[field]

    if "frequency" in data:
        try:
            upd_hour = int(data.get("send_at_hour", 8))
        except (TypeError, ValueError):
            raise ValueError("send_at_hour must be an integer")
        if not 0 <= upd_hour <= 23:
            raise ValueError("send_at_hour must be 0-23")
        update["next_run"] = _calculate_next_run(
            data["frequency"], upd_hour, data.get("day_of_week", 1), data.get("day_of_month", 1)
        ).isoformat()

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
    next_run = _calculate_next_run(
        schedule.get("frequency", "weekly"), schedule.get("send_at_hour", 8),
        schedule.get("day_of_week", 1), schedule.get("day_of_month", 1),
    )
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
        if not schedule.get("framework_id"):
            await enrich_report_data(data, db, tenant_id)

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

        title = _html.escape(report_data.get("report_name", "Security Report"), quote=False)
        story.append(Paragraph(title, styles["Title"]))
        story.append(Spacer(1, 12))
        story.append(Paragraph(
            f"Generated: {_html.escape(str(report_data.get('generated_at', '')), quote=False)}",
            styles["Normal"],
        ))
        story.append(Paragraph(
            f"Period: {_html.escape(str(report_data.get('period_start', '')), quote=False)} — "
            f"{_html.escape(str(report_data.get('period_end', '')), quote=False)}",
            styles["Normal"],
        ))
        story.append(Spacer(1, 24))

        _render_narratives(story, report_data, styles, section="executive")

        skip = {"report_type", "report_name", "generated_at", "tenant_id", "period_start", "period_end",
                "ai_executive_summary", "ai_framework_narratives", "top_failing_controls"}
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

        _render_narratives(story, report_data, styles, section="frameworks")

        doc.build(story)
        return buf.getvalue()
    except Exception as exc:
        logger.warning("[Reports] PDF generation failed: %s", exc)
        return None

def _build_html(report_data: Dict[str, Any]) -> str:
    """Generate a self-contained HTML report from report_data."""
    title = _html.escape(report_data.get("report_name", "Security Report"))
    generated_at = _html.escape(report_data.get("generated_at", ""))
    period_start = _html.escape(report_data.get("period_start", ""))
    period_end = _html.escape(report_data.get("period_end", ""))
    skip = {"report_type", "report_name", "generated_at", "tenant_id", "period_start", "period_end"}
    rows_html = "".join(
        f"<tr><td>{_html.escape(k.replace('_', ' ').title())}</td><td>{_html.escape(str(v))}</td></tr>"
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

async def _deliver_report(schedule: Dict[str, Any], report_data: Dict[str, Any], tenant_id: str = "") -> Optional[str]:
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
            if not pdf_bytes:
                raise RuntimeError(
                    f"PDF generation failed for schedule '{schedule.get('name', schedule.get('id'))}'"
                )
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
                # Re-validate at delivery time (not just at save time): DNS can be
                # rebound after the schedule was created/updated, so this is
                # defense-in-depth against SSRF, not just input validation.
                await _validate_webhook_url(webhook_url)
                import aiohttp
                async with aiohttp.ClientSession() as session:
                    await session.post(webhook_url, json=report_data, timeout=aiohttp.ClientTimeout(total=10))
            except Exception as exc:
                logger.warning("[Reports] Webhook delivery failed: %s", exc)

    return delivered_filename

# ── Background scheduler loop ──────────────────────────────────────────────────

async def _process_due_schedule(schedule: Dict[str, Any], db) -> None:
    """Generate, deliver, and log one due schedule. Never raises — all exceptions logged."""
    try:
        sched_tenant_id = schedule.get("tenant_id", "")
        report_data = await _generate_report(schedule, sched_tenant_id)
        filename = await _deliver_report(schedule, report_data, sched_tenant_id)
        await _write_delivery_log(db, schedule, "success", None, filename)
        next_run = _calculate_next_run(
            schedule.get("frequency", "weekly"), schedule.get("send_at_hour", 8),
            schedule.get("day_of_week", 1), schedule.get("day_of_month", 1),
        )
        now = datetime.now(timezone.utc).isoformat()
        await db.report_schedules.update_one(
            {"id": schedule["id"]},
            {
                "$set": {"last_run": now, "next_run": next_run.isoformat(), "last_error": None},
                "$inc": {"run_count": 1},
            },
        )
        logger.info("[Reports] Delivered scheduled report '%s' for tenant %s", schedule.get("name"), sched_tenant_id)
    except Exception as exc:
        logger.error("[Reports] Failed to deliver %s: %s", schedule.get("id"), exc)
        await _write_delivery_log(db, schedule, "failure", str(exc), None)
        await db.report_schedules.update_one({"id": schedule["id"]}, {"$set": {"last_error": str(exc)}})

async def start_report_scheduler():
    """Background loop: check every 5 minutes for due reports."""
    logger.info("[Reports] Scheduler loop started")
    while True:
        try:
            await asyncio.sleep(300)
            set_tenant_id("platform-admin")  # allow cross-tenant query; per-schedule re-scope happens in _generate_report
            db = get_database()
            now = datetime.now(timezone.utc).isoformat()
            due_schedules = await db.report_schedules.find(
                {"enabled": True, "next_run": {"$lte": now}}
            ).to_list(length=50)

            for schedule in due_schedules:
                await _process_due_schedule(schedule, db)

        except Exception as exc:
            logger.error("[Reports] Scheduler loop error: %s", exc)

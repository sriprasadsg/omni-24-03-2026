"""
Compliance Remediation SLA Service.

Pure SLA-computation layer for compliance_remediation_tasks (SLA-01/SLA-02).

Exports (44-01):
  - compute_remediation_sla(task, at_risk_window_days) — pure, day-scale SLA
    status compute; mutates and returns the task dict
  - compute_escalation_level(days_overdue) — tiered escalation level (D-04)
  - get_sla_at_risk_window(db, tenant_id) — per-tenant configurable at-risk
    window, tenant-doc -> global-doc -> hardcoded-default lookup (D-02)

Exports (44-02):
  - run_sla_pass(db) — background sweep: recomputes sla_status for every
    open/in_progress task, tiers the escalation_level on breach, appends an
    immutable remediation_escalations entry, and notifies the resolved
    assignee plus all tenant admins in-app (D-03/D-04, SLA-01)
  - start_remediation_sla_scheduler(db) — polling loop wrapper around
    run_sla_pass, mirrors ticketing_bridge.start_close_loop_scheduler

Anti-pattern (RESEARCH.md): this module must never resolve its own database
handle. Only request-scoped endpoint handlers may do that; the sweep (44-02)
passes raw mongodb.db in. This keeps the module usable from both a
request-scoped TenantIsolatedDatabase call-site and the raw-db background
sweep without ever resolving its own tenant context.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from notification_service import get_notification_service

logger = logging.getLogger(__name__)

# Tenant-admin recipient role set for escalation notifications (D-03,
# RESEARCH.md Open Question 1) — kept identical to notification_manager.py's
# set; do not introduce a third variant.
_ADMIN_ROLES = {"admin", "Admin", "Tenant Admin", "Super Admin", "super_admin", "platform-admin"}

# Escalation tier boundaries in days-past-due -> escalation_level 1/2/3 (D-04).
# A small, justified default confirmed reasonable during planning (CONTEXT.md);
# tunable, not locked.
_TIER_DAYS = [1, 3, 7]

# Hardcoded final fallback for the per-tenant at-risk window (days) when no
# tenant-scoped or global system_settings doc exists (Assumption A1).
_DEFAULT_AT_RISK_WINDOW_DAYS = 3


def compute_remediation_sla(task: Dict[str, Any], at_risk_window_days: int) -> Dict[str, Any]:
    """Pure function — computes sla_status without persisting (SLA-01).

    Mirrors tickets_helpers._compute_sla()'s defensive due-date-parsing shape,
    NOT its hour-scale threshold or ("resolved", "closed") status check —
    those are wrong for compliance_remediation_tasks' day-scale, 3-value
    status enum (RESEARCH.md Pitfall 2).

    Args:
        task: the remediation task dict (mutated in place and returned).
        at_risk_window_days: configurable at-risk window, from
            get_sla_at_risk_window().

    Returns:
        The same task dict with "sla_status" set to one of:
        "ok" | "at_risk" | "breached" | "none".
    """
    if task.get("status") == "resolved":
        task["sla_status"] = "ok"  # resolved tasks are not SLA-tracked
        return task

    due = task.get("due_date")
    if not due:
        task["sla_status"] = "none"
        return task
    try:
        due_str = str(due).replace("Z", "+00:00")
        due_dt = datetime.fromisoformat(due_str)
        if due_dt.tzinfo is None:
            due_dt = due_dt.replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        task["sla_status"] = "none"
        return task

    now = datetime.now(timezone.utc)
    days_remaining = (due_dt - now).total_seconds() / 86400

    if now > due_dt:
        task["sla_status"] = "breached"
    elif days_remaining <= at_risk_window_days:
        task["sla_status"] = "at_risk"
    else:
        task["sla_status"] = "ok"
    return task


def compute_escalation_level(days_overdue: float) -> int:
    """Tiered escalation level per D-04 — 1/3/7 days past due -> level 1/2/3.

    Below the first tier (< 1 day overdue) returns level 0.
    """
    level = 0
    for i, threshold in enumerate(_TIER_DAYS, start=1):
        if days_overdue >= threshold:
            level = i
    return level


async def get_sla_at_risk_window(db, tenant_id) -> int:
    """Per-tenant configurable at-risk window, in days (D-02).

    Lookup order:
    1. Per-tenant doc: {type: "remediation_sla_at_risk", tenantId: <tenant_id>}
    2. Global doc:     {type: "remediation_sla_at_risk"} (no tenantId field)
    3. Hard-coded default: _DEFAULT_AT_RISK_WINDOW_DAYS

    Cloned verbatim from evidence_staleness.get_staleness_threshold() (Phase 7,
    STALE-02), renaming type -> "remediation_sla_at_risk", field -> "windowDays".

    Args:
        db: TenantIsolatedDatabase (request-scoped) or raw Motor db (sweep).
        tenant_id: tenant identifier string or None/empty.

    Returns:
        int — window days (minimum 1, default _DEFAULT_AT_RISK_WINDOW_DAYS).
    """
    def _safe_window(raw_val: int) -> int:
        """Enforce the documented minimum of 1 (defends against 0/negative
        values written directly to the DB, bypassing API validation)."""
        return max(1, raw_val)

    # Dual call-site guard: the sweep (44-02) always passes raw mongodb.db, so
    # this branch never triggers there — it only matters when this function is
    # also called from a request-scoped endpoint where db is a
    # TenantIsolatedDatabase wrapper. Kept exactly as evidence_staleness.py does.
    raw = db._db if hasattr(db, "_db") else db

    if tenant_id:
        doc = await raw.system_settings.find_one(
            {"type": "remediation_sla_at_risk", "tenantId": tenant_id}
        )
        if doc and isinstance(doc.get("windowDays"), int):
            return _safe_window(doc["windowDays"])
    doc = await raw.system_settings.find_one(
        {"type": "remediation_sla_at_risk", "tenantId": {"$exists": False}}
    )
    if doc and isinstance(doc.get("windowDays"), int):
        return _safe_window(doc["windowDays"])
    return _DEFAULT_AT_RISK_WINDOW_DAYS


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_due_date(due: Any) -> Optional[datetime]:
    """Same defensive parsing as compute_remediation_sla(), extracted so the
    sweep can recover the actual overdue duration without re-deriving it."""
    if not due:
        return None
    try:
        due_str = str(due).replace("Z", "+00:00")
        due_dt = datetime.fromisoformat(due_str)
        if due_dt.tzinfo is None:
            due_dt = due_dt.replace(tzinfo=timezone.utc)
        return due_dt
    except (ValueError, TypeError):
        return None


async def _resolve_assignee_email(db, assignee: Any, assignee_type: Any) -> Optional[str]:
    """Resolve a remediation task's free-text `assignee` field to a real
    user's email (T-44-04 / Pitfall 4): email -> id -> username, in that
    order. `assignee` is untrusted free text, not an @mention token, so this
    never passes it straight through as a recipient. An agent-type assignee
    or an unresolved lookup returns None — the caller skips the assignee
    notification only, never the whole escalation, and this never raises.
    """
    if not assignee or assignee_type == "agent":
        return None
    try:
        user = await db.users.find_one({"email": assignee})
        if not user:
            user = await db.users.find_one({"id": assignee})
        if not user:
            user = await db.users.find_one({"username": assignee})
        if user and user.get("email"):
            return user["email"]
    except Exception:
        pass  # silent skip — mirrors control_comments_service.resolve_mentions
    return None


async def _tenant_admin_emails(db, tenant_id: str) -> List[str]:
    """All tenant admin-role users' emails (D-03), via _ADMIN_ROLES."""
    emails: List[str] = []
    try:
        cursor = db.users.find({"tenantId": tenant_id, "role": {"$in": list(_ADMIN_ROLES)}})
        async for user in cursor:
            email = user.get("email")
            if email:
                emails.append(email)
    except Exception:
        pass  # best-effort recipient lookup — never blocks the escalation
    return emails


async def run_sla_pass(db) -> None:
    """One background sweep over open/in_progress compliance_remediation_tasks
    (SLA-01, Success Criterion 2). Cloned structurally from
    ticketing_bridge.run_close_loop_pass — same collection, same raw-db
    requirement, same top-level non-fatal try/except shape.

    For every task: extract tenantId directly from the doc (no ambient tenant
    context exists in a background task); a task with no tenantId is skipped
    entirely (T-44-03). Recompute sla_status via compute_remediation_sla().
    On a breach where the tiered escalation_level would increase, persist the
    new sla_status/escalated/escalation_level, append one immutable
    remediation_escalations entry, and notify the resolved assignee plus all
    tenant admins in-app (D-03). Never escalates twice for the same tier.
    """
    try:
        query = {"status": {"$in": ["open", "in_progress"]}}
        cursor = db.compliance_remediation_tasks.find(query, {"_id": 0})
        async for task in cursor:
            tenant_id = task.get("tenantId")
            if not tenant_id:
                continue  # T-44-03: malformed doc, never escalate/notify

            window = await get_sla_at_risk_window(db, tenant_id)
            compute_remediation_sla(task, window)
            if task["sla_status"] != "breached":
                continue

            due_dt = _parse_due_date(task.get("due_date"))
            if due_dt is None:
                continue  # breached with an unparseable due_date shouldn't
                          # happen, but never escalate on ambiguous evidence

            days_overdue = (datetime.now(timezone.utc) - due_dt).total_seconds() / 86400
            new_level = compute_escalation_level(days_overdue)
            current_level = task.get("escalation_level") or 0
            if new_level <= current_level:
                continue  # only escalate once per tier increase

            await db.compliance_remediation_tasks.update_one(
                {"id": task["id"], "tenantId": tenant_id},
                {"$set": {
                    "sla_status": task["sla_status"],
                    "escalated": True,
                    "escalation_level": new_level,
                }},
            )

            recipients: List[str] = []
            assignee_email = await _resolve_assignee_email(
                db, task.get("assignee"), task.get("assignee_type")
            )
            if assignee_email:
                recipients.append(assignee_email)
            for email in await _tenant_admin_emails(db, tenant_id):
                if email not in recipients:
                    recipients.append(email)

            await db.remediation_escalations.insert_one({
                "task_id": task["id"],
                "tenantId": tenant_id,
                "escalation_level": new_level,
                "days_overdue": days_overdue,
                "notified": recipients,
                "created_at": _now_iso(),
            })

            if recipients:
                try:
                    svc = get_notification_service(db)
                    await svc.send_alert(
                        title="Remediation task SLA breached",
                        message=(
                            f"Task {task['id']} (control {task.get('control_id', 'N/A')}) "
                            f"is {days_overdue:.1f} days overdue — escalation level {new_level}."
                        ),
                        severity="warning",
                        recipients=recipients,
                        tenant_id=tenant_id,
                        channels=[],  # in-app only, mirrors control_comments_endpoints
                        metadata={"task_id": task["id"], "event": "sla_escalation"},
                    )
                except Exception:
                    pass  # non-fatal — a notification failure never aborts the sweep

            try:
                from websocket_manager import broadcast_remediation_update
                await broadcast_remediation_update(tenant_id, {
                    "task_id": task["id"],
                    "sla_status": task["sla_status"],
                    "escalation_level": new_level,
                })
            except Exception:
                pass  # best-effort broadcast — non-fatal
    except Exception as exc:
        logger.error("SLA pass failed: %s", exc)


async def start_remediation_sla_scheduler(db) -> None:
    """Loop every 5 minutes running the SLA pass. Must receive db as a
    passed-in raw parameter — see module docstring; the caller (app startup)
    is responsible for supplying the unwrapped Motor handle, never the
    request-scoped tenant-isolated wrapper."""
    logger.info("Remediation SLA escalation scheduler started (interval=300s)")
    while True:
        await run_sla_pass(db)
        await asyncio.sleep(300)

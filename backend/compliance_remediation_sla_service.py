"""
Compliance Remediation SLA Service.

Pure SLA-computation layer for compliance_remediation_tasks (SLA-01/SLA-02).

Exports (this plan, 44-01):
  - compute_remediation_sla(task, at_risk_window_days) — pure, day-scale SLA
    status compute; mutates and returns the task dict
  - compute_escalation_level(days_overdue) — tiered escalation level (D-04)
  - get_sla_at_risk_window(db, tenant_id) — per-tenant configurable at-risk
    window, tenant-doc -> global-doc -> hardcoded-default lookup (D-02)

44-02 adds the background sweep (run_sla_pass/start_remediation_sla_scheduler)
to this same file — kept under 500 lines with room to grow.

Anti-pattern (RESEARCH.md): this module must never resolve its own database
handle. Only request-scoped endpoint handlers may do that; the sweep (44-02)
passes raw mongodb.db in. This keeps the module usable from both a
request-scoped TenantIsolatedDatabase call-site and the raw-db background
sweep without ever resolving its own tenant context.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict

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

"""ITAM finance computations (Phase 59).

This module holds the ITAM finance computations for Phase 59 and deliberately
imports neither FastAPI nor any database symbol, so every function is
unit-testable without an app or a DB — and so the background warranty-alert
sweep Plan 59-04 adds here can never resolve its own database handle (it will
receive one as a parameter, exactly like compliance_remediation_sla_service.py's
run_sla_pass).

Exports (59-04):
  - WARRANTY_EVENT_TYPE — the event-type string this module's sweep dispatches,
    matching the vocabulary Plan 59-02 opened in notification_service.VALID_EVENTS
    and notification_endpoints.RuleCreate.event_type.
  - run_warranty_alert_pass(db) — background sweep: finds assets whose warranty
    is inside the tenant's alert window or already past expiry, delivers an
    alert through both the guaranteed in-app path and the rule-routed path, and
    marks each asset so it is never alerted twice for the same warranty.
  - start_warranty_alert_scheduler(db) — polling loop wrapper around
    run_warranty_alert_pass, mirrors
    compliance_remediation_sla_service.start_remediation_sla_scheduler.

Anti-pattern (this module must never resolve its own database handle): only
request-scoped endpoint handlers may do that. The sweep receives an unwrapped
handle from application startup as a parameter — it never imports a database
module and never resolves a handle of its own. This keeps the module usable
from both a request-scoped call-site (this plan's read route) and the raw-db
background sweep without ever resolving its own tenant context.
"""
import asyncio
import calendar
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from notification_service import get_notification_service, send_notification

from compliance_remediation_sla_service import _ADMIN_ROLES

logger = logging.getLogger(__name__)

REASON_NO_PURCHASE_RECORD = "no_purchase_record"
REASON_NO_DEPRECIATION_POLICY = "no_depreciation_policy_assigned"

WARRANTY_STATUS_NONE = "none"
WARRANTY_STATUS_ACTIVE = "active"
WARRANTY_STATUS_EXPIRING = "expiring"
WARRANTY_STATUS_EXPIRED = "expired"

WARRANTY_ALERT_WINDOW_SETTING_TYPE = "itam_warranty_alert_window"
_DEFAULT_WARRANTY_ALERT_WINDOW_DAYS = 30

# The exact event-type string Plan 59-02 added to
# notification_service.VALID_EVENTS and notification_endpoints.RuleCreate's
# Literal — a mismatch here means every tenant-configured rule silently
# matches nothing.
WARRANTY_EVENT_TYPE = "itam.warranty_expiring"

# An hourly cadence is ample for a window measured in days (the SLA sweep's
# 300 seconds serves a much shorter-fuse concern) — the warrantyAlertSentAt
# marker makes the exact interval non-critical either way.
_WARRANTY_SWEEP_INTERVAL_SECONDS = 3600


def compute_book_value(
    purchase_date: str,
    purchase_cost_cents: int,
    useful_life_years: int,
    salvage_value_cents: int,
    now: datetime,
) -> Dict[str, Any]:
    """Straight-line depreciation, whole-year boundary proration (ITAM-FIN-03,
    D-04). Never persisted — computed purely from the supplied inputs.

    Returns {"bookValueCents": int, "yearsElapsed": int,
    "annualDepreciationCents": int}. Floors at salvage_value_cents — the
    result is never negative and never below salvage.

    Raises ValueError when useful_life_years is not a positive integer or
    when purchase_date is unparseable — the caller is responsible for turning
    that into a structured response; this function never guesses a default
    policy.
    """
    if not isinstance(useful_life_years, int) or useful_life_years <= 0:
        raise ValueError(f"useful_life_years must be a positive integer, got {useful_life_years!r}")

    try:
        purchase_dt = datetime.fromisoformat(purchase_date.replace("Z", "+00:00"))
    except (ValueError, AttributeError) as exc:
        raise ValueError(f"purchase_date must be an ISO-8601 date/datetime string, got {purchase_date!r}") from exc

    if purchase_dt.tzinfo is None:
        purchase_dt = purchase_dt.replace(tzinfo=timezone.utc)

    years_elapsed = now.year - purchase_dt.year
    if (now.month, now.day) < (purchase_dt.month, purchase_dt.day):
        years_elapsed -= 1
    years_elapsed = max(0, years_elapsed)
    years_elapsed = min(years_elapsed, useful_life_years)

    annual_depreciation_cents = (purchase_cost_cents - salvage_value_cents) // useful_life_years

    book_value_cents = purchase_cost_cents - (years_elapsed * annual_depreciation_cents)
    book_value_cents = max(book_value_cents, salvage_value_cents)

    return {
        "bookValueCents": book_value_cents,
        "yearsElapsed": years_elapsed,
        "annualDepreciationCents": annual_depreciation_cents,
    }


def _add_months(dt: datetime, months: int) -> datetime:
    """Adds a whole number of calendar months to dt, landing on a real date.

    A day that doesn't exist in the target month (e.g. the 31st plus one
    month landing on February) is clamped to that month's last real day via
    calendar.monthrange — dt.replace(month=2, day=31) would otherwise raise
    ValueError, and a raised exception inside a background sweep is silently
    swallowed by its outer handler, stopping every alert for every tenant.
    """
    total = dt.month - 1 + months
    year = dt.year + total // 12
    month = total % 12 + 1
    day = min(dt.day, calendar.monthrange(year, month)[1])
    return dt.replace(year=year, month=month, day=day)


def compute_warranty_status(
    purchase_date: Optional[str],
    warranty_months: Optional[int],
    now: datetime,
    alert_window_days: int,
) -> Dict[str, Any]:
    """Derives warranty expiry and status from purchase_date + warranty_months
    (ITAM-FIN-02, PD-04) — never stored, always computed fresh.

    Returns {"warrantyStatus": ..., "warrantyExpiresAt": ..., "daysToExpiry": ...}.
    warrantyStatus is one of WARRANTY_STATUS_NONE/ACTIVE/EXPIRING/EXPIRED.
    daysToExpiry is the floor of the remaining interval in whole days and
    goes negative once expired, so a caller comparing it against a threshold
    gets a deterministic answer.

    A missing warranty_months, a falsy purchase_date, or a purchase_date that
    cannot be parsed all degrade to WARRANTY_STATUS_NONE with a null expiry —
    this never raises, since a stored value written before this phase's
    validator existed (or written directly to the database) must not take
    down the read route or the background sweep.
    """
    none_result = {
        "warrantyStatus": WARRANTY_STATUS_NONE,
        "warrantyExpiresAt": None,
        "daysToExpiry": None,
    }
    if not purchase_date or warranty_months is None:
        return none_result

    try:
        purchase_dt = datetime.fromisoformat(purchase_date.replace("Z", "+00:00"))
    except (ValueError, AttributeError, TypeError):
        return none_result

    if purchase_dt.tzinfo is None:
        purchase_dt = purchase_dt.replace(tzinfo=timezone.utc)

    expires_at = _add_months(purchase_dt, warranty_months)
    days_to_expiry = (expires_at - now).days

    if now >= expires_at:
        warranty_status = WARRANTY_STATUS_EXPIRED
    elif days_to_expiry <= alert_window_days:
        warranty_status = WARRANTY_STATUS_EXPIRING
    else:
        warranty_status = WARRANTY_STATUS_ACTIVE

    return {
        "warrantyStatus": warranty_status,
        "warrantyExpiresAt": expires_at.isoformat(),
        "daysToExpiry": days_to_expiry,
    }


async def get_warranty_alert_window(db, tenant_id) -> int:
    """Per-tenant configurable warranty alert window, in days.

    Lookup order:
    1. Per-tenant doc: {type: WARRANTY_ALERT_WINDOW_SETTING_TYPE, tenantId: <tenant_id>}
    2. Global doc:     {type: WARRANTY_ALERT_WINDOW_SETTING_TYPE} (no tenantId field)
    3. Hard-coded default: _DEFAULT_WARRANTY_ALERT_WINDOW_DAYS

    Cloned field-for-field from
    compliance_remediation_sla_service.get_sla_at_risk_window, renaming the
    setting type and default. A configured value below 1 is clamped to 1
    (defends against a 0/negative value written directly to the database,
    bypassing API validation); a non-integer configured value is ignored and
    the lookup continues to the next step in the order.

    Args:
        db: TenantIsolatedDatabase (request-scoped, this plan's read route)
            or raw Motor db (Plan 59-04's background sweep).
        tenant_id: tenant identifier string or None/empty.
    """
    def _safe_window(raw_val: int) -> int:
        return max(1, raw_val)

    # Dual call-site guard — identical to get_sla_at_risk_window's own
    # comment: this function is called with a request-scoped wrapped handle
    # from this plan's route and with a raw handle from Plan 59-04's sweep,
    # and it must resolve the same settings document either way.
    raw = db._db if hasattr(db, "_db") else db

    if tenant_id:
        doc = await raw.system_settings.find_one(
            {"type": WARRANTY_ALERT_WINDOW_SETTING_TYPE, "tenantId": tenant_id}
        )
        if doc and isinstance(doc.get("windowDays"), int):
            return _safe_window(doc["windowDays"])
    doc = await raw.system_settings.find_one(
        {"type": WARRANTY_ALERT_WINDOW_SETTING_TYPE, "tenantId": {"$exists": False}}
    )
    if doc and isinstance(doc.get("windowDays"), int):
        return _safe_window(doc["windowDays"])
    return _DEFAULT_WARRANTY_ALERT_WINDOW_DAYS


class _RawDbForNotificationRules:
    """Minimal adapter exposing the single `_db` attribute
    notification_service.send_notification reads on its first line.

    A raw Motor handle has no such attribute, so passing one directly raises
    AttributeError before any work happens — which, inside a sweep whose
    outer handler only logs, would disable warranty alerting entirely and
    invisibly.

    This deliberately is not a TenantIsolatedDatabase: send_notification's
    rule and channel queries already carry explicit tenant filters, so no
    ambient tenant context is needed, and importing a database module here
    would break this module's no-self-resolved-handle guarantee.
    """

    __slots__ = ("_db",)

    def __init__(self, db):
        self._db = db


async def _tenant_admin_emails(db, tenant_id: str) -> List[str]:
    """All tenant admin-role users' emails, via the shared _ADMIN_ROLES set
    (imported from compliance_remediation_sla_service rather than
    redeclared — that module's own comment states the set is kept identical
    to notification_manager.py's and that a third variant must not be
    introduced). The explicit tenantId term in this query is the control
    that stops one tenant's warranty alert reaching another tenant's admins
    — it is not optional and must never be dropped, because in this code
    path there is no wrapper to inject it for us."""
    emails: List[str] = []
    try:
        cursor = db.users.find({"tenantId": tenant_id, "role": {"$in": list(_ADMIN_ROLES)}})
        async for user in cursor:
            email = user.get("email")
            if email:
                emails.append(email)
    except Exception:
        pass  # best-effort recipient lookup — never blocks an alert
    return emails


async def run_warranty_alert_pass(db) -> int:
    """One background sweep over assets with a purchase/warranty record
    (ITAM-FIN-02). Cloned structurally from
    compliance_remediation_sla_service.run_sla_pass: one outer
    try/except Exception that logs and never re-raises, wrapping an
    async for over a cursor.

    For every asset: extract tenantId directly from the doc (no ambient
    tenant context exists in a background task); an asset with no tenantId
    is skipped entirely — it can never be safely attributed to anyone, so it
    is never alerted and never written to. Recompute warranty status via the
    same compute_warranty_status/get_warranty_alert_window the read route
    calls, so an operator's on-screen status and the alert they receive can
    never disagree.

    Delivery is attempted on two independent paths, each inside its own
    non-fatal try/except: the guaranteed in-app path
    (get_notification_service(db).send_alert, called with the raw db
    directly — NotificationService never unwraps its handle) and the
    rule-routed path (notification_service.send_notification, called
    through the _RawDbForNotificationRules adapter, since that function
    reads a `_db` attribute a raw handle does not have). A failure on one
    path never suppresses the other, and neither may abort the sweep.

    The warrantyAlertSentAt marker is written unconditionally once an asset
    has reached the delivery step, regardless of whether either delivery
    attempt succeeded: retrying on every pass until a delivery succeeds
    would turn one permanently misconfigured channel into an unbounded
    notification storm against a third party, and re-alerting is still
    reachable through the documented reset (a
    PATCH /api/assets/{asset_id}/purchase that changes purchaseDate or
    warrantyMonths clears the marker — Plan 59-01). Both terms of the
    update filter matter: the tenantId term is what stops a colliding asset
    id in another tenant from being written.

    Returns the count of assets handled (alerted and marked) this pass.
    """
    count = 0
    try:
        query = {
            "purchaseDate": {"$exists": True, "$ne": None},
            "warrantyMonths": {"$exists": True, "$ne": None},
            "warrantyAlertSentAt": {"$exists": False},
        }
        cursor = db.assets.find(query, {"_id": 0})
        async for asset in cursor:
            tenant_id = asset.get("tenantId")
            if not tenant_id:
                continue  # a document with no tenant cannot be safely
                          # attributed to anyone

            if asset.get("warrantyAlertSentAt"):
                continue  # same guard again in Python — idempotency does
                          # not depend on the database honoring the query
                          # term above

            window = await get_warranty_alert_window(db, tenant_id)
            status_result = compute_warranty_status(
                asset.get("purchaseDate"),
                asset.get("warrantyMonths"),
                datetime.now(timezone.utc),
                window,
            )
            if status_result["warrantyStatus"] not in (
                WARRANTY_STATUS_EXPIRING,
                WARRANTY_STATUS_EXPIRED,
            ):
                continue

            asset_label = asset.get("assetTag") or asset.get("id")
            title = "Asset warranty expiring"
            message = (
                f"Asset {asset_label} warranty is {status_result['warrantyStatus']} "
                f"(expires {status_result['warrantyExpiresAt']})."
            )

            # Path one, guaranteed in-app: pass the raw db straight in —
            # NotificationService stores whatever handle it is given and
            # writes self.db.notifications.insert_one(...) directly, so this
            # path needs no adapter. channels=[] is load-bearing: omitting
            # it makes send_alert default to ["email"] and attempt SMTP.
            try:
                recipients = await _tenant_admin_emails(db, tenant_id)
                if recipients:
                    await get_notification_service(db).send_alert(
                        title=title,
                        message=message,
                        severity="warning",
                        recipients=recipients,
                        tenant_id=tenant_id,
                        channels=[],
                        metadata={
                            "asset_id": asset["id"],
                            "event": WARRANTY_EVENT_TYPE,
                            "warrantyStatus": status_result["warrantyStatus"],
                            "warrantyExpiresAt": status_result["warrantyExpiresAt"],
                        },
                    )
            except Exception as exc:
                logger.warning(
                    "Warranty in-app alert failed for asset %s: %s", asset.get("id"), exc
                )

            # Path two, rule-routed: routes to a tenant's configured
            # Slack/webhook/email channel rules, whether or not there were
            # in-app recipients — it routes to configured channels rather
            # than to people. The hasattr unwrap keeps the adapter correct
            # if a caller ever passes an already-wrapped handle.
            try:
                raw_handle = db._db if hasattr(db, "_db") else db
                await send_notification(
                    _RawDbForNotificationRules(raw_handle),
                    tenant_id,
                    WARRANTY_EVENT_TYPE,
                    {
                        "message": message,
                        "severity": "warning",
                        "asset_id": asset["id"],
                        "assetTag": asset.get("assetTag"),
                        "warrantyStatus": status_result["warrantyStatus"],
                        "warrantyExpiresAt": status_result["warrantyExpiresAt"],
                    },
                )
            except Exception as exc:
                logger.warning(
                    "Warranty rule-routed alert failed for asset %s: %s", asset.get("id"), exc
                )

            await db.assets.update_one(
                {"id": asset["id"], "tenantId": tenant_id},
                {"$set": {"warrantyAlertSentAt": datetime.now(timezone.utc).isoformat()}},
            )
            count += 1
    except Exception as exc:
        logger.error("Warranty alert pass failed: %s", exc)
    return count


async def start_warranty_alert_scheduler(db) -> None:
    """Loop forever running the warranty alert pass. Must receive db as a
    passed-in raw parameter — see module docstring; the caller (application
    startup) is responsible for supplying the unwrapped handle rather than
    any request-scoped wrapper."""
    logger.info(
        "Warranty alert scheduler started (interval=%ss)", _WARRANTY_SWEEP_INTERVAL_SECONDS
    )
    while True:
        await run_warranty_alert_pass(db)
        await asyncio.sleep(_WARRANTY_SWEEP_INTERVAL_SECONDS)

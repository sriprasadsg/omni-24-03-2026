"""ITAM finance computations (Phase 59).

This module holds the ITAM finance computations for Phase 59 and deliberately
imports neither FastAPI nor any database symbol, so every function is
unit-testable without an app or a DB — and so the background warranty-alert
sweep Plan 59-04 adds here can never resolve its own database handle (it will
receive one as a parameter, exactly like compliance_remediation_sla_service.py's
run_sla_pass).
"""
import calendar
from datetime import datetime, timezone
from typing import Any, Dict, Optional

REASON_NO_PURCHASE_RECORD = "no_purchase_record"
REASON_NO_DEPRECIATION_POLICY = "no_depreciation_policy_assigned"

WARRANTY_STATUS_NONE = "none"
WARRANTY_STATUS_ACTIVE = "active"
WARRANTY_STATUS_EXPIRING = "expiring"
WARRANTY_STATUS_EXPIRED = "expired"

WARRANTY_ALERT_WINDOW_SETTING_TYPE = "itam_warranty_alert_window"
_DEFAULT_WARRANTY_ALERT_WINDOW_DAYS = 30


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

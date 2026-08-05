"""ITAM finance computations (Phase 59).

This module holds the ITAM finance computations for Phase 59 and deliberately
imports neither FastAPI nor any database symbol, so every function is
unit-testable without an app or a DB — and so the background warranty-alert
sweep Plan 59-04 adds here can never resolve its own database handle (it will
receive one as a parameter, exactly like compliance_remediation_sla_service.py's
run_sla_pass).
"""
from datetime import datetime, timezone
from typing import Any, Dict

REASON_NO_PURCHASE_RECORD = "no_purchase_record"
REASON_NO_DEPRECIATION_POLICY = "no_depreciation_policy_assigned"


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

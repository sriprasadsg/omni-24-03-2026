"""ITAM background sweeps that dispatch webhook events and create tickets for
conditions that are functions of elapsed time rather than of a mutation
(Phase 73, Plan 73-03).

Every function here receives a raw, unwrapped database handle as a
parameter and never resolves one itself — mirroring itam_finance_service.py
and compliance_remediation_sla_service.py's own anti-pattern comment — and
every outbound webhook dispatch is individually tenant-bracketed, since the
same reasoning ticketing_bridge.py's module docstring already records: a
background sweep has no request and therefore no ambient tenant, so an
unbracketed call resolves the subscription lookup against a filter that
matches nothing and fails silently (RESEARCH Pitfall 3).

Exports (73-03):
  - LICENSE_EXPIRY_ALERT_WINDOW_DAYS — fixed 30-day window, deliberately not
    a tenant setting (no new configuration surface for this phase).
  - LICENSE_EXPIRY_MARKER_FIELD — idempotency marker, mirrors
    itam_finance_service.py's warrantyAlertSentAt naming.
  - _dispatch_tenant_scoped_event(tenant_id, event_type, payload) — the one
    tenant-bracketing helper every sweep in this module dispatches through,
    so the bracket cannot be forgotten at a new call site. This is not an
    event-dispatch abstraction layer in D-07's sense: it adds no routing, no
    registry, and no indirection about which event fires where — it is a
    tenant-context guard around the single trigger_webhook call.
  - run_license_expiry_alert_pass(db) — background sweep: finds licenses
    whose expiry date is inside the alert window or already past, claims
    each one atomically (marker-absent as part of the update filter, not a
    separate read-then-write), and dispatches license.expiring_soon under
    that license's own tenant context.

Extended by Plan 73-05 (not built here): run_audit_overdue_alert_pass,
run_stuck_approval_ticket_pass, start_itam_event_sweep_scheduler,
AUDIT_OVERDUE_MARKER_FIELD, ITAM_EVENT_SWEEP_INTERVAL_SECONDS.

Ordering note (documented per this plan's own output contract): this
sweep's claim precedes its dispatch (find_one_and_update's own filter
carries the marker-absent condition), the opposite of
itam_finance_service.run_warranty_alert_pass's dispatch-then-mark order.
That warranty ordering marks unconditionally after the delivery step to
bound a permanently misconfigured subscriber's retry storm; this sweep's
claim IS the concurrency guard against two overlapping passes double-firing
the same licence, so it must happen before the dispatch, not after. Plan
73-05 should choose this claim-then-act ordering for its own new sweeps.
"""
import logging
from datetime import datetime, timezone

from itam_webhook_events import EVENT_LICENSE_EXPIRING_SOON
from tenant_context import set_tenant_id, reset_tenant_id
from webhook_service import WebhookService

logger = logging.getLogger(__name__)

# Module-level singleton — mirrors itam_finance_service.py's own
# WebhookService() instance shape (never one-per-call).
_webhook_service = WebhookService()

# Mirrors itam_finance_service.py's default warranty alert window — a fixed
# constant rather than a tenant setting, the same call the user made for the
# other thresholds in this phase (no new configuration surface).
LICENSE_EXPIRY_ALERT_WINDOW_DAYS = 30

# Mirrors itam_finance_service.py's warrantyAlertSentAt naming.
LICENSE_EXPIRY_MARKER_FIELD = "licenseExpiryAlertSentAt"


async def _dispatch_tenant_scoped_event(tenant_id: str, event_type: str, payload: dict) -> None:
    """Brackets a single awaited trigger_webhook call with
    set_tenant_id/reset_tenant_id around tenant_id, catches and logs any
    exception, and never re-raises — so one document's dispatch failure
    never aborts the sweep it was called from. Every sweep in this module,
    including the two Plan 73-05 adds, must dispatch through this one
    helper rather than calling trigger_webhook directly, so the bracket
    cannot be forgotten at a new call site."""
    token = set_tenant_id(tenant_id)
    try:
        await _webhook_service.trigger_webhook(event_type, payload)
    except Exception as exc:
        logger.warning(
            "Webhook dispatch failed for event %s (tenant %s): %s", event_type, tenant_id, exc
        )
    finally:
        reset_tenant_id(token)


async def run_license_expiry_alert_pass(db) -> int:
    """One background sweep over licenses with an expiry date (ITAM-API-02,
    D-05). Structural clone of
    itam_finance_service.run_warranty_alert_pass: one outer
    try/except Exception that logs and never re-raises, wrapping an
    async for over a cursor.

    For every license: extract tenantId directly from the doc (no ambient
    tenant context exists in a background task); a license with no tenantId
    is skipped entirely — never alerted, never written to, mirroring the
    warranty sweep's existing rule. Compute expiry using
    itam_license_endpoints._enrich_license_seats_and_expiry (imported here,
    inside the function body, to avoid an import cycle at application
    startup — following itam_reporting_prebuilt.py's own precedent for
    importing that same helper), passing a seats-assigned value of zero
    since only the expiry half of its output is used here. A license is
    treated as in-window when its computed days-until-expiry is at or below
    LICENSE_EXPIRY_ALERT_WINDOW_DAYS, which includes already-expired
    licenses.

    The claim precedes the dispatch: find_one_and_update's own filter
    carries the license id, the tenant id, and a marker-field-absent
    condition, setting the marker to the current timestamp. When it returns
    nothing, another pass already claimed this license — the sweep
    continues without dispatching. Only a successful claim is followed by
    _dispatch_tenant_scoped_event. See this module's docstring for why this
    ordering deliberately differs from the warranty sweep's.

    Returns the count of licenses claimed (and, where the claim raised no
    dispatch-worthy exception, alerted) this pass.
    """
    from itam_license_endpoints import _enrich_license_seats_and_expiry

    count = 0
    try:
        query = {
            "expiryDate": {"$exists": True, "$ne": None},
            LICENSE_EXPIRY_MARKER_FIELD: {"$exists": False},
        }
        cursor = db.licenses.find(query, {"_id": 0})
        async for license_doc in cursor:
            tenant_id = license_doc.get("tenantId")
            if not tenant_id:
                continue  # a document with no tenant cannot be safely
                          # attributed to anyone

            license_id = license_doc.get("id")
            if not license_id:
                continue

            now = datetime.now(timezone.utc)
            enriched = _enrich_license_seats_and_expiry(dict(license_doc), 0, now)
            days_until_expiry = enriched.get("daysUntilExpiry")
            if days_until_expiry is None or days_until_expiry > LICENSE_EXPIRY_ALERT_WINDOW_DAYS:
                continue

            try:
                claimed = await db.licenses.find_one_and_update(
                    {
                        "id": license_id,
                        "tenantId": tenant_id,
                        LICENSE_EXPIRY_MARKER_FIELD: {"$exists": False},
                    },
                    {"$set": {LICENSE_EXPIRY_MARKER_FIELD: now.isoformat()}},
                )
            except Exception as exc:
                logger.warning(
                    "License expiry claim failed for license %s: %s", license_id, exc
                )
                continue

            if not claimed:
                continue  # already claimed by another (overlapping) pass

            await _dispatch_tenant_scoped_event(
                tenant_id,
                EVENT_LICENSE_EXPIRING_SOON,
                {
                    "licenseId": license_id,
                    "name": license_doc.get("name"),
                    "expiryDate": license_doc.get("expiryDate"),
                    "daysUntilExpiry": days_until_expiry,
                    "isExpired": enriched.get("isExpired", False),
                },
            )
            count += 1
    except Exception as exc:
        logger.error("License expiry alert pass failed: %s", exc)
    return count

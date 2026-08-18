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
from datetime import datetime, timedelta, timezone

from itam_webhook_events import EVENT_ASSET_AUDIT_OVERDUE, EVENT_LICENSE_EXPIRING_SOON
from tenant_context import set_tenant_id, reset_tenant_id
from ticketing_bridge import create_ticket_for_itam_event
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

# Plan 73-05: audit-overdue sweep idempotency marker, mirroring
# warrantyAlertSentAt's naming convention.
AUDIT_OVERDUE_MARKER_FIELD = "auditOverdueAlertSentAt"

# Plan 73-05: both new sweeps in this module (audit-overdue, stuck-approval)
# run on this single daily cadence, deliberately daily rather than the
# warranty/licence job's hourly cadence — the underlying threshold both new
# sweeps check against is measured in months/a year, not hours (user's
# resolution of RESEARCH Open Question 2). Expressed as a literal seconds
# value so start_itam_event_sweep_scheduler needs no unit conversion.
ITAM_EVENT_SWEEP_INTERVAL_SECONDS = 24 * 60 * 60

# Plan 73-05 Task 2: stuck-approval sweep idempotency marker.
STUCK_APPROVAL_MARKER_FIELD = "stuckApprovalTicketedAt"

# Plan 73-05 Task 2: fixed escalation window for a pending high-value asset
# request (D-10's second automatic trigger) — a fixed constant, not a
# tenant setting, matching the user's resolution of research Open Question 3.
STUCK_APPROVAL_WINDOW_DAYS = 7

# Plan 73-05 Task 2: fixed high-value classification thresholds — both fixed
# constants, not tenant-configurable (user's resolution of Open Question 3).
# HIGH_VALUE_REQUEST_QUANTITY exists because no asset-request document in any
# existing tenant carries `estimated_cost` (RESEARCH.md Assumption A2 is
# false — see this plan's Flagged Assumptions item 1): a cost-only rule would
# never fire against real data, so quantity is a deliberate, recorded
# substitute criterion, not an invented requirement.
HIGH_VALUE_REQUEST_COST = 2000
HIGH_VALUE_REQUEST_QUANTITY = 10

# Plan 73-05 Task 2: this sweep creates a ticket only — D-05 defines no
# webhook event for a stuck approval, so no EVENT_* constant is added to
# itam_webhook_events.py for it. This string exists solely for
# create_ticket_for_itam_event's mechanical type-derivation (73-04's
# `itam_<event_type>` rule), never dispatched as a webhook.
STUCK_APPROVAL_TICKET_EVENT_TYPE = "asset_request.stuck_approval"


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


async def run_audit_overdue_alert_pass(db) -> int:
    """One background sweep over assets overdue for physical audit
    (ITAM-API-02 D-05, ITAM-API-03 D-10's first automatic trigger).
    RESEARCH.md Pitfall 6: the overdue-audit condition is purely a function
    of elapsed time — nothing mutates when an asset crosses the threshold —
    and the existing overdue-audit report route (itam_lifecycle_endpoints.py)
    is deliberately computed at request time, not swept. This function is
    the sweep D-05/D-10 need, built on top of that report's own query/row
    helpers rather than a re-expressed definition, so the two can never
    drift (imported here, deferred, mirroring itam_reporting_prebuilt.py's
    own precedent for the identical import).

    Structural clone of run_license_expiry_alert_pass: claim precedes
    dispatch (find_one_and_update's own filter carries the marker-absent
    condition) — this sweep's claim IS its concurrency guard, per this
    module's own docstring ordering note. Only after a successful claim:
    dispatch asset.audit_overdue (via _dispatch_tenant_scoped_event), then
    attempt the automatic ticket (via create_ticket_for_itam_event) — each
    inside its own non-re-raising try/except, so a ticket-creation failure
    never prevents the webhook from having been dispatched and never aborts
    the pass. create_ticket_for_itam_event already brackets its own tenant
    context and already refuses a second ticket for an entity carrying a
    ticket_ref (dedup guard) — no extra guard is needed at this call site.

    A document with no tenantId is skipped entirely — never alerted, never
    ticketed, never written to.

    Returns the count of assets claimed (and alerted) this pass.
    """
    from itam_lifecycle_endpoints import _audit_cutoff_iso, _overdue_query, _overdue_row

    count = 0
    try:
        cutoff = _audit_cutoff_iso()
        query = dict(_overdue_query(cutoff))
        query[AUDIT_OVERDUE_MARKER_FIELD] = {"$exists": False}

        cursor = db.assets.find(query)
        async for asset_doc in cursor:
            tenant_id = asset_doc.get("tenantId")
            if not tenant_id:
                continue  # a document with no tenant cannot be safely attributed to anyone

            asset_id = asset_doc.get("id")
            if not asset_id:
                continue

            now = datetime.now(timezone.utc)
            try:
                claimed = await db.assets.find_one_and_update(
                    {
                        "id": asset_id,
                        "tenantId": tenant_id,
                        AUDIT_OVERDUE_MARKER_FIELD: {"$exists": False},
                    },
                    {"$set": {AUDIT_OVERDUE_MARKER_FIELD: now.isoformat()}},
                )
            except Exception as exc:
                logger.warning("Audit-overdue claim failed for asset %s: %s", asset_id, exc)
                continue

            if not claimed:
                continue  # already claimed by another (overlapping) pass

            row = _overdue_row(claimed, cutoff, now)

            try:
                await _dispatch_tenant_scoped_event(
                    tenant_id,
                    EVENT_ASSET_AUDIT_OVERDUE,
                    {
                        "assetId": claimed.get("id"),
                        "assetTag": claimed.get("assetTag"),
                        "hostname": claimed.get("hostname"),
                        "ageBasis": row.get("ageBasis"),
                        "neverAudited": row.get("neverAudited"),
                        "daysOverdue": row.get("daysOverdue"),
                    },
                )
            except Exception as exc:
                logger.warning("Audit-overdue webhook dispatch failed for asset %s: %s", asset_id, exc)

            try:
                await create_ticket_for_itam_event(
                    db, "asset", claimed, tenant_id, EVENT_ASSET_AUDIT_OVERDUE,
                )
            except Exception as exc:
                logger.warning("Audit-overdue ticket creation failed for asset %s: %s", asset_id, exc)

            count += 1
    except Exception as exc:
        logger.error("Audit-overdue alert pass failed: %s", exc)
    return count


def _is_high_value_request(request: dict) -> bool:
    """True when `estimated_cost` is present and at or above
    HIGH_VALUE_REQUEST_COST, or when `quantity` is at or above
    HIGH_VALUE_REQUEST_QUANTITY.

    The quantity arm exists because RESEARCH.md Assumption A2 is false: no
    asset-request document in any existing tenant carries `estimated_cost`
    (it did not exist as a field before this plan), so a cost-only rule
    would never fire against real data. This is a deliberate, recorded
    substitution for that false assumption (this plan's Flagged Assumptions
    item 1), not an invented requirement — quantity is a real, always-present
    field on every request document, cost is not.
    """
    cost = request.get("estimated_cost")
    if cost is not None and cost >= HIGH_VALUE_REQUEST_COST:
        return True
    quantity = request.get("quantity") or 0
    return quantity >= HIGH_VALUE_REQUEST_QUANTITY


async def run_stuck_approval_ticket_pass(db) -> int:
    """One background sweep over pending asset requests stuck beyond the
    escalation window (ITAM-API-03 D-10's second automatic trigger),
    structurally cloned from run_audit_overdue_alert_pass. D-05 defines no
    webhook event for a stuck approval, so this sweep creates a ticket only
    — it never dispatches through _dispatch_tenant_scoped_event.

    The `asset_requests` collection genuinely differs from `assets`: tenant
    id lives under the snake_case `tenant_id` key (itam_asset_request_service.py),
    not camelCase `tenantId` — every filter and claim in this function uses
    that snake_case key, matching ticketing_bridge.ITAM_ENTITY_COLLECTIONS'
    own asset_request entry.

    Claim precedes ticket creation (find_one_and_update's own filter carries
    the marker-absent condition) — this sweep's claim IS its concurrency
    guard, same ordering as run_audit_overdue_alert_pass and for the same
    reason (this module's docstring).

    Returns the count of requests claimed (and ticketed) this pass.
    """
    count = 0
    try:
        cutoff = datetime.now(timezone.utc) - timedelta(days=STUCK_APPROVAL_WINDOW_DAYS)
        query = {
            "status": "pending",
            "request_date": {"$lt": cutoff},
            STUCK_APPROVAL_MARKER_FIELD: {"$exists": False},
        }
        cursor = db.asset_requests.find(query)
        async for request_doc in cursor:
            tenant_id = request_doc.get("tenant_id")
            if not tenant_id:
                continue  # a document with no tenant cannot be safely attributed to anyone

            request_id = request_doc.get("id")
            if not request_id:
                continue

            if not _is_high_value_request(request_doc):
                continue

            now = datetime.now(timezone.utc)
            try:
                claimed = await db.asset_requests.find_one_and_update(
                    {
                        "id": request_id,
                        "tenant_id": tenant_id,
                        STUCK_APPROVAL_MARKER_FIELD: {"$exists": False},
                    },
                    {"$set": {STUCK_APPROVAL_MARKER_FIELD: now.isoformat()}},
                )
            except Exception as exc:
                logger.warning("Stuck-approval claim failed for request %s: %s", request_id, exc)
                continue

            if not claimed:
                continue  # already claimed by another (overlapping) pass

            try:
                await create_ticket_for_itam_event(
                    db, "asset_request", claimed, tenant_id, STUCK_APPROVAL_TICKET_EVENT_TYPE,
                )
            except Exception as exc:
                logger.warning("Stuck-approval ticket creation failed for request %s: %s", request_id, exc)

            count += 1
    except Exception as exc:
        logger.error("Stuck-approval ticket pass failed: %s", exc)
    return count

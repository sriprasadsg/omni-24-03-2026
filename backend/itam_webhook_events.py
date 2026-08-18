"""ITAM webhook event-type constants (Phase 73, D-05).

Single source of truth for every ITAM webhook event-type string. These
values are matched verbatim against `db.webhooks` subscription documents'
`events` arrays (see `webhook_service.WebhookService.trigger_webhook`) and
are mirrored identically in the frontend event picker by plan 73-06 —
renaming one of these strings orphans every existing tenant subscription to
it, since a subscription document stores the literal string, not a symbolic
reference to this module.

This module is constants-only: no functions, no dispatch wrapper (D-07
forbids a new event-dispatch abstraction layer — call sites use
`webhook_service.WebhookService.trigger_webhook` directly with one of these
constants).
"""

EVENT_ASSET_CHECKED_OUT = "asset.checked_out"
EVENT_ASSET_CHECKED_IN = "asset.checked_in"
EVENT_ASSET_WARRANTY_EXPIRING = "asset.warranty_expiring"
EVENT_LICENSE_EXPIRING_SOON = "license.expiring_soon"
EVENT_ASSET_REQUEST_APPROVED = "asset.request_approved"
EVENT_ASSET_REQUEST_DENIED = "asset.request_denied"
EVENT_CONSUMABLE_LOW_STOCK = "consumable.low_stock"
EVENT_ASSET_AUDIT_OVERDUE = "asset.audit_overdue"

ITAM_WEBHOOK_EVENT_TYPES = (
    EVENT_ASSET_CHECKED_OUT,
    EVENT_ASSET_CHECKED_IN,
    EVENT_ASSET_WARRANTY_EXPIRING,
    EVENT_LICENSE_EXPIRING_SOON,
    EVENT_ASSET_REQUEST_APPROVED,
    EVENT_ASSET_REQUEST_DENIED,
    EVENT_CONSUMABLE_LOW_STOCK,
    EVENT_ASSET_AUDIT_OVERDUE,
)

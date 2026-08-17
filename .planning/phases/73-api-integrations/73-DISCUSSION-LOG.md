# Phase 73: API & Integrations - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-08-18
**Phase:** 73-api-integrations
**Areas discussed:** REST API auth model (ITAM-API-01), Webhook event catalog (ITAM-API-02), Jira/ServiceNow scope (ITAM-API-03), API discoverability/docs

---

## REST API auth model (ITAM-API-01)

| Option | Description | Selected |
|--------|-------------|----------|
| Extend existing routers | Swap `_require_itam_admin`'s `Depends(get_current_user)` → `Depends(get_current_user_or_api_key)` across `itam_*_endpoints.py`. Reuses Phase 69's ITAM-scoped API key system. | ✓ |
| Separate /api/v1/itam surface | New dedicated external API routers wrapping internal ITAM services. | |

**User's choice:** Extend existing routers.

| Option | Description | Selected |
|--------|-------------|----------|
| All ITAM routers | Asset, lifecycle, license, consumable, component, finance, reports — every `_require_itam_admin`-gated router. | ✓ |
| Curated subset only | Pick specific routers for the initial API surface. | |

**User's choice:** All ITAM routers.

| Option | Description | Selected |
|--------|-------------|----------|
| Reuse existing paths | No `/v1/` prefix. | ✓ |
| Add /api/v1/itam/* prefix | New versioned path space. | |

**User's choice:** Reuse existing paths.

| Option | Description | Selected |
|--------|-------------|----------|
| Reuse existing limiter | `api_key_auth.py`'s existing per-key `_check_rate_limit`. | ✓ |
| ITAM-specific tier | Separate rate limit for ITAM bulk operations. | |

**User's choice:** Reuse existing limiter.

---

## Webhook event catalog (ITAM-API-02)

| Option | Description | Selected |
|--------|-------------|----------|
| Asset check-out/check-in | Phase 57 lifecycle actions. | ✓ |
| Warranty/license expiring | Mirrors Phase 71/59's alert windows. | ✓ |
| Asset request approved/denied | Phase 71's approval workflow. | ✓ |
| Low-stock consumable / overdue audit | Phase 72's pre-built-report triggers as push events. | ✓ |

**User's choice:** All four event categories selected.

| Option | Description | Selected |
|--------|-------------|----------|
| Flat asset-record payload | Matches existing `webhook_service.py._send_single_webhook` shape. | ✓ |
| Custom structured envelope per event type | Bespoke payload schema per event. | |

**User's choice:** Flat asset-record payload.

| Option | Description | Selected |
|--------|-------------|----------|
| Inline in service functions | `trigger_webhook()` calls directly in `itam_*_service.py` mutation functions. | ✓ |
| Separate event-dispatch layer | New `itam_events.py` mediator module. | |

**User's choice:** Inline in service functions.

**Follow-up:** Warranty/license-expiring events aren't triggered by a mutation. Where should that check live?

| Option | Description | Selected |
|--------|-------------|----------|
| Piggyback existing scheduler | Add `trigger_webhook()` at Phase 71's existing periodic warranty/depreciation alert job (ITAM-PRO-05). | ✓ |
| New dedicated scheduled job | Separate periodic task independent of Phase 71's scheduler. | |

**User's choice:** Piggyback existing scheduler.

---

## Jira/ServiceNow scope (ITAM-API-03)

| Option | Description | Selected |
|--------|-------------|----------|
| Generalize the bridge to ITAM events too | New ITAM-event alert-shape adapter alongside `_task_to_alert_shape`, reusing `create_jira_ticket`/`create_servicenow_incident` as-is. | |
| Asset data sync (CMDB-style) | Push/sync asset records into Jira/ServiceNow on schedule or change. | |
| Both, but ticket-per-event is primary | Build the alert-shape adapter now; note CMDB sync as deferred. | ✓ |

**User's choice:** Both, but ticket-per-event is primary — CMDB-style sync deferred to a future phase.

| Option | Description | Selected |
|--------|-------------|----------|
| Overdue physical audit | Closest precedent to how `compliance_remediation_tasks` already triggers tickets. | ✓ |
| High-value asset request pending approval too long | Mirrors Phase 44's SLA/escalation pattern applied to Phase 71's request workflow. | ✓ |
| None automatically — manual "Create Ticket" button only | No automatic triggers; manual action only. | ✓ |

**User's choice:** All three selected (ambiguous as multiSelect) — clarified via follow-up.

**Follow-up:** Confirming automatic triggers (overdue audit, stuck approval) PLUS an additive manual "Create Ticket" button for other cases?

| Option | Description | Selected |
|--------|-------------|----------|
| Yes — both | Automatic triggers plus additive manual button, not a fallback. | ✓ |
| Manual only, no automatic triggers | Drop automatic triggers entirely. | |

**User's choice:** Yes — both (automatic triggers + additive manual button).

| Option | Description | Selected |
|--------|-------------|----------|
| Reuse existing config | Same tenant-level Jira/ServiceNow credentials already configured for remediation tickets. | ✓ |
| Separate ITAM integration config | New settings section for ITAM-specific Jira/ServiceNow project/credentials. | |

**User's choice:** Reuse existing config.

---

## API discoverability/docs

| Option | Description | Selected |
|--------|-------------|----------|
| FastAPI auto /docs is sufficient | ITAM routers already appear in the existing OpenAPI /docs page once API-key auth is added. | ✓ |
| Dedicated API docs page in the console | New ITAM Console tab/page for endpoints, webhook events, Jira/ServiceNow setup steps. | |

**User's choice:** FastAPI auto /docs is sufficient.

| Option | Description | Selected |
|--------|-------------|----------|
| Inline in the existing webhook creation form | Populate `WebhookManagement.tsx`'s `availableEvents` picker with new ITAM event_type constants. | ✓ |
| Separate reference doc/page | Standalone markdown/docs page listing every event_type. | |

**User's choice:** Inline in the existing webhook creation form.

---

## Claude's Discretion

- Exact request/response field naming for any new endpoints beyond what already exists on the internal routers.
- Exact wording/placement of the manual "Create Ticket" button (likely alongside Phase 63's per-row Label action pattern).
- Whether the ITAM-event alert-shape adapter lives in `ticketing_bridge.py` itself or a new sibling module.

## Deferred Ideas

- CMDB-style asset data sync into Jira (as issues) or ServiceNow (as CIs), on a schedule or on change.
- A dedicated ITAM API documentation page / OpenAPI export beyond FastAPI's auto `/docs`.

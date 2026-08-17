# Phase 73: API & Integrations - Context

**Gathered:** 2026-08-18
**Status:** Ready for planning

<domain>
## Phase Boundary

Extend ITAM (asset management) with a REST API surface for external automation, webhook event notifications, and Jira/ServiceNow ticket integration for ITAM events — closing the "API & Integrations" gap identified in `ITAM-VS-SNIPE.md` §9 against Snipe-IT parity.

Three requirements: ITAM-API-01 (REST API for ITAM operations), ITAM-API-02 (webhooks), ITAM-API-03 (Jira/ServiceNow integration).

This phase is almost entirely *reuse and wiring*, not new infrastructure — the codebase already has a generic, working API-key auth system (`api_key_auth.py`, built by Phase 69 with scopes that already mirror ITAM permission strings), a generic webhook dispatch system (`webhook_service.py`'s `trigger_webhook(event_type, payload)`, subscription CRUD already built), and a Jira/ServiceNow ticketing bridge (`ticketing_bridge.py`, currently scoped to `compliance_remediation_tasks` only). None of these have ever been connected to ITAM.

</domain>

<decisions>
## Implementation Decisions

### REST API Auth Model (ITAM-API-01)
- **D-01:** Extend the existing internal ITAM routers to also accept API-key auth — swap `_require_itam_admin`'s `Depends(get_current_user)` → `Depends(get_current_user_or_api_key)` across `itam_*_endpoints.py`. Do NOT build a separate external `/api/v1/itam/*` surface. — **Reversibility:** reversible — a dependency swap per router; a separate versioned surface could be layered on later without undoing this.
- **D-02:** All `_require_itam_admin`-gated ITAM routers get API-key access (asset, lifecycle, license, consumable, component, finance, reports) — not a curated subset. Matches ITAM-API-01's unqualified "perform ITAM operations" wording.
- **D-03:** No `/v1/` version prefix — API keys unlock the same `/api/itam/*` paths the frontend already calls. No versioning precedent exists elsewhere in this codebase.
- **D-04:** Reuse `api_key_auth.py`'s existing per-key rate limiter as-is (`_check_rate_limit`) — no ITAM-specific rate-limit tier.

### Webhook Event Catalog (ITAM-API-02)
- **D-05:** Four event categories fire webhooks via the existing `WebhookService.trigger_webhook(event_type, payload)`:
  - `asset.checked_out` / `asset.checked_in` (Phase 57 lifecycle actions)
  - `asset.warranty_expiring` / `license.expiring_soon` (mirrors Phase 71/59's existing alert-window computation)
  - `asset.request_approved` / `asset.request_denied` (Phase 71's approval workflow)
  - `consumable.low_stock` / `asset.audit_overdue` (Phase 72's pre-built-report triggers, now also pushed as events)
- **D-06:** Payload is a flat asset/license/consumable record (or a before/after diff for check-out/in) plus event metadata — matches the existing shape `webhook_service.py._send_single_webhook` already sends for other event types. No bespoke per-event-type schema.
- **D-07:** `trigger_webhook()` calls are added inline, directly inside the relevant `itam_*_service.py` mutation functions (e.g. `itam_lifecycle_service.py`'s check-out/check-in functions) — no new event-dispatch abstraction layer.
- **D-08:** `asset.warranty_expiring` / `license.expiring_soon` are NOT mutation-triggered (nothing mutates when a date threshold is crossed) — the `trigger_webhook()` call is added at Phase 71's existing periodic warranty/depreciation alert job (ITAM-PRO-05), not a new scheduled job.

### Jira/ServiceNow Scope (ITAM-API-03)
- **D-09:** Generalize `ticketing_bridge.py` with a new ITAM-event-to-alert-shape adapter, alongside the existing `_task_to_alert_shape` (which is `compliance_remediation_tasks`-specific). Reuse `create_jira_ticket`/`create_servicenow_incident`/the close-loop status-polling (`run_close_loop_pass`) as-is — only the shape-adapter is new. — **Reversibility:** reversible — additive adapter function, existing remediation-task path untouched.
- **D-10:** Two automatic ticket triggers this phase: `asset.audit_overdue` and a high-value asset request stuck pending approval too long (mirrors Phase 44's SLA/escalation pattern, applied to Phase 71's request workflow). PLUS an additive manual "Create Ticket" button available on any asset/request for ad-hoc cases — the manual button is not a fallback replacing the automatic triggers, both exist together.
- **D-11:** Ticket creation reuses the existing tenant-level Jira/ServiceNow connection config (`jira_url`, `jira_api_token`, etc.) already set up for remediation tickets — no new ITAM-specific integration settings UI. If a tenant needs a different project/issue-type for ITAM tickets, that's a field on the ticket payload, not a new config surface.
- **D-12 (deferred, not built this phase):** CMDB-style asset data sync into Jira (as issues) or ServiceNow (as CIs) on a schedule or on change. This phase builds the ticket-per-event adapter only — see Deferred Ideas.

### API Discoverability / Docs
- **D-13:** No dedicated API docs page or OpenAPI export this phase — FastAPI's existing auto-generated `/docs` page already covers the ITAM routers once API-key auth is added (D-01/D-02).
- **D-14:** The webhook event_type catalog (D-05) is documented by populating `components/WebhookManagement.tsx`'s existing `availableEvents` checkbox array with the new ITAM event types — no separate reference doc. This UI already exists and already drives webhook subscription creation.

### Claude's Discretion
- Exact request/response field naming for any new endpoints beyond what already exists on the internal routers.
- Exact wording of the manual "Create Ticket" button placement (likely alongside the existing per-row action group established in Phase 63's Label action).
- Whether the ITAM-event alert-shape adapter (D-09) lives in `ticketing_bridge.py` itself or a new sibling module — implementation detail for research/planning to resolve against the existing module layout.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Requirements & gap analysis
- `.planning/REQUIREMENTS.md` — ITAM-API-01/02/03 definitions and traceability table
- `.planning/codebase/ITAM-VS-SNIPE.md` §9 (API & Integrations) — the Snipe-IT parity gap this phase closes
- `.planning/ROADMAP.md` Phase 73 section — goal, requirements, success criteria

### Existing API-key auth to extend (ITAM-API-01)
- `backend/api_key_auth.py` — `get_current_user_or_api_key`, `APIKeyService`, and the predefined scopes that already mirror ITAM permission strings (built by Phase 69 with ITAM in mind, never wired to ITAM routers)
- `backend/api_key_endpoints.py` — API key CRUD lifecycle (create/list/revoke)
- `backend/itam_asset_endpoints.py` — `_require_itam_admin` helper (currently `Depends(get_current_user)` only) — the swap point for D-01

### Existing webhook infra to wire (ITAM-API-02)
- `backend/webhook_service.py` — `WebhookService.trigger_webhook(event_type, payload)`, generic tenant-scoped dispatch, already working
- `backend/webhook_endpoints.py` — webhook subscription CRUD (`get_webhooks`/`create_webhook`/`delete_webhook`/`update_webhook`/deliveries/test), already gated by `get_current_user_or_api_key`
- `components/WebhookManagement.tsx` — frontend subscription UI with the `availableEvents` checkbox array (D-14's addition point)
- `.planning/phases/71-procurement-asset-workflow/` — ITAM-PRO-05 periodic warranty/depreciation alert job (D-08's wiring point)

### Existing ticketing bridge to generalize (ITAM-API-03)
- `backend/ticketing_bridge.py` — `create_ticket_for_remediation_task`, `_task_to_alert_shape`, `get_jira_issue_status`/`get_servicenow_incident_status`, `run_close_loop_pass` — all reused as-is per D-09
- `backend/integration_service_ticketing.py` — `create_jira_ticket`/`create_servicenow_incident` client functions
- `.planning/phases/44-remediation-sla-escalation/` (or equivalent) — the SLA/escalation pattern D-10's "stuck approval" trigger mirrors
- `.planning/phases/71-procurement-asset-workflow/` — asset request approval workflow (D-10's trigger source)

### Existing ITAM backend/frontend for router-scope context (D-02)
- `backend/itam_lifecycle_service.py`, `itam_finance_service.py`, `itam_license_service.py`, `itam_consumable_service.py`, `itam_component_endpoints.py` — the full set of `_require_itam_admin`-gated routers getting API-key access
- `components/itam/ITAMConsole.tsx` — console shell; no new tab required this phase (API/webhook/ticket surfaces are backend + existing WebhookManagement.tsx UI, not a new ITAM Console tab)

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `api_key_auth.py`'s ITAM-scoped API key predefined scopes — designed for this exact use case, currently unused by any ITAM router
- `webhook_service.py`'s generic `trigger_webhook()` — zero new webhook infrastructure needed, only new event_type constants and call sites
- `ticketing_bridge.py`'s Jira/ServiceNow client functions and close-loop status polling — reusable as-is, only need a new alert-shape adapter for ITAM events
- `components/WebhookManagement.tsx`'s existing `availableEvents` checkbox-driven subscription form — self-documents new event types with no separate doc page

### Established Patterns
- `_require_itam_admin` → `manage:assets` gate (Phase 47/48/61/63 precedent) — the auth swap in D-01 changes its `Depends()` source, not its permission semantics
- Single generic event-dispatch function (`trigger_webhook`) called inline at mutation points — no per-feature event bus, consistent with how this codebase avoids extra abstraction layers
- `_task_to_alert_shape` → provider dispatch (`jira`/`servicenow`) → `create_*_ticket` — the exact shape D-09's new adapter follows for ITAM events

### Integration Points
- `itam_*_endpoints.py` routers: one `Depends()` swap per router (D-01)
- `itam_*_service.py` mutation functions: new `trigger_webhook()` call sites (D-07)
- Phase 71's periodic alert job: new `trigger_webhook()` call site for expiry events (D-08)
- `ticketing_bridge.py`: new ITAM alert-shape adapter function + new automatic-trigger call sites in lifecycle/request-workflow services (D-09/D-10)
- `WebhookManagement.tsx`: extend `availableEvents` array (D-14)

</code_context>

<specifics>
## Specific Ideas

No specific UI mockups or exact wording were given — this phase is primarily backend wiring reusing existing UI (WebhookManagement.tsx) and existing docs surface (FastAPI auto /docs).

</specifics>

<deferred>
## Deferred Ideas

- CMDB-style asset data sync into Jira (as issues) or ServiceNow (as CIs), on a schedule or on change (D-12) — a future phase's concern if a tenant needs asset-inventory-as-CMDB rather than event-driven tickets.
- A dedicated ITAM API documentation page / OpenAPI export beyond FastAPI's auto `/docs` (D-13) — revisit if external integrators need something beyond the auto-generated surface.

### Reviewed Todos (not folded)
None — no pending todos matched this phase (`todo.match-phase` returned 0 matches).

</deferred>

---

*Phase: 73-api-integrations*
*Context gathered: 2026-08-18*

---
phase: 73-api-integrations
plan: 04
subsystem: api
tags: [fastapi, jira, servicenow, ticketing, itam, pydantic]

# Dependency graph
requires:
  - phase: 73-01
    provides: dual session/API-key _require_itam_admin guard (itam_asset_endpoints.py) and itam_webhook_events.py's EVENT_ASSET_AUDIT_OVERDUE constant
provides:
  - "ticketing_bridge._itam_event_to_alert_shape — ITAM sibling of _task_to_alert_shape, consumed unchanged by create_jira_ticket/create_servicenow_incident (D-09)"
  - "ticketing_bridge.ITAM_ENTITY_COLLECTIONS — the asset/asset_request -> (collection, id_field, tenant_field) mapping; the camelCase (tenantId) vs snake_case (tenant_id) divergence is real and encoded here"
  - "ticketing_bridge.create_ticket_for_itam_event — entity-aware orchestrator with dedup guard, tenant-context-bracketed config lookup, per-collection write-back (D-09/D-10/D-11)"
  - "AssetRequest.ticket_provider/ticket_ref/ticket_url — additive response-model-only fields (never client-writable)"
  - "POST /api/itam/tickets — manual create-ticket endpoint, registered in router_registry.py"
affects: [73-05, 73-06]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "ITAM_ENTITY_COLLECTIONS mapping pattern: entity kind -> (collection, id_field, tenant_field) namedtuple, so a single write-back/lookup helper can be correct across collections that disagree on their tenant field's casing"
    - "set_tenant_id/reset_tenant_id bracketing around a call into a function (get_ticketing_config) that resolves its own database handle via the request-scoped accessor — required whenever that function may be invoked with no ambient request context (background sweep)"

key-files:
  created:
    - backend/itam_ticketing_endpoints.py
  modified:
    - backend/ticketing_bridge.py
    - backend/itam_models.py
    - backend/router_registry.py
    - backend/tests/test_itam_ticketing_bridge.py

key-decisions:
  - "type derivation is purely mechanical (itam_ + event_type with dots replaced by underscores, or a distinct itam_manual_ticket for operator-triggered tickets) rather than a hardcoded per-event map — plan 73-05's still-undefined 'stuck approval' event type will automatically get a distinct, self-describing type value with zero changes to this adapter"
  - "severity is resolved from a small event-type -> word map (only asset.audit_overdue mapped explicitly today), defaulting to medium — ITAM entities carry no severity field of their own and must never have one read off them"

patterns-established:
  - "Any future ITAM automatic-ticket trigger (plan 73-05's audit-overdue and stuck-approval sweeps) calls create_ticket_for_itam_event with a raw, unwrapped db handle and its own event_type string — no changes needed to the orchestrator or adapter"

requirements-completed: [ITAM-API-03]

coverage:
  - id: D1
    description: "An ITAM audit-overdue asset or a stuck asset request can be turned into a Jira issue or ServiceNow incident using create_jira_ticket/create_servicenow_incident completely unmodified, via a new ITAM-event alert-shape adapter"
    requirement: "ITAM-API-03"
    verification:
      - kind: unit
        ref: "backend/tests/test_itam_ticketing_bridge.py -k alert_shape (14 tests)"
        status: pass
    human_judgment: false
  - id: D2
    description: "An operator can create a ticket on demand for any asset or asset request, choosing the provider explicitly, with the created ticket reference persisted onto that asset or request"
    requirement: "ITAM-API-03"
    verification:
      - kind: unit
        ref: "backend/tests/test_itam_ticketing_bridge.py -k manual_create (10 tests)"
        status: pass
      - kind: unit
        ref: "backend/tests/test_itam_ticketing_bridge.py -k itam_ticket_create (9 tests)"
        status: pass
    human_judgment: false
  - id: D3
    description: "A second ticket is never created for an asset or request that already carries a ticket reference — dedup guard mirrors the remediation bridge's behaviour, at both the orchestrator layer and the endpoint's 409"
    requirement: "ITAM-API-03"
    verification:
      - kind: unit
        ref: "backend/tests/test_itam_ticketing_bridge.py::test_itam_ticket_create_dedup_second_call_creates_nothing"
        status: pass
      - kind: unit
        ref: "backend/tests/test_itam_ticketing_bridge.py::test_manual_create_already_ticketed_returns_409_not_a_second_ticket"
        status: pass
    human_judgment: false
  - id: D4
    description: "Ticket creation reuses the tenant's existing Jira/ServiceNow connection config via get_ticketing_config, bracketed by set_tenant_id/reset_tenant_id so a background-sweep caller with no ambient tenant context still resolves the config"
    requirement: "ITAM-API-03"
    verification:
      - kind: unit
        ref: "backend/tests/test_itam_ticketing_bridge.py::test_itam_ticket_create_resolves_config_with_no_ambient_tenant_context"
        status: pass
    human_judgment: false
  - id: D5
    description: "Write-back uses each ITAM collection's own tenant field — assets via camelCase tenantId, asset_requests via snake_case tenant_id — proven by a test asserting a camelCase filter would match zero asset-request documents"
    requirement: "ITAM-API-03"
    verification:
      - kind: unit
        ref: "backend/tests/test_itam_ticketing_bridge.py::test_itam_ticket_create_asset_request_uses_snake_case_tenant_field"
        status: pass
    human_judgment: false
  - id: D6
    description: "The manual endpoint is reachable in the assembled application (registered in router_registry.py), never returns a credential, and rejects a non-enum provider value before the handler runs"
    requirement: "ITAM-API-03"
    verification:
      - kind: unit
        ref: "backend/tests/test_itam_ticketing_bridge.py::test_manual_create_registered_in_real_app"
        status: pass
      - kind: unit
        ref: "backend/tests/test_itam_ticketing_bridge.py::test_manual_create_response_body_key_set_is_exactly_three_ticket_keys"
        status: pass
      - kind: unit
        ref: "backend/tests/test_itam_ticketing_bridge.py::test_manual_create_invalid_provider_rejected_before_handler"
        status: pass

duration: 45min
completed: 2026-08-18
status: complete
---

# Phase 73 Plan 04: ITAM-to-Ticketing Bridge (D-09/D-10 manual/D-11) Summary

**ITAM asset/asset-request events (audit-overdue, manual) can now become Jira issues or ServiceNow incidents through the existing connectors unmodified — via a new `_itam_event_to_alert_shape` adapter, an entity-aware `create_ticket_for_itam_event` orchestrator with dedup + tenant-context bracketing, and a registered `POST /api/itam/tickets` manual endpoint.**

## Performance

- **Duration:** ~45 min
- **Completed:** 2026-08-18
- **Tasks:** 3/3
- **Files modified:** 3 production files (`ticketing_bridge.py`, `itam_models.py`, `router_registry.py`), 1 new production file (`itam_ticketing_endpoints.py`), 1 new test file

## Accomplishments

- `ticketing_bridge._itam_event_to_alert_shape(db, event_type, entity_kind, entity)` — the ITAM sibling of `_task_to_alert_shape`, returning the identical 8-key alert shape (verified against the real function's key set, not a hardcoded list) so `create_jira_ticket`/`create_servicenow_incident` consume it with zero changes. Deterministic `alert_id`, mechanical `type` derivation (`itam_<event_type with dots as underscores>`, or a distinct `itam_manual_ticket` for operator-triggered tickets), hostname fallback chain (`hostname` → `assetTag` → placeholder) for assets, no asset lookup at all for asset requests.
- `ticketing_bridge.ITAM_ENTITY_COLLECTIONS` — the `{"asset": ("assets", "id", "tenantId"), "asset_request": ("asset_requests", "id", "tenant_id")}` mapping. **This is the artifact plans 73-05 and 73-06 both depend on** — it is the single place encoding that `assets` documents use camelCase `tenantId` while `asset_requests` documents use snake_case `tenant_id`; a shared filter shape across both collections would silently write to nothing for one of them.
- `ticketing_bridge.create_ticket_for_itam_event(db, entity_kind, entity, tenant_id, event_type, provider_override=None)` — a close clone of `create_ticket_for_remediation_task`: dedup guard on a truthy `ticket_ref` before any outbound call, `get_ticketing_config` lookup bracketed by `set_tenant_id`/`reset_tenant_id` (mandatory — `ticketing_configs` is not tenant-isolation-exempt, and this function may be called from plan 73-05's background sweeps with no ambient tenant context at all), provider dispatch unchanged, write-back through the entity kind's own id/tenant field pair. Never re-raises.
- `AssetRequest` gains optional `ticket_provider`/`ticket_ref`/`ticket_url` fields — response-model only, absent from `AssetRequestCreate`/`AssetRequestUpdate` (bridge-written, never client-writable). Without this, the model's `extra="ignore"` config would silently strip these fields off every API response.
- New `backend/itam_ticketing_endpoints.py`: `POST /api/itam/tickets`, gated by the same dual session/API-key `_require_itam_admin` as the rest of the ITAM surface. Resolves the entity via `ITAM_ENTITY_COLLECTIONS`' id/tenant field pair (404 if absent from the caller's tenant), 409 without calling the bridge if already ticketed, 502 on a bridge failure. `entityKind`/`provider` are strict typing literals — an out-of-vocabulary value is rejected by request validation before the handler runs. Response restricted to exactly three keys via `response_model`.
- Registered in `router_registry.py` immediately after the Phase 72 ITAM routers.

## Task Commits

Each task followed the RED (`test`) → GREEN (`feat`) TDD cycle, verified by reverting the implementation and confirming the test failures before reapplying:

1. **Task 1: ITAM-event alert-shape adapter**
   - `812fc001a` (test) — 14 failing tests (`AttributeError`, adapter didn't exist)
   - `b469fb107` (feat) — adapter + `ITAM_ENTITY_COLLECTIONS` + manual-event sentinel; all 14 pass
2. **Task 2: Entity-aware ticket-creation orchestrator + additive AssetRequest fields**
   - `f35f256e2` (test) — 9 tests, 8/9 failing (`AttributeError`/`KeyError`, orchestrator + model fields didn't exist)
   - `f45c0b5db` (feat) — orchestrator + model fields; all 9 pass, plus the 14 alert_shape tests still pass (23/23)
3. **Task 3: Manual create-ticket endpoint, registered**
   - `a4dc21620` (test) — 10 tests, whole module fails to collect (`ModuleNotFoundError`, endpoint file didn't exist)
   - `9ac9687f6` (feat) — endpoint + router registration; full file green (33/33)

## Files Created/Modified

- `backend/ticketing_bridge.py` — `_itam_event_to_alert_shape`, `ITAM_ENTITY_COLLECTIONS`, `ITAM_TICKET_EVENT_MANUAL`, `create_ticket_for_itam_event`; the existing `_task_to_alert_shape`/`create_ticket_for_remediation_task`/close-loop functions are byte-unchanged (verified via `grep -c "def _task_to_alert_shape"` == 1 and the full pre-existing `test_ticketing_bridge.py` suite still green)
- `backend/itam_models.py` — `AssetRequest` gains `ticket_provider`/`ticket_ref`/`ticket_url` (optional, response-only); `AssetRequestCreate`/`AssetRequestUpdate` deliberately unchanged
- `backend/itam_ticketing_endpoints.py` (new) — `POST /api/itam/tickets`
- `backend/router_registry.py` — one new registration line for `itam_ticketing_endpoints`
- `backend/tests/test_itam_ticketing_bridge.py` (new, 33 tests) — `-k alert_shape` (14), `-k itam_ticket_create` (9), `-k manual_create` (10)

## Decisions Made

- **Type derivation is mechanical, not a per-event lookup table.** `type` = `itam_` + `event_type` with `.` replaced by `_` (or the distinct `itam_manual_ticket` sentinel for operator-triggered tickets with no originating event). This means plan 73-05's stuck-approval event type — not yet defined anywhere in this codebase — will automatically produce a distinct, self-describing `type` value the moment 73-05 picks a string for it, with zero changes required to this adapter.
- **Severity map deliberately sparse.** Only `EVENT_ASSET_AUDIT_OVERDUE` is mapped explicitly (`"medium"`); everything else — including whatever event type 73-05 chooses for the stuck-approval trigger — falls through to the `"medium"` default. Widening this map is a one-line, backward-compatible addition for 73-05 to make if a different severity is warranted; it was not guessed at here since ITAM entities carry no severity field of their own to validate against.
- **`ITAM_ENTITY_COLLECTIONS` uses a `namedtuple`, not a dict-of-dicts.** Slightly stricter (attribute access, `TypeError` on typos) than a nested dict, and matches how downstream code (Task 2's write-back, Task 3's lookup) will consume it — attribute access (`info.collection`, `info.id_field`, `info.tenant_field`) rather than string-keyed lookups scattered across three call sites.

## Deviations from Plan

None — plan executed exactly as written. The plan's own `<action>` text was precise enough (exact field names, exact dedup/bracketing contract, exact response shape) that no gaps needed filling during implementation.

## Issues Encountered

None. The full backend suite was re-run after all three tasks landed: 2357 passed / 34 skipped / 11 failed — all 11 failures are the pre-existing, unrelated baseline documented in prior sessions' STATE.md notes (`test_agentic_ai`, `test_e2e_integration`, `test_itam_audit`'s purchase-route entry, `test_mfa`'s replay test, `test_powershell_evidence` JWT/cross-tenant, `test_rust_heartbeat_parity`, `test_secret_manager_service`'s 4 Vault-client tests) — none touch any file this plan modified.

## User Setup Required

None — no external service configuration required. Ticket creation reuses the tenant's existing Jira/ServiceNow connection config (D-11); no new settings surface was introduced.

## Next Phase Readiness

- Plan 73-05 (automatic triggers: `asset.audit_overdue` sweep + a high-value-stuck-approval sweep) can call `create_ticket_for_itam_event(raw_db, entity_kind, entity, tenant_id, event_type)` directly from a background loop with no ambient tenant context — the bracketing this plan built is exactly what makes that safe. It should pick its own event-type string for the stuck-approval condition; the adapter requires no changes to accommodate it.
- Plan 73-06 (row-action UI: `RequestsPanel.tsx`/`LifecyclePanel.tsx` ticket-reference display) can read `ticket_provider`/`ticket_ref`/`ticket_url` directly off `GET` responses for assets and asset requests, and can call `POST /api/itam/tickets` for the manual row action — the endpoint's response shape (`{ticket_provider, ticket_ref, ticket_url}`) and its 404/409/502 status codes are locked by this plan's own tests.
- `ITAM_ENTITY_COLLECTIONS` is the canonical reference for both plans — reuse it rather than re-deriving the collection/id-field/tenant-field mapping.
- No blockers.

---
*Phase: 73-api-integrations*
*Completed: 2026-08-18*

## Self-Check: PASSED
- FOUND: backend/itam_ticketing_endpoints.py
- FOUND: backend/tests/test_itam_ticketing_bridge.py
- FOUND: .planning/phases/73-api-integrations/73-04-SUMMARY.md
- FOUND: commit 812fc001a
- FOUND: commit b469fb107
- FOUND: commit f35f256e2
- FOUND: commit f45c0b5db
- FOUND: commit a4dc21620
- FOUND: commit 9ac9687f6

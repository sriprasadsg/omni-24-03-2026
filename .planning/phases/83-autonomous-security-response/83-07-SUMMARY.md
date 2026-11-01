---
phase: 83-autonomous-security-response
plan: 07
subsystem: autonomous-ops
tags: [autonomous-ops, settings, two-signal, block-length, watched-services, bulk, pytest]
status: complete

requires:
  - phase: 83-autonomous-security-response
    provides: "83-03 response_settings.load, response_messages (CONTROL_LABELS, API_DETAIL) and the shared contract file with criticalServices; 83-06 fences"
provides:
  - "response_settings.save, validate_changes, validate_service_name, SERVICE_NAME_RE, MAX_SERVICES, MIN_BLOCK_HOURS, MAX_BLOCK_HOURS, SettingsError, PlatformTenantError"
  - "GET and PUT /api/autonomous-ops/response-settings (manage:autonomous_ops, interactive session)"
  - "GET /api/platform/autonomous-ops/response-settings and PUT .../response-settings/bulk (control:platform_autonomous_ops, interactive session)"
  - "One control row (two_signal_on or two_signal_off, block_length_changed, watched_services_changed) and one audit event per value that really changes, naming the person"
affects: [83-08, 83-09, 83-10, 83-16, 83-17]

actuals:
  tokens: 10600
  tasks: 2
  commits: 2
plan_head_before: cd510c9d1b323147aa465b9fdb08223f0406298c
plan_head_after: 0fc1571e3db232c2b1e50235f6498a0d8ff60160

tech-stack:
  added: []
  patterns:
    - "A setting that loosens a safeguard is written, then its control row; if the row cannot be recorded the old values are put back and the request fails (PROH-83-09)"
    - "Bulk = a loop of per-tenant saves with per-tenant failure collection; the platform organization is never in the loop"

key-files:
  created:
    - backend/autonomous_ops_response_endpoints.py
    - backend/autonomous_ops_response_platform_endpoints.py
    - backend/tests/test_autonomous_ops_response_endpoints.py
  modified:
    - backend/autonomous_ops/response_settings.py
    - backend/autonomous_ops/response_messages.py
    - backend/catalogue_mounts_autonomous_ops.py
    - backend/router_registry.py
    - shared/autonomous-ops-banned-terms.json
    - backend/tests/test_autonomous_ops_copy.py
    - src/__tests__/autonomousOpsCopy.test.ts
    - backend/tests/_autonomous_ops_http.py
    - backend/tests/test_catalogue_slice_autonomous_ops.py

key-decisions:
  - "A save writes the values first and the control rows second; if a row cannot be recorded the old values are restored and the error is raised, so the two-source rule can never stay off without a record."
  - "A Super Admin changing one organization through the tenant route is recorded with scope platform, so the organization's own viewers see 'Platform administrator' (Phase 81 D-25), not the person."
  - "Unknown ids in onlyTenants are listed in failures (organization_missing), not a 404, so a retry after an organization was deleted still finishes the rest."
  - "GET on the tenant route also refuses API keys (the plan listed only _require_manage on GET); must_haves say keys cannot use these routes."
  - "An empty PUT body is 422 on the tenant route too, not a silent no-op."

requirements-completed: []

coverage:
  - id: D1
    description: "A tenant admin reads defaults and changes twoSignal; one control row two_signal_off with the person's name and the audit event autonomous_ops.two_signal_off; same values write nothing"
    requirement: "RESP-08"
    verification:
      - kind: integration
        ref: "backend/tests/test_autonomous_ops_response_endpoints.py#test_two_signal_off_is_recorded_with_the_persons_name_and_an_audit_event"
        status: pass
      - kind: integration
        ref: "backend/tests/test_autonomous_ops_response_endpoints.py#test_saving_the_same_values_writes_nothing"
        status: pass
  - id: D2
    description: "blockHours 1 to 168 whole numbers only; 0, 169, 1.5, a string and a boolean answer 422 and store nothing"
    requirement: "RESP-04"
    verification:
      - kind: integration
        ref: "backend/tests/test_autonomous_ops_response_endpoints.py#test_block_length_range_and_types"
        status: pass
  - id: D3
    description: "watchedServices: agent name rule, 50 limit, case-insensitive duplicates and the contract's critical services refused"
    requirement: "RESP-04"
    verification:
      - kind: integration
        ref: "backend/tests/test_autonomous_ops_response_endpoints.py#test_watched_services_validation"
        status: pass
  - id: D4
    description: "Roles, keys and tenants: manage only; Platform Support, keys and another tenant 403; Super Admin with tenantId works and is recorded as platform scope; platform organization 409"
    requirement: "ACTV-02"
    verification:
      - kind: integration
        ref: "backend/tests/test_autonomous_ops_response_endpoints.py#test_roles_keys_and_tenants"
        status: pass
      - kind: integration
        ref: "backend/tests/test_autonomous_ops_response_endpoints.py#test_the_role_matrix_on_the_real_app"
        status: pass
  - id: D5
    description: "restartAvailable false without remediation_executor and the list still saves; a malformed stored value reads as the default with readable false"
    requirement: "RESP-04"
    verification:
      - kind: integration
        ref: "backend/tests/test_autonomous_ops_response_endpoints.py#test_restart_is_unavailable_without_remediation_but_the_list_still_saves"
        status: pass
      - kind: integration
        ref: "backend/tests/test_autonomous_ops_response_endpoints.py#test_a_malformed_stored_value_reads_as_the_safe_default"
        status: pass
  - id: D6
    description: "A change whose control row cannot be recorded is not kept (PROH-83-09)"
    requirement: "RESP-08"
    verification:
      - kind: integration
        ref: "backend/tests/test_autonomous_ops_response_endpoints.py#test_a_change_that_cannot_be_recorded_is_not_kept"
        status: pass
  - id: D7
    description: "Bulk writes each organization with its own rows, never the platform organization; one failure is listed while the others change; onlyTenants retries only the failed; empty and service bodies are 422; platform routes refuse everyone but the Super Admin"
    requirement: "RESP-08"
    verification:
      - kind: integration
        ref: "backend/tests/test_autonomous_ops_response_endpoints.py#test_bulk_writes_each_organization_with_its_own_rows"
        status: pass
      - kind: integration
        ref: "backend/tests/test_autonomous_ops_response_endpoints.py#test_one_failing_organization_does_not_stop_the_others_and_a_retry_sends_only_it"
        status: pass
      - kind: integration
        ref: "backend/tests/test_autonomous_ops_response_endpoints.py#test_bulk_refuses_empty_bad_and_service_bodies"
        status: pass
      - kind: integration
        ref: "backend/tests/test_autonomous_ops_response_endpoints.py#test_platform_routes_refuse_everyone_but_the_super_admin"
        status: pass
  - id: D8
    description: "Both routers mounted, required at start-up, carry the catalogue guard or the platform dependency, and pass the slice, parity and auth baseline tests"
    requirement: "ACTV-02"
    verification:
      - kind: structural
        ref: "backend/tests/test_catalogue_slice_autonomous_ops.py"
        status: pass
---

# Phase 83 Plan 07: Response settings routes Summary

**Tenant admins read and save the two-source switch, the block length (1 to 168 hours) and up to 50 watched services; a Super Admin sees the spread and writes the first two to every organization; each real change leaves a control row and audit event naming the person.**

## Request and response shapes (for the settings panel)

Tenant router, prefix `/api/autonomous-ops`. Needs `manage:autonomous_ops` and an interactive session on both methods. `?tenantId=` is honoured only for a Super Admin (omitting it gives 400; the platform organization gives 409; an unknown one 404; a tenant naming another tenant 403).

`GET /response-settings` and the 200 of `PUT /response-settings`:

```json
{ "twoSignal": true, "blockHours": 24, "watchedServices": [], "readable": true, "restartAvailable": false }
```

- `readable: false` means a stored value was not understood; the safe default is shown (two sources, 24 hours, none watched) and the next save repairs the stored document.
- `restartAvailable: false` means `remediation_executor` is not ticked for the organization. The list still saves.

`PUT /response-settings` body: any of `twoSignal` (strict boolean), `blockHours` (strict integer 1 to 168), `watchedServices` (list of strings, at most 50). `null` counts as absent. An empty body is 422. Values equal to the stored ones write nothing and record nothing. 422 `detail` is a plain sentence:

| Case | detail |
|---|---|
| block length outside 1..168, a fraction, a string | `Enter a block length between 1 hour and 7 days.` |
| name outside the agent rule | `Use only letters, numbers, dots, hyphens and underscores, starting with a letter or number.` |
| empty name | `Enter a service name.` |
| duplicate (case-insensitive) | `{name} is already on the list.` |
| more than 50 | `You can watch up to 50 services.` |
| name on the contract's critical list | `{name} is a system service, so it is never restarted automatically.` |
| nothing to change | `Choose at least one setting to change.` |
| `twoSignal` not a boolean, `watchedServices` not a list | `Check the setting and try again.` (pydantic's own 422 list for wrong JSON types) |

Platform router, prefix `/api/platform/autonomous-ops`. Needs `control:platform_autonomous_ops` and an interactive session.

`GET /response-settings`:

```json
{ "organizations": 2, "twoSignal": { "on": 1, "off": 1 }, "blockHours": { "12": 1, "24": 1 }, "unreadable": 0 }
```

`organizations` is a count, platform organization excluded. `unreadable` counts organizations shown at the defaults because their stored value could not be read.

`PUT /response-settings/bulk` body: `twoSignal`, `blockHours`, `onlyTenants` (at most 1000 ids). Anything else (including `watchedServices`) is 422; an empty body is 422. Response (always 200 unless the request itself is refused):

```json
{ "changed": ["t1", "t2"], "failures": [ { "tenantId": "t1", "name": "T1", "detail": "The settings could not be saved for this organization." } ] }
```

`changed` lists the organizations written (including any already at the value, which get no new rows). A retry sends `onlyTenants` with the failed ids only. Naming the platform organization in `onlyTenants` is 409. An id that no longer exists appears in `failures` with `detail: This organization no longer exists.` The failure detail never carries the exception text.

Ledger rows: `two_signal_on` / `two_signal_off`, `block_length_changed`, `watched_services_changed`, kind `control`, `actor` the person, `scope` `tenant` for a tenant admin and `platform` when a Super Admin wrote it (single organization or bulk). The audit event is `autonomous_ops.<controlEvent>`.

## Deviations from Plan

**1. [Rule 2 - Missing critical] GET on the tenant route refuses API keys.** The plan's action listed `_require_manage` only on GET, while the must-haves say API keys cannot use these routes. Added `_require_interactive_session` to GET.
**2. [Rule 2 - Missing critical] Failed control row restores the old values.** The plan says each change writes a control row; it did not say what happens when the row cannot be written. A loosened safeguard with no record breaks PROH-83-09, so `save` puts the previous values back and raises (tested).
**3. [Rule 1 - Bug avoided] Malformed stored `response` repaired by a whole-document write.** A dotted `$set` into a non-object `response` would fail in MongoDB; when `load` reports `readable: false`, `save` writes the merged document instead.
**4. Scope `platform` for a Super Admin on the tenant route.** Not in the plan; follows Phase 81 D-25 so a tenant never sees which platform person acted.
**5. Unknown `onlyTenants` ids go to `failures`, not 404.** So a retry after a deletion still completes.
**6. Test marker.** The test module uses `real_agent_capabilities`, because `tests/conftest.py` otherwise makes every tenant allow every capability and `restartAvailable` could never be false.
**7. Commit split.** The two tasks share seven files. Task 1's commit was staged from reconstructed file versions (tenant-only hunks) via `git update-index --cacheinfo`, then Task 2 added the rest from the working copy. The Task 1 commit's tests (12) pass on their own (checked as a temporary copy), but the Task 1 tree was not checked out and run as a whole.

## User-visible sentences not worded by the UI-SPEC

All are in `backend/autonomous_ops/response_messages.py` (banned-terms gate applies and passes). Please read these:

- `{name} is a system service, so it is never restarted automatically.` (critical service refusal; the UI-SPEC words no such error)
- `Check the setting and try again.`
- `Choose at least one setting to change.`
- `The settings could not be saved for this organization.`
- `This organization no longer exists.`
- Control row reasons: `Two different sources must now agree before an IP address is blocked or a file is quarantined.` / `One source is now enough to block an IP address or quarantine a file.` / `New blocks now last {length}.` / `{count} watched: {names}.` / `No services are watched now, so nothing restarts on its own.`

The spec's own sentences (`Enter a service name.`, `{name} is already on the list.`, the invalid-name sentence, `You can watch up to 50 services.`, the block-length sentence) are used verbatim as the server detail.

## Verification

- `backend/tests/test_autonomous_ops_response_endpoints.py`: 17 passed on the private mongod (27998), none skipped.
- Task 1 command (response endpoints, catalogue slice, route parity, auth baseline, copy): 118 passed, 1 failed. The one failure is `test_catalogue_route_parity.py::test_ledger_ratchets` with exactly the nine known names from the run notes (audit_program, compliance_evidence, compliance_report(s), export_report, reporting, route_aliases, scheduled_reports, soa); no new name.
- After Task 2: response endpoints, slice, auth baseline, copy, response rows, endpoints, endpoint writes, router-registry-required: 122 passed.
- `npx vitest run src/__tests__/autonomousOpsCopy.test.ts`: 18 passed (exit 0).
- One mutation check: raising `MAX_BLOCK_HOURS` to 200 made two tests fail; reverted.
- The tests were written after the code, not before. There was no RED run; a RED-by-ImportError would have been the only kind possible. Honest label: tests-after.
- No agent, firewall or service call is involved in this plan.

## Not read

83-RESEARCH.md was not read (the plan names it only as context; the decisions and shapes this plan needed are in 83-CONTEXT.md and 83-UI-SPEC.md, which I read: CONTEXT in full, UI-SPEC sections 6 and 7, R8 to R12 and Open Item 4). 83-03-SUMMARY.md and 83-PATTERNS.md were not read; the code they describe was read instead.

## Cross-plan facts for the orchestrator

- Stored shape: `autonomy_settings.response` = `{twoSignal, blockHours, watchedServices}`; after a first save by dotted `$set` only the changed keys exist (the rest read as defaults). `response_settings.load` is the one reader.
- Plans that read `watchedServices` (83-08/83-10, heartbeat reply) and `blockHours` (the sweep's block ttl: `blockHours * 3600`) should use `response_settings.load`; its `block_hours` is always 1..168 or the default.
- `response_settings.save(db, tenant, changes, *, actor, scope)` is the only writer and records the control rows; do not `$set` `response.*` elsewhere.
- Tests that need `restartAvailable` to depend on the tenant's list must carry `@pytest.mark.real_agent_capabilities` (conftest otherwise allows everything).
- `requirements-completed` is empty: RESP-04 (block length and watched services reaching an agent), RESP-08 (the sweep reading `twoSignal`) and ACTV-02 (the panel) finish in later plans.

## Self-Check: PASSED

Files exist (response_settings.py, both endpoint modules, the test module), commits 0afbdd923 and 0fc1571e3 are ancestors of HEAD, and `commits: 2` was measured from the ledger. No file in the commits was one carrying user hunks (checked with `git show --stat`).

---
phase: 76-catalogue-manifest-backend-route-enforcement
plan: 10
subsystem: api
tags: [rbac, catalogue-manifest, settings, system-health, secrets, integrations, webhooks, notifications, mssp, d-01, d-02]

requires:
  - phase: 76-catalogue-manifest-backend-route-enforcement
    provides: catalogue_guard / catalogue_exempt / MOUNTS convention / parity helpers (76-01), full manifest (76-02)
provides:
  - backend/catalogue_mounts_settings_ops.py (named guards, 22 MOUNTS entries)
  - backend/tests/test_catalogue_slice_settings_ops.py (7 tests: parity, manifest drift, public routes, governance settings unguarded, real-app 403/200, role-scoped catalogues, integration-key webhooks)
  - route-level guards in webhook, final, agent_location_history, system, llm_proxy, reporting and tickets_workflow endpoints
affects: [76-11, 76-12, 77]

requirements-completed: [ACC-04]

status: complete
actuals:
  tokens: 4100
  tasks: 3
  commits: 3
plan_head_before: 27b4e8364e0a5467e04ed49ed66f71686d7f4a70
plan_head_after: d0cc9c6be28fa9abc8ea8fefd6a584a775b0f9c4

tech-stack:
  added: []
  patterns:
    - "Pure routers get a MOUNTS entry keyed on the module router_registry loads; mixed or public-bearing routers get per-route dependencies=[Depends(NAMED_GUARD)]"
    - "A guard may wrap catalogue access with an identity pass-through (tenant integration keys) while keeping the __catalogue_guard__ tag the parity walker reads"

key-files:
  created:
    - backend/catalogue_mounts_settings_ops.py
    - backend/tests/test_catalogue_slice_settings_ops.py
  modified:
    - backend/webhook_endpoints.py
    - backend/final_endpoints.py
    - backend/agent_location_history_endpoints.py
    - backend/system_endpoints.py
    - backend/llm_proxy.py
    - backend/reporting_endpoints.py
    - backend/tickets_workflow_endpoints.py
    - backend/tests/test_agent_location_history_endpoints.py

key-decisions:
  - "No route is catalogue_exempt: every user route in the slice maps cleanly to a manifest owner. App-shell style reads found in the frontend are data reused by another view, which slice rule 4 says is not an exemption reason (see Phase 77 UX notes)"
  - "compliance_evidence_lifecycle_endpoints and compliance_remediation_sla_endpoints were NOT edited: the manifest puts /api/settings/evidence-staleness in complianceEvidence and /api/settings/remediation-sla in remediationWorkflow, both under the unenforced governance group (D-01). A test pins that they stay unguarded"
  - "Webhook list, create, delete and deliveries accept a tenant integration key (role api-integration, issued by tenant admins for this job, no role document). Their guard passes that identity through and checks every other caller against the catalogue, so the connector flow in test_api_key_auth keeps working. PUT and POST /test stay session-only and use the plain guard"
  - "agent location-history uses the agents catalogue guard and agent-location-tracking the geoSecurity guard, exactly as the manifest assigns them"

coverage:
  - id: D1
    description: "parity_offenders over slice_modules('settings_ops') is empty (29 modules)"
    requirement: ACC-04
    verification:
      - kind: unit
        ref: "backend/tests/test_catalogue_slice_settings_ops.py#test_settings_ops_slice_parity"
        status: pass
    human_judgment: false
  - id: D2
    description: "Every named guard and mount entry equals the manifest's resolved read/write"
    requirement: ACC-04
    verification:
      - kind: unit
        ref: "backend/tests/test_catalogue_slice_settings_ops.py#test_settings_ops_guards_match_manifest"
        status: pass
    human_judgment: false
  - id: D3
    description: "A role without manage:settings gets 403 on settings, secrets, system, HA/DR, retention, webhooks and integration reads on the real app; tenant_admin does not"
    requirement: ACC-04
    verification:
      - kind: integration
        ref: "backend/tests/test_catalogue_slice_settings_ops.py#test_settings_ops_real_app_enforced"
        status: pass
    human_judgment: false
  - id: D4
    description: "Inbound webhook receivers and the public /api/system/health duplicate carry no tag; governance settings routes stay unguarded"
    requirement: ACC-04
    verification:
      - kind: unit
        ref: "backend/tests/test_catalogue_slice_settings_ops.py#test_settings_ops_public_routes_untouched"
        status: pass
      - kind: unit
        ref: "backend/tests/test_catalogue_slice_settings_ops.py#test_settings_ops_governance_settings_stay_unguarded"
        status: pass
    human_judgment: false
  - id: D5
    description: "Full backend suite green (3699 passed, 47 skipped, 0 failed)"
    requirement: ACC-04
    verification:
      - kind: command
        ref: "backend/venv/bin/python -m pytest backend/tests -q -p no:cacheprovider"
        status: pass
    human_judgment: false
---

# Phase 76 Plan 10: Settings and Platform-Operations Slice Summary

**Manifest guards on settings, system health, cache, HA/DR, secrets, retention, cloud and platform integrations, ticketing, notifications, MSSP, fleet views, native security ops, data warehouse and webhook management, with inbound receivers and public routes left untouched.**

Duration: about 55 minutes (started 2026-10-15T18:42Z, finished 19:37Z), 3 tasks, 10 files.

## Accomplishments

- 22 pure routers mounted through `catalogue_mounts_settings_ops.MOUNTS` (settings, email, system_health, cache, maintenance, hadr, secrets, retention, retention_tiers, geo_security, cloud_integrations, integration_endpoints, integrations_v2, ticketing, notification, mssp, fleet geo and observability, native_security_ops, etl, warehouse, data_lake).
- Per-route guards in the seven modules that mix catalogues, carry public receivers or serve another module's paths: webhook_endpoints (6 user routes; jira and zoho inbound untouched), final_endpoints (4 integration routes; public `/api/system/health` and the ML routes untouched), agent_location_history_endpoints (agents + geoSecurity), system_endpoints (apiStatus + systemHealth), llm_proxy (`GET /api/ai/config` only), reporting_endpoints (`/api/notifications/send` and `/history` only; `/api/reports` left for the ledger), tickets_workflow_endpoints (`/api/tickets/webhooks` only).
- Slice test with 7 functions; full backend suite 3699 passed, 47 skipped, 0 failed (baseline 3692 plus the 7 new tests).

## slice_modules("settings_ops") versus the plan's expected list

Measured: agent_fleet_geo, agent_fleet_observability, agent_location_history, cache, cloud_integrations, data_lake, email, etl, final, geo_security, hadr, integration, integrations_v2, llm_proxy, maintenance, mssp, native_security_ops, notification, reporting, retention, retention_tiers, secrets, settings, system, system_health, ticketing, tickets_workflow, warehouse, webhook (29).

- Extra modules the plan did not list (guarded, so the slice parity is empty): `data_lake_endpoints` (dataWarehouse), `email_endpoints` (settings, via the manifest's `/api/email` prefix), `llm_proxy` (`/api/ai/config`, settings).
- Listed but absent from the slice, correctly: `log_endpoints` (logExplorer is observability, not enforced), `tickets_endpoints`, `tickets_config_endpoints`, `ticket_reports_endpoints` (internalTickets is automation, not enforced; the plan made these conditional), `compliance_evidence_lifecycle_endpoints` and `compliance_remediation_sla_endpoints` (governance, not enforced).
- router_registry loads `llm_proxy` with a bare `app.include_router`, not `_load`, so it cannot take a MOUNTS entry; its one in-scope route is guarded per route.

## Exempt routes

None. No route in the slice acts only on the caller's own records. Frontend evidence for reads used outside their own view (all guarded, none exempted, per slice rule 4):

| Call | Where it is used outside its catalogue view |
|------|----------------------------------------------|
| `GET /api/integrations/list` | `App.tsx` line 508 (`ifOn('integrations', api.fetchIntegrations)`) |
| `GET /api/settings/database`, `/api/settings/llm` | `App.tsx` line 510 (`ifOn('settings', api.fetchInfrastructure)`) |
| `GET /api/ticketing/config` | ITAM `RequestsPanel.tsx` and `LifecyclePanel.tsx` (`getTicketingConfig`, errors swallowed, returns `{}`) |
| `GET /api/settings/agent-location-tracking` | `PrivacyDashboard.tsx` (`getAgentLocationTracking`, falls back to `{enabled: true}`) |

## Deviations from Plan

**1. [Rule 3 - Blocking] Compliance settings routes left unguarded.** Task 3 listed `compliance_evidence_lifecycle_endpoints.py` and `compliance_remediation_sla_endpoints.py`. The manifest assigns their settings paths to governance catalogues, which are not enforced, so there is nothing to guard (D-01) and the plan's own wording ("only the routes the manifest assigns to an enforced catalogue") applies. Both files are unchanged; `test_settings_ops_governance_settings_stay_unguarded` pins this.

**2. [Rule 1 - Bug] Tenant integration keys would have been locked out of webhook management.** A plain `catalogue_guard(..., auth=get_current_user_or_api_key)` returned 403 for role `api-integration`, breaking five `test_api_key_auth` tests. The routes already special-case that role, so the webhook guard passes that one identity through and checks everyone else. Found during: Task 2. Files: `catalogue_mounts_settings_ops.py`, `webhook_endpoints.py`. Commit: 751472443 and 5cb9c5fed. Verified by `test_webhook_management_keeps_tenant_integration_keys` and `test_api_key_auth.py`.

**3. [Rule 1 - Bug] PUT and POST /test on webhooks use the session guard.** Both routes depend on `get_current_user`, not the API-key dependency, so the API-key variant returned 401 where tests expect 403 (`test_viewer_cannot_act_on_agents`) and 401 (`test_webhook_route_update_still_requires_jwt_user`). Added `WEBHOOKS_SESSION_GUARD`.

**4. [Rule 3 - Blocking] One test principal changed (slice rule 6).** `test_agent_location_history_endpoints.py::TestToggleGet::test_toggle_get_defaults_to_enabled_true` read `/api/settings/agent-location-tracking` as the plain `user` role, which lacks manage:settings. The test function now uses the tenant admin principal. Commit: 5cb9c5fed.

**Total deviations:** 4 (2 bug fixes, 2 blocking). Impact: none on scope; the integration-key pass-through is the only guard that is not a plain manifest check.

## Manifest corrections for 76-11

These are in `shared/catalogue-access.json`, which this plan did not edit. They are role lockouts the guard introduces where a built-in role held the route's own permission before:

1. `secretsManagement`: read is `manage:settings`, but `platform_support` holds `view:secrets` (what the routes check). It can no longer list secret metadata. Suggest read `["view:secrets"]`.
2. `integrations`: read is `manage:settings`; `platform_support` holds `view:integrations` and used to reach `GET /api/integrations/list` (that route had no permission check). Suggest read `["view:integrations"]` if platform staff should keep it.
3. `fleetGeoMap` and `fleetObservability`: read is `manage:agents`, while `analyst`, `incident_responder`, `platform_support` and `user` hold `view:agents`. They lose both fleet pages. The manage twin only widens a `view:` read, so this reads as an unintended `manage:` string.
4. `hadr`: routes check `view:backups`, `manage:backups` and `view:system`, which no built-in role holds apart from the Super Admin wildcard, so a tenant admin has never been able to use HA/DR. The manifest string `manage:settings` is additive and unchanged in effect, but the pair of strings needs reconciling (either grant the permissions to `tenant_admin` or change the route checks).
5. `retentionPolicy` (`/api/retention`, previously any signed-in user) now needs `manage:settings`; confirm that matches the intent for `itam_admin`.

## Phase 77 UX notes

- `App.tsx` startup loads (`fetchIntegrations`, `fetchInfrastructure`) now return 403 for roles without manage:settings; the feature switches that gate them are tenant features, not permissions. The UI should skip those loads by permission.
- ITAM `RequestsPanel` and `LifecyclePanel` derive ticket-creation availability from `GET /api/ticketing/config`; roles without manage:settings will see it as unavailable.
- `PrivacyDashboard` shows the location-tracking toggle from `GET /api/settings/agent-location-tracking`; non-admins now see the default instead of the tenant's value.
- `GET /api/system/health` has a public duplicate in `final_endpoints` and a user route in `system_health_endpoints`; which one answers depends on route order. Worth removing the duplicate in a later cleanup (out of scope here, D-02).

## Known Stubs

None.

## Threat Flags

None. No new endpoints, auth paths or schema; T-76-22, T-76-23 and T-76-24 are mitigated by the mounts, route guards and `test_settings_ops_public_routes_untouched`.

## Self-Check: PASSED

- backend/catalogue_mounts_settings_ops.py and backend/tests/test_catalogue_slice_settings_ops.py exist.
- Commits 751472443, 5cb9c5fed, d0cc9c6be are ancestors of HEAD.
- Plan verification: slice, route parity and auth baseline tests pass; full backend suite 3699 passed, 47 skipped, 0 failed.

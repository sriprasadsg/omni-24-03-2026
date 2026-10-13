---
phase: 76-catalogue-manifest-backend-route-enforcement
plan: 02
subsystem: api
tags: [rbac, catalogue-manifest, route-ownership, pytest, json]

requires:
  - phase: 76-catalogue-manifest-backend-route-enforcement
    provides: manifest seed, catalogue_guard, route walker, parity helper (plan 01)
provides:
  - shared/catalogue-access.json complete (8 groups, 202 catalogues, 188 nav, route ownership, 5 unownedPrefixes)
  - backend/tests/test_catalogue_manifest.py (15 tests; structural rules reusable via manifest_problems)
  - SLICES extended to 110 enforced views (six enforced views with no sidebar item added)
affects: [76-03, 76-04, 76-05, 76-06, 76-07, 76-08, 76-09, 76-10, 76-11, 76-12]

actuals:
  tokens: 21000
  tasks: 3
  commits: 3
plan_head_before: 1ddb99443811c7c56e29d1a14b41e9e75f04e7c3
plan_head_after: 3b5429089692c2899a45c0ecf192584c568f8056

tech-stack:
  added: []
  patterns:
    - "Manifest authored from the mounted route table: every user route has a longest-prefix owner or an unownedPrefixes reason"
    - "Enforced catalogue write list = union of grantable strings the existing guards already require; group default only when no guard string exists"
    - "Shared backend between two nav items: first in sidebar order or best-fitting guard owns the prefix, the other states 'shares routes with <view>'"

key-files:
  created:
    - backend/tests/test_catalogue_manifest.py
  modified:
    - shared/catalogue-access.json
    - backend/tests/_catalogue_parity.py
    - backend/tests/test_catalogue_route_parity.py

key-decisions:
  - "Six enforced views with no sidebar item (agentChat, supportChat, vulnerabilities, persistence, insiderThreat, fim) are added to SLICES; slice partition is 110 views"
  - "SSO/LDAP admin routes (/api/admin/sso, /api/admin/ldap) belong to userManagement: no frontend caller exists and the existing guard (manage:assets) is exactly userManagement's write list"
  - "/api/users/me and /api/tenants/me belong to profile, /api/users/me/notification-preferences to notificationPrefs, both write view:profile, so self-service stays open to every role"
  - "knowledgeBase, subscriptionManagement and invoices write list is manage:settings (D-08 user confirmation); the old manage:ai_risks guard on /api/knowledge writes still applies on top"
  - "servicePricing shares /api/finops with finops; /api/response goes to edr because EDRDashboard calls it"

patterns-established:
  - "manifest_problems(manifest, mounted_paths) returns structural violations; negative control proves each rule fires"
  - "Two-state frontend checks: compare against the Sidebar/App literals while they exist, then require the manifest import"

requirements-completed: [ACC-03, ACC-04]

coverage:
  - id: D1
    description: "Manifest has exactly one entry per AppView member (202), 188 nav in Sidebar group and item order, one permission string each"
    requirement: ACC-03
    verification:
      - kind: unit
        ref: "backend/tests/test_catalogue_manifest.py#test_views_equal_appview_union"
        status: pass
      - kind: unit
        ref: "backend/tests/test_catalogue_manifest.py#test_nav_entries_are_188_and_follow_sidebar_order"
        status: pass
    human_judgment: false
  - id: D2
    description: "Nine mismatched views carry the Sidebar string; D-08 billing trio is manage:settings, finops view:finops; D-09 users and roles read manage:users or manage:rbac"
    requirement: ACC-03
    verification:
      - kind: unit
        ref: "backend/tests/test_catalogue_manifest.py#test_nine_mismatched_views_use_the_sidebar_string"
        status: pass
      - kind: unit
        ref: "backend/tests/test_catalogue_manifest.py#test_d08_billing_trio_is_manage_settings_and_finops_is_view_finops"
        status: pass
      - kind: unit
        ref: "backend/tests/test_catalogue_manifest.py#test_d09_users_and_roles_read_rule_and_write_lists"
        status: pass
    human_judgment: false
  - id: D3
    description: "Every manifest permission, read and write string is granted by a role or super-admin only"
    requirement: ACC-04
    verification:
      - kind: unit
        ref: "backend/tests/test_catalogue_manifest.py#test_every_manifest_string_is_granted_by_some_role"
        status: pass
    human_judgment: false
  - id: D4
    description: "Route ownership: prefixes real, unique, nested prefixes resolved by longest owner, every mounted user route owned or reasoned, SLICES partition the enforced views"
    requirement: ACC-04
    verification:
      - kind: unit
        ref: "backend/tests/test_catalogue_manifest.py#test_structure_rules_hold_on_the_real_manifest"
        status: pass
      - kind: unit
        ref: "backend/tests/test_catalogue_manifest.py#test_every_mounted_user_route_is_owned_or_reasoned"
        status: pass
      - kind: unit
        ref: "backend/tests/test_catalogue_manifest.py#test_slices_cover_each_enforced_catalogue_exactly_once"
        status: pass
    human_judgment: false
  - id: D5
    description: "Whether the confirmed route-to-view mappings are the right product ownership (for example /api/response to EDR, SSO/LDAP to user management)"
    verification: []
    human_judgment: true
    rationale: "Ownership of shared backends is a product judgment; the tests prove consistency, not that a given owner is the intended one. Review the deviation list below."

duration: 13min
completed: 2026-10-13
status: complete
---

# Phase 76 Plan 02: Complete Catalogue Manifest Summary

**The shared manifest now lists all 202 AppView catalogues in Sidebar order with one permission each, confirmed route prefixes and explicit write lists for the 110 enforced views, a stated owner or reason for every one of the 1500 mounted user routes, and 15 tests that lock it.**

## Performance

- **Duration:** 13 min
- **Started:** 2026-10-13T04:28Z
- **Completed:** 2026-10-13T04:42Z
- **Tasks:** 3
- **Files modified:** 4 (1 created, 3 modified)

## Accomplishments
- 202 catalogues (188 nav, 14 App-only), 8 groups with enforce true only for infra, security, mgmt; the nine mismatched views use the Sidebar strings (D-11) and `view:jobs` stays in `SUPER_ADMIN_ONLY_PERMISSIONS`.
- D-08: subscriptionManagement, invoices, knowledgeBase are `manage:settings` and own `/api/payments`, `/api/billing`, `/api/knowledge`; finops is `view:finops` and owns `/api/finops`. D-09: userManagement and roleManagement read `manage:users` or `manage:rbac`; the Phase 75 ceiling is untouched.
- Route ownership generated from the real mounted walk: zero unowned user routes, 5 `unownedPrefixes`, 23 catalogues with a `noBackendReason` (of which 8 are in enforced groups with no routes of their own).
- Edge assumptions confirmed by test: duplicate prefixes fail, nested prefixes resolve by longest owner (`/api/payments` vs `/api/payments/invoices`, `/api/agents` vs `/api/agents/capabilities`, `/api/settings` vs `/api/settings/geo-security`), shared backends use `shares routes with <view>` naming an existing view, empty routes need a reason, an empty manifest or empty group fails (`test_structure_rules_fire_on_a_broken_manifest`).

## Task Commits

1. **Task 1: Manifest sanity tests (RED)** - `86e9ce3ad` (test). 9 of 15 failed against the seed, including AppView coverage (201 views missing).
2. **Task 2: Enforced groups** - `51a96286e` (feat). 110 catalogues; only AppView, nav-count, Sidebar/App agreement, nine-views, structure and unowned-route tests still failed, all because the five non-enforced groups were absent.
3. **Task 3: Non-enforced groups, App-only views, unownedPrefixes** - `3b5429089` (feat). Full green.

**Plan metadata:** committed with this SUMMARY (docs: complete plan)

## TDD Gate Compliance

RED `86e9ce3ad` (test) precedes GREEN `51a96286e`/`3b5429089` (feat). RED assessment: the target test `test_views_equal_appview_union` failed on its own assertion ("AppView members missing from the manifest", 201 missing) against the unchanged seed, not on an import or fixture error. No REFACTOR commit.

## Test results
- `pytest backend/tests/test_catalogue_manifest.py test_catalogue_route_parity.py test_catalogue_guards.py` 39 passed; with `test_route_auth_baseline.py` and `test_rbac_defaults.py` 97 passed.
- `npx vitest run src/__tests__/catalogueAccess.test.ts` 2 passed; `tsc --noEmit` shows no error in `utils/catalogueAccess.ts`.
- Full backend suite: 3315 passed, 47 skipped (76-01 baseline 3300 / 47; +15 new tests, no regressions) in 2m48s.

## In-scope catalogues (read by 76-04..76-10)

Permission is the read rule (guard also accepts the `manage:` twin). Write is the guard's any-of list. Empty write means no routes of its own.

| View | Permission | Read (if not permission) | Write | Owned prefixes / reason |
|---|---|---|---|---|
| agents | view:agents |  | investigate:security,manage:agents,manage:compliance,remediate:agents | /api/agents /api/agent /api/agent-updates |
| agentCapabilities | view:agent_capabilities |  | manage:agents | /api/agents/capabilities |
| assetManagement | view:assets |  | manage:assets,manage:compliance_evidence | /api/assets |
| itam | view:itam |  | manage:assets,manage:procurement,request:assets | /api/itam /api/v1/itam /api/assets/labels /api/assets/reports |
| patchManagement | view:patching |  | manage:patches | /api/patches /api/repo |
| deploymentApprovals | view:patching |  | manage:approvals | /api/approvals |
| softwareUpdates | view:software_updates |  | manage:patches | /api/software |
| softwareDeployment | view:software_deployment |  | manage:settings,view:software_deployment | /api/deployments |
| stagedDeployments | view:software_deployment |  | - | (none) shares routes with softwareDeployment |
| windowsAutopilot | view:autopilot |  | manage:assets | /api/autopilot |
| mobileDeviceManagement | view:mdm |  | manage:assets | /api/mdm |
| mobileAppManagement | view:mam |  | manage:assets | /api/mam |
| androidEnterprise | view:android_enterprise |  | manage:assets | /api/android-enterprise |
| branchSites | view:branch_sites |  | manage:agents | /api/branch-sites |
| appCatalog | view:app_catalog |  | manage:assets | /api/app-catalog |
| assetIntelligence | view:asset_intelligence |  | manage:assets | /api/asset-intelligence |
| deviceConfigProfiles | view:device_config_profiles |  | manage:assets | /api/device-config-profiles |
| firmwareDriverUpdates | view:firmware_drivers |  | investigate:security,manage:patches | /api/firmware-drivers /api/firmware-attestation |
| serviceCatalog | view:service_catalog |  | manage:automation | /api/service-catalog |
| jobs | view:jobs |  | manage:automation | /api/jobs |
| remoteAccess | view:remote_access |  | view:remote_access | /api/remote |
| chat | manage:agents |  | manage:agents | /api/support /api/agent-chat |
| certificates | view:assets |  | manage:settings | /api/certificates |
| security | view:security |  | manage:security_cases,manage:settings | /api/security |
| alertManagement | view:security |  | manage:security_cases | /api/alerts /api/alert-rules |
| edr | view:security |  | investigate:security,manage:active_response,manage:security_cases | /api/edr /api/response |
| yaraRules | view:security |  | investigate:security | /api/analysis |
| mdr | view:mdr |  | investigate:security | /api/mdr |
| xdr | view:xdr |  | investigate:security,manage:security_cases | /api/xdr |
| mitreAttack | view:security |  | investigate:security | /api/mitre |
| dlp | view:security |  | investigate:security | /api/dlp |
| cloudSecurity | view:cloud_security |  | investigate:security,manage:security_cases | /api/cspm /api/cloud |
| cloudAccounts | view:cloud_security |  | manage:settings,view:cloud_security | /api/cloud-accounts |
| cloudChecksScanner | view:cloud_security |  | manage:compliance | /api/cloud-checks |
| iacContainer | view:cloud_security |  | manage:settings,view:dashboard | /api/container /api/iac |
| threatHunting | view:threat_hunting |  | view:threat_hunting | /api/ai/threat-hunt |
| siem | view:security |  | manage:security_cases,manage:settings | /api/siem |
| threatIntelligence | view:threat_intel |  | view:threat_intel | /api/threat-intel /api/ai/reputation |
| securityIntelConnectors | view:security |  | manage:settings | /api/security-intel |
| siemRules | view:security |  | - | (none) shares routes with siem |
| incidentResponse | investigate:security |  | investigate:security | /api/security-cases /api/security-events |
| incidentWarRoom | investigate:security |  | investigate:security | /api/incidents |
| deception | view:security |  | manage:security_cases | /api/deception |
| aiAnomaly | view:security |  | - | (none) shares routes with ueba |
| ueba | view:security |  | investigate:security | /api/ueba /api/itdr |
| shadowAI | view:security |  | - | (none) shares routes with ueba |
| ndr | view:security |  | investigate:security,manage:settings | /api/ndr /api/ot-ics |
| correlations | view:security |  | manage:security_cases,view:security | /api/correlations |
| emailSecurity | view:security |  | manage:security_cases,manage:settings | /api/email-security |
| incidentImpact | investigate:security |  | investigate:security | /api/security/incident-impact |
| dataSecurity | view:dspm |  | - | (none) no dedicated /api route is mounted |
| attackPath | view:attack_path |  | investigate:security,manage:security_cases | /api/security/attack-paths |
| pentest | view:security |  | investigate:security,manage:security_cases | /api/pentest |
| dast | view:security |  | investigate:security | /api/dast |
| zeroTrustQuantum | view:zero_trust |  | manage:settings,view:security | /api/zero-trust /api/quantum-security /api/pqc |
| vulnerabilityManagement | view:vulnerabilities |  | investigate:security,manage:patches,manage:security_cases,view:security | /api/vulnerabilities /api/vulnerability-scans |
| persistenceDetection | view:persistence |  | investigate:security | /api/persistence |
| securitySimulation | view:security |  | remediate:agents | /api/simulation |
| securityAudit | view:security_audit |  | investigate:security,manage:security_cases | /api/security/audit-log |
| runtimeSecurity | view:security |  | - | (none) no /api route is mounted |
| pam | manage:settings |  | manage:settings | /api/pam |
| advancedHunting | view:advanced_hunting |  | investigate:security | /api/advanced-hunting |
| detectionRules | view:detection_rules |  | manage:security_cases | /api/detection-rules |
| connectorsHub | view:connectors_hub |  | manage:settings | /api/connectors-hub |
| securityCopilot | view:security_copilot |  | investigate:security | /api/security-copilot |
| attackTimeline | view:attack_timeline |  | - | (none) shares routes with advancedHunting |
| geographicMap | view:geographic_map |  | - | (none) shares routes with advancedHunting |
| scaAssessment | view:sca |  | investigate:security | /api/sca |
| agentGroups | view:agent_groups |  | manage:agents | /api/agent-groups |
| configDrift | view:config_drift |  | remediate:agents | /api/config-drift |
| fimMonitoring | view:fim |  | manage:agents | /api/fim |
| activeResponse | view:active_response |  | manage:active_response | /api/active-response |
| finops | view:finops |  | manage:settings,view:reporting | /api/finops |
| servicePricing | manage:pricing |  | - | (none) shares routes with finops |
| paymentSettings | manage:settings |  | manage:settings | /api/payments/setup /api/payments/configured-gateways /api/payments/gateways /api/payments/methods /api/billing/stripe-config /api/billing/paypal-config /api/billing/payment-methods |
| subscriptionManagement | manage:settings |  | manage:settings | /api/payments |
| invoices | manage:settings |  | manage:settings | /api/payments/invoices /api/billing |
| cloudIntegrations | manage:settings |  | manage:settings | /api/cloud-integrations |
| secretsManagement | manage:settings |  | manage:secrets,view:secrets | /api/secrets |
| hadr | manage:settings |  | manage:settings | /api/hadr |
| retentionPolicy | manage:settings |  | manage:settings | /api/retention |
| retentionPolicies | view:retention_policies |  | manage:settings | /api/retention-tiers |
| msspMonitoring | view:mssp |  | manage:mssp | /api/mssp |
| knowledgeBase | manage:settings |  | manage:settings | /api/knowledge |
| geoSecurity | manage:settings |  | manage:settings | /api/settings/geo-security /api/settings/agent-location-tracking |
| fleetObservability | manage:agents |  | manage:agents | /api/fleet/observability |
| fleetGeoMap | manage:agents |  | manage:agents | /api/fleet/geo |
| nativeSecurity | manage:active_response |  | manage:active_response | /api/security-ops |
| systemHealth | manage:settings |  | manage:settings | /api/system /api/cache /api/maintenance |
| apiStatus | manage:settings |  | manage:settings | /api/system/routes |
| settings | manage:settings |  | manage:settings | /api/settings /api/ai/config /api/ai/test-connection /api/data-sources /api/email |
| tenantManagement | manage:tenants |  | manage:tenants,manage:settings | /api/tenants |
| bundleManagement | manage:tenants |  | manage:tenants | /api/bundles |
| webhooks | manage:settings |  | manage:settings | /api/webhooks |
| ticketing | manage:settings |  | investigate:security,manage:settings | /api/ticketing |
| ticketWebhooks | manage:settings |  | manage:settings | /api/tickets/webhooks |
| notificationPrefs | view:profile |  | view:profile | /api/users/me/notification-preferences |
| dataWarehouse | view:reporting |  | manage:settings,view:reporting | /api/etl /api/warehouse /api/data-lake |
| vulnerabilities | view:vulnerabilities |  | - | (none) shares routes with vulnerabilityManagement |
| persistence | view:persistence |  | - | (none) shares routes with persistenceDetection |
| insiderThreat | view:security |  | investigate:security,manage:settings | /api/insider-threat |
| fim | view:security |  | - | (none) shares routes with fimMonitoring |
| supportChat | view:dashboard |  | - | (none) shares routes with chat |
| agentChat | manage:agents |  | - | (none) shares routes with chat |
| userManagement | manage:rbac | manage:users,manage:rbac | manage:assets | /api/users /api/admin/sso /api/admin/ldap |
| roleManagement | manage:rbac | manage:users,manage:rbac | manage:rbac | /api/roles |
| apiKeys | manage:api_keys |  | manage:api_keys,manage:assets | /api/api-keys /api/admin/api-keys |
| profile | view:profile |  | view:profile | /api/users/me /api/tenants/me |
| notifications | view:dashboard |  | manage:settings,view:dashboard | /api/notifications |
| integrations | manage:settings |  | manage:security_cases,manage:settings | /api/integrations |

Write-list notes: strings no role holds (`manage:security` on pentest and threat-intel, `manage:backups` on hadr, `manage:system` and `view:system` on finops/apm) were dropped because the existing guard keeps them super-admin-only on its own and the grantable test rejects them. Where no existing guard string was found the list falls back to the twin if granted, else the group default (security: `investigate:security`, `manage:security_cases`; infra: `manage:agents`/`manage:assets`; mgmt: `manage:settings`).

## unownedPrefixes
`/api/auth` (self-service session lookup), `/api/mfa` (self-service MFA), `/api/passkey` (self-service passkeys), `/api/search` (cross-catalogue global search), `/api/platform` (app-shell feature flags).

## Deviations from RESEARCH Appendix A/B (confirmed routes that differ, with evidence)

Evidence is the component or module that calls the route, plus the mounted walk.
- serviceCatalog: Appendix says no backend; `/api/service-catalog` is mounted (`platform_endpoints`, 4 routes), so it is owned and enforced.
- threatHunting: Appendix none; `/api/ai/threat-hunt` (`ai_endpoints`, write guard `view:threat_hunting`).
- cloudSecurity: Appendix none; `/api/cspm/findings` (`platform_endpoints`) and `/api/cloud/remediation/*` (`cloud_remediation_endpoints`).
- xdr: Appendix none; `XDRDashboard.tsx` calls `/api/xdr/automated-hunts` and `/api/correlations`.
- edr and mdr: `EDRDashboard.tsx` calls `/api/response/execute` and `/history`, so `/api/response` belongs to edr (view:security), not mdr; mdr keeps `/api/mdr`.
- incidentResponse: Appendix none; `/api/security-cases` and `/api/security-events` (`security_cases_endpoints`).
- incidentImpact: Appendix `agent`; `/api/security/incident-impact/{id}` only. `/api/ai/analyze-impact` stays with the Automation AI assistant (its existing guard is `view:dashboard`, which would have made the write list incoherent).
- attackPath `/api/security/attack-paths`, securityAudit `/api/security/audit-log` are sub-prefixes of `/api/security` and win by longest prefix; the rest of `/api/security` (ip-bans, keypair, encrypt) is `security`.
- stagedDeployments, deploymentApprovals, softwareDeployment: `/api/deployments` guards use `view:software_deployment`, so softwareDeployment owns it and stagedDeployments shares; `/api/approvals` goes to deploymentApprovals; `/api/software` to softwareUpdates (Appendix gave softwareDeployment `software`).
- patchManagement: `/api/patches` plus `/api/repo` (`PatchManagementDashboard` imports repo); approvals moved out.
- assetManagement and itam: `/api/assets/labels` and `/api/assets/reports` (`itam_label_endpoints`, `itam_lifecycle_endpoints`) go to itam; path-parameter routes (`/api/assets/{id}/...`) cannot be split by prefix and stay with assetManagement (D-04 strip is a later plan).
- agentCapabilities: only `/api/agents/capabilities/*`; `/api/agents/{id}/capabilities` stays under agents (path parameter).
- zeroTrustQuantum gains `/api/pqc`; ndr gains `/api/ot-ics`; ueba gains `/api/itdr`; firmwareDriverUpdates gains `/api/firmware-attestation`.
- ueba, shadowAI, aiAnomaly: Appendix ndr,ueba; ueba owns `/api/ueba` (the `ueba_endpoints`/`ueba_service` module), shadowAI and aiAnomaly share it.
- settings: Appendix `integrations,settings`; `/api/integrations` moves to the App-only `integrations` (mgmt) view; settings keeps `/api/settings`, `/api/email`, `/api/data-sources`, `/api/ai/config`, `/api/ai/test-connection`. `/api/settings/geo-security` and `/api/settings/agent-location-tracking` go to geoSecurity.
- SSO/LDAP admin (`/api/admin/sso`, `/api/admin/ldap`) go to userManagement; no frontend file references them (grep of components, services, App), and their existing guard is `_require_itam_admin_session_only` (manage:assets), identical to userManagement's write list. `/api/admin/api-keys` goes to apiKeys.
- subscriptionManagement, invoices, paymentSettings: `/api/payments/{setup,configured-gateways,gateways,methods}` and `/api/billing/{stripe-config,paypal-config,payment-methods}` are paymentSettings; `/api/payments/invoices` and `/api/billing` are invoices; remaining `/api/payments` is subscriptionManagement (`InvoiceList`, `SubscriptionManagement`, `PaymentSettings` call these).
- servicePricing shares `/api/finops` (pricing routes live there); msspMonitoring owns only `/api/mssp` (`/api/alerts` is alertManagement).
- ticketWebhooks owns only `/api/tickets/webhooks`; the rest of `/api/tickets` is internalTickets (Automation, not enforced). notificationPrefs owns only `/api/users/me/notification-preferences`.
- dataWarehouse gains `/api/data-lake`; systemHealth gains `/api/cache`, `/api/maintenance`; apiStatus owns `/api/system/routes` (`system_endpoints`).
- Appendix B placed these in the Security group, but their views are in DevSecOps (not enforced) so they go to the ledger: `/api/pipeline-security`, `/api/supply-chain-security`, `/api/api-security`, `/api/dam`, `/api/k8s-security`. `/api/network-devices` and `/api/logs` belong to Observability views.
- Appendix B listed `/api/auth/ldap|saml` and `/api/sso`; the mounted paths are `/api/admin/ldap` and `/api/admin/sso/saml`. `/api/auth` has only `/api/auth/me` (unowned, self-service).

## Decisions Made
See key-decisions. All write lists follow the plan rule (union of existing guard strings); the two intentional departures are the D-08 trio (manage:settings) and the self-service profile entries (view:profile).

## Deviations from Plan

**1. [Rule 3 - Blocking] SLICES and its partition test needed six extra enforced views**
- **Found during:** Task 2
- **Issue:** Six nav:false views confirmed in enforced groups (agentChat, supportChat, vulnerabilities, persistence, insiderThreat, fim) were not in SLICES, and `test_slices_partition_every_in_scope_catalogue_once` hard-coded 104 with identity views as the only non-sidebar entries.
- **Fix:** Added them to the agents, secops and secposture slices (the plan allows adjusting SLICES); updated that 76-01 test to 110 with an explicit alias set.
- **Files modified:** backend/tests/_catalogue_parity.py, backend/tests/test_catalogue_route_parity.py
- **Committed in:** 51a96286e

**2. Task 1 test file anticipates 76-03:** the Sidebar/App agreement test has the two-state rule from the plan; the second state (manifest import, no literals) is exercised only after 76-03.

**Total deviations:** 1 auto-fixed (Rule 3). **Impact:** none on scope.

## Issues Encountered
- Introspected guard strings come from closures and handler source; routes that are login-only today have no string, so their write list uses the sibling-route union or the group default. Reviewers should read the write column for catalogues marked with default fallbacks (xdr, cloudSecurity, attackPath, pentest, securityAudit, chat, servicePricing shares).

## Open items for the user (not blocking)
- Existing guards for user CRUD, SSO, LDAP and admin API keys are `manage:assets`; the manifest mirrors that (userManagement write). Consider moving them to `manage:users`/`manage:rbac` in a later hardening step.
- `/api/notifications`, `/api/integrations`, `/api/email` and `/api/tenants` are now owned by enforced mgmt catalogues; wave-3 plans must exempt self-service routes (tenant-scoped routes in `tenant_endpoints`, notification read/mark-read) per Pitfall 7 or the guard will 403 tenant admins.
- `apiKeys` read requires `manage:api_keys` (tenant_admin only today), so an itam_admin loses direct API access to its own keys once the guard lands; the page was already hidden from it.

## Known Stubs
None. No hardcoded placeholder data was added; `noBackendReason` entries are intentional documented states.

## Threat Flags
None. No endpoints, auth paths or schema were added; this plan only edits data and tests.

## Self-Check: PASSED

---
*Phase: 76-catalogue-manifest-backend-route-enforcement*
*Completed: 2026-10-13*

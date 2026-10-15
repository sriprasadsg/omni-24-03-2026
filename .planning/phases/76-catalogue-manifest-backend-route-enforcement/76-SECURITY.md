---
phase: "76"
slug: "catalogue-manifest-backend-route-enforcement"
status: verified
# threats_open = count of OPEN threats at or above workflow.security_block_on severity (the blocking gate)
threats_open: 0
asvs_level: 1
created: "2026-10-15"
---

# Phase 76 — Security

> Per-phase security contract: threat register, accepted risks, and audit trail.

---

## Trust Boundaries

| Boundary | Description | Data Crossing |
|----------|-------------|---------------|
| browser/API client -> FastAPI router | Untrusted callers (session JWT or API key) reach catalogue routes; the guard is the access decision | Tenant security, asset, financial and identity data |
| agent -> /api/agents* (register, heartbeat, instructions, results, telemetry, scan uploads, uninstall report), deployment results, patch progress | Agent key / agent JWT traffic that must stay outside user guards (D-02) | Endpoint telemetry and command results |
| external systems / IdP -> inbound webhooks, SSO/SAML/LDAP, tenant lookup-key, Stripe webhook, EDR ingest, deception webhook | Public by design; signature or credential checked inside the handler | Sign-in assertions, payment and security events |
| URL hash / deep link -> App view switch | User-controlled input selects a view; the manifest permission decides | View selection (UI only) |
| manifest data -> backend guards and frontend navigation | One wrong permission or route owner becomes the expected guard everywhere | Access policy |
| developer change -> mounted route table; reviewer -> committed gap ledger | A new router can add an unguarded route; the ledger decides which gaps are accepted | Access policy |
| in-memory asset cache -> later callers | Cached objects are returned by reference | Asset finance fields |
| test harness -> MongoDB | Tests must never reach the live omni_platform database | Production data |

---

## Threat Register

| Threat ID | Category | Component | Severity | Disposition | Mitigation | Status |
|-----------|----------|-----------|----------|-------------|------------|--------|
| T-76-01 | Elevation of Privilege | catalogue_guard / check_catalogue_access | high | mitigate | `catalogue_guard` read/write/scope rules: test_catalogue_guards.py (test_read_refused_without_view_or_manage, test_write_refused_with_view_only, test_role_is_checked_before_scopes) | closed |
| T-76-02 | Denial of Service | mount-level guard on agent or API-key routes | high | mitigate | Agent/API-key routes keep their own auth: test_route_auth_baseline.py, test_catalogue_slice_agents.py::test_agent_routes_untouched, test_api_key_scope_* in test_catalogue_guards.py | closed |
| T-76-03 | Information Disclosure | asset finance fields on /api/assets reads | high | mitigate | test_asset_finance_fields.py (list/search/detail strip finance fields without view:itam) | closed |
| T-76-04 | Tampering | test_route_auth_baseline.py during walker extraction | medium | mitigate | test_route_auth_baseline.py kept green on the shared `_route_walk.py` walker | closed |
| T-76-05 | Information Disclosure | real-app probe in tests | medium | mitigate | `_route_walk.throwaway_env()` points MONGODB_URL at an unroutable port and MONGODB_DB_NAME at `catalogue_probe_throwaway` | closed |
| T-76-06 | Elevation of Privilege | manifest permission for the nine mismatched views and the D-08 trio | high | mitigate | test_catalogue_manifest.py::test_nine_mismatched_views_use_the_sidebar_string, ::test_d08_billing_trio_is_manage_settings_and_finops_is_view_finops | closed |
| T-76-07 | Information Disclosure | route ownership (in-scope route assigned to an out-of-scope catalogue) | high | mitigate | test_catalogue_manifest.py::test_every_mounted_user_route_is_owned_or_reasoned, ::test_nested_prefixes_resolve_to_the_longest_owner | closed |
| T-76-08 | Denial of Service | write lists stricter than existing guards | medium | mitigate | test_catalogue_manifest.py::test_enforced_catalogues_have_explicit_write_lists, ::test_every_manifest_string_is_granted_by_some_role | closed |
| T-76-09 | Elevation of Privilege | App.tsx hash routing using a weaker App-only string (for example swarm via view:dashboard) | medium | mitigate | App.tsx resolves view permissions from the manifest (catalogueAccess.test.ts 'resolves view permissions and hash routes from the manifest reader'); viewPermissionMap literal removed | closed |
| T-76-10 | Spoofing | client-side sidebar hiding treated as security | low | accept | Accepted: sidebar hiding is cosmetic; the backend guards enforce (see Accepted Risks) | closed |
| T-76-11 | Information Disclosure | @cached shared objects | medium | mitigate | test_asset_finance_fields.py::test_stripping_never_mutates_the_source_documents, ::test_cached_results_do_not_cross_callers | closed |
| T-76-12 | Elevation of Privilege | /api/jobs reads | medium | mitigate | /api/jobs guarded; tenant_admin refused (76-05 SUMMARY, test_catalogue_slice_agents.py::test_agents_real_app_enforced) | closed |
| T-76-13 | Denial of Service | write lists stricter than existing patch/deploy guards | medium | mitigate | Write lists are the union of existing write strings (76-02); full backend suite green with no existing test changed (76-06) | closed |
| T-76-14 | Information Disclosure | security telemetry and incident data | high | mitigate | test_catalogue_slice_secops.py::test_secops_real_app_enforced (403 without view:security on alerts, SIEM and 9 other reads) | closed |
| T-76-15 | Denial of Service | security writes locked out by an ungranted write string | medium | mitigate | test_catalogue_slice_secops.py::test_secops_writes_use_existing_strings | closed |
| T-76-16 | Information Disclosure | cloud account, vulnerability and PAM data | high | mitigate | test_catalogue_slice_secposture.py::test_secposture_real_app_enforced, ::test_secposture_vulnerability_read_needs_view_vulnerabilities | closed |
| T-76-17 | Denial of Service | write lists stricter than existing guards | medium | mitigate | test_catalogue_slice_secposture.py::test_secposture_writes_use_existing_strings | closed |
| T-76-18 | Information Disclosure | invoices, subscriptions, payments and FinOps reads reachable by every role (view:dashboard) | high | mitigate | test_catalogue_slice_billing_identity.py::test_d08_billing_requires_manage_settings, ::test_d08_finops_requires_view_finops | closed |
| T-76-19 | Elevation of Privilege | user and role administration | high | mitigate | test_catalogue_slice_billing_identity.py::test_d09_user_and_role_admin, ::test_identity_admin_enforced | closed |
| T-76-20 | Denial of Service | SSO/SAML/LDAP sign-in, tenant lookup-key, Stripe webhook | high | mitigate | test_catalogue_slice_billing_identity.py::test_public_identity_routes_untouched (SSO/SAML/LDAP, lookup-key, Stripe webhook) | closed |
| T-76-21 | Denial of Service | self-service profile and API-key routes | medium | mitigate | Self-service routes are catalogue_exempt with reasons; probe asserts /api/users/me, notification prefs and own API keys for every default role (test_catalogue_slice_billing_identity.py) | closed |
| T-76-22 | Information Disclosure | settings, LLM/database config, secrets and cache stats reachable by any signed-in user | high | mitigate | test_catalogue_slice_settings_ops.py::test_settings_ops_real_app_enforced, ::test_settings_ops_role_scoped_catalogues | closed |
| T-76-23 | Tampering | login-only cache invalidation and retention runs | medium | mitigate | Cache invalidation and retention runs carry the settings guard (catalogue_mounts_settings_ops.py); test_settings_ops_slice_parity | closed |
| T-76-24 | Denial of Service | inbound webhook receivers, public health route, app-shell settings reads | high | mitigate | test_catalogue_slice_settings_ops.py::test_settings_ops_public_routes_untouched | closed |
| T-76-25 | Elevation of Privilege | new router or route added without a guard | high | mitigate | test_catalogue_route_parity.py::test_all_enforced_routes_guarded, ::test_unguarded_routers_are_ledgered | closed |
| T-76-26 | Tampering | ledger or exemptions edited to hide gaps | medium | mitigate | test_catalogue_route_parity.py::test_ledger_ratchets plus ledger negative controls (slack, stale, enforced-in-ledger, exempt over ratchet); helper never writes the ledger | closed |
| T-76-27 | Elevation of Privilege | alias routes in route_aliases.py bypassing the canonical guard | high | mitigate | route_aliases.py aliases carry the owning catalogue's guard; covered by test_all_enforced_routes_guarded | closed |
| T-76-28 | Elevation of Privilege | asset, ITAM, certificate routers (login-only reads today) | high | mitigate | test_catalogue_slice_assets.py::test_assets_real_app_enforced, ::test_itam_reads_follow_view_itam_on_real_app | closed |
| T-76-29 | Denial of Service | ITAM API-key callers | high | mitigate | test_catalogue_slice_assets.py::test_itam_api_key_unchanged | closed |
| T-76-30 | Elevation of Privilege | login-only agent-console and remote-access reads | high | mitigate | test_catalogue_slice_agents.py::test_agents_real_app_enforced | closed |
| T-76-31 | Denial of Service | agent enrollment, heartbeat, instructions, downloads | high | mitigate | test_catalogue_slice_agents.py::test_agent_routes_untouched (structural); live agent check is a post-deploy manual item | closed |
| T-76-32 | Elevation of Privilege | login-only patch/device reads | high | mitigate | test_catalogue_slice_devices.py::test_devices_real_app_enforced, ::test_device_management_real_app_enforced | closed |
| T-76-33 | Denial of Service | agent deployment-result and patch-progress routes | high | mitigate | test_catalogue_slice_devices.py::test_device_agent_routes_untouched | closed |
| T-76-34 | Elevation of Privilege | login-only security reads | high | mitigate | test_catalogue_slice_secops.py::test_secops_real_app_enforced, ::test_secops_guards_match_manifest | closed |
| T-76-35 | Denial of Service | EDR ingest and deception webhook | high | mitigate | test_catalogue_slice_secops.py::test_secops_public_routes_untouched (EDR ingest, deception webhook, alert posts) | closed |
| T-76-36 | Elevation of Privilege | login-only posture reads | high | mitigate | test_catalogue_slice_secposture.py::test_secposture_real_app_enforced, ::test_secposture_guards_match_manifest | closed |
| T-76-37 | Elevation of Privilege | login-only agent console reads in the data-plane routers | high | mitigate | test_catalogue_slice_agents_dataplane.py::test_dataplane_real_app_enforced | closed |
| T-76-38 | Denial of Service | agent instructions, results, telemetry, scan uploads, tickets, uninstall reports | high | mitigate | test_catalogue_slice_agents_dataplane.py::test_dataplane_agent_routes_untouched, ::test_dataplane_agent_auth_unchanged | closed |
| T-76-SC | Tampering | npm/pip installs | low | accept | No new dependencies were installed in any of the 12 plans; see Accepted Risks | closed |

*Status: open · closed · open — below high threshold (non-blocking)*
*Severity: critical > high > medium > low — only open threats at or above workflow.security_block_on count toward threats_open*
*Disposition: mitigate (implementation required) · accept (documented risk) · transfer (third-party)*

Register authored at plan time (all 12 PLAN files carry a `<threat_model>`). Verified at ASVS level 1 (grep depth: each mitigation traced to its guard module or a green test). Every cited test passed on 2026-10-15: the phase test set (132 backend tests), `catalogueAccess.test.ts` (26), and the full backend suite (3721 passed, 0 failed).

**Pre-existing finding, not introduced by this phase (76-05):** `GET /api/support/presence` returns online status for any requested usernames with no tenant scoping (cross-tenant presence lookup). It is catalogue_exempt as self-service; a tenant filter is still needed. Not a phase 76 threat; tracked here so it is not lost.

---

## Accepted Risks Log

| Risk ID | Threat Ref | Rationale | Accepted By | Date |
|---------|------------|-----------|-------------|------|
| AR-76-01 | T-76-10 | The sidebar hides views client-side only; that is cosmetic by design. Every enforced catalogue is refused by the backend guard, and the parity gate keeps the two in step | Plan 76-03 threat model (planner) | 2026-10-13 |
| AR-76-02 | T-76-SC | Supply-chain risk of npm/pip installs. Low severity; no plan in this phase installed or upgraded a dependency | Plans 76-01..76-12 threat models (planner) | 2026-10-13 |

*Accepted risks do not resurface in future audit runs.*

---

## Security Audit Trail

| Audit Date | Threats Total | Closed | Open | Run By |
|------------|---------------|--------|------|--------|
| 2026-10-15 | 39 | 39 | 0 | /gsd-secure-phase 76 (orchestrator, ASVS L1 short-circuit: register authored at plan time, 0 open) |

---

## Sign-Off

- [x] All threats have a disposition (mitigate / accept / transfer)
- [x] Accepted risks documented in Accepted Risks Log
- [x] `threats_open: 0` confirmed
- [x] `status: verified` set in frontmatter

**Approval:** verified 2026-10-15

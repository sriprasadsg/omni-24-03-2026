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
| T-76-39 | Information Disclosure | GET /api/software/download/{filename}, GET /api/response/tasks/{agent_id} (76-13) | high | mitigate | `agent_tolerant(SOFTWARE_UPDATES_GUARD)` / `agent_tolerant(EDR_GUARD)` on both routes (software_endpoints.py:118, response_endpoints.py:197); test_catalogue_guard_variants.py::test_download_on_the_real_app, ::test_download_refuses_roles_without_view_software_updates, ::test_task_poll_refuses_people_without_view_security, ::test_task_poll_and_chat_list_on_the_real_app | closed |
| T-76-40 | Spoofing | agent identity check in the guard (76-13) | low | accept | Accepted (AR-76-03): identity is the auth layer's own test (role claim exactly `agent` via get_current_user_or_agent); test_role_spelled_Agent_is_a_person, ::test_plain_guard_still_refuses_agent_role_without_the_permission | closed |
| T-76-41 | Denial of Service | agent polling and installer download (76-13) | high | mitigate | Agent identity returns before any permission lookup (catalogue_guards.py:143); test_agent_identity_skips_the_permission_lookup, ::test_download_serves_agent_and_permitted_roles, ::test_task_poll_serves_agent_and_security_readers | closed |
| T-76-42 | Tampering | agentCapableRoutes / exemptRoutes edited to hide a gap (76-14) | medium | mitigate | Exact per-route lists with reason equality; test_catalogue_route_parity.py::test_reworded_exempt_reason_is_an_offender_showing_both_reasons, ::test_ledger_offender_for_unlisted_agent_capable_route_is_paste_ready, ::test_committed_exempt_list_matches_the_production_registry; helper never writes the ledger | closed |
| T-76-43 | Elevation of Privilege | platform_read guard variant (76-13) | high | mitigate | Construction refuses permissions outside PLATFORM_ONLY_PERMISSIONS (catalogue_guards.py:138); runtime uses has_platform_permission on SAFE_METHODS only (catalogue_guards.py:81-85); test_platform_read_must_be_platform_only, ::test_platform_support_reads_but_never_writes, ::test_platform_support_in_a_tenant_is_refused, ::test_narrowed_scope_refuses_platform_staff | closed |
| T-76-44 | Information Disclosure | GET allowlist, enrollment-keys, email/config, email/preferences, license (76-15) | high | mitigate | SETTINGS_GUARD (tenant_endpoints.py:492, 625) and TENANT_CONTROLS_READ_GUARD (tenant_endpoints.py:714, tenant_enrollment_endpoints.py:67, 121); test_catalogue_slice_billing_identity.py::test_tenant_settings_reads_are_role_gated (403 for nine tenant roles on all five paths) | closed |
| T-76-45 | Elevation of Privilege | platform_read on TENANT_CONTROLS_READ_GUARD (76-15) | high | mitigate | platform_read is only `view:tenants` (catalogue_mounts_billing_identity.py:66-68), checked through has_platform_permission on safe methods (T-76-43 tests); writes keep TENANT_PLATFORM_STAFF plus _require_license_manager (test_platform_role_routes.py) | closed |
| T-76-46 | Denial of Service | tenant admins and platform staff losing reads they use (76-15) | medium | mitigate | test_tenant_settings_reads_are_role_gated asserts not-refused for tenant_admin, admin, super_admin and (license/allowlist/install keys) platform staff; license consumer precondition grep held; live check is a post-deploy manual item | closed |
| T-76-47 | Tampering | exemption reasons that misdescribe what a route returns (76-15) | medium | mitigate | Self-service-on-tenant/user-path rule in _catalogue_parity.ledger_offenders; test_catalogue_route_parity.py::test_self_service_exemption_on_a_tenant_path_is_an_offender, ::test_self_service_exemption_on_a_user_id_path_is_an_offender, plus two clean controls | closed |
| T-76-48 | Information Disclosure | future agent-capable read under an enforced catalogue added without a guard (76-14) | medium | mitigate | _parity_scope puts safe-method agent-capable routes under enforce:true catalogues in parity scope; test_catalogue_route_parity.py::test_untagged_agent_capable_read_in_enforced_catalogue_is_a_parity_offender | closed |
| T-76-49 | Denial of Service | a non-tolerant catalogue tag on an agent-capable route refusing the agent (76-14) | medium | mitigate | Parity offender for any agent_capable record with a tag lacking allow_agent True; test_catalogue_route_parity.py::test_plain_guard_on_agent_capable_route_would_refuse_the_agent | closed |
| T-76-SC | Tampering | npm/pip installs | low | accept | No new dependencies were installed in any of the 15 plans; see Accepted Risks | closed |

*Status: open · closed · open — below high threshold (non-blocking)*
*Severity: critical > high > medium > low — only open threats at or above workflow.security_block_on count toward threats_open*
*Disposition: mitigate (implementation required) · accept (documented risk) · transfer (third-party)*

Register authored at plan time (all 15 PLAN files carry a `<threat_model>`). Re-audited 2026-10-18 after gap plans 76-13..76-15: T-76-39..T-76-49 added, each traced to its guard and a green test; full backend suite 3779 passed, 0 failed at 8d1280bbe.

Register authored at plan time (all 12 PLAN files carry a `<threat_model>`). Verified at ASVS level 1 (grep depth: each mitigation traced to its guard module or a green test). Every cited test passed on 2026-10-15: the phase test set (132 backend tests), `catalogueAccess.test.ts` (26), and the full backend suite (3721 passed, 0 failed).

**Pre-existing finding, not introduced by this phase (76-05):** `GET /api/support/presence` returns online status for any requested usernames with no tenant scoping (cross-tenant presence lookup). It is catalogue_exempt as self-service; a tenant filter is still needed. Not a phase 76 threat; tracked here so it is not lost.

**Observations from the gap plans, not introduced by this phase (left for WR-02 / ACC-F2):**
- Checked 2026-10-18 (code review): no supported path gives a person the role string `agent` — `rbac_defaults.builtin_role_keys()` excludes it and user create/update, SAML and LDAP mapping validate against that set; SSO defaults to `analyst`. Only a direct database write could, so T-76-40 / AR-76-03 stays an accepted low risk.
- Code review CR-01 (2026-10-18): `GET /api/tenants/me` (route_aliases.py:204) returns the whole tenant document, including `registrationKey` (accepted as `X-Tenant-Key` by agent_auth.py:104) and `emailConfig`, to every signed-in role. Pre-existing since 2026-07-01, live in production; it undercuts T-76-44. Open, pending the user's decision.
- `POST /api/agents/{agent_id}/raise-ticket` has no permission check for people beyond tenant pinning (recorded honestly in the agentCapableRoutes ledger reason).

---

## Accepted Risks Log

| Risk ID | Threat Ref | Rationale | Accepted By | Date |
|---------|------------|-----------|-------------|------|
| AR-76-01 | T-76-10 | The sidebar hides views client-side only; that is cosmetic by design. Every enforced catalogue is refused by the backend guard, and the parity gate keeps the two in step | Plan 76-03 threat model (planner) | 2026-10-13 |
| AR-76-02 | T-76-SC | Supply-chain risk of npm/pip installs. Low severity; no plan in this phase installed or upgraded a dependency | Plans 76-01..76-15 threat models (planner) | 2026-10-13 |
| AR-76-03 | T-76-40 | The agent-tolerant guard trusts the auth layer's agent identity (role claim exactly `agent`, issued through get_current_user_or_agent with path binding and Pending admission). A person holding that role string is a pre-existing auth-layer property shared by every agent-capable route; fixing it belongs with WR-02 | Plan 76-13 threat model (planner) | 2026-10-16 |

*Accepted risks do not resurface in future audit runs.*

---

## Security Audit Trail

| Audit Date | Threats Total | Closed | Open | Run By |
|------------|---------------|--------|------|--------|
| 2026-10-15 | 39 | 39 | 0 | /gsd-secure-phase 76 (orchestrator, ASVS L1 short-circuit: register authored at plan time, 0 open) |
| 2026-10-18 | 50 | 50 | 0 | /gsd-secure-phase 76 after gap plans 76-13..76-15 (orchestrator, ASVS L1 short-circuit: register authored at plan time, 0 open) |

---

## Sign-Off

- [x] All threats have a disposition (mitigate / accept / transfer)
- [x] Accepted risks documented in Accepted Risks Log
- [x] `threats_open: 0` confirmed
- [x] `status: verified` set in frontmatter

**Approval:** verified 2026-10-15; re-verified 2026-10-18 after gap plans 76-13..76-15 (50 threats, 50 closed, 0 open)

## Security Audit 2026-10-18

| Metric | Count |
|---|---|
| Threats found | 50 |
| Closed | 50 |
| Open | 0 |

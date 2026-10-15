---
phase: 76-catalogue-manifest-backend-route-enforcement
reviewed: 2026-10-15T00:00:00Z
depth: standard
files_reviewed: 90
files_reviewed_list:
  - App.tsx
  - backend/agent_approval_endpoints.py
  - backend/agent_chat_endpoints.py
  - backend/agent_core_endpoints.py
  - backend/agent_download_endpoints.py
  - backend/agent_location_history_endpoints.py
  - backend/agent_metrics_endpoints.py
  - backend/agent_registry_endpoints.py
  - backend/agent_security_endpoints.py
  - backend/agent_tasks_endpoints.py
  - backend/agent_telemetry_endpoints.py
  - backend/agent_uninstall_endpoints.py
  - backend/agentic_tasks_endpoints.py
  - backend/ai_endpoints.py
  - backend/alert_endpoints.py
  - backend/api_key_endpoints.py
  - backend/asset_endpoints.py
  - backend/asset_finance_fields.py
  - backend/billing_endpoints.py
  - backend/bundle_endpoints.py
  - backend/capability_endpoints.py
  - backend/catalogue_guards.py
  - backend/catalogue_mounts.py
  - backend/catalogue_mounts_agents.py
  - backend/catalogue_mounts_assets.py
  - backend/catalogue_mounts_billing_identity.py
  - backend/catalogue_mounts_devices.py
  - backend/catalogue_mounts_secops.py
  - backend/catalogue_mounts_secposture.py
  - backend/catalogue_mounts_settings_ops.py
  - backend/compliance_evidence_endpoints.py
  - backend/compliance_scans_endpoints.py
  - backend/compliance_status_endpoints.py
  - backend/deception_endpoints.py
  - backend/edr_telemetry_endpoints.py
  - backend/final_endpoints.py
  - backend/future_ops_endpoints.py
  - backend/itam_label_endpoints.py
  - backend/itam_lifecycle_endpoints.py
  - backend/ldap_endpoints.py
  - backend/llm_proxy.py
  - backend/payment_billing_endpoints.py
  - backend/payment_gateway_endpoints.py
  - backend/platform_endpoints.py
  - backend/remote_endpoints.py
  - backend/reporting_endpoints.py
  - backend/response_endpoints.py
  - backend/route_aliases.py
  - backend/router_registry.py
  - backend/security_cases_endpoints.py
  - backend/security_keys_endpoints.py
  - backend/security_ops_endpoints.py
  - backend/security_scans_endpoints.py
  - backend/software_endpoints.py
  - backend/sso_endpoints.py
  - backend/support_endpoints.py
  - backend/system_endpoints.py
  - backend/tenant_endpoints.py
  - backend/tenant_enrollment_endpoints.py
  - backend/tests/_catalogue_parity.py
  - backend/tests/_route_walk.py
  - backend/tests/test_agent_location_history_endpoints.py
  - backend/tests/test_asset_finance_fields.py
  - backend/tests/test_bundles_and_reports.py
  - backend/tests/test_catalogue_guards.py
  - backend/tests/test_catalogue_manifest.py
  - backend/tests/test_catalogue_route_parity.py
  - backend/tests/test_catalogue_slice_agents.py
  - backend/tests/test_catalogue_slice_agents_dataplane.py
  - backend/tests/test_catalogue_slice_assets.py
  - backend/tests/test_catalogue_slice_billing_identity.py
  - backend/tests/test_catalogue_slice_devices.py
  - backend/tests/test_catalogue_slice_secops.py
  - backend/tests/test_catalogue_slice_secposture.py
  - backend/tests/test_catalogue_slice_settings_ops.py
  - backend/tests/test_core_endpoints.py
  - backend/tests/test_itam_asset_request_endpoints.py
  - backend/tests/test_route_auth_baseline.py
  - backend/tests/test_session_revocation.py
  - backend/threat_endpoints.py
  - backend/tickets_workflow_endpoints.py
  - backend/update_endpoints.py
  - backend/user_endpoints.py
  - backend/webhook_endpoints.py
  - components/Sidebar.tsx
  - components/sidebarPresentation.tsx
  - shared/catalogue-access.json
  - shared/catalogue-gaps.json
  - src/__tests__/catalogueAccess.test.ts
  - utils/catalogueAccess.ts
findings:
  critical: 0
  warning: 6
  info: 4
  total: 10
status: issues_found
---

# Phase 76: Code Review Report

**Reviewed:** 2026-10-15
**Depth:** standard
**Files Reviewed:** 90
**Status:** issues_found

## Summary

The guard, mount map, manifest and parity gate hold up well under adversarial checking. I verified the following by walking the real mounted app (1616 routes) in a hermetic child interpreter, and by running `test_catalogue_guards`, `test_catalogue_manifest`, `test_catalogue_route_parity`, all `test_catalogue_slice_*` and `test_route_auth_baseline` (121 passed):

- No route that an agent, an external system, SSO/LDAP sign-in, the Stripe webhook, the Jira/Zoho inbound hooks, the deception trigger or `/api/system/health` calls carries a catalogue guard. Every mount-level guard sits on a route whose own authentication is `get_current_user` or `get_current_user_or_api_key`. No route that was public or agent-keyed gained a user-auth requirement.
- Guards are additive. The only auth lines removed from the endpoint files are unrelated spec C1-C6 work (finops pricing moved to `require_super_admin`, tenant `is_super_admin` check replaced by `has_platform_permission`). No existing permission dependency was replaced by a catalogue guard.
- The guard's auth callable always matches the route's own (session guards on session routes, API-key guards on API-key routes). No API-key route sits behind a session-only guard.
- No WebSocket route received a guard (the guard takes a `Request` parameter and would fail on a WebSocket).
- Every `MOUNTS` key resolves to a loaded router. No stale or typo'd keys.

The findings below are therefore about residual holes and design inconsistencies, not about a broken ingest path. The main residual risk is that the 15 `agent_capable` routes (user or agent token) are outside the parity gate by design (D-02) and therefore give an ordinary signed-in user, with no catalogue permission, access to two data-bearing routes in enforced catalogues.

## Warnings

### WR-01: Agent-capable routes in enforced catalogues give any signed-in user a catalogue-free path

**File:** `backend/software_endpoints.py:113`, `backend/response_endpoints.py:192`
**Issue:** `GET /api/software/download/{filename}` (catalogue `softwareUpdates`) and `GET /api/response/tasks/{agent_id}` (catalogue `edr`) use `get_current_user_or_agent` and carry no guard. D-02 excludes them so agents keep working, and the `agentAuthExcludedRoutes: 15` ratchet counts them, but the exclusion also applies to human callers.
- `download_software` performs no permission check at all. Any tenant user, including a `viewer` who has neither `view:software_updates` nor `manage:patches`, can download any installer in the global `uploads/repo` directory. That directory is shared across tenants. This is the same data that the guarded sibling `GET /api/software/repository` hides from that role.
- `get_pending_tasks` checks only that the agent is in the caller's tenant. Any signed-in user can read an agent's queued response tasks (isolate, kill, quarantine payloads). Its sibling write routes do require `remediate:agents` for non-agent callers.

The parity test cannot see this, because `_in_scope` returns `None` for any record whose auth class is not `user`.
**Fix:** Add an agent-tolerant guard variant that skips only the agent identity and applies the catalogue check to everyone else:
```python
def catalogue_guard(..., auth=get_current_user, allow_agent=False): ...
    async def _require_catalogue(request: Request, user = Depends(auth)):
        if allow_agent and getattr(user, "role", "") == "agent":
            return user
        await check_catalogue_access(user, request.method, read_t, write_t)
        return user
```
Mount it with `auth=get_current_user_or_agent, allow_agent=True` on these two routes, and have the walker count it as a tag so the parity gate covers `agent_capable` routes too.

### WR-02: Webhook guard bypass is keyed on a role string any custom role can carry

**File:** `backend/catalogue_mounts_settings_ops.py:63-75`
**Issue:** `_webhooks_guard_with_integration_keys` returns immediately when `user.role == "api-integration"`, skipping `check_catalogue_access` entirely. That role string is produced by the legacy tenant key path (`api_key_auth.py:282`), but the TokenData it builds has the default `auth_source="session"`, so nothing distinguishes a key from a user. `role_endpoints.py:69-73` only blocks custom role names that normalise to a built-in key, so a tenant admin can create a custom role literally named `api-integration` and assign it. That user then passes the catalogue guard, and the four route-level `role != "api-integration"` checks at `webhook_endpoints.py:123,155`, for list/create/delete/deliveries without holding `manage:settings`. The phase copied the bypass into the new guard rather than closing it. The impact is limited to the tenant's own webhooks, but it is a role-name-based authorization decision.
**Fix:** Mark the legacy key identity unambiguously and test that, not the role name:
```python
# api_key_auth.py
return TokenData(tenant_id=tenant_doc["id"], role="api-integration", username="api-key", auth_source="tenant_key")
# catalogue_mounts_settings_ops.py
if getattr(user, "auth_source", "") == "tenant_key":
    return user
```
Also reserve `api-integration` in the role-name validator.

### WR-03: ITAM guard read rule drops the `manage:assets` read compatibility that the handlers and the scope check keep

**File:** `backend/catalogue_mounts_assets.py:19-20,31-33`, `backend/catalogue_guards.py:63-68`
**Issue:** `_require_itam_viewer` (`itam_asset_endpoints.py:68-93`) accepts `view:itam` or `manage:assets` for reads ("every manage:assets holder can also read"). The new ITAM guard accepts only `view:itam` and `manage:itam` for safe methods (`ITAM_READ = ("view:itam",)` plus the twin). The guard adds a compatibility rule for API-key scopes (write scopes also authorise reads), but not for roles. A tenant custom role that holds `manage:assets` but not `view:itam` or `manage:itam` could read the ITAM console before and now gets 403. The built-in roles are unaffected, because `tenant_admin` and `itam_admin` also hold `view:itam`. Roles and scopes are treated asymmetrically.
**Fix:** Either add the write permissions to the role-side read check for the ITAM catalogue (make `read=("view:itam", "manage:assets")` in `ITAM_READ`, which the manifest then mirrors), or drop the scope-side widening and state in the manifest that ITAM reads need `view:itam` or `manage:itam`.

### WR-04: Secrets catalogue is internally incoherent (read needs `manage:settings`, write accepts the read permission)

**File:** `backend/catalogue_mounts_settings_ops.py:39-41`, `shared/catalogue-access.json` (`secretsManagement`)
**Issue:** `SECRETS_GUARD` reads need `manage:settings`, writes accept `manage:secrets` or `view:secrets`. A `view:secrets` holder, for example `platform_support`, is refused `GET /api/secrets/list`, `/stats`, `/audit-log`, `/rotation/check` and `GET /api/secrets/{name}`. Each of these routes' own check is `view:secrets`, so the role the route says may read is now refused by the guard. The same role passes the guard on `POST /api/secrets/scan`. The write list containing a `view:` string means the guard never restricts mutating requests for holders of the read permission. The `write` list was evidently mined from the route-level strings rather than designed.
**Fix:** Make the read rule `read=("manage:settings", "view:secrets")` (or accept the lockout deliberately and remove `view:secrets` from `write`), and make `write=("manage:secrets",)`. Update the manifest and the slice test together.

### WR-05: `catalogue_exempt` on tenant GET routes lets any tenant role read the hardware allowlist, install-key list, SMTP config and license

**File:** `backend/tenant_enrollment_endpoints.py:67,121`, `backend/tenant_endpoints.py:489,622,711`
**Issue:** `TENANT_OWN_SCOPE` is documented as "self-service ... pinned by `_assert_tenant_access` / `_assert_tenant_read`". Those helpers pin the tenant, not the role. A `viewer` or `itam_viewer` of the tenant can therefore read the enrolled-machine hardware allowlist (serials, SMBIOS UUIDs, MACs), the install-key list with limits and notes, the SMTP host/user configuration and the license/seat summary. The catalogue guard (`manage:tenants`/`manage:settings`) would have refused them. The exemption reason is true for tenant isolation but does not justify skipping role gating. The `maxExemptRoutes: 34` ratchet cannot detect this, because the reasons are only length-checked.
**Fix:** Give these reads a tag, for example a `TENANT_SETTINGS_READ` guard with `read=("manage:settings", "view:agents")`, and keep `TENANT_OWN_SCOPE` only for branding and the license summary the app shell needs.

### WR-06: `test_tracer_mdm_enforced_on_real_app` and several slice probes assert only `!= 403` for the allowed case

**File:** `backend/tests/test_catalogue_guards.py:24`, `backend/tests/test_catalogue_slice_agents_dataplane.py` (`test_dataplane_real_app_enforced`)
**Issue:** The "role holding the permission is not refused" assertion passes for any non-403 status, including a 401, 404, 422 or 500 caused by a broken route or an unreachable database (the probe points Mongo at an unroutable port). A regression that made the guard raise 500 or 401 for permitted roles would not fail these tests. The denied side is meaningful, since 403 is what the guard raises. Separately, `test_dataplane_agent_auth_unchanged` pins agent auth by counting source-text occurrences of `Depends(verify_agent_key)`, which fails on unrelated refactors and does not detect a guard added by other means.
**Fix:** In the probe, stub the route handler or assert a positive status class. For example, return 200 from a stub route, or accept only `status not in (401, 403, 500)` and add a case where the allowed role reaches a handler that returns 200. Replace the source-count test with the walker-based check, which `test_dataplane_agent_routes_untouched` already provides.

## Info

### IN-01: Write lists carry read-grade `view:` strings, so the guard is a no-op for writes in those catalogues

**File:** `shared/catalogue-access.json` (`threatHunting`, `threatIntelligence`, `remoteAccess`, `profile`, `iacContainer` (`view:dashboard`), `notifications` (`view:dashboard`), `cloudAccounts`, `zeroTrustQuantum`, `correlations`, `vulnerabilityManagement`, `softwareDeployment`, `dataWarehouse`)
**Issue:** `catalogue_guards.py` states that non-safe methods "accept exactly the declared write permissions". For these catalogues the declared write permission is a `view:` string, in two cases `view:dashboard`, which every signed-in role holds. I checked every non-GET guarded route in these catalogues: each carries its own permission check, so there is no unprotected write today. But the catalogue guard adds no protection to those writes, and a future route that relies on the guard alone would be open. Related: the guard role-checks at request time for every route, so each guarded request also repeats the permission lookup the route's own dependency performs.
**Fix:** Either tighten the manifest `write` lists to `manage:` strings, or add a manifest test that rejects a `view:dashboard` write entry.

### IN-02: Unused imports in new modules

**File:** `backend/catalogue_guards.py:18`, `backend/catalogue_mounts_assets.py:14`
**Issue:** `Dict` is imported and unused in `catalogue_guards.py`. `get_current_user` is imported and unused in `catalogue_mounts_assets.py`. Ruff F401 flags both.
**Fix:** Remove the unused names.

### IN-03: Duplicate guard definitions drift silently

**File:** `backend/catalogue_mounts_agents.py:36` and `backend/catalogue_mounts_settings_ops.py:94` (`AGENTS_GUARD`); `backend/route_aliases.py:19` (`UEBA_GUARD`) versus the `ueba` guard in `catalogue_mounts_secops.py`
**Issue:** The same catalogue guard is constructed in two modules as two separate dependency objects. They are equal today only because the parity test compares metadata by value. A change to the manifest needs edits in every copy. `route_aliases.py` also defines a private `UEBA_GUARD` rather than importing one.
**Fix:** Keep one definition per catalogue, imported everywhere (settings_ops can import `AGENTS_GUARD` from `catalogue_mounts_agents`).

### IN-04: `viewPermission(view) as Permission` can pass `undefined` into `hasPermission`

**File:** `App.tsx` (`handleSetCurrentView`, the line `const requiredPermission = viewPermission(view) as Permission;`)
**Issue:** The cast hides the `undefined` that `viewPermission` returns for a view with no manifest entry. `catalogueAccess.test.ts` pins that every `AppView` has an entry, and `hasPermission(undefined)` denies for non-super-admins (so it fails closed), but it returns true for a super-admin and the cast defeats the type check on future views. The comment defers this to Phase 77.
**Fix:** Handle the `undefined` explicitly (`if (!requiredPermission) { warn; return; }`) instead of casting.

---

_Reviewed: 2026-10-15_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_

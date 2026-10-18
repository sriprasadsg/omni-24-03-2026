---
phase: 76-catalogue-manifest-backend-route-enforcement
reviewed: 2026-10-18T00:00:00Z
depth: standard
files_reviewed: 17
files_reviewed_list:
  - backend/agent_chat_endpoints.py
  - backend/catalogue_guards.py
  - backend/catalogue_mounts_billing_identity.py
  - backend/response_endpoints.py
  - backend/software_endpoints.py
  - backend/tenant_endpoints.py
  - backend/tenant_enrollment_endpoints.py
  - backend/tests/_catalogue_parity.py
  - backend/tests/_route_walk.py
  - backend/tests/test_catalogue_guard_variants.py
  - backend/tests/test_catalogue_route_parity.py
  - backend/tests/test_catalogue_slice_agents.py
  - backend/tests/test_catalogue_slice_billing_identity.py
  - backend/tests/test_catalogue_slice_devices.py
  - backend/tests/test_catalogue_slice_secops.py
  - shared/catalogue-access.json
  - shared/catalogue-gaps.json
findings:
  critical: 1
  warning: 2
  info: 3
  total: 6
status: issues_found
---

# Phase 76: Code Review Report (gap plans 76-13, 76-14, 76-15)

**Reviewed:** 2026-10-18
**Depth:** standard
**Files Reviewed:** 17 (committed HEAD content, incremental against `24fc1c59e`)
**Status:** issues_found

## Summary

This is an incremental review of the three gap-closure plans. It overwrites the previous report. Prior findings the gap plans did not touch (WR-02, WR-03, WR-04, WR-06, IN-01..IN-04 of the old report) are not repeated and keep their old disposition.

I ran the venv test suites that cover the changed code: `test_catalogue_guard_variants`, `test_catalogue_route_parity` (82 passed) and the four `test_catalogue_slice_*` files in scope (22 passed).

**Prior WR-01 (agent-capable reads give any signed-in user a catalogue-free path): resolved.**
- `GET /api/software/download/{filename}`, `GET /api/response/tasks/{agent_id}` and `GET /api/agent-chat/sessions` now carry `agent_tolerant(...)` guards.
- The bypass keys on the exact token role `agent`, which the auth layer produces only for registered agent tokens. User roles can only be built-in keys (`user_endpoints._VALID_ROLE_KEYS`, SAML and LDAP mapping), so no person can carry the role string `agent`.
- Every other caller, including `viewer`, `itam_viewer` and a role spelled `Agent`, gets the full catalogue check. The new real-app probes show 403 for those roles and 404 or 200 for the agent and permitted roles.
- The parity gate now puts agent-capable reads in an enforced group in scope. It also rejects any plain, agent-refusing guard on an agent-capable route, so the hole cannot reopen silently.

**Prior WR-05 (tenant GET routes exempt from role gating): partially resolved.**
- The five named routes (`email/config`, `email/preferences`, `license`, `allowlist`, `enrollment-keys`) are now role-gated. Tenant roles need `manage:settings`. Platform staff keep their read through `platform_read=("view:tenants",)`, which is correct for both platform roles, since both hold `view:tenants`.
- The same data is still readable by every role through another exempt route, `GET /api/tenants/me` (CR-01). WR-05's impact is therefore not removed, and the new ratchet rule cannot catch it (WR-01 below).

## Critical Issues

### CR-01: `GET /api/tenants/me` returns the whole tenant document to every signed-in role, bypassing the WR-05 gating and leaking the tenant registration key

**File:** `backend/route_aliases.py:200-211` (route and exemption), `shared/catalogue-gaps.json` (`exemptRoutes`, `GET /api/tenants/me`). The file is outside the listed scope. It is the exempt route whose reason 76-15 left standing and the ledger now freezes.
**Issue:** `get_my_tenant` is `catalogue_exempt("self-service: caller's own tenant record")`, authenticated by `get_current_user` only. It returns `tenants.find_one({"id": tenant_id}, {"_id": 0})`, which is every field of the tenant document. Per `create_tenant` and `agent_download_endpoints.py`, that document holds:
- `registrationKey`. This is the tenant enrollment credential: `agent_auth.py:104` and `tunnel_endpoints.py:262` accept it as `X-Tenant-Key`, and it ships in installers. It lets a caller register agents into the tenant.
- `emailConfig`. This includes `smtpHost`, `smtpUser`, `smtpPasswordEncrypted` and, on legacy tenants, a plaintext `smtpPassword` (the code in `get_email_config` still strips a legacy field, so it can exist).
- `license` and `maxAgents`, plus notification preferences.

A `viewer` or `itam_viewer` of the tenant can therefore read exactly the SMTP and license data that 76-15 gated on `email/config` and `license`, and also the enrollment key. Per `catalogue_exempt`, the exemption means no role check applies. The 76-15 self-service rule and the `test_tenant_exempt_routes_reachable_by_every_role` test do not see it. The rule only matches paths with `{tenant_id}` or `{user_id}`, and the test only walks `tenant_endpoints`, `tenant_enrollment_endpoints` and `bundle_endpoints` modules. `/api/tenants/me` lives in `route_aliases`.
**Fix:** Project the response to display fields and keep the route exempt, since the app shell needs it for every role:
```python
SAFE_TENANT_FIELDS = {"_id": 0, "id": 1, "name": 1, "subscriptionTier": 1, "branding": 1,
                      "enabledFeatures": 1, "createdAt": 1}
tenant = await mongodb.db.tenants.find_one({"id": tenant_id}, SAFE_TENANT_FIELDS)
```
Check the UI callers first for any field they read, such as the seat count. If one is needed, expose only that field. Gate the sensitive fields behind `TENANT_CONTROLS_READ_GUARD` routes. Add a regression test that calls `GET /api/tenants/me` as `viewer` against a tenant document seeded with `registrationKey`, `emailConfig` and `license`, and asserts none of those keys is in the body. Also assess whether the registration key has already been exposed and needs rotation.

## Warnings

### WR-01: The new self-service exemption rule (PROH-76-08) is lexical and does not catch the case it was written for

**File:** `backend/tests/_catalogue_parity.py:244-246,346-349`
**Issue:** The rule fires only when the reason starts with `self-service` and the path contains one of four literal placeholders (`{tenant_id}`, `{tenantId}`, `{user_id}`, `{userId}`). Rewording the reason, or using another placeholder (`{org_id}`, `{id}`, `{username}`) or no placeholder at all, passes. `GET /api/tenants/me` (CR-01) is a counter-example already in the repository: a self-service route with no placeholder that returns every tenant field. The exempt-route ledger only freezes the reason text, so a human still has to judge each reason. The ratchet therefore cannot detect a regression of the WR-05 class, which is what the plan claimed it would.
**Fix:** Add a behavioural check instead of, or alongside, the lexical one. For every exempt GET, probe it on the real app as the lowest tenant role against a document seeded with sentinel secrets (`registrationKey`, `emailConfig`, `license`). Fail if any sentinel appears in the body. Keep the path rule as a cheap pre-check, but stop calling it the safeguard.

### WR-02: `agent_tolerant()` silently drops `platform_read`

**File:** `backend/catalogue_guards.py:162-173`
**Issue:** `agent_tolerant` rebuilds the guard from `meta["catalogue"]`, `meta["read"]` and `meta["write"]` only. If the wrapped guard was built with `platform_read`, the tolerant copy forgets it. The wrapped route then refuses platform staff that the original guard would have admitted, with no error at import time. No guard combines the two today, so this is latent. The two variants were introduced in the same plan and the function is documented as "the same catalogue guard".
**Fix:** Forward the field, or refuse the combination explicitly:
```python
return catalogue_guard(
    meta["catalogue"], read=tuple(meta["read"]), write=tuple(meta["write"]),
    auth=get_current_user_or_agent, allow_agent=True,
    platform_read=tuple(meta.get("platform_read", ())),
)
```
Add a unit test for the combination.

## Info

### IN-01: New real-app probes assert only `not in (401, 403)` for the allowed case (inherits old WR-06)

**File:** `backend/tests/test_catalogue_guard_variants.py:285-300`, `backend/tests/test_catalogue_slice_billing_identity.py` (`_expect_through`)
**Issue:** The probe app has an unreachable Mongo, so the allowed side of `test_task_poll_and_chat_list_on_the_real_app` and `test_tenant_settings_reads_are_role_gated` passes on a 500. The denied side asserts exactly 403, so those assertions still have teeth. The router-level tests in the same file (`response_app`, `software_app`) do prove the 200 path for the agent and permitted roles.
**Fix:** Where a positive status is reachable (the download probe uses 404 for a missing file), assert it. For the DB-backed routes, stub the handler's DB dependency in the probe or accept only the expected handler status.

### IN-02: `_listed` has an unused parameter, and `TENANT_CONTROLS_READ_GUARD` restates the `settings` read/write strings

**File:** `backend/tests/_catalogue_parity.py:353` (`key` is never used), `backend/catalogue_mounts_billing_identity.py:66-68`
**Issue:** `_listed(entries, key)` ignores `key`. `TENANT_CONTROLS_READ_GUARD` redeclares `catalogue_guard("settings", read=_SETTINGS, write=_SETTINGS, ...)` next to `SETTINGS_GUARD` in `catalogue_mounts_settings_ops`. Drift is caught by the parity test only for routes that test sees.
**Fix:** Drop the parameter. Build the tolerant and platform variants from `SETTINGS_GUARD`'s tag, or add a one-line assertion that the two tags agree.

### IN-03: The `agentCapableRoutes` and `exemptRoutes` reasons are prose that nothing verifies

**File:** `shared/catalogue-gaps.json` (`agentCapableRoutes`, `exemptRoutes`)
**Issue:** The gate checks that each reason exists, is long enough and matches the app. It cannot check that the claim is true. For example, `POST /api/agents/{agent_id}/raise-ticket` is justified by "people are pinned to their tenant", so any tenant role, a viewer included, can raise a ticket for any agent in the tenant. Those reasons are the review record, so each should be verified when the list is next touched.
**Fix:** Add an owner and a verified-on date to each entry, or back the claim with a probe like the one proposed in WR-01.

---

_Reviewed: 2026-10-18_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_

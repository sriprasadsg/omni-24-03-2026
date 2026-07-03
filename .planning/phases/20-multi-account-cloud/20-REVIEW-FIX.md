---
phase: 20-multi-account-cloud
fixed_at: 2026-07-03T22:54:50Z
review_path: .planning/phases/20-multi-account-cloud/20-REVIEW.md
iteration: 1
findings_in_scope: 8
fixed: 8
skipped: 0
status: all_fixed
---

# Phase 20: Code Review Fix Report

**Fixed at:** 2026-07-03T22:54:50Z
**Source review:** .planning/phases/20-multi-account-cloud/20-REVIEW.md
**Iteration:** 1

**Summary:**
- Findings in scope: 8 (CR-01, CR-02, WR-01 through WR-06 — fix_scope: critical_warning)
- Fixed: 8
- Skipped: 0

Info findings (IN-01, IN-02, IN-03) were out of scope for this pass per `fix_scope: critical_warning`.

## Fixed Issues

### CR-01: Cloud credentials silently stored in plaintext when `CLOUD_CREDENTIALS_KEY` is unset

**Files modified:** `backend/cloud_accounts_service.py`, `backend/app_startup.py`
**Commit:** fc5005e
**Applied fix:** Mirrored the established fail-closed pattern already used by `backend/encryption_service.py` (`PAYMENT_ENCRYPTION_KEY`) and `backend/saas_integration_service.py` (`ENCRYPTION_KEY`): module-load now raises `RuntimeError` if `CLOUD_CREDENTIALS_KEY` is unset and `APP_ENV=production` (matching the `APP_ENV` check already used in `app_startup.py::_check_placeholder_secrets`); otherwise it logs a warning and falls back to a per-process ephemeral Fernet key so credentials are always encrypted, never silently stored in plaintext. Removed the now-dead `if _FERNET` / `if _FERNET and creds_raw` conditionals in `register_account`, `discover_org_accounts`, and `_encrypt` since `_FERNET` is guaranteed to be a real cipher. Also added `CLOUD_CREDENTIALS_KEY` to `app_startup.py::_validate_startup_config`'s issue list so it is surfaced at boot the same way `JWT_SECRET_KEY`/`SUPER_ADMIN_PASSWORD` are.
**Verification:** Confirmed the module imports cleanly and logs the expected warning with no `CLOUD_CREDENTIALS_KEY`/`APP_ENV` set (dev default); confirmed `APP_ENV=production` without the key raises `RuntimeError` as expected; re-ran `backend/tests/test_cloud_accounts.py` (all 8 tests pass — the suite does not set `CLOUD_CREDENTIALS_KEY`/`APP_ENV`, so the dev/ephemeral-key path is exercised and unaffected).

### CR-02: Cross-tenant unauthorized write to `scan_status`/`last_scan` (IDOR)

**Files modified:** `backend/cloud_accounts_service.py`
**Commit:** 6793be5
**Applied fix:** `scan_account()` now looks up the account with a tenant-scoped `find_one({"id": account_id, "tenantId": tenant_id})` *before* any write, returns `{"error": "Cloud account not found", "ran": 0}` if no match, and scopes all three `update_one` calls (`scanning` → `idle`/`last_scan`, or `failed` on exception) by `{"id": account_id, "tenantId": tenant_id}` instead of `{"id": account_id}` alone. A user from another tenant can no longer flip another tenant's account into `scanning`/`idle`/`failed` state or stomp its `last_scan` timestamp.
**Verification:** Re-ran `backend/venv/bin/python -m pytest backend/tests/test_cloud_accounts.py -v` — all 8 tests pass with the added `tenantId` scoping.

### WR-01: Frontend never checks HTTP status before treating a response as success

**Files modified:** `components/CloudAccountsDashboard.tsx`
**Commit:** a3d093d
**Applied fix:** `fetchData()`, `register()`, `scan()`, and `loadResults()` now check `response.ok` before parsing/toasting success; non-2xx responses throw (using the FastAPI `detail` field where available) so the existing `catch` blocks surface an error toast instead of a false "success" for e.g. a 400 on missing `provider`/`account_id`.

### WR-02: Scan failures are swallowed into a 200 response, then reported as success by the UI

**Files modified:** `components/CloudAccountsDashboard.tsx`
**Commit:** deb6f93
**Applied fix:** `scan()` now inspects `r.error` on the (2xx) response body and shows an error toast (`Scan failed: {error}`) instead of unconditionally showing the success toast — applied the frontend-side variant of the two options the review offered, since it does not require changing the endpoint's status-code semantics (that remains IN-03, out of scope for this pass).

### WR-03: `provider`/`environment` are not validated against their documented enums

**Files modified:** `backend/cloud_account_endpoints.py`
**Commit:** 4eb89ca
**Applied fix:** Added `_VALID_PROVIDERS = {"aws", "azure", "gcp"}` and `_VALID_ENVS = {"prod", "staging", "dev"}` module-level sets; `register_account()` now raises `HTTPException(400)` if `provider` or `environment` (default `"dev"`) is not in the respective allowed set, closing the path where an out-of-enum `environment` value became permanently invisible in the dashboard.

### WR-04: No uniqueness/dedup check on `account_id`

**Files modified:** `backend/cloud_accounts_service.py`
**Commit:** d00db92
**Applied fix:** Both `register_account()` and `discover_org_accounts()` now look up any existing document keyed on `{tenantId, provider, account_id}` first, preserve its `id`/`created_at`/`scan_status`/`last_scan` on re-registration, and `update_one(key, {"$set": doc}, upsert=True)` instead of unconditionally `insert_one`-ing. Repeated registration or repeated `discover-org` calls no longer create duplicate account rows with the same `account_id`.

### WR-05: Stale per-account results cache after a new scan

**Files modified:** `components/CloudAccountsDashboard.tsx`
**Commit:** 9f37460
**Applied fix:** `scan()` now clears the cached `results[id]` entry (`setResults(s => { const {[id]: _omit, ...rest} = s; return rest; }); `) right after a scan completes, so `loadResults()`'s early-return-if-cached guard no longer serves a stale pre-scan snapshot.

### WR-06: Test suite asserts only HTTP status codes — would not catch CR-01 or CR-02

**Files modified:** `backend/tests/test_cloud_accounts.py`
**Commit:** 9dee114
**Applied fix:**
1. `test_register_aws_account` now asserts `"credentials_ref" not in r.json()["account"]`.
2. `test_scan_sets_status` now mocks `find_one` to return a real tenant-tagged account and patches `cloud_checks_service.cloud_checks_service.run_checks` (avoiding a real DB call), then asserts the exact `scan_status` transition sequence (`["scanning", "idle"]`) and that every `update_one` call is scoped by `tenantId` — this would now catch a CR-02-style regression.
3. `test_tenant_isolation` now configures the mocked `find()` to return tenant-tagged documents and filters by the query's `tenantId`, then asserts the query passed to `find()` includes the calling user's `tenantId`, that only the matching tenant's account is returned, and that `credentials_ref` is excluded — this would now catch a tenant-scoping regression in `list_accounts`.

**Verification:** All 8 tests (including the 3 strengthened ones) pass together via `backend/venv/bin/python -m pytest backend/tests/test_cloud_accounts.py -v`.

## Skipped Issues

None — all 8 in-scope findings were fixed.

---

_Fixed: 2026-07-03T22:54:50Z_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 1_

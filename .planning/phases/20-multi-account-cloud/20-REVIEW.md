---
phase: 20-multi-account-cloud
reviewed: 2026-07-04T00:00:00Z
depth: standard
files_reviewed: 5
files_reviewed_list:
  - backend/cloud_accounts_service.py
  - backend/cloud_account_endpoints.py
  - backend/tests/test_cloud_accounts.py
  - backend/router_registry.py
  - components/CloudAccountsDashboard.tsx
findings:
  critical: 2
  warning: 6
  info: 3
  total: 11
status: issues_found
---

# Phase 20: Code Review Report

**Reviewed:** 2026-07-04T00:00:00Z
**Depth:** standard
**Files Reviewed:** 5
**Status:** issues_found

## Summary

Reviewed the multi-account cloud scanning feature: `cloud_accounts_service.py` (registration/scan/discovery logic), `cloud_account_endpoints.py` (the FastAPI router — note: the actual filename is singular `cloud_account_endpoints.py`, not the plural `cloud_accounts_endpoints.py` listed in the plan's `files_modified`; `router_registry.py:226` and the test's `import cloud_account_endpoints as m` are both wired correctly under the singular name, so this is a plan-vs-actual naming discrepancy only, not a code defect), `test_cloud_accounts.py`, `router_registry.py`, and `CloudAccountsDashboard.tsx`.

Two Critical issues were found, both of which represent a real gap between what the plan's must-haves promise and what the code actually enforces:

1. **Silent plaintext-credential fallback** when `CLOUD_CREDENTIALS_KEY` is unset — confirmed independently (see CR-01). This directly contradicts the plan's must-have "Credentials are stored encrypted (Fernet) in cloud_accounts collection" with no fail-closed behavior and no startup warning, unlike every other Fernet-backed service in this codebase (`encryption_service.py`, `saas_integration_service.py`), which both refuse to start in production or at minimum log a loud warning and use an ephemeral key.
2. **Cross-tenant unauthorized write (IDOR)** in `scan_account()` — the two bracketing `update_one` calls that flip `scan_status` are not scoped by `tenantId`, so any authenticated user of any tenant can mutate another tenant's cloud-account row by supplying its `account_id`.

The 8 tests in `test_cloud_accounts.py` all pass, but per-test assertions are shallow (status-code-only in most cases) and do not verify the specific behaviors their names in the plan's TDD order imply (credential encryption, credential exclusion from list responses, tenant isolation) — see WR-06. Neither of the two Critical bugs above would have been caught by this suite.

## Critical Issues

### CR-01: Cloud credentials silently stored in plaintext when `CLOUD_CREDENTIALS_KEY` is unset

**File:** `backend/cloud_accounts_service.py:9-10, 19, 77, 83-86`
**Issue:** `_FERNET` is only constructed if `CLOUD_CREDENTIALS_KEY` is set:
```python
_FERNET_KEY = os.environ.get("CLOUD_CREDENTIALS_KEY", "")
_FERNET = Fernet(_FERNET_KEY.encode()) if _FERNET_KEY else None
```
`_encrypt()` then silently returns the plaintext input unchanged when `_FERNET` is `None`:
```python
def _encrypt(plain: str) -> str:
    if not _FERNET or not plain:
        return plain
    return _FERNET.encrypt(plain.encode()).decode()
```
and both call sites (`register_account` line 19, `discover_org_accounts` line 77) gate encryption on the same falsy check, so `credentials_ref` — AWS ARNs, GCP service-account keys, Azure principals — is written to the `cloud_accounts` collection **unencrypted** whenever this one env var is missing. I independently verified:
- `CLOUD_CREDENTIALS_KEY` is referenced nowhere else in `backend/` (not in `app_startup.py::_validate_startup_config`, not in any required-env check).
- No warning of any kind is logged when this fallback path is taken — an operator has no signal that credential encryption is silently disabled.
- This is a genuine deviation from the codebase's own established pattern: both `backend/encryption_service.py` (`PAYMENT_ENCRYPTION_KEY`) and `backend/saas_integration_service.py` (`ENCRYPTION_KEY`) either **raise at startup in production** or, at minimum, **log a warning and use a per-process ephemeral key** so ciphertext is never silently degraded to plaintext.

This directly contradicts the phase's explicit must-have: *"Credentials are stored encrypted (Fernet) in cloud_accounts collection, credentials_ref field only."* In the current code, that guarantee holds only if an operator happens to set an otherwise-unenforced env var.

**Fix:**
```python
_FERNET_KEY = os.environ.get("CLOUD_CREDENTIALS_KEY", "")
if not _FERNET_KEY:
    if os.environ.get("APP_ENV", "development").lower() == "production":
        raise RuntimeError(
            "CLOUD_CREDENTIALS_KEY is not set. Refusing to start in production "
            "without a stable encryption key for cloud account credentials. "
            "Generate one with: python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
        )
    logger.warning(
        "CLOUD_CREDENTIALS_KEY not set — using ephemeral key (dev only). "
        "Cloud account credentials will not survive restart."
    )
    _FERNET_KEY = Fernet.generate_key().decode()
_FERNET = Fernet(_FERNET_KEY.encode())
```
Then drop the `if _FERNET` / `if _FERNET and creds_raw` conditionals in `register_account`, `discover_org_accounts`, and `_encrypt` — `_FERNET` is now always a real cipher, so the plaintext-passthrough branch can never be silently reached. Also add `CLOUD_CREDENTIALS_KEY` to `app_startup.py::_validate_startup_config`'s issue list so it is surfaced the same way `JWT_SECRET_KEY`/`SUPER_ADMIN_PASSWORD` are.

### CR-02: Cross-tenant unauthorized write to `scan_status`/`last_scan` (IDOR)

**File:** `backend/cloud_accounts_service.py:36-47`
**Issue:**
```python
async def scan_account(db, account_id: str, tenant_id: str) -> dict:
    from cloud_checks_service import cloud_checks_service
    await db._db.cloud_accounts.update_one({"id": account_id}, {"$set": {"scan_status": "scanning"}})
    try:
        account = await db._db.cloud_accounts.find_one({"id": account_id, "tenantId": tenant_id})
        provider = account.get("provider", "aws") if account else "aws"
        result = await cloud_checks_service.run_checks(account_id, provider, tenant_id)
        await db._db.cloud_accounts.update_one({"id": account_id}, {"$set": {"scan_status": "idle", "last_scan": _now()}})
        return result
    except Exception as e:
        await db._db.cloud_accounts.update_one({"id": account_id}, {"$set": {"scan_status": "failed"}})
        return {"error": str(e), "ran": 0}
```
All three `update_one` calls filter only by `{"id": account_id}` — none of them include `tenantId`. `cloud_checks_service.run_checks()` (the only call that reads/writes scan *results*) does correctly scope by `tenantId`, so scan results themselves aren't cross-tenant readable. But the account document's `scan_status`/`last_scan` fields are writable by *any authenticated user of any tenant*, for *any* `account_id`, regardless of which tenant owns it. `POST /api/cloud-accounts/{account_id}/scan` passes `account_id` straight from the URL path with no ownership check before the first write. A user in tenant B who learns or guesses a tenant A `account_id` (format `acct-{12 hex chars}`, but IDs can also leak via shared support channels, logs, referrers, etc.) can flip tenant A's account into `scanning`/`idle` state and stomp its `last_scan` timestamp — an authorization gap and a minor denial-of-service/data-integrity vector (dashboard for tenant A would show incorrect scan status/timestamps caused by an unrelated tenant).

**Fix:** Scope every write by `tenantId`, and look the account up (with tenant filter) before doing anything:
```python
async def scan_account(db, account_id: str, tenant_id: str) -> dict:
    from cloud_checks_service import cloud_checks_service
    account = await db._db.cloud_accounts.find_one({"id": account_id, "tenantId": tenant_id})
    if not account:
        return {"error": "Cloud account not found", "ran": 0}
    await db._db.cloud_accounts.update_one(
        {"id": account_id, "tenantId": tenant_id}, {"$set": {"scan_status": "scanning"}}
    )
    try:
        provider = account.get("provider", "aws")
        result = await cloud_checks_service.run_checks(account_id, provider, tenant_id)
        await db._db.cloud_accounts.update_one(
            {"id": account_id, "tenantId": tenant_id}, {"$set": {"scan_status": "idle", "last_scan": _now()}}
        )
        return result
    except Exception as e:
        await db._db.cloud_accounts.update_one(
            {"id": account_id, "tenantId": tenant_id}, {"$set": {"scan_status": "failed"}}
        )
        return {"error": str(e), "ran": 0}
```

## Warnings

### WR-01: Frontend never checks HTTP status before treating a response as success

**File:** `components/CloudAccountsDashboard.tsx:14-25, 29-34, 36-44, 46-50`
**Issue:** `fetchData()`, `register()`, `scan()`, and `loadResults()` all do `(await authFetch(...)).json()` and treat the parsed body as success data unconditionally. `authFetch` (see `services/apiService.ts`) returns the raw `fetch` `Response` and does not throw on non-2xx status. Since FastAPI error responses (`{"detail": "..."}`) are valid JSON, `.json()` succeeds even on a 400/422/500, so e.g. `register()` will call `showToast('Account registered', 'success')` after a request that the server actually rejected with 400 (missing `provider`/`account_id`).
**Fix:** Check `response.ok` (or status) before parsing/toasting success, e.g.:
```ts
const res = await authFetch('/api/cloud-accounts', { method: 'POST', ... });
if (!res.ok) { const err = await res.json().catch(() => ({})); throw new Error(err.detail || 'Register failed'); }
const doc = await res.json();
```

### WR-02: Scan failures are swallowed into a 200 response, then reported as success by the UI

**File:** `backend/cloud_accounts_service.py:45-47`, `backend/cloud_account_endpoints.py:34-38`, `components/CloudAccountsDashboard.tsx:36-44`
**Issue:** When `cloud_checks_service.run_checks()` raises, `scan_account()` catches the exception and returns `{"error": str(e), "ran": 0}` with an implicit HTTP 200 (the endpoint just returns the dict as-is, no exception, no non-2xx status). The frontend's `scan()` never inspects `r.error`; it unconditionally shows `` `Scan complete: ${r.ran || 0} checks` `` as a **success** toast — so a hard scan failure looks identical in the UI to a scan that legitimately found 0 checks for a provider. Combined with WR-01, there is no path in the UI for a user to learn a scan actually failed except by noticing `scan_status: failed` after a manual refresh.
**Fix:** Either have the endpoint return a non-2xx status when `result.get("error")` is present, or have the frontend check `r.error` and show an error toast:
```ts
if (r.error) { showToast(`Scan failed: ${r.error}`, 'error'); } else { showToast(`Scan complete: ${r.ran || 0} checks`, 'success'); }
```

### WR-03: `provider`/`environment` are not validated against their documented enums, and invalid `environment` values silently vanish from the dashboard

**File:** `backend/cloud_account_endpoints.py:25-31`, `components/CloudAccountsDashboard.tsx:52-56, 95`
**Issue:** `register_account()` in `cloud_account_endpoints.py` only checks that `provider` and `account_id` are *present* (truthy), not that `provider` ∈ `{aws, azure, gcp}` or `environment` ∈ `{prod, staging, dev}` as the plan's must-haves specify. This violates this project's own CLAUDE.md rule ("Validate input at system boundaries"). The consequence is visible in the frontend: `grouped` in `CloudAccountsDashboard.tsx` only buckets `['prod', 'staging', 'dev']` (lines 52-56, 95), so an account registered directly against the API (bypassing the `<select>` dropdown) with e.g. `environment: "qa"` or `environment: ""` is still counted in `summary.total_accounts`/`by_environment`, yet never rendered in any environment section — it becomes permanently invisible in the dashboard with no error surfaced anywhere.
**Fix:** Validate `provider` and `environment` server-side (400 on invalid value), e.g.:
```python
_VALID_PROVIDERS = {"aws", "azure", "gcp"}
_VALID_ENVS = {"prod", "staging", "dev"}
if payload.get("provider") not in _VALID_PROVIDERS:
    raise HTTPException(status_code=400, detail=f"provider must be one of {_VALID_PROVIDERS}")
if payload.get("environment", "dev") not in _VALID_ENVS:
    raise HTTPException(status_code=400, detail=f"environment must be one of {_VALID_ENVS}")
```

### WR-04: No uniqueness/dedup check on `account_id` — repeated registration or discovery creates duplicate records

**File:** `backend/cloud_accounts_service.py:17-28, 72-80`
**Issue:** `register_account()` always `insert_one`s a new document with a fresh `id` regardless of whether a document with the same `(tenantId, provider, account_id)` already exists. `discover_org_accounts()` is worse: it unconditionally creates 3 new `org-acct-{1,2,3}` records (with brand-new `acct-...` IDs) on **every single call** — calling `POST /api/cloud-accounts/discover-org` twice produces 6 accounts, three pairs sharing the same `account_id` but different `id`s. This inflates `summary.total_accounts`/`by_provider`/`by_environment` and creates ambiguous, indistinguishable duplicate rows in the dashboard.
**Fix:** Use `update_one(..., upsert=True)` keyed on `{"tenantId": tenant_id, "provider": provider, "account_id": account_id}` instead of `insert_one` in both functions.

### WR-05: Stale per-account results cache after a new scan

**File:** `components/CloudAccountsDashboard.tsx:36-44, 46-50`
**Issue:** `loadResults(id)` early-returns if `results[id]` is already set (`if (results[id]) return;` — line 47), including when it's an already-fetched empty array. `scan(id)` calls `fetchData()` afterward (line 41) but never clears/invalidates `results[id]`. So if a user viewed "Results" before running a new scan, the results panel keeps showing the pre-scan snapshot indefinitely (until page reload), even though the account's `scan_status`/`last_scan` visibly updated.
**Fix:** Clear the cached results for that account when a scan completes: `setResults(s => { const {[id]: _, ...rest} = s; return rest; });` inside `scan()`'s success path (before or instead of relying on `fetchData()`).

### WR-06: Test suite asserts only HTTP status codes — would not catch CR-01 or CR-02

**File:** `backend/tests/test_cloud_accounts.py:38-77`
**Issue:** The plan's TDD order names 8 specific behaviors to verify (`test_register_aws_account_encrypts_credentials`, `test_list_accounts_never_returns_credentials`, `test_discover_org_accounts`, `test_tenant_isolation`, etc.), but the actual tests only assert `status_code == 200` (or, worse, `status_code in (200, 500)` for `test_scan_sets_status`, line 56, which passes even on outright failure). None of them:
- Inspect the stored/returned document to confirm `credentials_ref` is encrypted or absent (would have caught CR-01).
- Register accounts under two different tenants and confirm cross-tenant isolation on `list`/`scan`/`results` (would have caught CR-02) — `test_tenant_isolation` (lines 74-77) just hits `GET /api/cloud-accounts` once with a mock DB that always returns `[]` regardless of query filters, so it cannot distinguish correct tenant-scoped queries from no filtering at all.
- Assert on response body shape for `list_accounts`/`register_account` beyond "it's 200".

The suite is green, but it is exercising routing/wiring, not the documented security/correctness guarantees.
**Fix:** Strengthen at minimum: (1) assert `"credentials_ref" not in r.json()["account"]` in `test_register_aws_account`; (2) make `test_scan_sets_status` assert exactly `200` and assert the mock's `update_one` was called with the expected `scan_status` values; (3) make `test_tenant_isolation` configure the mock `find` to return tenant-tagged docs and assert the query passed to `find()` includes the calling user's `tenantId`.

## Info

### IN-01: Pervasive `any` typing in a form that handles credential-adjacent input

**File:** `components/CloudAccountsDashboard.tsx:6, 7, 10, 12, 101, 116`
**Issue:** `accounts`, `summary`, `form`, `results`, and the `.map((a: any) => ...)` / `.map((r: any, i: number) => ...)` callbacks are all typed `any`, discarding compile-time safety for a component that renders/handles account registration data.
**Fix:** Define minimal `CloudAccount`/`CloudCheckResult`/`AccountSummary` interfaces and replace the `any`s; low effort given the shapes are already fixed by the backend response schema.

### IN-02: `discover_org_accounts` accepts an unvalidated, effectively-unused `credentials` payload

**File:** `backend/cloud_accounts_service.py:72-80`, `backend/cloud_account_endpoints.py:55-59`
**Issue:** The endpoint and service both accept a `credentials: dict` parameter (intended to be AWS Organizations management-account credentials per the plan) but never inspect or validate it — the function is a hardcoded simulation that ignores its input entirely and always fabricates exactly 3 accounts. This is clearly intentional per the docstring ("Simulate org discovery (real impl calls AWS Organizations ListAccounts)"), but there's no `HTTPException` even for a completely empty `{}` body, which will be surprising when this stub is later replaced with a real implementation and validation needs to be retrofitted. Worth a `# TODO` or minimal shape check so the API contract is stable ahead of the real integration.
**Fix:** Add a lightweight guard (e.g., require a `management_account_id` or `credentials_ref` key) even in stub form, or note the contract expectation in a comment near the FastAPI route so future implementers don't have to reverse-engineer it from the plan.

### IN-03: `scan_account` endpoint always returns HTTP 200, even for a nonexistent account or an internal failure

**File:** `backend/cloud_account_endpoints.py:34-38`, `backend/cloud_accounts_service.py:36-47`
**Issue:** Unlike `register_account`'s endpoint (which raises `HTTPException(400)` for bad input), `scan_account`'s endpoint returns whatever dict `svc.scan_account` produces verbatim, including `{"error": "Cloud account not found", "ran": 0}` or `{"error": str(e), "ran": 0}`, both with implicit status 200. This is inconsistent with REST conventions used elsewhere in this same router file and is part of what makes WR-02 possible on the frontend.
**Fix:** Have the endpoint map an `"error"` key in the service result to an appropriate status code (404 for not-found, 502/500 for scan execution failure) rather than always returning 200.

---

_Reviewed: 2026-07-04T00:00:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_

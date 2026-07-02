---
phase: 09-compliance-score-dashboard
reviewed: 2026-07-02T12:57:44Z
depth: standard
files_reviewed: 8
files_reviewed_list:
  - backend/compliance_bulk_evidence_endpoints.py
  - backend/compliance_score_endpoints.py
  - backend/compliance_status_endpoints.py
  - backend/router_registry.py
  - backend/tests/test_compliance_score.py
  - components/ComplianceScorePanel.tsx
  - components/Dashboard.tsx
  - services/apiService.ts
findings:
  critical: 4
  warning: 4
  info: 2
  total: 10
status: issues_found
---

# Phase 09: Code Review Report

**Reviewed:** 2026-07-02T12:57:44Z
**Depth:** standard
**Files Reviewed:** 8
**Status:** issues_found

## Summary

The phase adds a severity-weighted compliance score endpoint (`GET /api/compliance/score`), a companion `threat-score` and `score/history` endpoint, Redis-backed caching/invalidation, and a new `ComplianceScorePanel` frontend component. The core scoring math (`_weighted_score`, per-framework breakdown) is correct and well tested for the happy paths in `test_compliance_score.py`.

However, cross-referencing `compliance_score_endpoints.py` against the codebase's established tenant-isolation conventions (`auth_roles.py`, `user_endpoints.py`, `compliance_evidence_lifecycle_endpoints.py`) surfaced a serious, provable defect: the endpoint's notion of "is_super" (`auth_roles.SUPER_AND_ADMIN_ROLES`, which includes the plain `"admin"` role) is broader than the tenant-scoped role that role represents elsewhere in the codebase (`_SUPER_ADMIN_ROLES` in `user_endpoints.py` deliberately excludes `"admin"`). Because `/api/compliance/score/history` bypasses `TenantIsolatedCollection` (queries `db._db` directly) and gates its tenant filter on this same broad `is_super` flag, **any user with role `"admin"` — a per-tenant role, not a platform role — receives every tenant's compliance/threat-score history**, and the `/score` and `/threat-score` cache keys collapse to a single shared `"__super__"` key across all such users, causing genuine cross-tenant score leakage via the Redis cache. Additionally, `/api/compliance/score/history` will crash with a `NameError` on every call because `timedelta` is used but never imported. The compliance-status override endpoint has no role/permission gate at all — any authenticated tenant user, including read-only roles, can silently overwrite an asset's compliance status.

These are all reachable via the reviewed code paths as written and are not covered by the existing test suite (which mocks the cache layer directly, masking the cache-key collision, and has no test at all for `/score/history`).

## Critical Issues

### CR-01: `GET /api/compliance/score/history` crashes on every request — `timedelta` is never imported

**File:** `backend/compliance_score_endpoints.py:19,269`

**Issue:** The module only imports `from datetime import datetime, timezone` (line 19), but `get_score_history` computes `cutoff = datetime.now(timezone.utc) - timedelta(days=days)` (line 269). `timedelta` is undefined in this module's namespace, so every call to this endpoint raises `NameError`, which is caught by the blanket `except Exception` handler and turned into an opaque `500 Internal server error`. The endpoint is completely non-functional as shipped. This was not caught because `test_compliance_score.py` has no test exercising `/api/compliance/score/history` at all.

**Fix:**
```python
from datetime import datetime, timezone, timedelta
```

---

### CR-02: `is_super` role check incorrectly includes tenant-scoped `"admin"`, causing cross-tenant data leakage

**File:** `backend/compliance_score_endpoints.py:17,62-63,171,264-265,272-274`

**Issue:** `_SUPER_ROLES` is imported as `auth_roles.SUPER_AND_ADMIN_ROLES`, which is defined as `SUPER_ROLES | {"admin"}` (`auth_roles.py:3`). Elsewhere in this same codebase (`user_endpoints.py:16-18`, `compliance_evidence_lifecycle_endpoints.py:24`) the equivalent "is this caller platform-level" check deliberately uses a narrower set that **excludes** plain `"admin"` (a per-tenant role), precisely to avoid this class of bug. Concretely:

- In `get_score_history` (lines 264-274), the query only adds `query["tenant_id"] = tenant_id` `if not is_super`. Since `is_super` is `True` for role `"admin"` — an ordinary tenant admin, not a platform admin — that filter is skipped entirely, and the query runs unscoped against `db._db.compliance_score_history` (raw Motor, bypassing `TenantIsolatedCollection`). **Any user with role `"admin"` receives every tenant's historical compliance/threat-score snapshots**, not just their own.
- In `get_compliance_score` and `get_threat_score` (lines 62-64, 171), the cache key collapses to the single shared string `"compliance:score:__super__"` / `"compliance:threat-score:__super__"` whenever `is_super` is `True`. Because the *query itself* (`db.asset_compliance`, `db.assets`, etc.) is still correctly tenant-scoped via `TenantIsolatedCollection`'s ambient tenant context for a plain `"admin"` caller, the first tenant-A admin to hit the endpoint within the 300s TTL populates `"compliance:score:__super__"` with **tenant-A's own score**. Any subsequent request from a *different* tenant's `"admin"`-role user, within the same TTL window, gets a cache **hit** on that same key and is served tenant-A's compliance/threat-score data verbatim. This is a genuine cross-tenant data disclosure, exploitable by any customer whose account happens to carry the (very common) `"admin"` role.

The existing test suite does not catch this because every test's default fake user has `role="admin"` (`tests/test_compliance_score.py:36`), and `cache.get`/`cache.set` are patched directly in every test (`_score_get`, lines 88-90), so the real cache key namespace collision is never exercised.

**Fix:** Use the narrower, already-established platform-role set (excluding `"admin"`) for any check that controls tenant-scope bypass or cache-key partitioning:
```python
# compliance_score_endpoints.py
from auth_roles import SUPER_ROLES as _SUPER_ROLES   # excludes "admin"
```
`auth_roles.SUPER_ROLES` (`{"Super Admin", "superadmin", "super_admin", "platform-admin"}`) is the correct set for "bypasses tenant isolation" semantics; `SUPER_AND_ADMIN_ROLES` should only be used for coarse "has admin-level UI permissions" checks, never for cache-key or query-scoping decisions.

---

### CR-03: `compliance:score:__super__` and `compliance:threat-score:*` caches are never invalidated by any write path

**File:** `backend/compliance_bulk_evidence_endpoints.py:231`, `backend/compliance_status_endpoints.py:90`, `backend/compliance_score_endpoints.py:171`

**Issue:** The only two places that call `invalidate_cache` for compliance scores are:
```python
invalidate_cache(f"compliance:score:{tenant_id}")           # compliance_bulk_evidence_endpoints.py:231
invalidate_cache(f"compliance:score:{resolved_tenant_id}")  # compliance_status_endpoints.py:90
```
Neither ever invalidates the literal key `"compliance:score:__super__"` that `get_compliance_score` writes to for any `is_super` caller (line 64), nor `"compliance:threat-score:{tenant_id}"` / `"compliance:threat-score:__super__"` at all — there is no `invalidate_cache` call anywhere in the reviewed files (or the rest of the backend, confirmed via repo-wide grep) that targets the `threat-score` cache namespace. Consequences:
- Every evidence upload or compliance-status override leaves the `threat-score` cache serving data up to 300s stale, unconditionally, for every user.
- For any `is_super` caller (see CR-02), the score cache is *never* invalidated by writes at all — the `"__super__"` key is orphaned from the invalidation logic entirely, so once cached it persists for the full TTL regardless of subsequent evidence/status changes, compounding the cross-tenant leak window in CR-02.

**Fix:** Invalidate the cache key(s) that could plausibly have been populated by the caller's tenant, including the shared super key and the threat-score namespace:
```python
invalidate_cache(f"compliance:score:{tenant_id}")
invalidate_cache("compliance:score:__super__")
invalidate_cache(f"compliance:threat-score:{tenant_id}")
invalidate_cache("compliance:threat-score:__super__")
```
(Apply the same pattern in both `compliance_bulk_evidence_endpoints.py` and `compliance_status_endpoints.py`.) This should be paired with the CR-02 fix so `"__super__"` genuinely means platform-wide, not "whichever tenant's admin happened to call first."

---

### CR-04: `PATCH /api/assets/{asset_id}/compliance/status` has no write-permission check — any authenticated tenant user can override compliance status

**File:** `backend/compliance_status_endpoints.py:28-91`

**Issue:** The handler only checks `Depends(get_current_user)` (authentication) and a tenant-*ownership* guard (`if user_role not in _SUPER_ROLES and resolved_tenant_id != tenant_id: raise 403`, line 56). There is no check that the caller's role actually has permission to *mutate* compliance status. Contrast with the sibling bulk-evidence endpoint, which explicitly gates writes with `_WRITE_ROLES` (`compliance_bulk_evidence_endpoints.py:33-35,64-65`). As written, a user with a low-privilege role (e.g. `"viewer"`, `"analyst"`, or any custom read-only role) who is a legitimate member of the tenant can call this endpoint and unilaterally set `status: "Compliant"` on any control for any asset in their tenant, with only a free-text `notes` field as an audit trail — no evidence, no elevated privilege required. This undermines the integrity guarantee the rest of the compliance system (evidence-backed status, chain-of-custody) is built on.

**Fix:** Add an explicit write-role gate before performing the update, mirroring the pattern already used in `compliance_bulk_evidence_endpoints.py`:
```python
from auth_roles import SUPER_AND_ADMIN_ROLES  # or a dedicated compliance-write role set

_STATUS_WRITE_ROLES = SUPER_AND_ADMIN_ROLES | {"Tenant Admin", "tenant_admin", "compliance_manager"}

...
if user_role not in _STATUS_WRITE_ROLES:
    raise HTTPException(status_code=403, detail="Insufficient permissions to override compliance status")
```

## Warnings

### WR-01: Bulk-upload docstring guarantee ("422 with per-file errors, zero commits") is broken for corrupt/unreadable zip entries

**File:** `backend/compliance_bulk_evidence_endpoints.py:122-145`

**Issue:** The per-entry read loop only catches `KeyError` (entry name not found in the archive):
```python
try:
    buf = io.BytesIO()
    with zf.open(raw_name) as entry_fh:
        ...
except KeyError:
    errors.append({"filename": raw_name, "error": "File not found in zip"})
    continue
```
If a zip entry is corrupt (e.g. `zlib.error`/`BadZipFile` from a truncated or tampered CRC), that exception is not caught here — it propagates out of the `for item in items` loop and the `with zipfile.ZipFile(...)` block, and is caught by the function-level `except Exception` handler, which returns a generic `500 Internal server error` instead of the documented `422` with a per-file error entry. This contradicts the module docstring's explicit contract ("Any single failure returns 422 with per-file errors and zero commits") and gives callers a worse (and misleading, since 500 implies a server bug rather than bad input) error experience for a plausible, attacker-controllable input (a hand-crafted corrupt zip entry).

**Fix:**
```python
except (KeyError, zipfile.BadZipFile, OSError, zlib.error) as exc:
    errors.append({"filename": raw_name, "error": f"Could not read entry: {exc}"})
    continue
```

### WR-02: `ComplianceScorePanel`'s "no monitored controls" empty state is effectively unreachable

**File:** `components/ComplianceScorePanel.tsx:147`

**Issue:** The empty-state branch is:
```tsx
if (data && data.frameworks.length === 0 && data.overall_score === 0) { ... }
```
But the backend's `frameworks` array always contains one entry per row in the global `compliance_frameworks` collection (`compliance_score_endpoints.py:96-126`), regardless of whether any controls in that framework have been evaluated — `total_controls` (not array length) is what drops to 0 for an unconfigured tenant. In any real deployment with at least one seeded framework (which is the normal case), `data.frameworks.length` will be > 0 even for a brand-new tenant with zero evidence, so this friendly "Upload evidence..." onboarding message never renders. Instead, new tenants see a literal `0%` score with all frameworks displayed at `0%`/0 passing/0 failing, which reads as "you have failed every control" rather than "nothing has been evaluated yet" — a materially misleading UX for exactly the audience (new tenants) this branch was written for.

**Fix:** Base the empty check on the sum of `total_controls` across frameworks, not the array length:
```tsx
const totalEvaluated = data ? data.frameworks.reduce((s, f) => s + f.total_controls, 0) : 0;
...
if (data && totalEvaluated === 0) { ... }
```

### WR-03: `patch_asset_compliance_status` has a TOCTOU race between reading and writing `previous_status`

**File:** `backend/compliance_status_endpoints.py:60-88`

**Issue:** `previous_status` is captured via a separate `find_one` (line 60-63) before the `update_one` (line 67-88) that performs the actual mutation and appends the `status_history` entry. If two PATCH requests for the same asset/control race, the second request's `status_history` entry can record an incorrect `previous_status` (the value read before the first request's write, not the value actually in effect immediately before the second request's own update), corrupting the audit trail this endpoint exists to guarantee (STATUS-02 explicitly requires an accurate `previous_status` in the immutable history).

**Fix:** Use `find_one_and_update` to make the read-then-write atomic, or accept the previous document's `status` from the atomic operation's return value:
```python
doc = await db.asset_compliance.find_one_and_update(
    {"assetId": asset_id, "controlId": body.control_id, "tenantId": resolved_tenant_id},
    {"$set": {...}, "$push": {...}},
    upsert=True,
)
previous_status = doc.get("status", "Unknown") if doc else "Unknown"
```

### WR-04: No coverage for the cache-key namespace or the `/score/history` endpoint

**File:** `backend/tests/test_compliance_score.py:36,85-91`

**Issue:** `_score_get` unconditionally patches `score_mod.cache.get`/`cache.set` (lines 88-90) in every test, so the real Redis/fakeredis key namespace (`"compliance:score:{tenant_id}"` vs `"compliance:score:__super__"`) is never exercised, and `_fake_user`'s default `role="admin"` means every existing test (including `test_score_tenant_isolation`) runs with `is_super=True` without the suite ever noticing that two different tenants would collapse onto the same cache key in production. There is also no test at all for `GET /api/compliance/score/history`, which is why CR-01 (a guaranteed `NameError` on every call) shipped undetected.

**Fix:** Add a test that exercises the real `CacheService`/fakeredis-backed cache (not mocked) with two different tenants both using role `"admin"`, asserting the second tenant's response does not equal the first tenant's cached payload; add a basic `test_score_history_endpoint` smoke test that calls `GET /api/compliance/score/history` and asserts `200`.

## Info

### IN-01: Unmapped control categories silently default to "Low" severity

**File:** `backend/compliance_score_endpoints.py:27-36,44`

**Issue:** `_CATEGORY_SEVERITY` maps only 8 category strings; any control whose `category` field doesn't exactly match one of these (typo, new category added later, framework import with different casing) silently falls back to `"Low"` severity (`SEVERITY_WEIGHTS.get(c.get("severity", "Low"), 1)` combined with `_CATEGORY_SEVERITY.get(c.get("category", ""), "Low")`). This can quietly understate the compliance score's sensitivity to a genuinely critical, but miscategorized/newly-added, control, with no logging or metric to surface the mismatch.

**Fix:** Log a warning (rate-limited) when a control's `category` isn't found in `_CATEGORY_SEVERITY`, so miscategorized/new categories are visible in ops rather than silently under-weighted.

### IN-02: `notes` field on the status-override request has no length bound

**File:** `backend/compliance_status_endpoints.py:22-25`

**Issue:** `ComplianceStatusUpdate.notes: str = ""` accepts an arbitrary-length string that is pushed verbatim into `status_history` on every PATCH, with no cap. Per CLAUDE.md's "Validate input at system boundaries," this should have an explicit bound to prevent a single request from growing an asset's `asset_compliance` document unboundedly (MongoDB's 16MB document limit is a real ceiling this could eventually hit for frequently-overridden assets).

**Fix:**
```python
notes: str = Field("", max_length=2000)
```

---

_Reviewed: 2026-07-02T12:57:44Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_

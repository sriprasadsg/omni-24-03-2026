---
phase: 70-core-data-audit-customization
reviewed: 2026-08-12T15:09:55Z
depth: standard
files_reviewed: 32
files_reviewed_list:
  - backend/audit_endpoints.py
  - backend/audit_service.py
  - backend/itam_asset_endpoints.py
  - backend/itam_audit_service.py
  - backend/itam_catalog_endpoints.py
  - backend/itam_catalog_service.py
  - backend/itam_component_endpoints.py
  - backend/itam_consumable_endpoints.py
  - backend/itam_customization_endpoints.py
  - backend/itam_customization_service.py
  - backend/itam_data_endpoints.py
  - backend/itam_data_service.py
  - backend/itam_finance_endpoints.py
  - backend/itam_license_endpoints.py
  - backend/itam_lifecycle_endpoints.py
  - backend/router_registry.py
  - backend/tests/test_itam_audit.py
  - backend/tests/test_itam_custom_fields.py
  - backend/tests/test_itam_customization.py
  - backend/tests/test_itam_data_csv.py
  - components/itam/ActivityLogPanel.tsx
  - components/itam/BulkImportExportPanel.tsx
  - components/itam/CatalogPanel.tsx
  - components/itam/CustomFieldsManager.tsx
  - components/itam/ITAMConsole.tsx
  - components/itam/itamI18n.tsx
  - components/itam/SettingsPanel.tsx
  - services/apiService.ts
  - src/__tests__/ITAMActivityLogPanel.test.tsx
  - src/__tests__/ITAMBulkImportExport.test.tsx
  - src/__tests__/ITAMConsole.test.tsx
  - src/__tests__/ITAMCustomFieldsManager.test.tsx
  - src/__tests__/ITAMSettingsPanel.test.tsx
  - types.ts
findings:
  critical: 0
  warning: 6
  info: 2
  total: 8
status: issues_found
---

# Phase 70: Code Review Report

**Reviewed:** 2026-08-12T15:09:55Z
**Depth:** standard
**Files Reviewed:** 32 (listed above; `types.ts` also read for the new type contracts)
**Status:** issues_found

## Summary

This phase adds Custom Fields, an audit-trail read surface + a 20-call-site audit backfill,
CSV import/export, and a new ITAM console Settings/branding/localization surface, on top of
the existing Pydantic/pymongo backend and Vite/React frontend. The security-sensitive
surfaces called out for adversarial attention are, on the whole, solid:

- CSV formula-injection sanitisation (`sanitize_csv_cell`) covers `=+-@\t\r` leading
  characters and is applied uniformly to base and custom-field columns, and is unit-tested.
- Upload size capping is genuinely bounded — the import route reads in 64 KiB chunks and
  aborts before ever buffering the whole file, and row count is capped separately.
- Every new/modified Mongo query in the ITAM endpoint files goes through
  `TenantIsolatedCollection`/`TenantIsolatedDatabase`, confirmed by reading `database.py`;
  the one deliberate exception (`itam_customization_endpoints.py` using the raw `db._db`
  handle for `system_settings`) is correctly reasoned in its own docstring — `system_settings`
  is not tenant-isolated by `database.py`'s wrapper, so going through the wrapper would make
  the global-fallback document unreachable, exactly as that module's comment says.
- The logo-URL scheme allowlist and hex-colour regex are enforced server-side
  (`itam_customization_service.validate_itam_settings`) and mirrored client-side as
  defence-in-depth in both `SettingsPanel.tsx` and `ITAMConsole.tsx`.
- `audit_service.py`'s `_compute_hash` payload (`timestamp|userName|action|resourceType|
  resourceId|previous_hash`) is untouched by this phase's diff — verified against
  `git diff fb09a99f..HEAD` — so the hash chain's contract is unchanged; only `get_logs`
  gained new optional filter/pagination parameters appended after the existing tenant-scope
  logic, and the 20-site backfill is purely additive (`await log_itam_action(...)` calls
  that never touch the ledger directly, matching `itam_audit_service.py`'s own claim).

None of the issues found below are exploitable data leaks across tenants. They are mostly
edge cases involving tenant-less ("platform-admin") accounts, one missing exception handler
on a rare race condition, and a couple of feature/vocabulary drifts between backend and
frontend or between this phase's new filters and a pre-existing method's original design.

## Warnings

### WR-01: Tenant-less admin's ITAM settings save is silently unrecoverable

**File:** `backend/itam_customization_endpoints.py:80-96`
**Issue:** `save_itam_settings` writes `{"tenantId": tenant_id}` verbatim, where
`tenant_id = getattr(current_user, "tenant_id", None)`. For a user whose JWT carries no
`tenant_id` (a true platform-wide admin — `authentication_service.py` sets the ambient
tenant context to the literal `"platform-admin"` precisely for this case, and
`"platform-admin"` is itself one of `_SETTINGS_ADMIN_ROLES`, so this is a reachable role/
tenant combination), this persists a document with `"tenantId": None` — the key **exists**
with a null value. `get_itam_settings`'s global-fallback query is
`{"type": ITAM_SETTINGS_TYPE, "tenantId": {"$exists": False}}` (line 57-59), which requires
the key to be **absent**, not merely falsy. A `tenantId: null` document therefore matches
neither the per-tenant branch (`tenant_id` is falsy, so that `if tenant_id:` branch at line
52 is skipped entirely) nor the fallback branch. The result: the save returns 200 with the
saved values, but every subsequent `GET /api/itam/settings` from that same account falls
straight to `merge_with_defaults(None)` and shows the built-in defaults again — the save
appears to silently vanish.
**Fix:** Reject the write (400) when `tenant_id` is falsy, or explicitly write a sentinel
(e.g. omit the `tenantId` key entirely via `$unset`, or use a real `"platform-admin"`
literal that `get_itam_settings` also checks for) so the round-trip is consistent:
```python
tenant_id = getattr(current_user, "tenant_id", None)
if not tenant_id:
    raise HTTPException(status_code=400, detail="A tenant context is required to save ITAM settings.")
```

### WR-02: CSV import's per-row insert has no `DuplicateKeyError` handling

**File:** `backend/itam_data_endpoints.py:190-201`
**Issue:** `create_manual_asset` (the single-asset path) wraps its `insert_one` in a
`try/except DuplicateKeyError` and converts a race-lost insert into a clean 409 (see
`itam_asset_endpoints.py:156-176`). The CSV import path duplicates the same duplicate-tag
pre-check (`existing = await db.assets.find_one({"assetTag": asset_tag})`, line 180) but its
`await db.assets.insert_one(document)` at line 193 has no matching exception handler. If two
imports (or an import racing a manual create) both pass the pre-check for the same
`(tenantId, assetTag)` before either inserts, the compound unique index
(`database.py`'s `assets` index on `("tenantId", "assetTag")`) will raise
`DuplicateKeyError` on the second insert, which is not caught here — the whole import
request returns an unhandled 500, and the response body (created/skipped counts, per-row
errors) for every row processed so far in that request is lost even though those rows were
already committed to the database.
**Fix:** Wrap the insert the same way `create_manual_asset` does, and record the row as
skipped rather than aborting the request:
```python
try:
    await db.assets.insert_one(document)
except DuplicateKeyError:
    skipped += 1
    if len(errors) < MAX_IMPORT_ERRORS:
        errors.append({"row": idx, "problems": [f"Asset with tag '{resolved_tag}' already exists in this tenant."]})
    continue
```

### WR-03: `itam_audit_service.log_itam_action`'s tenant fallback can mislabel/misplace audit entries

**File:** `backend/itam_audit_service.py:83-84`
**Issue:** `tenant_id = getattr(current_user, "tenant_id", None) or "default-tenant"`. For a
tenant-less admin acting through a route that doesn't itself pre-validate `tenant_id`
(`itam_catalog_endpoints.py`'s `create_catalog_entity`/`update_catalog_entity` write
`current_user.tenant_id` straight into the document with no upfront null-check, unlike the
asset/finance routes), the underlying resource can be persisted with a real `tenantId: None`
while its corresponding ledger entry is written with `tenantId: "default-tenant"` — a
literal string that several of this repo's own test fixtures (`test_itam_catalog.py`,
`test_itam_custom_fields.py`, `test_itam_foundation.py`) use as an actual seeded tenant id.
If any real deployment ever provisions a tenant literally named `default-tenant`, a
tenant-less admin's audit trail entries would land inside that tenant's own audit log and be
readable by that tenant's `view:audit_log` holders, and the entry would misrepresent which
resource/tenant it actually describes.
**Fix:** Use a sentinel that cannot collide with a real tenant id (e.g. `"platform-admin"`,
matching the ambient `tenant_context` convention already used elsewhere), or refuse to log
under a fabricated tenant id and instead log under `is_super_admin`-style scoping so
`get_logs`'s existing tenant-fail-closed behaviour applies consistently.

### WR-04: CSV export silently truncates at 10,000 rows with no truncation signal

**File:** `backend/itam_data_endpoints.py:74-102`
**Issue:** `assets = await db.assets.find(query, {"_id": 0}).limit(MAX_EXPORT_ROWS)...` caps
the export at 10,000 rows but the response has no equivalent of the import path's
`errorsTruncated` flag — an admin exporting a >10,000-asset tenant's inventory (e.g. for a
compliance audit) receives a CSV that looks complete (valid header, valid rows, HTTP 200)
but is silently missing rows, with nothing in the response to indicate that.
**Fix:** Add a response header (e.g. `X-Export-Truncated: true`) or a summary row/comment
when `len(assets) == MAX_EXPORT_ROWS`, and surface it in `BulkImportExportPanel.tsx`.

### WR-05: Frontend activity-log filter vocabulary has drifted from the backend's

**File:** `components/itam/ActivityLogPanel.tsx:13-26` vs. `backend/itam_audit_service.py:35-49`
**Issue:** The frontend's `ITAM_RESOURCE_TYPES` array (documented as "a local mirror" of the
backend's `ITAM_RESOURCE_TYPES` frozenset, "that module is the source of truth") lists 12
entries and omits `'itam_export'`, which the backend set does include (and which
`itam_data_endpoints.py`'s `export_assets` does write, action `itam_export.assets`). An
admin therefore cannot filter the Activity tab down to CSV-export events via the type
buttons, even though the backend logs and can return them.
**Fix:** Add `'itam_export'` to the frontend array (and consider generating one array from
the other, or asserting parity in a test, so the two lists cannot silently diverge again).

### WR-06: `GET /api/audit-logs`'s "super-admin sees all tenants" path is unreachable through this route

**File:** `backend/audit_endpoints.py:30-39`, `backend/audit_service.py:78-119`
**Issue:** `AuditService.get_logs`'s docstring (pre-existing, but its signature was extended
by this phase to add `resource_type`/`resource_id`/`limit`/`skip`) says "Super-admins with
`is_super_admin=True` may omit `tenant_id` to see all tenants." `get_audit_logs` always
passes `tenant_id=get_tenant_id()` — and for a tenant-less super-admin,
`authentication_service.py` sets the ambient tenant context to the literal string
`"platform-admin"`, which is truthy. `get_logs`'s `if tenant_id: query["tenantId"] = tenant_id`
branch therefore always fires for these users too, filtering the ledger to the literal
(and almost certainly non-existent) `tenantId == "platform-admin"` instead of taking the
`is_super_admin` all-tenants branch — a genuine platform super-admin viewing the new
resourceType/resourceId-filterable Activity tab or clicking "Verify ledger integrity" gets
an empty result set instead of the cross-tenant view the code was written to support. This
pre-dates this phase's diff, but this phase is what wires a real, tested UI path
(`ActivityLogPanel.tsx`'s "Verify ledger integrity" button, `verify_integrity`) onto it.
**Fix:** In `get_audit_logs`, don't forward the ambient tenant sentinel as if it were a real
tenant id:
```python
tenant_id = get_tenant_id()
is_super_admin = getattr(current_user, "role", "") in _SUPER_ROLES
effective_tenant_id = None if tenant_id == "platform-admin" else tenant_id
return await get_audit_service().get_logs(tenant_id=effective_tenant_id, is_super_admin=is_super_admin, ...)
```

## Info

### IN-01: `assignLicenseSeat`'s `log_itam_action` call may log with `resource_id=None`

**File:** `backend/itam_license_endpoints.py:164-170`
**Issue:** `resource_id=assignment.get("id")` — if `assign_license_seat` ever returns an
assignment dict without an `"id"` key (e.g. a future refactor of
`itam_license_service.assign_license_seat`), the ledger entry is written with
`resourceId: None`, which stringifies into the hash payload as the literal text `"None"`.
Not currently reachable (the service always sets `id`), but there's no defensive check.
**Fix:** Low priority — consider `assignment.get("id") or "unknown"` for symmetry with
`log_itam_action`'s own `username`/`tenant_id` fallback pattern.

### IN-02: `itam_asset_endpoints.py`'s 8-hex-char asset ids get materially higher fan-out from CSV import

**File:** `backend/itam_asset_endpoints.py:83` (via `build_asset_document`, reused by
`itam_data_endpoints.py`'s import path)
**Issue:** `asset_id = f"asset-{uuid.uuid4().hex[:8]}"` — 32 bits of entropy, pre-existing
from Phase 56/65-03's `build_asset_document` extraction. CSV import can now create up to
5,000 assets in a single request (`MAX_IMPORT_ROWS`), which is a much higher per-request
fan-out against this id space than the single-asset manual-create route ever produced. Not
a security issue (ids are not used as an authorization boundary) and collision would surface
as a loud 500/insert failure rather than silent corruption, but worth a note given the
volume this phase adds through the same id generator.
**Fix:** No action required for this phase; consider widening to the full UUID (or a
counter-backed id) if/when asset volume grows enough to matter.

---

_Reviewed: 2026-08-12T15:09:55Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_

# Phase 65: Core Data, Audit & Customization - Research

**Researched:** 2026-08-12
**Domain:** Backend (FastAPI + MongoDB) custom-field/audit/settings extension of an existing ITAM module; Frontend (Vite + React + TS) settings/audit UI panels
**Confidence:** HIGH

## Summary

This phase adds three backend capabilities (custom fields engine, audit trail, CSV bulk import/export) and three settings capabilities (global settings UI, branding/theming, localization) to the existing ITAM console. The single most important fact this research establishes is that **none of this is greenfield** — the prior 4 PLAN.md files in this phase directory assumed a Next.js/Prisma/tRPC stack that does not exist anywhere in this repository (verified: zero `prisma/`, `src/server/`, or `src/app/` directories in the repo; the actual frontend is Vite+React+TS at the repo root, the actual backend is Python FastAPI+Pydantic+Motor/MongoDB under `backend/`). Those 4 plans must not be reused or referenced by the planner.

Three of the six requirements already have real, working prior art in this codebase that must be **extended, not replaced**: `backend/itam_catalog_service.py` already implements a complete custom-fields ("fieldsets") validation engine consumed by `itam_catalog_endpoints.py` (model fieldset CRUD) and `itam_asset_endpoints.py` (asset `customFields` validation at create time) — ITAM-DAT-01's backend is roughly 70% done and only needs a dedicated settings/management UI plus (if scoped in) a reusable field-definition registry. `backend/audit_service.py`/`audit_endpoints.py` already implement a generic, hash-chained, tenant-isolated audit ledger (`db.audit_logs`) with a `GET /api/audit-logs` list route — but **zero ITAM write paths currently call `log_action_async`**, so ITAM-DAT-02's real gap is wiring the existing service into ITAM create/update/delete paths and adding entity-scoped query filtering, not building a new audit system. `backend/settings_endpoints.py` already establishes the exact persistence pattern (`db.system_settings` collection, `type` discriminator field, tenant-scoped vs. global-fallback documents, `_require_admin` gate) that ITAM-SET-01 should clone for `type: "itam_branding"` / `type: "itam_locale"` documents. A separate, pre-existing, non-ITAM-specific white-labeling feature (`components/TenantBrandingSettings.tsx` + `backend/tenant_endpoints.py` `/api/tenants/{id}/branding`) exists at the platform-tenant level — it is prior art for the branding *pattern* but is NOT the ITAM Global Settings surface the phase goal describes; the planner must decide (flagged as an Open Question below) whether ITAM-SET-02 reuses that platform-level branding or introduces an ITAM-console-scoped branding document, since the ROADMAP phrases this as "in Global Settings" of the ITAM console specifically.

ITAM-DAT-03 (CSV import/export) has strong prior art too: `pandas` and `openpyxl` are already backend dependencies (`backend/requirements.txt`), `backend/export_service.py` already has a working `_generate_csv` (Python's stdlib `csv` module, `csv.DictWriter`) pattern, and `backend/compliance_framework_mgmt_endpoints.py` already has a working `UploadFile` + `csv.DictReader` import pattern to clone. ITAM-SET-03 (localization) is the one genuinely greenfield requirement — the frontend has zero i18n library and zero locale/translation files anywhere in the tree today.

**Primary recommendation:** Extend the existing flat-file `backend/itam_<domain>_service.py` + `backend/itam_<domain>_endpoints.py` convention with two new domain pairs — `itam_customization_service.py`/`itam_customization_endpoints.py` (custom-field registry UI backing, global settings) and `itam_audit_service.py` (thin wrapper functions, NOT a new class, around the existing `audit_service.py` singleton, adding entity-filtered queries) — plus extend `itam_catalog_service.py` in place rather than duplicating its validation logic. Do not create any `prisma/`, `src/server/`, or `.ts` router file — every backend artifact is a `.py` file under `backend/`.

## Real Stack vs. Discarded Assumptions

| | Discarded prior plans assumed | Verified actual stack |
|---|---|---|
| Backend framework | Next.js API routes / tRPC routers (`src/server/api/routers/itam/*.ts`) | FastAPI, flat `backend/itam_<domain>_endpoints.py` files mounted via `backend/router_registry.py` [VERIFIED: direct file read] |
| ORM / DB | Prisma (`prisma/schema.prisma`, `AuditLog`/`ITAMSettings` models, `gsd_run query prisma.diff`) | MongoDB via Motor async driver; Pydantic models in `backend/itam_models.py`; no ORM, no schema migrations [VERIFIED: `from bson import ObjectId` in itam_models.py, `AsyncIOMotorCollection` throughout] |
| Validation | Zod schemas (`src/server/api/schemas/itam/*.ts`) | Pydantic v2 `BaseModel` subclasses in `itam_models.py` [VERIFIED] |
| Frontend framework | Next.js App Router (`src/app/(dashboard)/settings/itam/page.tsx`) | Vite + React 19 + TypeScript; `components/itam/*.tsx` panels registered in `components/itam/ITAMConsole.tsx` [VERIFIED: `vite.config.ts`, `package.json` `"react": "^19.2.0"`, no `next` dependency] |
| Frontend data layer | Per-router tRPC client hooks | Single shared `services/apiService.ts` with `authFetch`/`itamThrow` helpers, REST calls to `${API_BASE}/itam/...` or `${API_BASE}/assets/...` [VERIFIED] |
| Frontend tests | (unspecified, implied Next test runner) | Vitest (`npx vitest run src/__tests__`), tests at `src/__tests__/ITAM*.test.tsx` [VERIFIED: `.planning/config.json` `workflow.test_command`] |

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Custom fields definition (fieldsets on AssetModel) | API / Backend | Database (embedded doc) | Already lives on `asset_models` documents; `itam_catalog_service.py` owns validation, no separate collection per existing MVP-boundary decision (see that file's own docstring) |
| Custom fields values (on individual assets) | API / Backend | Database (embedded doc) | `Asset.customFields: Dict[str, Any]` embedded on `assets` documents, validated against the owning model's fieldset at write time |
| Custom Fields Manager UI | Browser / Client | API / Backend | New settings-style panel calling the extended catalog/model PATCH endpoint; no new backend collection needed for the base case |
| Audit trail (entity change log) | API / Backend | Database | `audit_service.py`'s hash-chained `db.audit_logs` collection already owns this; needs entity-filtered read query + write-call integration into ITAM services |
| Audit trail viewer UI | Browser / Client | API / Backend | New read-only panel calling an extended `GET /api/audit-logs?resourceType=&resourceId=` |
| CSV bulk import | API / Backend | Database | Server-side parse+validate+write (never trust client-parsed CSV); reuses `validate_custom_field_values`/catalog reference checks per row |
| CSV bulk export | API / Backend | Browser / Client | Server generates CSV via stdlib `csv` module (clone `export_service.py`'s `_generate_csv`); browser triggers `Blob`/`createObjectURL` download (clone `apiService.ts`'s `downloadComplianceReport` pattern) |
| Global Settings (branding/theming) | API / Backend | Database (`system_settings`) | Persistence via `db.system_settings` with a `type` discriminator, cloning `settings_endpoints.py`'s exact pattern |
| Global Settings UI (branding, locale) | Browser / Client | API / Backend | New settings tab/panel within `ITAMConsole.tsx` or (if scoped there) `SettingsDashboard.tsx` — see Open Questions |
| Localization / language switch | Browser / Client | API / Backend (persist chosen locale) | UI-string translation is a pure client-tier concern; the *selected* locale value persists server-side alongside other global settings |

## Standard Stack

### Core (already in this repo — no new backend installs required)
| Library | Version (verified installed) | Purpose | Why Standard (for this codebase) |
|---------|---------|---------|--------------|
| pandas | `>=2.1.0,<3.0.0` [VERIFIED: backend/requirements.txt] | CSV/Excel parsing for bulk import if column-type coercion is needed | Already a hard dependency; reused across export/report code |
| openpyxl | `>=3.1.0` [VERIFIED: backend/requirements.txt] | Excel (.xlsx) read/write, if ITAM-DAT-03's "CSV" scope is confirmed to include Excel too | Already used by `compliance_framework_mgmt_endpoints.py`'s import path |
| Python stdlib `csv` | n/a (stdlib) | CSV read (`csv.DictReader`) / write (`csv.DictWriter`) | `export_service.py::_generate_csv` and `compliance_framework_mgmt_endpoints.py`'s import route both already use stdlib `csv`, not pandas, for the CSV-specific paths — simpler, no extra dependency surface, and matches the existing convention exactly |
| FastAPI `UploadFile`/`File` | (pinned via `fastapi` in requirements.txt) | Multipart file upload for CSV import | Existing pattern at `compliance_framework_mgmt_endpoints.py` `import_compliance_controls` |
| Motor / pymongo `ReturnDocument.AFTER` | (pinned) | Read-modify-write with the mutated document returned | Standard pattern across every `itam_*_endpoints.py` file |

### Supporting (frontend, already in this repo)
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| React 19 | `^19.2.0` [VERIFIED: package.json] | UI framework | All new panels |
| Vitest | `^3.2.4` [VERIFIED: package.json] | Test runner | All new frontend tests, under `src/__tests__/` |
| Existing `authFetch`/`itamThrow` (`services/apiService.ts`) | n/a (in-repo) | Authenticated fetch + ITAM-style error unwrapping | All new API client functions for this phase |

### New for this phase (genuinely greenfield)
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `i18next` | `26.3.6` [ASSUMED — discovered via WebSearch/training knowledge, registry-confirmed via `npm view` but not via official docs this session] | Locale dictionary/string-interpolation/pluralization engine | Industry-standard i18n core; framework-agnostic |
| `react-i18next` | `17.0.11` [ASSUMED — same caveat; flagged SUS below, see Package Legitimacy Audit] | React bindings (`useTranslation` hook, `<Trans>`) for i18next | The de facto standard React integration; avoids hand-rolling a translation-context provider |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| i18next + react-i18next | Hand-rolled `LocaleContext` + flat JSON dictionaries + a `t(key)` helper | Zero new dependencies, trivially small footprint matching this phase's likely actual scope (a locale switcher for the ITAM console only, not a full-app translation system); loses pluralization/interpolation/fallback-chain correctness that i18next gets for free. **Given CLAUDE.md's "keep files under 500 lines" and "nothing more than asked" bias, and that no other part of this app has i18n today, this lightweight approach is a legitimate discretion call — flagged in Open Questions, not locked here.** |
| stdlib `csv` for export | pandas `.to_csv()` | pandas adds no new dependency (already installed) but the existing `export_service.py` precedent uses stdlib `csv` directly for CSV-specific formatting control (e.g., flattening nested customFields); matching that precedent is lower-risk than introducing a second CSV-generation style in the same codebase |
| Reusing `audit_service.py`'s existing `AuditService` class | Writing a new ITAM-specific audit collection/class | A second immutable ledger would fragment audit history across two collections and lose the existing hash-chain integrity check (`verify_integrity`) for ITAM entities — strictly worse |

**Installation (frontend only, if i18next path is chosen):**
```bash
npm install i18next react-i18next
```
No backend installs needed — pandas/openpyxl/FastAPI/Motor are all already present.

**Version verification:** `npm view i18next version` → `26.3.6`; `npm view react-i18next version` → `17.0.11` (both checked live against the npm registry this session — see Package Legitimacy Audit for the SUS flag on react-i18next's very recent publish date).

## Package Legitimacy Audit

| Package | Registry | Age (latest version) | Downloads | Source Repo | Verdict | Disposition |
|---------|----------|-----|-----------|-------------|---------|-------------|
| i18next | npm | published 2026-07-09 | 20.6M/week | github.com/i18next/i18next | OK | Approved |
| react-i18next | npm | published 2026-07-22 (very recent) | 14.8M/week | github.com/i18next/react-i18next | SUS | Flagged — planner must add `checkpoint:human-verify` before install |
| pandas | n/a — already installed, not a new install | — | — | — | — | No audit needed (existing dependency) |
| openpyxl | n/a — already installed, not a new install | — | — | — | — | No audit needed (existing dependency) |

**Packages removed due to [SLOP] verdict:** none.
**Packages flagged as suspicious [SUS]:** `react-i18next` — flagged solely on "too-new" publish-date heuristic despite 14.8M weekly downloads, a long-established GitHub org/repo, no postinstall script, and not deprecated. This reads as a routine version-bump false positive, not a slopsquat signal, but per protocol it is not auto-cleared: the planner must gate the `npm install react-i18next` step behind a `checkpoint:human-verify` task. If the discretion call in Open Questions lands on the hand-rolled lightweight locale approach instead, this package is never installed and the flag is moot.

*Both i18next package names were discovered via WebSearch/training knowledge, not official documentation — both remain `[ASSUMED]` provenance regardless of registry confirmation, per this agent's provenance rules.*

## Architecture Patterns

### System Architecture Diagram

```
Browser (ITAMConsole.tsx or SettingsDashboard.tsx)
  │
  ├─ Custom Fields Manager panel ──PATCH /api/itam/catalog/models/{id}──▶ itam_catalog_endpoints.py
  │                                        (existing route; validates via  │
  │                                         itam_catalog_service.validate_fieldsets)
  │                                                                        ▼
  │                                                                  asset_models collection (Mongo)
  │
  ├─ Activity/Audit Log panel ──GET /api/audit-logs?resourceType=&resourceId=──▶ audit_endpoints.py (extended)
  │                                                                        │
  │                                                                        ▼
  │                                                              audit_service.get_logs()  (extended filter)
  │                                                                        │
  │                                                                        ▼
  │                                                                  audit_logs collection (hash-chained, Mongo)
  │                                                                        ▲
  │                                                    ITAM write paths call
  │                                                    log_action_async(...) on
  │                                                    create/update/delete (NEW wiring —
  │                                                    itam_catalog_endpoints.py,
  │                                                    itam_asset_endpoints.py, etc.)
  │
  ├─ Bulk Import/Export panel
  │     ├─ Export ──GET /api/itam/data/export?entity=assets──▶ itam_data (or itam_customization)_endpoints.py
  │     │                                                        │  stdlib csv.DictWriter, clone export_service.py
  │     │                                                        ▼
  │     │                                                  StreamingResponse / Content-Disposition attachment
  │     │                                                        │
  │     │◀────────────── browser Blob + createObjectURL download ┘  (clone apiService.ts downloadComplianceReport)
  │     │
  │     └─ Import ──POST /api/itam/data/import (multipart UploadFile)──▶ same endpoints file
  │                                                        │  csv.DictReader per row, per-row
  │                                                        │  validate_custom_field_values +
  │                                                        │  catalog-reference checks (clone
  │                                                        │  compliance_framework_mgmt_endpoints.py's import route)
  │                                                        ▼
  │                                                  assets collection (Mongo, tenant-isolated writes)
  │
  └─ Global Settings panel (branding, locale) ──GET/POST /api/itam/settings──▶ itam_customization_endpoints.py (NEW)
                                                          │  clone settings_endpoints.py's
                                                          │  db.system_settings + type discriminator pattern
                                                          ▼
                                                    system_settings collection
                                                    (type: "itam_branding" | "itam_locale")
```

### Recommended Project Structure
```
backend/
├── itam_catalog_service.py        # EXTEND (in place) — reuse validate_fieldsets/collect_field_defs
├── itam_catalog_endpoints.py      # EXTEND if a dedicated field-registry route is needed beyond
│                                   #   the existing PATCH /api/itam/catalog/models/{id}
├── itam_audit_service.py          # NEW — thin functions wrapping audit_service.get_audit_service(),
│                                   #   adding resourceType/resourceId filtering; NOT a new ledger class
├── itam_data_service.py           # NEW — CSV import/export row validation + generation logic
├── itam_data_endpoints.py         # NEW — GET export / POST import routes, mounted at /api/itam/data
├── itam_customization_service.py  # NEW — global settings (branding/locale) read/write helpers
├── itam_customization_endpoints.py # NEW — GET/POST /api/itam/settings routes
└── tests/
    ├── test_itam_audit.py         # NEW
    ├── test_itam_data_csv.py      # NEW
    └── test_itam_customization.py # NEW

components/itam/
├── ITAMConsole.tsx                 # EXTEND — add a new tab (e.g. 'settings' or 'audit')
├── CustomFieldsManager.tsx         # NEW
├── ActivityLogPanel.tsx            # NEW
├── BulkImportExportPanel.tsx       # NEW
└── ItamSettingsPanel.tsx           # NEW (branding + locale)

src/__tests__/
├── ITAMCustomFieldsManager.test.tsx  # NEW
├── ITAMActivityLogPanel.test.tsx     # NEW
└── ITAMSettingsPanel.test.tsx        # NEW

services/apiService.ts               # EXTEND — add itam data/audit/settings client functions
                                      #   following the existing itamThrow() + `${API_BASE}/itam/...` convention
```

### Pattern 1: Extending the existing fieldset validation engine (ITAM-DAT-01)
**What:** `itam_catalog_service.py` already validates fieldset *definitions* (`validate_fieldsets`) and asset `customFields` *values* against those definitions (`collect_field_defs` + `validate_custom_field_values`). Both are pure functions with no DB I/O.
**When to use:** Any new endpoint that creates/updates an `AssetModel`'s `fieldsets` or an `Asset`'s `customFields` must call these exact functions — never re-implement key-shape/type/required/select-option validation.
**Example:**
```python
# Source: backend/itam_catalog_service.py (in-repo, read in full this session)
from itam_catalog_service import validate_fieldsets, collect_field_defs, validate_custom_field_values

# Definition-side (model fieldset edit):
validate_fieldsets(document.get("fieldsets") or [])   # raises ValueError -> translate to HTTP 400

# Value-side (asset customFields write):
problems = validate_custom_field_values(collect_field_defs(model_doc), payload.customFields)
if problems:
    raise HTTPException(status_code=400, detail={"message": "...", "problems": problems})
```

### Pattern 2: Wiring the existing audit ledger into ITAM write paths (ITAM-DAT-02)
**What:** `audit_service.get_audit_service().log_action_async(...)` is the single audit-write entry point used elsewhere in the codebase (`agent_remote_control.py`, `deployment_endpoints.py`). No ITAM endpoint currently calls it — confirmed via `grep -rn "log_action_async" backend/itam_*.py` returning zero matches.
**When to use:** Every ITAM create/update/delete route this phase touches (and, as a stretch, existing Phase 56-60 ITAM routes if in scope) should call this after a successful write, inside a `try/except` that logs-and-continues on failure (mirroring `agent_remote_control.py`'s pattern) rather than failing the parent request if audit logging itself errors.
**Example:**
```python
# Source: backend/agent_remote_control.py (in-repo pattern to clone)
from audit_service import get_audit_service
try:
    await get_audit_service().log_action_async(
        user_name=current_user.username,
        action="itam_asset.update",       # <domain>.<verb> convention
        resource_type="itam_asset",       # new resourceType values this phase introduces
        resource_id=asset_id,
        details=f"Updated fields: {list(update_data.keys())}",
        previous_state=existing_doc,      # enables rollback via the existing endpoint
        tenant_id=current_user.tenant_id,
    )
except Exception as e:
    logger.error(f"Failed to log ITAM audit event: {e}")
```
**Gap this phase must close:** `audit_service.get_logs()` currently only filters by `tenantId` (plus an `is_super_admin` cross-tenant bypass) — it has no `resourceType`/`resourceId` filter, yet ITAM-DAT-02's stated success criterion is "view audit trail for **any asset/entity**". Add optional `resource_type`/`resource_id` query params to `get_logs()` and the `GET /api/audit-logs` route.

### Pattern 3: CSV export via stdlib `csv`, browser download via Blob (ITAM-DAT-03)
**What:** Server builds an in-memory CSV string with `csv.DictWriter`, returns it with a `Content-Disposition: attachment` header; browser fetches it and triggers a save via `Blob`/`createObjectURL`.
**Example (backend, source `backend/export_service.py::_generate_csv`, in-repo):**
```python
import csv, io
def _generate_csv(self, data: list[dict]) -> str:
    output = io.StringIO()
    all_keys = sorted({k for row in data for k in row})
    writer = csv.DictWriter(output, fieldnames=all_keys, extrasaction='ignore')
    writer.writeheader()
    writer.writerows(data)
    return output.getvalue()
```
**Example (frontend download, source `services/apiService.ts::downloadComplianceReport`, in-repo):**
```typescript
export const downloadComplianceReport = async (filename: string): Promise<void> => {
    const res = await authFetch(`${API_BASE}/compliance/reports/download/${encodeURIComponent(filename)}`);
    if (!res.ok) throw new Error('Failed to download report');
    const blob = await res.blob();
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url; a.download = filename; a.click();
};
```

### Pattern 4: CSV import via `UploadFile` + row-level validation (ITAM-DAT-03)
**What:** Multipart file upload, decoded and parsed row-by-row with `csv.DictReader`, each row validated before any write — never bulk-insert unvalidated rows.
**Example (source `backend/compliance_framework_mgmt_endpoints.py::import_compliance_controls`, in-repo):**
```python
@router.post("/api/itam/data/import")
async def import_assets_csv(file: UploadFile = File(...), current_user: TokenData = Depends(_require_itam_admin)):
    content = await file.read()
    reader = csv.DictReader(io.StringIO(content.decode("utf-8", errors="replace")))
    results = {"created": 0, "errors": []}
    for i, row in enumerate(reader):
        # resolve modelId -> model_doc, then:
        problems = validate_custom_field_values(collect_field_defs(model_doc), parsed_custom_fields)
        if problems:
            results["errors"].append({"row": i, "problems": problems})
            continue
        # insert_one(...) per validated row
        results["created"] += 1
    return results
```

### Pattern 5: Global settings persistence (ITAM-SET-01/02/03)
**What:** `system_settings` collection with a `type` discriminator, tenant-scoped document taking precedence over a global-fallback document with no `tenantId` field.
**Example (source `backend/settings_endpoints.py`, in-repo):**
```python
@router.get("/itam")
async def get_itam_settings(current_user: TokenData = Depends(get_current_user)):
    db = get_database()
    raw = db._db if hasattr(db, "_db") else db
    tenant_id = getattr(current_user, "tenant_id", None)
    doc = await raw.system_settings.find_one({"type": "itam_settings", "tenantId": tenant_id}, {"_id": 0})
    return doc or {"branding": {}, "locale": "en"}

@router.post("/itam")
async def save_itam_settings(settings: Dict[str, Any], current_user: TokenData = Depends(_require_admin_dep)):
    db = get_database()
    raw = db._db if hasattr(db, "_db") else db
    settings["type"] = "itam_settings"
    settings["tenantId"] = current_user.tenant_id
    await raw.system_settings.update_one(
        {"type": "itam_settings", "tenantId": current_user.tenant_id},
        {"$set": settings}, upsert=True,
    )
    return settings
```
Note the `db._db if hasattr(db, "_db") else db` unwrap — `system_settings` (like `ai_tools`) is read/written through the *raw* Motor handle in the existing code, not the `TenantIsolatedDatabase` wrapper, with `tenantId` filtering done explicitly in the query. Follow this exact convention for any new `system_settings` document type; do not assume `TenantIsolatedCollection` auto-scopes it (system_settings/ai_tools are read via `db._db`, sidestepping the wrapper entirely — verify this holds for whatever collection the planner ultimately proposes, since `database.py`'s exemption list, read this session, does NOT include `system_settings` by name, meaning it WOULD be tenant-wrapped if accessed via `db.system_settings` instead of `raw.system_settings`).

### Anti-Patterns to Avoid
- **Building a new `AuditLog` collection/class for ITAM specifically:** duplicates `audit_service.py`'s existing hash-chained ledger and its `verify_integrity()` guarantee; extend, don't fork.
- **Trusting client-side CSV parsing for import:** always parse and validate server-side; never accept a pre-parsed JSON array of rows from the browser as if it were already validated.
- **A parallel `custom_field_definitions` collection:** `itam_catalog_service.py`'s own docstring explicitly documents this as an out-of-scope MVP boundary decision from Phase 56 — introducing it now without a locked user decision would contradict a prior, documented architectural choice.
- **Writing settings through `db.system_settings` (the wrapped accessor) instead of `raw.system_settings`:** would silently apply `TenantIsolatedCollection`'s tenant-filter injection on top of the manual `tenantId` handling `settings_endpoints.py` already does, which is inconsistent with how `llm`/`ai-tools`/`database` settings types behave today.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|--------------|-----|
| Custom field type/shape/required/select-option validation | A new validator in a new file | `itam_catalog_service.validate_fieldsets` / `validate_custom_field_values` (existing) | Already handles duplicate-key detection, identifier-shape regex, unsupported-type rejection, select-options enforcement |
| Immutable, tamper-evident change history | A new audit collection/hashing scheme | `audit_service.py`'s existing SHA-256 hash-chained `AuditService` | Already implements chain verification (`verify_integrity`), tenant isolation, and rollback-support (`previousState`) |
| CSV parsing/generation | A hand-rolled string-splitting parser | Python stdlib `csv` module (`DictReader`/`DictWriter`) | Handles quoting, embedded commas/newlines, encoding edge cases that naive splitting breaks on |
| Locale string interpolation, pluralization, fallback chains | A hand-rolled `{key}` template replacer | `i18next` (if the full-i18n discretion path is chosen) | Pluralization rules and RTL/locale fallback logic are non-trivial and already solved; see Open Questions for the lightweight-alternative discretion call |
| Browser file download from a fetch response | Manually constructing a data URI | `Blob` + `URL.createObjectURL` + a synthetic `<a download>` click (existing `apiService.ts` pattern) | Already proven in this codebase for `downloadComplianceReport`; handles large payloads without base64 bloat |

**Key insight:** This phase's dominant risk is *not* "what library to use" — it's re-implementing logic that already exists in this exact codebase under a different phase's file. Every one of ITAM-DAT-01/02/03's "hand-roll" risks is actually a "did you grep for existing code first" risk.

## Runtime State Inventory

Not applicable — this is a greenfield feature-addition phase (new fields/collections/endpoints), not a rename/refactor/migration phase. No existing runtime state (stored data, live service config, OS-registered state, secrets, build artifacts) is being renamed or relocated by this phase's requirements.

## Common Pitfalls

### Pitfall 1: Reusing the discarded PLAN.md files or their file paths
**What goes wrong:** The 4 previously-written PLAN.md files in this exact phase directory reference `prisma/schema.prisma`, `src/server/api/routers/itam/*.ts`, and `src/app/(dashboard)/settings/itam/page.tsx` — none of which exist. A planner working from stale context (or from these files directly) will generate tasks with unverifiable `<verify>` commands (`gsd_run query prisma.diff` has no meaning in this repo) and files that can never be created at those paths without contradicting the actual project structure.
**Why it happens:** The prior planning run appears to have used a generic/templated ITAM stack assumption rather than reading this repository's actual `backend/`/`components/itam/` structure.
**How to avoid:** Every new plan task's `<files>` list must resolve to a `.py` file under `backend/` or a `.tsx`/`.ts` file under `components/`, `services/`, or `src/__tests__/` — cross-check each proposed path against `ls backend/ | grep itam` and `ls components/itam/` before finalizing.
**Warning signs:** Any task referencing `prisma`, `tRPC`, `Zod`, `src/server/`, or `src/app/(dashboard)/` in this phase is a signal the plan has regressed to the discarded assumption set.

### Pitfall 2: Assuming `system_settings` is tenant-isolated by the wrapper
**What goes wrong:** `database.py`'s `TenantIsolatedDatabase` exemption allowlist (verified this session) does NOT include `system_settings` — so `db.system_settings` (wrapped accessor) WOULD get an auto-injected `tenantId` filter, while the *existing* `settings_endpoints.py` code deliberately bypasses this by using `db._db.system_settings` and handling `tenantId`/global-fallback logic manually (see `_get_raw_llm_settings`). A new endpoint that mixes the two access styles (e.g., writes via `raw.system_settings` but later reads via `db.system_settings`) will silently see different documents than it wrote.
**Why it happens:** The wrapper's `__getattr__`/`__getitem__` both check the same exemption list, so it's easy to assume any collection not in that list is "just tenant scoped, don't worry about it" — but `system_settings`'s actual usage pattern (global-fallback documents with `tenantId: {"$exists": False}`) is incompatible with a naive equality-filter wrapper.
**How to avoid:** Follow `settings_endpoints.py`'s exact `raw = db._db if hasattr(db, "_db") else db` pattern for every new `system_settings`-backed read/write in this phase, and never mix it with the wrapped `db.system_settings` accessor in the same feature.
**Warning signs:** A settings GET returning `{}`/defaults immediately after a successful settings POST in manual testing.

### Pitfall 3: Audit trail integration missed on existing (pre-Phase-65) ITAM write paths
**What goes wrong:** If ITAM-DAT-02 only wires `log_action_async` into the endpoints newly created by this phase, users querying the audit trail for an asset created back in Phase 56/57 (before this phase existed) will see no history at all — contradicting the "view audit trail for **any** asset/entity" success criterion, which reads as an expectation covering all ITAM entities, not just ones touched after this phase ships.
**Why it happens:** It's natural to scope audit-logging additions to "the files this plan touches," but the requirement's wording implies retroactive/going-forward coverage across the whole ITAM surface.
**How to avoid:** Explicitly decide and document in the plan whether ITAM-DAT-02's scope is (a) audit logging added only to new/modified endpoints in this phase, or (b) audit logging backfilled into every existing ITAM write path (catalog, asset, lifecycle, license, consumable, component, finance, label). This is a genuine scope decision — flagged in Open Questions, not decided here.
**Warning signs:** UAT reveals an asset created in an earlier phase shows an empty audit trail even after this phase ships.

### Pitfall 4: Trusting a model-fabricated `is_super_admin`/admin-role string set inconsistently
**What goes wrong:** This codebase has at least three slightly different admin-role string sets across files (`_SUPER_ROLES` in `audit_endpoints.py`, `_SETTINGS_ADMIN_ROLES` in `settings_endpoints.py`, `_AP_SUPER_ROLES` in `audit_program_service.py` — all near-identical but independently maintained literals like `{"Super Admin", "super_admin", "admin", "platform-admin"}`). A new ITAM settings/audit endpoint that invents a fourth slightly-different set (e.g., forgetting `"platform-admin"`) will produce an inconsistent authorization surface.
**Why it happens:** No shared constant exists for this role set; each file defines its own.
**How to avoid:** Copy the exact literal set from `settings_endpoints.py::_SETTINGS_ADMIN_ROLES` verbatim for any new admin-gated ITAM settings endpoint, or (better, but a larger discretion call) extract a shared constant — flagged as a nice-to-have, not required for phase scope.
**Warning signs:** An admin who can access `/api/settings/*` gets 403 on a new `/api/itam/settings` endpoint.

## Code Examples

See Architecture Patterns section above — all 5 code examples are sourced directly from files read in full this session (`itam_catalog_service.py`, `agent_remote_control.py`, `export_service.py`, `apiService.ts`, `compliance_framework_mgmt_endpoints.py`, `settings_endpoints.py`), not from external documentation, since this phase is fundamentally about extending existing in-repo patterns rather than adopting new external APIs.

## State of the Art

| Old Approach (what discarded plans assumed) | Current Approach (verified in-repo) | When Changed | Impact |
|--------------------------------------------|--------------------------------------|---------------|--------|
| Prisma schema migrations for new fields | Pydantic model fields + Mongo's schemaless documents (no migration step; new optional fields are simply absent on old documents until written) | N/A — this has always been the actual state; the prior plans never matched reality | No `prisma migrate`-equivalent step exists or is needed in any task |
| tRPC router-per-feature | Flat FastAPI router files (`itam_<domain>_endpoints.py`) mounted centrally in `router_registry.py` | N/A — established since Phase 56 | New endpoint files must be added to `router_registry.py`'s `_load(app, "<module>", "router")` list to actually be reachable |

**Deprecated/outdated:** Nothing in this codebase is being deprecated by this phase — it is purely additive.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `i18next`/`react-i18next` are the right libraries for ITAM-SET-03, at the stated versions | Standard Stack / Package Legitimacy Audit | If the actual scope is "ITAM console strings only" rather than full-app i18n, a lighter hand-rolled context may be more appropriate — this is explicitly left as an Open Question, not locked |
| A2 | ITAM-SET-01/02 ("Global Settings") refers to a *new*, ITAM-console-scoped settings surface rather than the existing platform-level `SettingsDashboard.tsx`/`TenantBrandingSettings.tsx` | Architecture Patterns, Open Questions | If wrong, the plan would build a duplicate settings surface instead of extending the existing one — a meaningful rework risk |
| A3 | ITAM-DAT-02's audit-trail scope should extend to pre-existing (Phase 56-60) ITAM write paths, not just this phase's new endpoints | Common Pitfalls #3 | If wrong (scope is new-endpoints-only), over-building; if right and under-scoped, UAT will fail the "any asset/entity" success criterion |

## Open Questions

1. **Is "Global Settings" (ITAM-SET-01/02) a new ITAM-console-scoped settings tab, or an extension of the existing platform-level `SettingsDashboard.tsx` / `TenantBrandingSettings.tsx` / `tenant_endpoints.py` branding surface?**
   - What we know: `TenantBrandingSettings.tsx` + `/api/tenants/{id}/branding` already deliver logo/color/company-name branding, but at the whole-platform-tenant level, reachable from the main app's Settings area — not from inside `ITAMConsole.tsx`.
   - What's unclear: The ROADMAP phrase "in Global Settings" could mean either surface; the phase is explicitly scoped to the ITAM console (`ITAMConsole.tsx`'s existing 6 tabs have no Settings tab today).
   - Recommendation: Default to adding a new "Settings" tab inside `ITAMConsole.tsx` (matching the phase's own architectural boundary — this is an ITAM-Backlog milestone), backed by a new `type: "itam_settings"` `system_settings` document, while explicitly cross-linking/reusing `TenantBrandingSettings.tsx`'s existing branding fields shape (`logoUrl`, `primaryColor`, `companyName`) for consistency rather than inventing a second branding schema. Confirm with the user via discuss-phase before locking.

2. **Should ITAM-SET-03 use i18next/react-i18next (full i18n framework) or a lightweight hand-rolled locale-dictionary context?**
   - What we know: Zero i18n infrastructure exists anywhere in this repo today; the only stated requirement is "User can change the interface language."
   - What's unclear: Whether the intended scope is translating the entire application (large effort, justifies a real i18n framework) or just the ITAM console's own UI strings (small surface, a lightweight approach may suffice and avoids introducing the codebase's first new frontend dependency in this area).
   - Recommendation: Scope to the ITAM console only for this phase (matching the phase's stated boundary), and default to the lightweight hand-rolled approach given the CLAUDE.md minimalism directive and the flagged `react-i18next` SUS package-legitimacy signal — but this is a real discretion call for discuss-phase/planner, not decided here.

3. **Does ITAM-DAT-02's "audit trail for any asset/entity" require backfilling `log_action_async` calls into Phase 56-60's existing ITAM endpoints (catalog, asset, lifecycle, license, consumable, component, finance, label), or only the new work in this phase?**
   - What we know: Zero existing ITAM endpoints currently call `log_action_async` (confirmed by grep).
   - What's unclear: Whether "any asset/entity" is a claim about breadth-of-entity-type-support (any *kind* of entity) or breadth-of-time (from asset creation onward regardless of which phase created it).
   - Recommendation: Scope Wave 1 to wiring audit logging into all ITAM write paths that exist as of this phase (a moderate-sized but mechanical task, following Pattern 2 above) since the success criterion's plain-language reading implies completeness, not phase-boundary scoping. Confirm with the user if this significantly changes estimated task count.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python (backend venv) | All backend tasks | ✓ | via `backend/venv/bin/python` [VERIFIED: `backend/venv/bin/pytest` present] | — |
| pandas | CSV/Excel edge cases | ✓ | `>=2.1.0,<3.0.0` (installed) | — |
| openpyxl | Excel import/export (if scoped) | ✓ | `>=3.1.0` (installed) | — |
| MongoDB | All persistence | Assumed ✓ (existing app dependency; not re-probed this session — no evidence this phase changes DB requirements) | — | — |
| Node/npm | Frontend build/test | ✓ | matches existing `package.json` toolchain (Vite ^8, TS ~5.7) | — |
| i18next / react-i18next | ITAM-SET-03 (if that path is chosen) | ✗ (not installed) | latest verified: i18next 26.3.6, react-i18next 17.0.11 | Lightweight hand-rolled context (no new dependency) — see Open Question 2 |

**Missing dependencies with no fallback:** none.
**Missing dependencies with fallback:** i18next/react-i18next — fallback is the hand-rolled locale-context approach described in Open Question 2.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Backend framework | pytest, run via `backend/venv/bin/python -m pytest` [VERIFIED: memory + `backend/venv/bin/pytest` present] |
| Frontend framework | Vitest ^3.2.4 [VERIFIED: package.json] |
| Backend config file | `backend/pyproject.toml` / test discovery under `backend/tests/` |
| Frontend config file | `vite.config.ts` (embedded `test:` block, `environment: 'jsdom'`) |
| Quick run command (backend) | `cd backend && venv/bin/python -m pytest tests/test_itam_<new_file>.py -q` |
| Quick run command (frontend) | `npx vitest run src/__tests__/ITAM<NewPanel>.test.tsx` |
| Full suite command | `cd backend && venv/bin/python -m pytest -q` (backend); `npx vitest run src/__tests__` (frontend, per `.planning/config.json` `workflow.test_command`) |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| ITAM-DAT-01 | Custom field definitions validate correctly; asset customFields validated against model fieldsets via new UI-facing route(s) | unit + integration (httpx `TestClient` against FastAPI app, mocked Mongo per existing `test_itam_catalog.py` convention) | `backend/venv/bin/python -m pytest backend/tests/test_itam_catalog.py -q` (existing coverage) + new `test_itam_customization.py` | ✅ existing partial / ❌ new file needed (Wave 0) |
| ITAM-DAT-02 | Every ITAM create/update/delete logs an audit entry; entity-filtered query returns only that entity's history | integration | `backend/venv/bin/python -m pytest backend/tests/test_itam_audit.py -q` | ❌ Wave 0 |
| ITAM-DAT-03 | CSV export produces a well-formed file for a given entity type; CSV import creates/rejects rows per validation | integration | `backend/venv/bin/python -m pytest backend/tests/test_itam_data_csv.py -q` | ❌ Wave 0 |
| ITAM-SET-01 | Global settings GET/POST round-trip persists and returns the same document | integration | `backend/venv/bin/python -m pytest backend/tests/test_itam_customization.py -q` | ❌ Wave 0 (may share file with ITAM-DAT-01's UI-facing test) |
| ITAM-SET-02 | Branding fields (logo/color) persist and are returned on GET | integration | same file as ITAM-SET-01 | ❌ Wave 0 |
| ITAM-SET-03 | Locale selection persists; UI renders selected locale's strings for at least 2 languages | unit (frontend, Vitest) + integration (backend persistence) | `npx vitest run src/__tests__/ITAMSettingsPanel.test.tsx` | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** run the specific new/modified test file's quick command above.
- **Per wave merge:** `backend/venv/bin/python -m pytest backend/tests/ -q -k itam` (all ITAM backend tests) + `npx vitest run src/__tests__` (all frontend tests).
- **Phase gate:** Full backend suite (`backend/venv/bin/python -m pytest -q`) and `npx vitest run src/__tests__` both green before `/gsd-verify-work`, matching this project's established convention of checking the full suite (not just new tests) at phase boundaries per STATE.md history.

### Wave 0 Gaps
- [ ] `backend/tests/test_itam_audit.py` — covers ITAM-DAT-02 (entity-filtered audit query + write-path integration)
- [ ] `backend/tests/test_itam_data_csv.py` — covers ITAM-DAT-03 (import/export round-trip, per-row validation rejection)
- [ ] `backend/tests/test_itam_customization.py` — covers ITAM-DAT-01 (Custom Fields Manager backing route, if a new route beyond the existing catalog PATCH is added), ITAM-SET-01/02 (settings GET/POST round-trip)
- [ ] `src/__tests__/ITAMActivityLogPanel.test.tsx`, `ITAMSettingsPanel.test.tsx`, `ITAMCustomFieldsManager.test.tsx`, `ITAMBulkImportExport.test.tsx` — frontend panel tests, following the existing `ITAMCatalogPanel.test.tsx`/`ITAMConsole.test.tsx` convention (both already present in `src/__tests__/`)
- [ ] No new test-framework install needed — pytest and Vitest are both already configured and working (`backend/venv/bin/pytest`, `vite.config.ts`'s `test:` block).

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | No (unchanged — relies on existing `get_current_user`/`TokenData`) | Existing `authentication_service.py` |
| V3 Session Management | No (unchanged) | Existing JWT/session handling |
| V4 Access Control | Yes | `require_permission("manage:assets")` / `require_permission("view:audit_log")` / `require_permission("manage:settings")` dependencies — clone the existing `_require_itam_admin` / `_require_admin` patterns exactly; do not hand-roll a new role-check |
| V5 Input Validation | Yes | Pydantic models for all new request bodies (`itam_models.py`); `validate_fieldsets`/`validate_custom_field_values` for custom-field payloads; server-side CSV row validation (never trust client-parsed rows) |
| V6 Cryptography | Yes (incidental) | The audit ledger's SHA-256 hash chaining is already implemented in `audit_service.py` — do not modify `_compute_hash`'s algorithm or field order, as that would break `verify_integrity()`'s backward-compatibility with already-written log entries |

### Known Threat Patterns for this stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| CSV import used to bulk-create assets bypassing per-field validation (e.g., a crafted CSV cell containing a `customFields` JSON blob that isn't validated against the model's fieldset) | Tampering | Route every imported row's `customFields` through `validate_custom_field_values` exactly as the manual-create path does — never a separate/looser import-specific validator |
| CSV export leaking cross-tenant data if the export query isn't tenant-scoped | Information Disclosure | Use the tenant-isolated `db` accessor (`get_database()` wrapped form) for the export query, not the raw `db._db` form used for `system_settings` |
| Audit log tampering / selective deletion to hide an unauthorized change | Repudiation | Already mitigated by the existing hash-chain (`verify_integrity`); ensure no new code path ever calls `db.audit_logs.delete_one`/`update_one` directly — all audit writes must go through `log_action_async` (append-only) |
| A non-admin escalating access via a newly-added ITAM settings endpoint that forgets the `_require_admin`-equivalent gate | Elevation of Privilege | Every new settings/branding-write endpoint must depend on a `require_permission`/`_require_admin` check, mirroring `settings_endpoints.py::_require_admin` exactly (see Pitfall 4 re: keeping the admin-role string set consistent) |
| CSV import zip-bomb / oversized-file DoS | Denial of Service | Enforce a reasonable file-size cap on the `UploadFile` (e.g., reject >5-10MB) before calling `.read()` — not currently enforced by the `compliance_framework_mgmt_endpoints.py` precedent this phase clones, so this is a phase-specific addition, not an inherited guarantee |

## Sources

### Primary (HIGH confidence — direct in-repo file reads this session)
- `backend/itam_catalog_service.py` — full read; fieldset validation engine
- `backend/itam_catalog_endpoints.py` — full read; catalog CRUD + model reference/fieldset validation hook
- `backend/itam_asset_endpoints.py` (lines 1-115) — manual asset creation + customFields validation call site
- `backend/audit_service.py` — full read; hash-chained ledger implementation
- `backend/audit_endpoints.py` — full read; existing `/api/audit-logs` routes
- `backend/settings_endpoints.py` — full read; `system_settings` persistence pattern
- `backend/database.py` (lines 100-220) — `TenantIsolatedDatabase`/`TenantIsolatedCollection` exemption list, `connect_to_mongo`
- `backend/tenant_endpoints.py` (lines 220-267) — existing platform-level branding endpoints
- `backend/export_service.py` (CSV generation section) — `_generate_csv` pattern
- `backend/compliance_framework_mgmt_endpoints.py` (import route) — `UploadFile`/`csv.DictReader` pattern
- `backend/itam_lifecycle_endpoints.py` (header + top) — router mounting/prefix conventions
- `backend/router_registry.py` (itam section) — confirms which ITAM routers are actually wired into the app
- `backend/rbac_utils.py` (`verify_permission`/`require_permission`) — RBAC dependency pattern
- `components/itam/ITAMConsole.tsx` — full read; tab registration shape
- `components/TenantBrandingSettings.tsx` — full read; existing branding UI/API shape
- `components/SettingsDashboard.tsx` (imports + view-type union) — existing platform Settings surface
- `services/apiService.ts` (`itamThrow`, `downloadComplianceReport`, `fetchCatalogEntities`) — client convention
- `backend/requirements.txt` (grep) — pandas/openpyxl/reportlab already-installed confirmation
- `package.json` (grep) — confirmed no i18n/CSV/Next.js frontend dependencies exist yet; React 19/Vite/Vitest versions
- `.planning/milestones/v4.1-phases/65-core-data-audit-customization/65-0{1,2,3,4}-PLAN.md` — read to positively confirm the Prisma/tRPC/Next.js assumptions being warned against
- `.planning/REQUIREMENTS.md`, `.planning/config.json` — requirement text and workflow toggles (nyquist_validation=true, security_enforcement=true, test_command)

### Secondary (MEDIUM confidence)
- `npm view i18next version` / `npm view react-i18next version` — live registry checks this session (26.3.6 / 17.0.11)

### Tertiary (LOW confidence — package identity only, not documentation-verified)
- i18next/react-i18next as "the standard React i18n solution" — training-knowledge claim, registry-existence-confirmed but not documentation-verified this session; see Assumptions Log A1

## Metadata

**Confidence breakdown:**
- Standard stack (backend): HIGH — every recommended pattern is copied from files read in full this session, not from external sources
- Standard stack (frontend i18n): MEDIUM — package identity confirmed live against npm registry, but not cross-checked against official i18next documentation this session
- Architecture: HIGH — directly grounded in verified in-repo conventions (router_registry.py, database.py exemption list, existing itam_* file pairs)
- Pitfalls: HIGH — each pitfall is either a directly-observed gap (zero `log_action_async` calls in ITAM code; `system_settings` absent from the exemption allowlist) or a directly-read prior failure (the discarded Prisma/tRPC plans)

**Research date:** 2026-08-12
**Valid until:** 2026-09-11 (30 days — stable in-repo conventions; re-verify npm package versions if this window elapses before planning executes)

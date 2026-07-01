---
phase: 08-bulk-evidence-upload
plan: "01"
subsystem: backend
tags: [bulk-upload, compliance, evidence, security, zip, fastapi]
dependency_graph:
  requires:
    - 07-01  # evidence_coc._append_coc_entry
    - 07-02  # compliance_evidence_lifecycle_endpoints (registered before bulk)
  provides:
    - POST /api/compliance/evidence/bulk endpoint (BULK-01)
    - Validate-all-before-commit bulk evidence commit (BULK-02)
    - Bulk evidence in control_evidence collection (BULK-03)
  affects:
    - backend/router_registry.py (compliance_bulk_evidence_endpoints in _REQUIRED_ROUTERS)
tech_stack:
  added: []
  patterns:
    - Two-pass validate-all-before-commit (pass 1 validates, pass 2 commits if errors == [])
    - Zip-bomb guard via sum(infolist file_size) before any zf.read()
    - Zip-slip guard via os.path.basename(raw_name.replace("\\", "/"))
    - Stored filename is uuid4().hex+ext — completely independent of zip entry name
    - tenantId sourced from JWT (get_current_user), never from request body
key_files:
  created:
    - backend/compliance_bulk_evidence_endpoints.py
    - backend/tests/test_bulk_evidence_upload.py
  modified:
    - backend/router_registry.py
decisions:
  - "compliance_bulk_evidence_endpoints.py is a new file — compliance_evidence_endpoints.py at 495 lines would breach 500-line limit"
  - "Validate-all-before-commit two-pass design — pass 1 validates; pass 2 commits atomically only if errors == []"
  - "Manifest is a Form string (JSON) field not a file upload — supports both hand-built and UI-built manifest flows"
  - "Zip-slip: zf.read(raw_name) uses manifest filename directly; os.path.basename for safe display name only"
  - "MAX_BULK_FILES=50, MAX_BULK_BYTES=200 MB uncompressed; per-file cap 25 MB"
metrics:
  duration: "~8m"
  completed_date: "2026-06-21"
  tasks_completed: 2
  tasks_total: 2
  files_created: 2
  files_modified: 1
status: complete
---

# Phase 08 Plan 01: Backend Bulk Evidence Upload Endpoint Summary

Two-pass validate-all-before-commit bulk evidence endpoint with zip-bomb/zip-slip guards and 12-test coverage for BULK-01/02/03.

## What Was Built

### Task 1 (T-08-01): compliance_bulk_evidence_endpoints.py — commit b72896d
New FastAPI router with single `POST /api/compliance/evidence/bulk` endpoint implementing:
- **Pass 0a**: Manifest JSON parse, field validation, entry count guard (≤50)
- **Pass 0b**: Zip bytes read, container size guard (≤200 MB), `zipfile.is_zipfile` check, uncompressed sum guard
- **Pass 1** (validate-all, no writes): For each manifest entry — zip-slip basename guard, extension allowlist, `zf.read(raw_name)` (KeyError → error), 25 MB size cap, `_check_magic()` magic-byte check
- Any error → `HTTPException(422, detail={"errors": [...]})` with zero commits
- **Pass 2** (commit, only if errors == []): `asyncio.to_thread(_write_binary, ...)`, `db.control_evidence.insert_one(record)`, `_append_coc_entry(...)` per file
- `tenantId` always from JWT (`getattr(current_user, "tenant_id", None)`)
- File: 199 lines (under 200-line goal)

### Task 2 (T-08-02): Router registration + test suite — commit 259498f
**router_registry.py** (2-line edit):
- Added `"compliance_bulk_evidence_endpoints"` to `_REQUIRED_ROUTERS` frozenset
- Added `_load(app, "compliance_bulk_evidence_endpoints", "router")` after lifecycle endpoints

**tests/test_bulk_evidence_upload.py** (new, 379 lines, 12 test functions):
| Test | Coverage |
|------|----------|
| `test_bulk_upload_valid` | BULK-01 happy path: 2 files → 200, committed=2 |
| `test_bulk_manifest_invalid_json` | BULK-01: bad JSON → 400 |
| `test_bulk_manifest_missing_fields` | BULK-01: missing control_id → 400 |
| `test_bulk_not_a_zip` | BULK-02: non-zip bytes → 400 |
| `test_bulk_extension_rejected` | BULK-02: .exe → 422 per-file error |
| `test_bulk_file_too_large` | BULK-02: >25 MB → 422 per-file error |
| `test_bulk_magic_mismatch` | BULK-02: PDF name + PNG magic → 422 (real _check_magic) |
| `test_bulk_missing_entry` | BULK-02: manifest refs file not in zip → 422 |
| `test_bulk_mixed_rejects_all` | BULK-02: 1 valid + 1 invalid → 422, 0 insert_one calls |
| `test_bulk_zip_slip_guard` | Security: ../evil.pdf → KeyError → 422 |
| `test_bulk_zip_bomb_guard` | Security: fake infolist 300 MB → 400 |
| `test_bulk_appears_in_control_evidence` | BULK-03: insert_one×2, controlId + source=manual |

**Result:** 12/12 tests pass.

## Verification

```
cd backend && python -m pytest tests/test_bulk_evidence_upload.py -x -q
12 passed in 1.45s
```

Route smoke test: `POST /api/compliance/evidence/bulk` confirmed in app.routes.

## Security Threat Mitigations

| Threat | Status |
|--------|--------|
| T-08-01 Spoofing (tenantId binding) | tenantId from JWT only |
| T-08-02 Zip slip | os.path.basename(raw_name.replace("\\","/")); stored name is uuid4().hex+ext |
| T-08-03 Cross-tenant injection | tenantId in record from JWT, never from manifest |
| T-08-04 Zip bomb | sum(infolist file_size) > MAX_BULK_BYTES (200 MB) → 400 |
| T-08-05 Large zip DoS | len(zip_content) > MAX_BULK_BYTES → 413; per-file 25 MB cap |
| T-08-06 Polyglot file | _check_magic() validates leading bytes vs extension |
| T-08-07 Non-zip MIME confusion | zipfile.is_zipfile() validates container |
| T-08-08 No audit trail | _append_coc_entry called per committed file (fire-and-forget) |

## Deviations from Plan

None — plan executed exactly as written.

## Known Stubs

None — endpoint is fully wired with real imports (UPLOAD_DIR, _write_binary, _check_magic, _append_coc_entry, get_database, get_current_user).

## Threat Flags

None — no new network endpoints, auth paths, or schema changes beyond what the plan's threat model covers.

## Self-Check: PASSED

- `backend/compliance_bulk_evidence_endpoints.py` — FOUND (199 lines)
- `backend/tests/test_bulk_evidence_upload.py` — FOUND (379 lines, 12 tests pass)
- `backend/router_registry.py` — FOUND (compliance_bulk_evidence_endpoints in _REQUIRED_ROUTERS and _load call)
- Commit b72896d — FOUND
- Commit 259498f — FOUND

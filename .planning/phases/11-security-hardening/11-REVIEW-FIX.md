---
phase: 11-security-hardening
fixed_at: 2026-07-02T18:00:00Z
review_path: .planning/phases/11-security-hardening/11-REVIEW.md
iteration: 1
findings_in_scope: 9
fixed: 9
skipped: 0
status: all_fixed
---

# Phase 11: Code Review Fix Report

**Fixed at:** 2026-07-02T18:00:00Z
**Source review:** .planning/phases/11-security-hardening/11-REVIEW.md
**Iteration:** 1

**Summary:**
- Findings in scope: 9 (2 Critical, 7 Warning — `fix_scope: critical_warning`)
- Fixed: 9
- Skipped: 0

Info findings IN-01 (`tenant_id` default) and IN-02 (`.docx`/`.xlsx` magic-byte collision in
`compliance_artifacts_endpoints.py`) were explicitly out of scope for this pass per instructions and
were not touched.

All 14 pre-existing tests in `backend/tests/test_bulk_evidence_upload.py` pass unchanged against the
fixed code (`python3 -m pytest tests/test_bulk_evidence_upload.py -q` → 14 passed).

## Fixed Issues

### CR-01: Rollback failure leaves DB records pointing at deleted files (broken evidence links)

**Files modified:** `backend/compliance_bulk_evidence_endpoints.py`
**Commit:** `7e9dc0d`
**Applied fix:** Made on-disk file cleanup conditional on the compensating `delete_many` having
succeeded. If DB rollback fails, files are now left intact alongside the (un-rolled-back) DB records
and a `logger.error` line documents that the batch requires manual reconciliation, rather than
unconditionally unlinking files that a surviving DB record still points at.
**Verification note:** This is a control-flow/logic fix (rollback ordering under failure). Tier 1
(re-read) and Tier 2 (`ast.parse` + full pytest run) passed, but per verification_strategy this is
flagged as `fixed: requires human verification` for the specific failure-cascade scenario (delete_many
itself failing) since that path is not covered by the existing test suite.

### CR-02: Rollback can be bypassed entirely on request cancellation

**Files modified:** `backend/compliance_bulk_evidence_endpoints.py`
**Commit:** `13b46bf`
**Applied fix:** Restructured the commit loop from `try/except Exception` to `try/finally` with a
`committed_ok` sentinel, so the rollback logic (including the CR-01 conditional-cleanup fix already
applied) now runs on `finally` and is reached for `asyncio.CancelledError` and other
`BaseException`-derived exceptions, not just `Exception` subclasses. On cancellation, cleanup runs and
the original cancellation continues propagating (no HTTPException is synthesized for a client that has
already disconnected); on an ordinary `Exception`, cleanup runs and the exception is caught by the
existing outer `except Exception` handler and converted to a 500, same end-user behavior as before.
**Verification note:** This is a logic/control-flow fix around Python `try/finally` propagation
semantics. Tier 1 and Tier 2 (syntax + full pytest pass) passed, but flagged as
`fixed: requires human verification` — the `CancelledError` cancellation path is inherently difficult to
unit test and was not exercised by the existing test suite.

### WR-01: Compensating `delete_many` rollback filter is not tenant-scoped

**Files modified:** `backend/compliance_bulk_evidence_endpoints.py`
**Commit:** `7fff9e7`
**Applied fix:** Added `"tenantId": tenant_id` to the rollback `delete_many` filter, matching every
other tenant-scoped query/write in the handler.

### WR-02: Encrypted/password-protected zip entries crash the request instead of producing a validation error

**Files modified:** `backend/compliance_bulk_evidence_endpoints.py`
**Commit:** `86092ec`
**Applied fix:** Added `RuntimeError` to the caught exception tuple for the per-entry bounded read, so
an encrypted/password-protected zip entry now produces a per-file 422 validation error instead of an
opaque 500.

### WR-03: Manifest entries are not validated for element type before use

**Files modified:** `backend/compliance_bulk_evidence_endpoints.py`
**Commit:** `f64cd5a`
**Applied fix:** Added an `isinstance(item, dict)` check before the existing membership checks, and an
`isinstance(..., str)` check on both `filename` and `control_id`, all raising `ValueError` (already
caught by the existing `except (json.JSONDecodeError, ValueError)` handler at manifest-parse time) so a
malformed-but-valid-JSON manifest (e.g. `[1, 2, 3]` or non-string fields) now returns 400 "Invalid
manifest" instead of an unhandled 500.

### WR-04: Orphaned file left on disk if `_write_binary` itself fails mid-write

**Files modified:** `backend/compliance_bulk_evidence_endpoints.py`
**Commit:** `5d1bffc`
**Applied fix:** Moved `written_paths.append(file_path)` to before the `await
asyncio.to_thread(_write_binary, ...)` call, so a partial/failed write is still tracked for cleanup. The
existing rollback loop already handles a missing file gracefully via `except OSError` (now with logging
per WR-07).

### WR-05: Post-commit cache invalidation failure returns a false 500 after a real, successful commit

**Files modified:** `backend/compliance_bulk_evidence_endpoints.py`
**Commit:** `04ed410`
**Applied fix:** Wrapped the four post-commit `invalidate_cache(...)` calls in their own
`try/except Exception`, logging via `logger.error` on failure instead of letting the exception bubble to
the outer handler and convert a fully-committed batch into a reported 500 (which would previously have
invited client retries and duplicate evidence records).

### WR-06: Authorization check uses a brittle, hardcoded case-sensitive role allowlist

**Files modified:** `backend/compliance_bulk_evidence_endpoints.py`
**Commit:** `f387de5`
**Applied fix:** Added `_WRITE_ROLES_NORMALIZED`, a lower-cased/separator-stripped derivative of
`_WRITE_ROLES`, and compare against it using a similarly normalized `user_role` instead of exact-string
membership. `_WRITE_ROLES` itself is left in place (still used to derive the normalized set) so no
other reference to it breaks.

### WR-07: File-cleanup failures during rollback are silently swallowed with no logging

**Files modified:** `backend/compliance_bulk_evidence_endpoints.py`
**Commit:** `e1ef12a`
**Applied fix:** Changed `except OSError: pass` to `except OSError as unlink_exc: logger.error(...)` in
the file-cleanup loop, matching the logging already present on the parallel DB-rollback failure branch.

## Skipped Issues

None — all 9 in-scope findings were fixed.

---

_Fixed: 2026-07-02T18:00:00Z_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 1_

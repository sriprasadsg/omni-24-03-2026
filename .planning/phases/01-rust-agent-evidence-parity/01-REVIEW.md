---
phase: "01"
status: clean
depth: standard
reviewed_at: 2026-06-17
files_reviewed: 3
files_reviewed_list:
  - backend/compliance_evidence_processor.py
  - backend/agent_heartbeat_endpoints.py
  - backend/tests/test_rust_heartbeat_parity.py
findings:
  critical: 2
  warning: 2
  info: 2
  total: 6
---

# Phase 01: Code Review Report

**Reviewed:** 2026-06-17
**Depth:** standard
**Files Reviewed:** 3
**Status:** findings

## Summary

Phase 1 adds `agent_type` propagation from Rust agent heartbeats through to both the top-level `asset_compliance` document and the embedded `evidence` records. The implementation is functionally correct for the happy path, but contains two blockers: a duplicate `evidence_id` bug triggered by any heartbeat carrying checks that share a compliance control ID (which is routine — 15 control IDs are shared among the 12 Rust checks shipped in this phase), and a wrong-field reference that corrupts the `memory_used_mb` metric. Two warnings cover a missing `try/finally` around the main processing loop that can leave the tenant context dirty, and a test gap in the unit test that does not verify `agent_type` inside the `$push`-embedded evidence record.

---

## Critical Issues

### CR-01: Duplicate `evidence_id` When Multiple Checks Share a Control ID

**File:** `backend/compliance_evidence_processor.py:199`

**Issue:** `evidence_id` is generated as `f"auto-ev-{agent_hostname}-{control_id}-{timestamp}"`. The `timestamp` is computed once at the start of the function (line 179) and reused for all iterations. When two different check names (e.g., `"Audit Logging Policy"` and `"PowerShell Script Block Logging"`) both map to the same control ID (e.g., `A.8.15`, `CC9.2`, `AU-2`), they produce an identical `evidence_id` string in a single call. Among the 12 Rust checks introduced in this phase, 15 control IDs are shared across multiple checks. This means every Rust heartbeat will produce multiple `evidence` sub-documents with colliding `id` fields in the same `asset_compliance` document. Downstream UI and integrity-verification code that relies on `id` uniqueness within the evidence array will silently encounter duplicate records.

Specifically confirmed shared controls for the 12 Rust checks:
- `A.8.22`: Firewall Profiles, Remote Desktop Service, SMBv1, WinRM Status
- `CC9.2` / `A.8.15`: Audit Logging Policy, PowerShell Script Block Logging
- `A.8.1`: BitLocker Encryption, Secure Boot
- `CC6.1`: BitLocker, UAC, Password Policy (Min Length)
- (11 additional)

**Fix:** Include `check_name` in the evidence ID to make it unique per (host, check, control, timestamp) tuple:

```python
# Line 199 — replace:
evidence_id = f"auto-ev-{agent_hostname}-{control_id}-{timestamp}"

# With:
import hashlib as _hashlib
_check_slug = _hashlib.sha256(check_name.encode()).hexdigest()[:8]
evidence_id = f"auto-ev-{agent_hostname}-{control_id}-{_check_slug}-{timestamp}"
```

---

### CR-02: Wrong Field Used for `memory_used_mb` Calculation — Stores CPU% as Memory

**File:** `backend/agent_heartbeat_endpoints.py:216`

**Issue:** Line 216 computes `memory_used_mb` by multiplying `meta.get("current_cpu", 0)` by `(total_memory_gb * 1024 / 100)`. This uses the CPU utilisation percentage instead of the memory utilisation percentage. The result is a nonsensical value that will corrupt the `agent_metrics` and `asset_metrics` collections. For example, an agent at 50% CPU and 80% memory usage with 16 GB RAM will record `memory_used_mb = 8192` (80% of 16 GB) but for the wrong reason — it would store `8192` only if CPU happened to equal memory; otherwise the stored value is wrong.

```python
# Line 216 — current (wrong):
"memory_used_mb": meta.get("current_cpu", 0) * (meta.get("total_memory_gb", 16) * 1024 / 100),

# Fix:
"memory_used_mb": meta.get("current_memory", 0) * (meta.get("total_memory_gb", 16) * 1024 / 100),
```

---

## Warnings

### WR-01: Tenant Context Not Restored on Exception in Main Processing Loop

**File:** `backend/compliance_evidence_processor.py:177-268`

**Issue:** Lines 161–170 use a `try/finally` to safely restore `old_tenant_id` during the tenant-lookup phase. However, the main processing loop (lines 181–266) runs after `set_tenant_id(tenant_id)` is called at line 177, and it is not wrapped in a `try/finally`. If any `await db.*` call inside the loop raises an exception, execution jumps to the caller's `except` block (line 237 in `agent_heartbeat_endpoints.py`) and line 268 — which restores `old_tenant_id` — is never reached.

`tenant_context` uses Python's `ContextVar`, and a `ContextVar` mutation in a coroutine is visible to the rest of the same coroutine's execution frame. A confirmed test shows that after an exception is caught by the caller, the modified ContextVar value remains. If any code in the heartbeat handler runs after line 238 and calls `get_tenant_id()`, it will see the wrong tenant.

**Fix:** Wrap the second `set_tenant_id` call and the entire processing loop in a `try/finally`:

```python
# Line 176-268 — restructure:
try:
    if tenant_id:
        set_tenant_id(tenant_id)

    timestamp = datetime.now(timezone.utc).isoformat()

    for check in compliance_data.get("compliance_checks", []):
        # ... existing loop body ...
        pass
finally:
    set_tenant_id(old_tenant_id)

# Remove the bare set_tenant_id(old_tenant_id) at line 268
```

---

### WR-02: Unit Test Does Not Verify `agent_type` in the Embedded Evidence Record

**File:** `backend/tests/test_rust_heartbeat_parity.py:109-113`

**Issue:** The RUST-02 assertion in `test_rust02_and_rust03_db_calls` checks that `args[1]["$set"].get("agent_type") == "rust"` for the second `update_one` call (the `$set`/`$push` variant). This verifies `agent_type` at the document level. However, it does not inspect `args[1]["$push"]["evidence"]["agent_type"]` to confirm that the value is also written into the embedded evidence record — which is the other write path introduced in this phase (line 244 of `compliance_evidence_processor.py`).

The live-mode test (`main()`) does perform this check at line 172 (`any(e.get("agent_type") == "rust" for e in doc.get("evidence", []))`), but it is not exercised by `pytest`. If a future refactor removes `agent_type` from the evidence dict, the unit test would continue to pass while the feature is broken.

**Fix:** Add an assertion in `test_rust02_and_rust03_db_calls` that inspects the `$push` payload:

```python
# After the existing agent_type check in the loop:
if len(args) >= 2 and "$push" in args[1]:
    pushed_evidence = args[1]["$push"].get("evidence", {})
    assert pushed_evidence.get("agent_type") == "rust", (
        f"$push evidence missing agent_type=rust: {pushed_evidence}"
    )
```

---

## Info

### IN-01: Sleep-Based Synchronization in Live-Mode Test Is Unreliable

**File:** `backend/tests/test_rust_heartbeat_parity.py:166`

**Issue:** `time.sleep(1)` is used to wait for the backend to process the heartbeat and write compliance records before querying the database. This is a timing-dependent assumption. On a loaded CI host or a slow MongoDB instance, one second may be insufficient. If the compliance evidence processor is ever made truly asynchronous (e.g., offloaded to Celery), this sleep will become permanently inadequate.

**Fix:** Replace the sleep with a poll-with-timeout loop:

```python
import time
deadline = time.monotonic() + 10
while time.monotonic() < deadline:
    records = list(db.asset_compliance.find({"assetId": TEST_ASSET_ID}))
    if records:
        break
    time.sleep(0.25)
assert records, "No asset_compliance records found within 10 seconds"
```

---

### IN-02: Deferred Import of `tenant_context` Inside Async Function Body

**File:** `backend/compliance_evidence_processor.py:156`

**Issue:** `from tenant_context import set_tenant_id, get_tenant_id` is placed inside the function body rather than at module level. While Python caches module imports and there is no performance concern at runtime, the deferred import hides the dependency from static analysis tools and linters, and also from the test's module-patching strategy (the test patches `sys.modules["tenant_context"]` before `process_automated_evidence` runs its import, which works but is fragile — if the import is ever hoisted to module level, the test's `patch.dict` approach will fail silently because the names will have already been bound).

**Fix:** Move the import to module level:

```python
# Top of compliance_evidence_processor.py, after existing imports:
from tenant_context import set_tenant_id, get_tenant_id
```

And update the test to patch at the correct binding site:

```python
with patch("compliance_evidence_processor.set_tenant_id") as mock_set, \
     patch("compliance_evidence_processor.get_tenant_id", return_value=None):
    ...
```

---

_Reviewed: 2026-06-17_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_

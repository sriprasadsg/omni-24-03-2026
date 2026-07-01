# Phase 1: Rust Agent Evidence Parity - Research

**Researched:** 2026-06-17
**Domain:** Rust agent heartbeat → compliance evidence pipeline
**Confidence:** HIGH (all findings from direct codebase inspection)

---

## Summary

The Rust agent already collects 12 compliance checks via PowerShell (caps.rs), merges them into a `{compliance_checks:[...]}` wrapper (caps3.rs), and inserts them as `meta.compliance_enforcement` in each heartbeat. The backend heartbeat handler already calls `process_automated_evidence()` when that key is present. However, three concrete gaps block RUST-01/02/03:

**Gap 1 (RUST-01, blocking):** `agent_heartbeat_endpoints.py` line 230 imports `process_automated_evidence` from `compliance_endpoints`, not from `compliance_evidence_processor`. This import works today only because `compliance_endpoints.py` line 5 re-exports it as `from compliance_evidence_processor import process_automated_evidence  # noqa: F401`. This is a fragile transitive dependency that is not obvious from reading the heartbeat handler.

**Gap 2 (RUST-02, blocking):** The `evidence_record` dict built in `compliance_evidence_processor.py` (lines 233-244) does not include `agent_type`. The Rust agent sets `meta.agent_type = "rust"` but that value is never read by `process_automated_evidence`. RUST-02 explicitly requires `agent_type: rust` to be preserved in evidence records.

**Gap 3 (RUST-03, verified):** All 12 Rust agent check names from caps.rs exactly match keys in `COMPLIANCE_CHECK_MAPPINGS`. No mapping gap exists. However, the backend imports from the wrong module (Gap 1) currently and the WinRM check name sent by the Rust agent is `"WinRM Status"` — which does map correctly.

**Primary recommendation:** Fix Gap 2 (add `agent_type` to evidence_record in `compliance_evidence_processor.py`) and add a direct import fix/comment for Gap 1, then write a simulated heartbeat integration test to validate end-to-end flow.

---

## Gaps Found

### GAP-1: Fragile import path for `process_automated_evidence`

**File:** `backend/agent_heartbeat_endpoints.py` line 230
**Code:** `from compliance_endpoints import process_automated_evidence`
**Actual location:** `backend/compliance_evidence_processor.py`

`compliance_endpoints.py` line 5 re-exports it: `from compliance_evidence_processor import process_automated_evidence  # noqa: F401`

This works today but is architecturally fragile. If `compliance_endpoints.py` is refactored and the re-export is removed, the heartbeat handler silently breaks. The planner should fix the import to go directly to `compliance_evidence_processor`.

**Requirement:** RUST-01
**Severity:** LOW risk today, HIGH fragility debt

---

### GAP-2: `agent_type` not written to evidence records (BLOCKING for RUST-02)

**File:** `backend/compliance_evidence_processor.py` lines 233-244

The `evidence_record` dict built per check contains:
```python
evidence_record = {
    "id": evidence_id,
    "name": f"System Check: {check_name}",
    "url": "#",
    "type": "application/json",
    "uploadedAt": timestamp,
    "assetId": asset_id,
    "controlId": control_id,
    "tenantId": tenant_id,
    "systemGenerated": True,
    "content": evidence_content,
}
```

There is no `agent_type` field. The Rust agent sends `meta.agent_type = "rust"` (agent.rs line 165) but `process_automated_evidence(agent_hostname, compliance_data, db)` does not receive the `agent_type` value — it only receives hostname and compliance_data dict.

**What must change:**
1. `process_automated_evidence` signature must accept an optional `agent_type` parameter (default `None` for backward compat with Python agent callers).
2. The `evidence_record` dict must include `"agent_type": agent_type` when the parameter is provided.
3. `agent_heartbeat_endpoints.py` line 231 must pass `meta.get("agent_type")` when calling `process_automated_evidence`.

**Requirement:** RUST-02
**Severity:** BLOCKING — RUST-02 cannot be satisfied without this change

---

### GAP-3: `asset_compliance` `$set` block does not record `agent_type` at the document level

**File:** `backend/compliance_evidence_processor.py` lines 254-263

The upsert `$set` block updates the parent `asset_compliance` document with:
```python
"$set": {
    "tenantId": tenant_id,
    "status": compliance_status,
    "checkName": check_name,
    "lastUpdated": timestamp,
    "lastAutomatedCheck": timestamp,
},
```

No `agent_type` at the document level either. Both the embedded evidence record and the parent document need `agent_type` for RUST-02 to be fully satisfied and for the frontend to know which agent produced this compliance check.

**Requirement:** RUST-02
**Severity:** BLOCKING (same fix as GAP-2, same file)

---

### GAP-4: `merge_compliance_checks` returns `Value::Null` when both inputs are empty

**File:** `agent-rust/src/caps3.rs` lines 14-24

```rust
pub fn merge_compliance_checks(a: Value, b: Value) -> Value {
    let mut checks: Vec<Value> = Vec::new();
    if let Some(arr) = a.get("compliance_checks").and_then(|v| v.as_array()) {
        checks.extend(arr.clone());
    }
    if let Some(arr) = b.get("compliance_checks").and_then(|v| v.as_array()) {
        checks.extend(arr.clone());
    }
    if checks.is_empty() { return Value::Null; }  // <-- returns null when both PS batches fail
    json!({"compliance_checks": checks})
}
```

When PowerShell is unavailable (e.g., non-Windows environment, agent running as restricted service), both `caps::run_compliance_check()` and `caps3::run_compliance_check_extended()` return `Value::Null`. `merge_compliance_checks` returns `Value::Null`. In `agent.rs` line 196, null values from `sec_data` are skipped: `if !v.is_null() { m.insert(k.clone(), v.clone()); }` — so `compliance_enforcement` is simply absent from `meta`. This is correct defensive behavior: no null is sent to the backend and no crash occurs. However, it means no evidence is produced for that heartbeat tick. This is expected and acceptable, not a bug.

**Requirement:** RUST-01 (informational, not a blocker)
**Severity:** INFORMATIONAL — existing null guard already handles this correctly

---

### GAP-5: `compliance_native.rs` output format not confirmed to match `{compliance_checks:[...]}` wrapper

**File:** `agent-rust/src/compliance_native.rs` (not read in detail)

In `agent.rs` line 389, `compliance_native::run_native_compliance()` result is passed as the first argument to `merge_compliance_checks`. The merge function expects the `{compliance_checks:[...]}` wrapper format. If `run_native_compliance()` returns a different shape, `merge_compliance_checks` will silently skip it (it checks `.get("compliance_checks")` — if missing, nothing is added). This is not a crash risk but could cause missing checks if the native module is the only source.

**Requirement:** RUST-01, RUST-03 (informational)
**Severity:** LOW — planner should verify `compliance_native.rs` output format

---

### RUST-03 VERIFICATION: All 12 check names mapped

The 12 check names from caps.rs PowerShell (lines 148-258):

| # | Check name in caps.rs | In COMPLIANCE_CHECK_MAPPINGS? | Mapping |
|---|----------------------|-------------------------------|---------|
| 1 | `Windows Firewall Profiles` | YES | A.8.22, PCI-1.1, PR.AC-1, CC6.6 |
| 2 | `Windows Defender Antivirus` | YES | A.8.7, PCI-5.1, CC6.8, DE.CM-4, hitrust-01.0 |
| 3 | `BitLocker Encryption` | YES | A.8.1, A.8.24, 164.312(a)(2)(iv), PCI-3.4, PR.DS-1, CC6.1 |
| 4 | `User Access Control` | YES | A.5.15, A.8.2, PR.AC-1, CC6.1 |
| 5 | `Remote Desktop Service` | YES | A.8.22, PCI-2.2, PR.AC-3, CC6.6 |
| 6 | `SMBv1 Protocol Disabled` | YES | A.8.8, A.8.22, PR.IP-1, CC7.2 |
| 7 | `Password Policy (Min Length)` | YES | A.5.15, A.8.2, A.8.5, PCI-8.1.1, PR.AC-1, CC6.1 |
| 8 | `Audit Logging Policy` | YES | A.8.15, A.8.16, PCI-10.1, DE.AE-1, CC9.2, fedramp-AU-2 |
| 9 | `Windows Update Service` | YES | A.8.8, PCI-6.2, ID.AM-1, CC7.3, DE.CM-6 |
| 10 | `PowerShell Script Block Logging` | YES | A.8.15, DE.CM-1, CC9.2, fedramp-AU-2 |
| 11 | `WinRM Status` | YES | A.8.22, PCI-2.2, PR.AC-3 |
| 12 | `Secure Boot` | YES | A.8.1, A.8.27, ID.AM-1, CC7.2 |

**RUST-03 verdict: All 12 checks are mapped. Zero mapping gaps.**

---

## Key Files

| File | Role | Phase Relevance |
|------|------|-----------------|
| `backend/compliance_evidence_processor.py` | Processes compliance checks → writes `asset_compliance` records | PRIMARY — Gap 2 and Gap 3 fixes go here |
| `backend/agent_heartbeat_endpoints.py` | Receives Rust agent heartbeat, calls `process_automated_evidence` | PRIMARY — import fix and `agent_type` pass-through go here |
| `backend/compliance_endpoints.py` | Re-exports `process_automated_evidence` (line 5) — only reason GAP-1 doesn't crash | REFERENCE ONLY — no change needed if import is fixed in heartbeat handler |
| `agent-rust/src/caps.rs` | The 12 compliance check PowerShell scripts, output format | READ-ONLY — correct as-is |
| `agent-rust/src/caps3.rs` | `merge_compliance_checks()` + extended batch checks | READ-ONLY — correct as-is |
| `agent-rust/src/agent.rs` | Heartbeat construction, `agent_type: "rust"` in meta, sec_data merge | READ-ONLY — correct as-is |
| `agent-rust/src/compliance_native.rs` | Native (non-PS) compliance checks — verify output format | VERIFY shape matches `{compliance_checks:[...]}` |
| `components/AssetComplianceList.tsx` | Renders evidence per control per asset | READ-ONLY — no filter on agent_type, shows all `evidence[]` |
| `components/FrameworkDetail.tsx` | Framework detail view linking to AssetComplianceList | READ-ONLY |
| `services/apiService.ts` | `fetchGlobalComplianceData` hits `/api/compliance/evidence` | READ-ONLY |
| `backend/compliance_evidence_endpoints.py` | Serves `GET /api/compliance/evidence` from `asset_compliance` collection | READ-ONLY — no agent_type filter, shows all records |

---

## Implementation Path

The implementation is entirely in the backend. No Rust agent code changes are needed.

### Step 1: Fix `process_automated_evidence` signature to accept `agent_type`

**File:** `backend/compliance_evidence_processor.py`

Change function signature from:
```python
async def process_automated_evidence(agent_hostname: str, compliance_data: dict, db) -> None:
```
To:
```python
async def process_automated_evidence(agent_hostname: str, compliance_data: dict, db, agent_type: str | None = None) -> None:
```

Add `agent_type` to the `evidence_record` dict (inside the per-control loop):
```python
evidence_record = {
    "id": evidence_id,
    "name": f"System Check: {check_name}",
    "url": "#",
    "type": "application/json",
    "uploadedAt": timestamp,
    "assetId": asset_id,
    "controlId": control_id,
    "tenantId": tenant_id,
    "systemGenerated": True,
    "content": evidence_content,
    "agent_type": agent_type,   # NEW — "rust" or None (Python agent)
}
```

Add `agent_type` to the `$set` block in the `asset_compliance` upsert:
```python
"$set": {
    "tenantId": tenant_id,
    "status": compliance_status,
    "checkName": check_name,
    "lastUpdated": timestamp,
    "lastAutomatedCheck": timestamp,
    "agent_type": agent_type,   # NEW
},
```

### Step 2: Pass `agent_type` from heartbeat handler

**File:** `backend/agent_heartbeat_endpoints.py` lines 228-233

Change:
```python
if "compliance_enforcement" in meta:
    try:
        from compliance_endpoints import process_automated_evidence
        await process_automated_evidence(payload.get("hostname", agent_id), meta["compliance_enforcement"], db)
    except Exception as e:
        logger.error("ERROR processing compliance evidence: %s", e)
```

To:
```python
if "compliance_enforcement" in meta:
    try:
        from compliance_evidence_processor import process_automated_evidence
        await process_automated_evidence(
            payload.get("hostname", agent_id),
            meta["compliance_enforcement"],
            db,
            agent_type=meta.get("agent_type"),   # NEW — "rust" for Rust agent, None for Python
        )
    except Exception as e:
        logger.error("ERROR processing compliance evidence: %s", e)
```

Note: The import is changed from `compliance_endpoints` to `compliance_evidence_processor` directly (fixing GAP-1 fragility as well).

### Step 3: Verify `compliance_native.rs` output format

**File:** `agent-rust/src/compliance_native.rs`

Read the file. Confirm `run_native_compliance()` returns a `Value` with shape `{"compliance_checks": [...]}`. If it returns a flat list or different wrapper, no code change is needed in caps3.rs (the merge silently skips unrecognized shapes), but the planner may want to document this.

### Step 4: Write a simulated heartbeat test

Create a test script (in `backend/` per CLAUDE.md convention, or as a standalone `test_rust_heartbeat.py`) that:
1. Constructs a minimal Rust-style heartbeat payload with `meta.compliance_enforcement` containing all 12 check names and `meta.agent_type = "rust"`.
2. POSTs to `/api/agents/{test_agent_id}/heartbeat` with a valid agent token.
3. Queries `asset_compliance` collection and asserts evidence records exist with `agent_type = "rust"` and correct `controlId` values.

This validates RUST-01, RUST-02, and RUST-03 in a single pass.

### Step 5: Frontend smoke check

Load the Compliance Frameworks view in the browser. Select a framework that includes controls mapped by the 12 checks (e.g., SOC 2 for CC6.x controls). Confirm evidence records appear in the control detail with "System Check:" name prefix and `agent_type: rust` visible in the content.

---

## Risks

### Risk 1: Tenant lookup may miss Rust agents not yet in `assets` collection

**Location:** `compliance_evidence_processor.py` lines 162-170

The function first looks up `asset-{hostname}` in `assets`, then falls back to `agents.find_one({"hostname": hostname})`. If the Rust agent has registered (and thus is in `agents`) but has not yet created an asset record (which happens on first heartbeat), the asset lookup fails and falls through to the agent lookup. The agent document lookup uses `hostname` — this works as long as the heartbeat payload includes `hostname` (which it does, agent.rs line 217).

**Risk level:** LOW — the fallback path works, but if both lookups fail (e.g., agent not yet in DB and no prior asset), `tenant_id` is `None` and the evidence record is written with `"tenantId": None`. This triggers the database fail-closed guard and records land under the emergency tenant ID, making them invisible.

**Mitigation:** In the heartbeat handler, `_hb_tenant_id` is already known from `verify_agent_key`. Pass `_hb_tenant_id` to `process_automated_evidence` as a fallback tenant hint, so it doesn't need to re-query the DB for tenant resolution. This is an enhancement beyond RUST-02 scope but worth flagging.

### Risk 2: `compliance_enforcement` null guard passes through `{}` empty dicts

**Location:** `agent.rs` line 196

The null guard is `if !v.is_null()` — it skips `Value::Null` but NOT an empty object `Value::Object({})`. If `merge_compliance_checks` returns an empty `{compliance_checks:[]}` wrapper (not null), the backend will call `process_automated_evidence` with `compliance_data = {"compliance_checks": []}`, iterate zero checks, and return without writing any evidence. No error, no evidence. This is correct behavior but could cause confusion during debugging if developers expect evidence to appear for a zero-check heartbeat.

**Risk level:** LOW — not a bug, but a debugging footgun.

### Risk 3: Duplicate evidence IDs when hostname is long

**Location:** `compliance_evidence_processor.py` line 199

```python
evidence_id = f"auto-ev-{agent_hostname}-{control_id}-{timestamp}"
```

The `$pull` before `$push` (lines 247-249) removes old evidence for the same check name before inserting the new one, so duplicates are cleaned up. But the ID itself is timestamp-based and unique enough. No risk.

### Risk 4: `caps3.rs` `ps_json` function returns `Value::Null` on PS parse failure (not `{compliance_checks:[]}`)

**Location:** `agent-rust/src/caps3.rs` line 10

```rust
fn ps_json(s: &str) -> Value {
    if s.is_empty() || s == "null" { return Value::Null; }
    serde_json::from_str(s).unwrap_or(Value::Null)   // returns Null on parse error
}
```

If PowerShell outputs malformed JSON (partial output, error messages prepended), `ps_json` returns `Value::Null`. `merge_compliance_checks` receives `Value::Null` for that batch and silently skips it. The null guard in `agent.rs` then skips inserting `compliance_enforcement` entirely. No crash, but no evidence for that heartbeat tick.

**Risk level:** LOW — expected defensive behavior; no action needed.

---

## Validation Architecture

### How to verify RUST-01

Trigger `process_automated_evidence` is actually called via the Rust heartbeat path:

```bash
# Simulated Rust heartbeat payload (replace token and agent_id)
curl -X POST http://localhost:5000/api/agents/TEST-RUST-001/heartbeat \
  -H "Authorization: Bearer <agent_token>" \
  -H "Content-Type: application/json" \
  -d '{
    "status": "Online",
    "platform": "Windows",
    "version": "2.0.0-rust",
    "hostname": "test-rust-host",
    "meta": {
      "agent_type": "rust",
      "compliance_enforcement": {
        "compliance_checks": [
          {"check": "Windows Firewall Profiles", "status": "Pass", "details": "All profiles enabled"},
          {"check": "Windows Defender Antivirus", "status": "Pass", "details": "Enabled"},
          {"check": "BitLocker Encryption", "status": "Warning", "details": "Not enabled on C:"},
          {"check": "User Access Control", "status": "Pass", "details": "UAC enabled"},
          {"check": "Remote Desktop Service", "status": "Pass", "details": "RDP disabled"},
          {"check": "SMBv1 Protocol Disabled", "status": "Pass", "details": "SMBv1 disabled"},
          {"check": "Password Policy (Min Length)", "status": "Pass", "details": "MinLen:10"},
          {"check": "Audit Logging Policy", "status": "Pass", "details": "Audit policies configured"},
          {"check": "Windows Update Service", "status": "Pass", "details": "wuauserv Running"},
          {"check": "PowerShell Script Block Logging", "status": "Warning", "details": "Not configured"},
          {"check": "WinRM Status", "status": "Pass", "details": "WinRM not running"},
          {"check": "Secure Boot", "status": "Pass", "details": "Secure Boot enabled"}
        ]
      }
    }
  }'
```

Expected: HTTP 200 `{"success": true}`, backend logs show "Auto-mapped Windows Firewall Profiles -> A.8.22" (and 11 more).

### How to verify RUST-02

After the heartbeat above, query MongoDB:
```python
# In a Python shell connected to MongoDB
import pymongo
client = pymongo.MongoClient("mongodb://localhost:27017")
db = client.omni_platform

# Check evidence record has agent_type: rust
record = db.asset_compliance.find_one({"assetId": "asset-test-rust-host", "controlId": "A.8.22"})
assert record is not None
assert record.get("agent_type") == "rust"
assert any(e.get("agent_type") == "rust" for e in record.get("evidence", []))
print("RUST-02: PASS")
```

### How to verify RUST-03

After the heartbeat, check that all 12 checks produced records:
```python
controls_expected = [
    "A.8.22",  # Firewall Profiles
    "A.8.7",   # Defender
    "A.8.1",   # BitLocker
    "A.5.15",  # UAC
    "PR.AC-3", # RDP
    "PR.IP-1", # SMBv1
    "CC6.1",   # Password Policy
    "CC9.2",   # Audit Logging
    "CC7.3",   # Windows Update
    "DE.CM-1", # PS Script Block
    "PR.AC-3", # WinRM
    "CC7.2",   # Secure Boot
]
for ctrl in controls_expected:
    r = db.asset_compliance.find_one({"assetId": "asset-test-rust-host", "controlId": ctrl})
    if r:
        print(f"  {ctrl}: FOUND")
    else:
        print(f"  {ctrl}: MISSING <-- FAIL")
```

### Frontend validation

1. Navigate to Compliance Frameworks in the UI.
2. Click on any framework containing CC6.6 (e.g., SOC 2).
3. Open control CC6.6.
4. Confirm "System Check: Windows Firewall Profiles" evidence entry appears for asset "test-rust-host".
5. Open the evidence viewer and confirm content includes "Asset: test-rust-host" and "Check Name: Windows Firewall Profiles".

---

## Appendix: Data Flow Trace

```
Rust agent (agent.rs, every 10 ticks)
  → caps::run_compliance_check()         → {compliance_checks: [12 items]}
  → caps3::run_compliance_check_extended() → {compliance_checks: [28 items]}
  → compliance_native::run_native_compliance() → {compliance_checks: [...]} (verify shape)
  → caps3::merge_compliance_checks(native, caps, caps3_ext) → {compliance_checks: [N items]}
  → sec_cache["compliance_enforcement"] = merged

Heartbeat (every tick)
  → meta["compliance_enforcement"] = sec_cache["compliance_enforcement"]
  → meta["agent_type"] = "rust"
  → POST /api/agents/{id}/heartbeat

Backend (agent_heartbeat_endpoints.py)
  → if "compliance_enforcement" in meta:
      → process_automated_evidence(hostname, meta["compliance_enforcement"], db, agent_type=meta.get("agent_type"))

compliance_evidence_processor.py
  → tenant lookup (asset-{hostname} → agent by hostname fallback)
  → for each check in compliance_checks:
      → lookup COMPLIANCE_CHECK_MAPPINGS[check_name] → [control_ids]
      → for each control_id:
          → build evidence_record (WITH agent_type after fix)
          → db.asset_compliance.update_one(upsert=True, $push evidence)
          → db.asset_compliance.update_one($set status, agent_type)

Frontend
  → GET /api/compliance/evidence → returns all asset_compliance docs with evidence[]
  → FrameworkDetail → AssetComplianceList → EvidenceMarkdownViewer
  → Shows "System Check: {check_name}" evidence entries (no filter on agent_type)
```

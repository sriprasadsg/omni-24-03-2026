# Phase 1: Rust Agent Evidence Parity - Pattern Map

**Mapped:** 2026-06-17
**Files analyzed:** 2 (modified) + 2 (verified read-only)
**Analogs found:** 2 / 2 (self-contained; both modified files are the authoritative pattern)

---

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `backend/compliance_evidence_processor.py` | service | request-response (CRUD write) | self (existing function extended) | exact |
| `backend/agent_heartbeat_endpoints.py` | controller/endpoint | request-response | self (existing call-site patched) | exact |
| `agent-rust/src/compliance_native.rs` | utility (read-only verify) | transform | n/a — verified correct | n/a |
| `agent-rust/src/caps3.rs` | utility (read-only verify) | transform | n/a — verified correct | n/a |

---

## Verified: `agent-rust/src/compliance_native.rs`

**Status:** Output format CONFIRMED correct. No change required.

`run_native_compliance()` (line 64) returns:
```rust
json!({"compliance_checks": c})   // line 284
```
This matches the `{"compliance_checks": [...]}` wrapper expected by `caps3::merge_compliance_checks`. GAP-5 from RESEARCH.md is resolved — the native module wraps correctly.

The 28 check names emitted by `compliance_native.rs` all use names present in `COMPLIANCE_CHECK_MAPPINGS` (e.g., `"BitLocker Encryption"`, `"WinRM Status"`, `"TLS Security Configuration"`, `"LLMNR/NetBIOS Protection"`, etc.).

---

## Pattern Assignments

### `backend/compliance_evidence_processor.py` (service, CRUD write)

**Change type:** Function signature extension + dict field additions  
**Lines to modify:** 147 (signature), 233–244 (evidence_record dict), 253–259 ($set block)

**Current function signature** (line 147):
```python
async def process_automated_evidence(agent_hostname: str, compliance_data: dict, db) -> None:
```

**Target signature** (add `agent_type` as optional trailing parameter):
```python
async def process_automated_evidence(agent_hostname: str, compliance_data: dict, db, agent_type: str | None = None) -> None:
```

Rationale: trailing optional preserves backward compatibility with all existing callers (Python agent, compliance_endpoints re-export, any admin task handlers) that do not pass `agent_type`.

---

**Current `evidence_record` dict** (lines 233–244):
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

**Target `evidence_record` dict** (add `agent_type` field after `systemGenerated`):
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
    "agent_type": agent_type,
}
```

---

**Current `$set` block** (lines 253–259):
```python
"$set": {
    "tenantId": tenant_id,
    "status": compliance_status,
    "checkName": check_name,
    "lastUpdated": timestamp,
    "lastAutomatedCheck": timestamp,
},
```

**Target `$set` block** (add `agent_type` field):
```python
"$set": {
    "tenantId": tenant_id,
    "status": compliance_status,
    "checkName": check_name,
    "lastUpdated": timestamp,
    "lastAutomatedCheck": timestamp,
    "agent_type": agent_type,
},
```

---

### `backend/agent_heartbeat_endpoints.py` (controller, request-response)

**Change type:** Import fix + keyword argument addition  
**Lines to modify:** 228–233

**Current compliance_enforcement block** (lines 228–233):
```python
if "compliance_enforcement" in meta:
    try:
        from compliance_endpoints import process_automated_evidence
        await process_automated_evidence(payload.get("hostname", agent_id), meta["compliance_enforcement"], db)
    except Exception as e:
        logger.error("ERROR processing compliance evidence: %s", e)
```

**Target compliance_enforcement block:**
```python
if "compliance_enforcement" in meta:
    try:
        from compliance_evidence_processor import process_automated_evidence
        await process_automated_evidence(
            payload.get("hostname", agent_id),
            meta["compliance_enforcement"],
            db,
            agent_type=meta.get("agent_type"),
        )
    except Exception as e:
        logger.error("ERROR processing compliance evidence: %s", e)
```

Two changes:
1. Import changed from `compliance_endpoints` to `compliance_evidence_processor` directly (fixes GAP-1 fragile transitive re-export).
2. `agent_type=meta.get("agent_type")` added as keyword argument (fixes GAP-2/GAP-3, satisfies RUST-02).

**Pattern reference for import style:** The file already uses this same lazy-import-inside-try pattern for other services at lines 247, 282, 300, 319, etc. (e.g., `from streaming_service import broker`, `from ueba_service import persist_security_alert`). The compliance import should follow the same pattern.

**Pattern reference for `meta.get(...)` access:** The `meta` variable is already assigned at line 226 (`meta = payload.get("meta", {})`). All other meta key reads in this file use `meta.get(key)` (lines 100, 131–183, 253–294, etc.) — the new `meta.get("agent_type")` follows identical existing convention.

---

## Shared Patterns

### Error Handling (try/except around side-effect pipelines)
**Source:** `backend/agent_heartbeat_endpoints.py` lines 228–233 (and identical pattern at lines 407–420)  
**Apply to:** The compliance_enforcement block (already uses this pattern — preserve it)
```python
try:
    from module import function
    await function(...)
except Exception as e:
    logger.error("ERROR processing ...: %s", e)
```
Non-fatal: errors are logged but do not abort the heartbeat response. The `return {"success": True}` at line 422 is always reached.

### Optional trailing parameter (backward-compatible extension)
**Source:** Python typing convention used throughout this codebase  
**Apply to:** `process_automated_evidence` signature extension
```python
async def process_automated_evidence(agent_hostname: str, compliance_data: dict, db, agent_type: str | None = None) -> None:
```
`str | None` union syntax (PEP 604) is already used in this file at line 147's peer functions and in other backend files. Default `None` ensures all existing callers work without modification.

### `meta.get()` for optional meta fields
**Source:** `backend/agent_heartbeat_endpoints.py` lines 100–183 (all meta field reads)  
**Apply to:** Reading `agent_type` from meta in heartbeat handler  
```python
meta.get("agent_type")   # returns None if key absent (Python agent heartbeats)
```

---

## No Analog Found

None. Both files to be modified are fully self-contained changes to existing functions with clear existing patterns to follow.

---

## Metadata

**Analog search scope:** `backend/`, `agent-rust/src/`  
**Files read:** `backend/compliance_evidence_processor.py` (267 lines), `backend/agent_heartbeat_endpoints.py` (423 lines), `agent-rust/src/compliance_native.rs` (285 lines)  
**Pattern extraction date:** 2026-06-17

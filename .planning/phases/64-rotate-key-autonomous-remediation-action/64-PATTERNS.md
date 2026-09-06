# Phase 64: rotate_key autonomous-remediation action - Pattern Map

**Mapped:** 2026-08-11
**Files analyzed:** 8 (2 new Rust modules, 2 edited Rust files, 3 edited Python files, 1 new YAML file)
**Analogs found:** 8 / 8

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|--------------------|------|-----------|-----------------|---------------|
| `agent-install/omni-agent-rs/src/capabilities/remediation_actions.rs` (EDIT: add `rotate_key`) | service (action-arm) | event-driven | itself — `block_ip`/`restore_file` fns in same file | exact |
| `agent-install/omni-agent-rs/src/capabilities/ssh_key_rotation.rs` (NEW) | utility | file-I/O | `remediation_actions.rs` (validation + privileged-op shape) | role-match |
| `agent-install/omni-agent-rs/src/capabilities/ssh_key_checks.rs` (NEW) | utility | transform | `vulnerability_scan.rs`'s misconfig-check functions | role-match |
| `agent-install/omni-agent-rs/src/instructions.rs` (EDIT: add `"rotate_key"` dispatch arm) | route/dispatcher | request-response | same file's `"block_ip"`/`"disable_service"` arms (lines 444-464) | exact |
| `backend/remediation_playbook_service.py` (EDIT: `ACTION_MAP` + `select_playbook()`) | service | CRUD | itself — existing `vuln` branch (lines 121-125) | exact |
| `backend/playbooks/rotate_key.yaml` (NEW) | config | event-driven | `backend/playbooks/block_ip.yaml` (reversible, destructive) | exact |
| `backend/agent_vuln_ingest_service.py` (EDIT: add `fingerprint` to `set_fields`) | service | CRUD | itself — existing `set_fields` dict (lines 80-95) | exact |
| `backend/tests/test_remediation_playbook.py` (EDIT: add rotate_key case) | test | request-response | existing tests in same file | exact |

## Pattern Assignments

### `agent-install/omni-agent-rs/src/capabilities/remediation_actions.rs` — add `pub async fn rotate_key(...)`

**Analog:** `block_ip` (lines 179-204) for the platform-gated privileged-op shape; `restore_file` (lines 153-177) for the "refuse without required backing data" shape.

**Error enum to extend** (lines 29-49) — add a new variant rather than reusing an existing one (e.g. `RemediationError::LockoutRefused(String)` for D-05's sole-entry refusal), matching the existing one-variant-per-failure-class convention:
```rust
#[derive(Debug, thiserror::Error)]
pub enum RemediationError {
    #[error("Invalid target: {0}")]
    InvalidTarget(String),
    // ... existing variants ...
    #[error("Operation failed: {0}")]
    OperationFailed(String),
}
```

**Core pattern — platform gate + delegate to helper module** (mirrors `block_ip`, lines 181-204):
```rust
pub async fn block_ip(ip_address: &str) -> Result<(), RemediationError> {
    let ip = validate_ip(ip_address)?;
    #[cfg(target_os = "linux")]
    { run_privileged_command("iptables", &["-I", "INPUT", "-s", &ip.to_string(), "-j", "DROP"]) }
    #[cfg(target_os = "windows")]
    { /* ... */ }
    #[cfg(not(any(target_os = "linux", target_os = "windows")))]
    { Err(RemediationError::OperationFailed("block_ip is unsupported on this platform.".to_string())) }
}
```
`rotate_key` inverts this: gate IN on `#[cfg(any(target_os = "linux", target_os = "macos"))]`, refuse cleanly on everything else (Windows explicitly per Pitfall 3 in RESEARCH.md). Body should call into `ssh_key_rotation.rs` helpers rather than growing this file further — see "Don't Hand-Roll" and Pitfall 5 in RESEARCH.md (this file is already 424 lines, over the project's 500-line cap once new logic lands).

**Refuse-without-required-data pattern** (mirrors `restore_file`, lines 157-177) — apply this shape for D-05's sole-entry refusal and D-04's fingerprint-not-found refusal: validate/count first, return a structured `Err` before touching the filesystem, never guess.

**Privileged/test-stub convention** (lines 51-75) — if any part of `rotate_key` needs an OS-level call (none obviously required — file I/O only, no subprocess), it must use `run_privileged_command`'s `#[cfg(not(test))]` / `#[cfg(test)]` split so unit tests stay hermetic. File writes (authorized_keys edit, keypair write) don't need this — they can be tested directly with `tempfile`-based fixtures like the "Don't Hand-Roll" section recommends.

**Denylist pattern** (lines 21-27, `CRITICAL_PROCESS_NAMES`/`CRITICAL_SERVICE_NAMES`) — explicitly NOT needed per D-04 (fingerprint-exact targeting is the substitute safety mechanism), but the module-level `const` convention is the place to put any hard-coded refusal list if one becomes necessary later.

**Test module convention** (line 296, `mod tests`) — add `rotate_key` tests into a new `#[cfg(test)] mod tests` block in `ssh_key_rotation.rs`/`ssh_key_checks.rs`, following the existing inline-test-in-same-file convention used throughout this crate.

---

### `agent-install/omni-agent-rs/src/instructions.rs` — add `"rotate_key"` dispatch arm

**Analog:** `"block_ip"` / `"disable_service"` arms (lines 444-464):
```rust
"disable_service" => {
    let service = item.get("parameters").and_then(|p| p.get("service_name")).and_then(|v| v.as_str()).unwrap_or("");
    match crate::capabilities::remediation_actions::disable_service(service).await {
        Ok(()) => serde_json::json!({"status": "success", "message": "Service disable initiated"}),
        Err(e) => serde_json::json!({"status": "error", "error": e.to_string()}),
    }
}
```

**New arm shape** — extract `fingerprint` and `authorized_keys_path` from `item.parameters` (mirrors `restore_file`'s two-param extraction at lines 436-442), call `remediation_actions::rotate_key(...)`, and on success include `new_fingerprint`/`new_comment` in the JSON (never the private key — D-09):
```rust
"rotate_key" => {
    let fingerprint = item.get("parameters").and_then(|p| p.get("fingerprint")).and_then(|v| v.as_str()).unwrap_or("");
    let path = item.get("parameters").and_then(|p| p.get("authorized_keys_path")).and_then(|v| v.as_str()).unwrap_or("");
    match crate::capabilities::remediation_actions::rotate_key(fingerprint, path).await {
        Ok((new_fp, new_comment)) => serde_json::json!({
            "status": "success", "message": "Key rotated",
            "new_fingerprint": new_fp, "new_comment": new_comment
        }),
        Err(e) => serde_json::json!({"status": "error", "error": e.to_string()}),
    }
}
```
Insert before the `_ => { ... }` fallback arm at line 472.

---

### `backend/remediation_playbook_service.py` — extend `ACTION_MAP` + `select_playbook()`

**Analog:** the module itself — no external analog needed, this is a direct edit to an existing dispatcher.

**`ACTION_MAP` edit** (lines 22-33) — remove the "intentionally absent" comment (line 24) and add the new entry:
```python
ACTION_MAP: Dict[str, str] = {
    "patch_package": "upgrade_software",
    "kill_process": "kill_process",
    "restore_file": "restore_file",
    "block_ip": "block_ip",
    "unblock_ip": "unblock_ip",
    "disable_service": "disable_service",
    "enable_service": "enable_service",
    "rotate_key": "rotate_key",
}
```

**`select_playbook()` vuln branch edit** (lines 121-125) — insert the `playbook_ref` check BEFORE the `cveId` check (per RESEARCH.md Pitfall 1 — the YAML `match:` block is inert, this Python if/elif chain is the only real routing mechanism):
```python
if finding_type == "vuln":
    if details.get("playbook_ref") == "rotate_key":
        return by_name.get("rotate_key")
    cve_id = details.get("cveId") or details.get("cve_id")
    if cve_id:
        return by_name.get("patch_package")
    return by_name.get("disable_service")
```

**Docstring edit** (lines 96-103) — add a `rotate_key` line to the finding_class mapping comment, matching the existing style (e.g. `vuln + playbook_ref == "rotate_key" -> rotate_key`).

---

### `backend/playbooks/rotate_key.yaml` (NEW)

**Analog:** `backend/playbooks/block_ip.yaml` (full file, 15 lines) — same shape: reversible + destructive + real rollback steps (as opposed to `restore_file.yaml`'s `rollback: []` escalate-only pattern, since D-06 requires `rotate_key` to be reversible).

```yaml
name: block_ip
finding_class: nscan
match:
  scan_type: ip
steps:
  - action: block_ip
    params:
      ip_address: "{{finding.resource_id}}"
    destructive: true
# Reversible — unblock_ip removes the firewall rule this playbook adds.
rollback:
  - action: unblock_ip
    params:
      ip_address: "{{finding.resource_id}}"
```

**Apply as:**
```yaml
name: rotate_key
finding_class: vuln
match:
  playbook_ref: rotate_key   # documentation only — select_playbook() does the real routing
steps:
  - action: rotate_key
    params:
      fingerprint: "{{finding.details.fingerprint}}"
      authorized_keys_path: "{{finding.details.affected_path}}"
    destructive: true
# Reversible — mirrors restore_file's baseline/backup approach (D-06). If the
# rotate_key Rust action snapshots the whole authorized_keys file before
# editing (RESEARCH.md's recommended approach, see Open Question 2), the
# rollback step can reuse restore_file verbatim with zero new Rust code:
rollback:
  - action: restore_file
    params:
      path: "{{finding.details.affected_path}}"
      backup_path: "{{finding.details.rotate_key_backup_path}}"
```
NOTE: confirm backup-path plumbing (how the backup path gets from the agent's rotate_key result back into a rollback-step param) during implementation — this is Open Question 2 in RESEARCH.md, not fully resolved by pattern-mapping alone.

---

### `backend/agent_vuln_ingest_service.py` — add `fingerprint` to `set_fields`

**Analog:** the existing `set_fields` dict itself (lines 80-95):
```python
set_fields: Dict[str, Any] = {
    "cveId": cve_id,
    "cvss": cvss,
    "cvssScore": cvss,
    "severity": severity,
    "type": f.get("type"),
    "remediation_hint": f.get("remediation_hint"),
    "playbook_ref": f.get("playbook_ref"),
    "detail": detail,
    "description": detail or (cve_id or ""),
    "package": affected,
    "affectedSoftware": affected,
    "source": "agent",
    "status": "Open",
    "last_seen": now,
}
```
**Apply as:** add `"fingerprint": f.get("fingerprint"),` as a new key, following the exact same `f.get(...)` pass-through convention already used for `remediation_hint`/`playbook_ref`. Per RESEARCH.md Pitfall 4, this allowlist is a fixed set of keys — any Rust-scanner-emitted field not added here is silently dropped at ingest. This is a one-line addition, matching Option (b) recommended in RESEARCH.md's Assumptions Log (A3).

---

## Shared Patterns

### RemediationError enum + non-panicking Result shape
**Source:** `agent-install/omni-agent-rs/src/capabilities/remediation_actions.rs` lines 29-49
**Apply to:** `rotate_key` and any new helper functions in `ssh_key_rotation.rs`/`ssh_key_checks.rs` — every fallible operation returns `Result<T, RemediationError>`, never panics, uses `thiserror::Error` for display strings.

### Agent instruction dispatch → JSON status/error shape
**Source:** `agent-install/omni-agent-rs/src/instructions.rs` lines 429-471
**Apply to:** the new `"rotate_key"` arm — `Ok(...) => {"status": "success", ...}` / `Err(e) => {"status": "error", "error": e.to_string()}`, params always extracted via `item.get("parameters").and_then(...).and_then(|v| v.as_str()).unwrap_or("")`.

### Deterministic playbook selection (no LLM, pure if/elif)
**Source:** `backend/remediation_playbook_service.py` `select_playbook()` lines 91-134
**Apply to:** the new `rotate_key` branch — must be a Python code branch, NOT a YAML `match:` block edit alone (RESEARCH.md Pitfall 1 — the strongest cross-cutting risk in this phase).

### YAML playbook schema (destructive + reversible with rollback)
**Source:** `backend/playbooks/block_ip.yaml` (full file)
**Apply to:** `rotate_key.yaml` — `{name, finding_class, match, steps: [{action, params, destructive: true}], rollback: [{action, params}]}`.

### Fixed-allowlist ingest field pass-through
**Source:** `backend/agent_vuln_ingest_service.py` `set_fields` dict, lines 80-95
**Apply to:** any new Rust-scanner-emitted finding field (`fingerprint`) that needs to survive into `db.vulnerabilities` — must be explicitly added here, no wildcard passthrough exists.

### Module size discipline (CLAUDE.md 500-line cap)
**Source:** project constraint, reinforced by `remediation_actions.rs` (424 lines) and `vulnerability_scan.rs` (593 lines, already over) being near/over the cap
**Apply to:** put new SSH-key logic in two new focused modules — `ssh_key_checks.rs` (shared weak-key-detection predicate, used by both the scanner and the D-07 re-verify step) and `ssh_key_rotation.rs` (authorized_keys parse/backup/atomic-write/keygen mechanics) — `remediation_actions.rs` and `vulnerability_scan.rs` should each only gain a small integration call site.

## No Analog Found

| File | Role | Data Flow | Reason |
|------|------|-----------|--------|
| `agent-install/omni-agent-rs/src/capabilities/ssh_key_checks.rs` (NEW) | utility | transform | No existing SSH-key parsing/weak-key-detection code anywhere in the codebase (confirmed via exhaustive grep in RESEARCH.md) — closest structural precedent is `vulnerability_scan.rs`'s existing misconfig-check functions (e.g. `check_sshd()`) for the "emit a finding with playbook_ref" shape, but the actual key-parsing logic (RSA bit-length / DSA-type detection via the `ssh-key` crate) has no prior art in this repo |
| `agent-install/omni-agent-rs/src/capabilities/ssh_key_rotation.rs` (NEW) | utility | file-I/O | No existing atomic-file-replace-with-backup or SSH-keypair-generation code in the repo (confirmed via grep) — closest partial analogs are `restore_file`'s backup-based restore shape (for the rollback-source pattern) and `feed_bundle.rs`'s use of `ed25519-dalek` (for the crypto-primitive precedent), but neither covers keygen or `authorized_keys` line editing directly |

## Metadata

**Analog search scope:** `agent-install/omni-agent-rs/src/capabilities/`, `agent-install/omni-agent-rs/src/instructions.rs`, `backend/remediation_playbook_service.py`, `backend/playbooks/*.yaml`, `backend/agent_vuln_ingest_service.py`, `backend/remediation_audit_service.py`, `backend/tests/test_remediation_playbook.py`
**Files scanned:** 10 (all directly read this session; RESEARCH.md's own exhaustive prior grep for SSH-key code confirmed zero hits, reused rather than re-run)
**Pattern extraction date:** 2026-08-11

# Phase 64: rotate_key autonomous-remediation action - Research

**Researched:** 2026-08-11
**Domain:** Rust host-agent SSH-key remediation + Python deterministic playbook engine (extends Phase 53/51)
**Confidence:** HIGH (code patterns, exact signatures, exact file locations — all read directly from the shipped tree) / MEDIUM (crate API surface for `ssh-key` — confirmed via registry + docs.rs but exact method signatures need a final check against the pinned version during implementation)

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

- **D-01:** `rotate_key` rotates an SSH `authorized_keys` entry: generate a new keypair, replace the matching `authorized_keys` line, keep the old line backed up locally. Rejected alternatives: the agent's own enrollment/auth token, TLS/service certs, and a generic "rotate any named secret file" action. Reversibility: costly (renaming the target credential type later reworks playbook YAML + `ACTION_MAP` + the Rust arm signature + future audit records in lockstep).
- **D-02:** Triggering finding is `finding_class: vuln` — a weak (RSA < 2048 / DSA) or known-compromised key detected in `authorized_keys`. The finding names the exact key so the playbook step can target it precisely. FIM-triggered "unauthorized key appeared" is explicitly out of scope (that's a *remove*, not a *regenerate*). Reversibility: costly, same lockstep-wiring rationale as D-01.
- **D-03:** This phase also adds the underlying VULN detection (Phase 51's scanner currently has zero coverage for weak/compromised SSH keys) — without it, nothing would ever trigger this playbook automatically.
- **D-04:** Targeting is by exact key fingerprint, not a path/pattern. The agent only ever touches the one `authorized_keys` line matching that fingerprint. No separate protected-principal denylist (unlike `CRITICAL_PROCESS_NAMES`/`CRITICAL_SERVICE_NAMES`) — fingerprint-exact targeting was judged sufficient alone.
- **D-05:** Hard refusal case: if the matched key is the *only* entry in `authorized_keys`, the agent refuses (`{status: "error"}`) instead of rotating. Agent counts entries before acting.
- **D-06:** `rotate_key` is a REVERSIBLE action — it gets a real rollback playbook step, not Phase 53's escalate-only path. Rollback = restore the backed-up old `authorized_keys` line, delete the new one. Mirrors `restore_file`'s baseline/backup approach. Reversibility: costly — this classification determines which code branch the approval-gate/rollback dispatcher takes.
- **D-07:** Verify step re-scans `authorized_keys` after dispatch and confirms (a) the old fingerprint is gone and (b) the new entry passes the VULN weak-key check — grounded in actual post-action state, not the agent's self-report.
- **D-08:** v1 scope stops at "regenerate + replace on disk." Nothing else in the platform needs the new key — out-of-band private-key delivery is explicitly out of scope.
- **D-09 (hard security constraint):** The new private key material NEVER crosses the agent→backend channel and NEVER appears in the `remediation_audit` record or any log. The agent writes the private key to disk locally with locked-down permissions and reports back only the new key's fingerprint/comment. Reversibility: one-way — flag any future change to this behavior for human review, not a routine edit.

### Claude's Discretion

- Exact key algorithm for the newly generated keypair (ed25519 vs RSA-4096, etc.) — research/planner should pick a modern default and note it. **Research recommendation: ed25519** (see State of the Art below).
- Exact weak-key detection thresholds (RSA bit-length cutoff, compromised-key list/format) — left to research against Phase 51's actual VULN check patterns. **Research recommendation: RSA < 2048 bits (matches D-02's own literal wording) / any DSA key; compromised-key list deferred to a future signed-feed extension, v1 ships weak-type detection only** (see Common Pitfalls / Open Questions).
- Whether the new VULN check is a new standalone check or an extension of an existing SSH-related check — left to research/planner. **Research recommendation: new function, new file, called from the existing `scan_misconfigurations()` dispatcher** (see Architecture Patterns).

### Deferred Ideas (OUT OF SCOPE)

None — discussion stayed within phase scope. D-03 (adding the VULN weak-key check) was judged necessary for this action to function, not a scope expansion.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| AUTO-02 (extends) | Autonomous-remediation actions the engine can dispatch, deterministically selected via YAML playbooks | Adds the 5th action arm (`rotate_key`) to the existing 4 (kill_process/restore_file/block_ip/disable_service), following the exact pattern in `remediation_actions.rs`/`instructions.rs`/`remediation_playbook_service.py`/`backend/playbooks/*.yaml` documented below |
</phase_requirements>

## Summary

This phase extends an already-shipped, fully-understood system (Phase 53's deterministic remediation engine) with a 5th action, plus the one prerequisite VULN check Phase 51 never built (weak/compromised SSH key detection). Every integration point — the Rust action-arm shape, the YAML playbook schema, the `ACTION_MAP` allowlist, the audit-write path, and the dispatch/verify/rollback state machine — already exists and was read in full for this research. Nothing about the surrounding architecture needs to be invented; the work is almost entirely "add a 5th instance of an existing pattern," with the one genuinely new piece being SSH-key-specific: parsing/editing an OpenSSH `authorized_keys` file safely and generating a new keypair.

The codebase has **zero existing code** that touches `authorized_keys`, SSH key parsing, or SSH keypair generation (confirmed by exhaustive grep — the only hits are backend `secrets_service.py`, unrelated vendored packages, and one interesting pre-existing signal: the Rust VULN scanner's `scan_secrets()` already emits a "Private key material" finding with `playbook_ref: "rotate_key"` hardcoded, years before this phase existed — a forward-reference that was never wired up). The recommended crate is `ssh-key` (RustCrypto/SSH, crates.io, `OK` legitimacy verdict, 271k weekly downloads) at its latest **stable** release `0.6.7` (not the `0.7.0-rc.11` prerelease that `cargo search`/`cargo info` surface first) — it can parse/write `authorized_keys` lines, generate Ed25519 keypairs, and compute fingerprints, all in pure Rust with no C dependencies, matching the existing `ed25519-dalek`-based feed-verification precedent already in this exact Cargo.toml.

The single most important non-obvious finding: **`select_playbook()` in `remediation_playbook_service.py` does NOT read the YAML `match:` block at all** — playbook selection for `vuln`-class findings is a hardcoded Python if/elif chain keyed only on `details.get("cveId")` (present → `patch_package`, absent → `disable_service`). Adding `rotate_key.yaml` alone will never cause it to be selected; `select_playbook()` itself must be edited with a new branch, and the cleanest signal to key that branch on is the `playbook_ref` field the Rust scanner already emits per-finding and that `agent_vuln_ingest_service.py` already persists onto the `vulnerabilities` doc — reuse it, don't invent a new discriminator.

**Primary recommendation:** Mirror the Phase 53 action shape exactly (bounded, non-panicking, `Result<(), RemediationError>`, `#[cfg(test)]`-stubbed privileged calls), add `rotate_key` as a 5th branch to `select_playbook()` keyed on `details.get("playbook_ref") == "rotate_key"` (not on `cveId`, which weak-key findings won't have), generate Ed25519 keys via the `ssh-key` crate (stable `0.6.7`), and scope the action to Linux/macOS only — refuse cleanly with a structured error on Windows rather than attempting Windows `administrators_authorized_keys` (which requires ACL manipulation, not just file writes, and is architecturally a different problem).

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Weak/compromised SSH key detection (scan) | Host Agent (Rust) | Backend (ingest/store) | Detection requires reading local filesystem state (`~/.ssh/authorized_keys` per user) — only the agent has that access; the backend only stores/aggregates the finding via the existing heartbeat ingest path |
| Playbook selection (which action a finding triggers) | Backend (Python) | — | Deterministic, no LLM, pure lookup — matches Phase 53's `remediation_playbook_service.select_playbook()`, which already owns this responsibility for all 4 existing actions |
| Approval gate / rollback dispatch / concurrency lease | Backend (Python) | — | Already fully implemented in `autonomous_remediation_service.py`; rotate_key slots into the existing `is_destructive` / `rollback_steps` branches with zero new orchestration code |
| Keypair generation + authorized_keys file edit (execution) | Host Agent (Rust) | — | Only the agent has local filesystem + OS-user access to safely read/write `~/.ssh/authorized_keys` and set file permissions; this can never be done from the backend |
| Audit trail (fingerprint-only, never key material) | Backend (Python) | Host Agent (must never emit key material in its result payload) | `remediation_audit_service.write_audit` is the single append-only sink; but the invariant (D-09) is actually enforced one tier earlier — the agent's own JSON result to `report_instruction_result` must never contain the private key, since the backend endpoint persists the raw `result.message`/`result.error` fields verbatim |

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `ssh-key` | 0.6.7 (latest **stable**; `0.7.0-rc.11` exists but is a prerelease — `cargo add` without `--allow-prerelease` correctly resolves to 0.6.7) | Parse/write OpenSSH `authorized_keys` lines, generate Ed25519 keypairs, compute fingerprints, serialize private/public keys to OpenSSH text format | RustCrypto org, pure Rust (no C deps — matches this Cargo.toml's existing `ed25519-dalek`/`sha2`/`hex` pure-Rust posture), the same family that already implements ed25519 signature verification for `feed_bundle.rs` |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `ed25519-dalek` | 2 (already in Cargo.toml) | Underlying ed25519 primitive `ssh-key`'s `ed25519` feature depends on | Already a direct dependency for feed-bundle signature verification (Phase 50) — the `ssh-key` `ed25519` feature reuses it, no new crypto primitive introduced |
| `rand` | 0.8 (already in Cargo.toml) | RNG source for keypair generation | Already a dependency; `ssh-key`'s `rand_core` feature (already in `ssh-key`'s default feature set) is compatible |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `ssh-key` | Hand-rolled OpenSSH wire-format encoder (matching this codebase's stated "minimal-dependency style") | Rejected: OpenSSH's private-key armor format (`-----BEGIN OPENSSH PRIVATE KEY-----`) is a nontrivial bespoke encoding (bcrypt-KDF-wrapped, custom padding) — hand-rolling it is exactly the kind of "deceptively complex, don't hand-roll" problem this codebase already avoids elsewhere (e.g. it didn't hand-roll ed25519 signing for the feed bundle either) |
| `ssh-key` | `russh-keys` / `osshkeys` | Both exist and work, but `russh-keys` pulls in the larger `russh` SSH-protocol ecosystem (unneeded — this phase never speaks the SSH protocol, only edits key files) and `osshkeys` wraps OpenSSL (C dependency — violates the windows-gnu no-C-deps precedent this Cargo.toml has deliberately maintained for TLS/crypto) |
| RSA-4096 generation | Continue supporting only Ed25519 for newly-generated keys | RSA key generation via `ssh-key`'s `rsa` feature pulls in the `rsa`/`num-bigint-dig` crates (large compile-time cost, slower generation) for a key type current best practice actively steers users away from; Ed25519-only for *generation* is sufficient — RSA/DSA support is still needed for *parsing* (detecting existing weak keys), which is a separate, smaller feature surface |

**Installation:**
```bash
cd agent-install/omni-agent-rs
cargo add ssh-key --features ed25519,rand_core
```

**Version verification:** `cargo add ssh-key --dry-run --features ed25519,rand_core` resolved to `ssh-key v0.6.7` against the live crates.io index during this research session — this is the correct pin (not the `0.7.0-rc.11` release-candidate `cargo search`/`cargo info` list first).

## Package Legitimacy Audit

| Package | Registry | Age | Downloads | Source Repo | Verdict | Disposition |
|---------|----------|-----|-----------|-------------|---------|-------------|
| `ssh-key` | crates.io | published 2021-11-18 (~5 yrs) | 271,133/week | github.com/RustCrypto/SSH | OK | Approved |
| `ssh-encoding` | crates.io | published 2022-10-21 (~4 yrs) | 320,628/week | github.com/RustCrypto/SSH | OK | Approved — transitive dep of `ssh-key`, no direct `Cargo.toml` entry needed unless the planner wants to parse raw wire-format bytes directly |

**Packages removed due to [SLOP] verdict:** none
**Packages flagged as suspicious [SUS]:** none

Both packages were cross-checked directly against the live crates.io registry via `cargo info`/`cargo add --dry-run` (not training-data recall) and returned `OK` from `gsd-tools query package-legitimacy check --ecosystem crates` (RustCrypto org repo, high weekly downloads, not deprecated, no suspicious postinstall). Tagged `[VERIFIED: crates.io registry]` below rather than `[ASSUMED]`.

## Architecture Patterns

### System Architecture Diagram

```
┌─────────────────────────── Host Agent (Rust) ───────────────────────────┐
│                                                                          │
│  vulnerability_scan.rs::scan_misconfigurations()                       │
│    ├─ existing: check_sshd() → /etc/ssh/sshd_config                    │
│    ├─ existing: check_listening_ports()                                │
│    └─ NEW: check_authorized_keys() → per-user ~/.ssh/authorized_keys   │
│              (parse each line via ssh-key, flag RSA<2048 / DSA)         │
│              → emits {type:"misconfig", playbook_ref:"rotate_key",     │
│                       affected_path, detail: "<fingerprint> <algo>"}   │
│                                                                          │
│  (heartbeat carries payload.meta.vulnerability_scanning.vulnerabilities)│
└──────────────────────────────────┬───────────────────────────────────┘
                                    │ heartbeat POST
                                    ▼
┌─────────────────────────── Backend (Python) ────────────────────────────┐
│                                                                          │
│  agent_vuln_ingest_service.ingest_findings()                           │
│    upserts into db.vulnerabilities, preserving playbook_ref field       │
│    (ALREADY happens for every finding type — no ingest change needed    │
│     unless a fingerprint field needs to survive too, see Pitfalls)      │
│                                                                          │
│  autonomous_remediation_service.scan_for_remediable_findings()          │
│    → RemediationFinding(finding_type="vuln", details=<full vuln doc>)   │
│                                                                          │
│  remediation_playbook_service.select_playbook(finding)                  │
│    if finding_type == "vuln":                                           │
│      NEW: if details.get("playbook_ref") == "rotate_key":              │
│               return by_name.get("rotate_key")   ← ADD THIS BRANCH      │
│           elif details.get("cveId"): patch_package                     │
│           else: disable_service                                        │
│                                                                          │
│  autonomous_remediation_service.remediate()                             │
│    → is_destructive (rotate_key.yaml: destructive:true) → approval gate │
│    → approved → _dispatch_and_verify()                                  │
│        → _dispatch_step() → ACTION_MAP["rotate_key"] → agent_instructions│
│        → poll agent_instructions.status                                 │
│        → _verify_finding_resolved() → _verify_vuln_resolved()          │
│              (re-checks db.vulnerabilities — see Pitfall: id-field bug) │
│        → on failed verify: dispatch rotate_key.yaml's rollback steps    │
│                                                                          │
│  remediation_audit_service.write_audit() — every stage transition       │
│    (fingerprint/comment only, NEVER key material — D-09)                │
└──────────────────────────────────┬───────────────────────────────────┘
                                    │ agent_instructions queue (existing
                                    │ channel — no new dispatch path)
                                    ▼
┌─────────────────────────── Host Agent (Rust) ───────────────────────────┐
│                                                                          │
│  instructions.rs: match action { "rotate_key" => { ... } }  ← NEW ARM   │
│    extracts params (fingerprint, authorized_keys_path) from             │
│    item.parameters, calls remediation_actions::rotate_key(...)          │
│                                                                          │
│  remediation_actions.rs::rotate_key(fingerprint, path) -> Result<..>    │
│    1. read authorized_keys, parse all lines via ssh-key                 │
│    2. find line matching fingerprint (D-04)                             │
│    3. refuse if it's the only entry (D-05)                              │
│    4. generate new Ed25519 keypair (ssh-key::PrivateKey::random)        │
│    5. write new private key to disk, 0600 perms (D-09, POSIX-only)      │
│    6. atomically replace authorized_keys (write tmp + rename),          │
│       backing up the old line locally first (D-06 rollback source)      │
│    7. return {status:"success", new_fingerprint, new_comment}           │
│       — NEVER the private key (D-09)                                    │
│                                                                          │
│  #[cfg(not(any(target_os="linux", target_os="macos")))]:                │
│    return Err(OperationFailed("rotate_key unsupported on this          │
│    platform")) — clean refusal on Windows, matching block_ip's own      │
│    existing #[cfg(not(any(...)))] fallback-error pattern                │
└──────────────────────────────────────────────────────────────────────┘
```

### Recommended Project Structure

```
agent-install/omni-agent-rs/src/capabilities/
├── vulnerability_scan.rs      # EDIT: scan_misconfigurations() gains one new call
├── ssh_key_checks.rs          # NEW: shared weak-key-detection logic (used by BOTH
│                               #      the scanner above AND rotate_key's own D-07
│                               #      re-verify — do not duplicate the RSA<2048/DSA
│                               #      check in two places)
├── remediation_actions.rs     # EDIT: add rotate_key() — likely delegates most of
│                               #      its body to a new small module, see below
└── ssh_key_rotation.rs        # NEW (recommended): authorized_keys parse/backup/
                                #      atomic-write/keygen helpers, kept out of
                                #      remediation_actions.rs to avoid pushing that
                                #      already-424-line file past CLAUDE.md's 500-
                                #      line cap (see Project Constraints below)

backend/
├── remediation_playbook_service.py   # EDIT: ACTION_MAP + select_playbook() branch
├── playbooks/rotate_key.yaml         # NEW: mirrors block_ip.yaml's shape (destructive
│                                      #      + real rollback)
├── agent_vuln_ingest_service.py      # EDIT (likely): propagate a fingerprint field
│                                      #      if the planner adds one (see Pitfalls)
└── remediation_audit_service.py      # UNCHANGED — generic write_audit() already
                                       #      accepts any record dict; the D-09
                                       #      constraint is enforced by what the
                                       #      CALLER puts in the record, not by this
                                       #      module
```

### Pattern 1: The Rust action-arm shape (exact, from the shipped 4 actions)

**What:** Every remediation action is an `async fn` taking primitive `&str`/`Option<&str>` params (NOT a raw `&Value` as Phase 53's own plan document literally describes — the actual shipped code diverged from that plan text), returning `Result<(), RemediationError>`. `instructions.rs` extracts params from `item.parameters` and maps `Ok(())`/`Err(e)` to `{status:"success", message}` / `{status:"error", error: e.to_string()}`.

**When to use:** Every new action arm, including `rotate_key`.

**Example (existing `block_ip`, the closest structural analog — validates a single primitive input, dispatches a privileged OS operation, has a symmetric rollback counterpart):**
```rust
// Source: agent-install/omni-agent-rs/src/capabilities/remediation_actions.rs (read in full this session)
pub async fn block_ip(ip_address: &str) -> Result<(), RemediationError> {
    let ip = validate_ip(ip_address)?;
    #[cfg(target_os = "linux")]
    { run_privileged_command("iptables", &["-I", "INPUT", "-s", &ip.to_string(), "-j", "DROP"]) }
    #[cfg(target_os = "windows")]
    { /* netsh advfirewall ... */ }
    #[cfg(not(any(target_os = "linux", target_os = "windows")))]
    { Err(RemediationError::OperationFailed("block_ip is unsupported on this platform.".to_string())) }
}
```

**rotate_key should follow this shape but gate on Linux/macOS only** (not Windows) — see Pitfall "Windows authorized_keys is architecturally different."

### Pattern 2: `select_playbook()` is a hardcoded Python dispatcher, not YAML-driven

**What:** `remediation_playbook_service.select_playbook(finding, playbooks)` — despite every YAML playbook carrying a `match:` block, that block is **never read**. Selection is 100% the Python if/elif chain shown below.

**When to use:** Any time a new finding→playbook mapping is added, edit this function directly.

```python
# Source: backend/remediation_playbook_service.py (read in full this session)
if finding_type == "vuln":
    cve_id = details.get("cveId") or details.get("cve_id")
    if cve_id:
        return by_name.get("patch_package")
    return by_name.get("disable_service")
    # ^ a weak-key finding has no cveId, so WITHOUT a new branch it would be
    #   misrouted to disable_service (wrong — disable_service.yaml targets
    #   {{finding.details.package}}, a service name, not an SSH key)
```

**Recommended new branch (inserted BEFORE the `cve_id` check):**
```python
if finding_type == "vuln":
    if details.get("playbook_ref") == "rotate_key":
        return by_name.get("rotate_key")
    cve_id = details.get("cveId") or details.get("cve_id")
    ...
```
This reuses the `playbook_ref` field the Rust scanner already emits and `agent_vuln_ingest_service.py` already persists onto every vuln doc (`set_fields["playbook_ref"] = f.get("playbook_ref")`) — no new field needs to be plumbed through ingestion for *selection* to work (a fingerprint field is still needed for *targeting*, see Pitfalls).

### Pattern 3: YAML playbook shape (from `block_ip.yaml`, the closest reversible-destructive analog)

```yaml
# Source: backend/playbooks/block_ip.yaml (read in full this session)
name: block_ip
finding_class: nscan
match:
  scan_type: ip
steps:
  - action: block_ip
    params:
      ip_address: "{{finding.resource_id}}"
    destructive: true
rollback:
  - action: unblock_ip
    params:
      ip_address: "{{finding.resource_id}}"
```

**Recommended `rotate_key.yaml` shape:**
```yaml
name: rotate_key
finding_class: vuln
match:
  playbook_ref: rotate_key   # documentation only — see Pattern 2, this is NOT consulted
steps:
  - action: rotate_key
    params:
      fingerprint: "{{finding.details.fingerprint}}"    # requires ingest to persist this field
      authorized_keys_path: "{{finding.details.affected_path}}"
    destructive: true
# Reversible — the agent's rotate_key backs up the replaced line locally;
# rollback restores it (mirrors restore_file's baseline/backup approach, D-06).
rollback:
  - action: rotate_key_rollback   # or reuse restore_file if the backup is
                                   # written in a restore_file-compatible shape —
                                   # planner's call, see Open Questions
    params:
      authorized_keys_path: "{{finding.details.affected_path}}"
      fingerprint: "{{finding.details.fingerprint}}"
```

### Anti-Patterns to Avoid

- **Trusting the YAML `match:` block to route findings:** It's inert. Every routing decision lives in `select_playbook()`'s Python code. A planner task that only adds `rotate_key.yaml` and edits `ACTION_MAP` — without also editing `select_playbook()` — will ship a playbook that is never selected.
- **Duplicating the weak-key check:** D-07's verify step needs to re-run "the same weak-key check" after rotation. Don't write that logic twice (once in the scanner, once in the rotate action's own verify) — factor it into one shared function (`ssh_key_checks.rs`) both call.
- **Putting the private key anywhere in the agent's JSON result:** `report_instruction_result` (backend) persists `result.message`/`result.error`/`result.raw_status` verbatim into `db.agent_instructions`. Any field in the agent's response body is a potential leak surface — D-09 must be enforced at the point the Rust code constructs its `Ok`/success JSON, not by a later filter.
- **Reusing `restore_file`'s action verbatim for rollback:** `restore_file` requires an explicit `backup_path` file on disk holding the *entire* original file content (`std::fs::copy`). If rotate_key's backup strategy only stores the single replaced *line* (not the whole file), `restore_file` won't be usable unmodified — decide the backup granularity first (whole-file snapshot vs. single-line) and pick the matching rollback mechanism; don't assume `restore_file` "just works" without checking this.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| OpenSSH private-key armor encoding (`-----BEGIN OPENSSH PRIVATE KEY-----`, bcrypt-KDF wrapper, custom padding) | A bespoke serializer | `ssh-key`'s `PrivateKey::to_openssh()` | Nontrivial bespoke binary format; a hand-rolled encoder is exactly the "deceptively complex" class of problem this codebase already avoids (it uses `ed25519-dalek` for signing, not a hand-rolled Ed25519 implementation) |
| Public-key fingerprint computation (SHA256 base64, the `SHA256:xxxx` format `ssh-keygen -l` prints) | Manual SHA256-then-base64-then-strip-padding | `ssh-key`'s `Fingerprint` type | Exact byte-for-byte format matching (no trailing `=`, specific base64 alphabet) is easy to get subtly wrong; the crate is purpose-built for OpenSSH-format compatibility |
| Atomic file replacement for `authorized_keys` | A direct in-place `fs::write` | Write to a temp file in the same directory + `fs::rename` (POSIX rename is atomic on the same filesystem) | A crash or concurrent read mid-write on a live SSH auth file is exactly the kind of "destructive action on a live endpoint" Phase 53's own pitfalls list warns about; the codebase has no atomic-write helper today so this is genuinely new code, but the technique itself (`tempfile` + `rename`) is a one-line stdlib pattern, not a library dependency |

**Key insight:** The `ssh-key` crate exists specifically because OpenSSH's key/authorized_keys formats have several non-obvious, security-relevant encoding details (fingerprint format, private-key armor, MPI padding for RSA/DSA parsing). This is a domain where "just write the bytes" is a classic source of subtle bugs that don't surface until a real `ssh-keygen`/`sshd` refuses to read the file — reuse the maintained crate rather than reimplementing wire-format encoding.

## Runtime State Inventory

Not applicable — this is a greenfield feature addition (new action arm), not a rename/refactor/migration phase. No existing state carries old naming that needs updating.

## Common Pitfalls

### Pitfall 1: `select_playbook()` won't route to `rotate_key` without an explicit code branch (see Pattern 2)
**What goes wrong:** Planner adds `rotate_key.yaml` + `ACTION_MAP["rotate_key"]`, tests the Rust action in isolation, everything looks done — but in the real system, weak-key VULN findings keep getting routed to `disable_service` (the existing no-CVE fallback) instead.
**Why it happens:** The YAML `match:` block reads like it should be the selection mechanism (that's what `patch_package.yaml`'s `match: {requires_cve: true}` and `disable_service.yaml`'s `match: {requires_cve: false}` *look* like they're doing) but `select_playbook()` never reads `playbook["match"]` — it's purely documentation/future-proofing that was never wired up, confirmed by reading the full function.
**How to avoid:** Explicitly add the `playbook_ref == "rotate_key"` branch (or equivalent discriminator) to `select_playbook()`'s `vuln` handling, ordered *before* the `cveId` check.
**Warning signs:** A rotate_key.yaml plan task with no corresponding diff to `remediation_playbook_service.py`'s `select_playbook()` function.

### Pitfall 2: `_verify_vuln_resolved()` likely can never see a real "resolved" state for agent-native vuln findings (pre-existing, applies to this action too)
**What goes wrong:** `autonomous_remediation_service._verify_vuln_resolved()` queries `db.vulnerabilities.find_one({"id": finding.finding_id})`. But `agent_vuln_ingest_service.ingest_findings()` never sets a top-level `"id"` field on the documents it upserts (only Mongo's own `_id` exists). `finding.finding_id` is populated as `v.get("id") or str(v.get("_id", ""))` — for agent-native docs this is always `str(_id)` (an ObjectId string). Querying `{"id": "<objectid-string>"}` against a collection where no document has an `"id"` field will always return `None` → the verify function's `if vuln is None: return "resolved"` branch fires **immediately**, regardless of whether the rotation actually happened or worked.
**Why it happens:** `vuln_service.py`'s `get_vulnerabilities()` (the GET-list path) tries to synthesize `v["id"] = str(v["_id"])` at read time, but that code is itself dead (the Mongo query at that call site already projects `{"_id": 0}`, so `"_id" in v"` is always False) — this "id" synthesis has never actually run for any code path in this file.
**How to avoid:** This is a genuine pre-existing gap in the shared engine, not specific to rotate_key — it equally affects `patch_package`/`disable_service`'s verify today. Two options for the planner: (a) treat it as explicitly out-of-scope and document that rotate_key's D-07 "grounded verify" currently inherits this limitation (verify will report "resolved" without a real re-scan confirmation until the shared bug is fixed — file as a known gap, not a regression this phase introduces), or (b) fix `_verify_vuln_resolved`'s query to match on Mongo `_id` (requires importing `ObjectId` and handling the case where `finding_id` isn't a valid ObjectId string) as an in-scope fix, since D-07 is an explicit hard requirement for this specific action. **Recommend surfacing this as an explicit planning decision, not silently inheriting the bug**, since D-07 was called out as a requirement in CONTEXT.md specifically to avoid "trust the agent's self-report."
**Warning signs:** A verify step in tests that "passes" without ever exercising a real still-weak-key re-scan.

### Pitfall 3: Windows `authorized_keys` is architecturally different, not just a different path
**What goes wrong:** A naive cross-platform implementation tries to locate "the Windows authorized_keys file" the same way it locates the Linux one (home-dir-relative) and either fails silently or, worse, succeeds against the wrong file.
**Why it happens:** Per Microsoft's own OpenSSH-for-Windows docs [CITED: learn.microsoft.com], a non-administrator account uses `%USERPROFILE%\.ssh\authorized_keys` (same shape as Linux) — but any account in the local Administrators group uses a **single shared** `C:\ProgramData\ssh\administrators_authorized_keys` file instead, which additionally requires a strict ACL (only `NT AUTHORITY\SYSTEM` full control + `BUILTIN\Administrators`) — a plain file-permission edit (like the POSIX `0600` chmod this phase already needs for the new private key) is not sufficient; ACL manipulation needs `icacls`-equivalent Windows API calls this codebase has no precedent for.
**How to avoid:** Match CONTEXT.md's own framing — scope `rotate_key` to Linux (and optionally macOS, same POSIX `~/.ssh/authorized_keys` shape) for v1, and return a clean `RemediationError::OperationFailed("rotate_key is not supported on Windows")` under `#[cfg(target_os = "windows")]`, exactly mirroring `block_ip`'s/`disable_service`'s existing `#[cfg(not(any(target_os = "linux", target_os = "windows")))]` fallback pattern (just inverted — Windows is the excluded platform here, not the included one).
**Warning signs:** Any code path that constructs a Windows authorized_keys path without also handling the ACL requirement.

### Pitfall 4: A fingerprint field needs to survive ingestion, and today it wouldn't
**What goes wrong:** D-04 requires fingerprint-exact targeting. The Rust scanner's misconfig findings currently only carry `{type, cve_id, severity, affected_path, remediation_hint, playbook_ref, detail}` — there's no dedicated fingerprint field, and even if the Rust side adds one, `agent_vuln_ingest_service.ingest_findings()`'s `set_fields` dict is a fixed allowlist of keys (`cveId, cvss, cvssScore, severity, type, remediation_hint, playbook_ref, detail, description, package, affectedSoftware, source, status, last_seen`) — any new field the Rust scanner emits is silently dropped at ingest unless `set_fields` is explicitly extended to include it.
**How to avoid:** Either (a) encode the fingerprint into the existing `detail` field (already free text, e.g. `"SHA256:abcd... (RSA 1024-bit)"`) and have the rotate_key playbook param extract it via a template/regex at dispatch time, or (b) explicitly add a `fingerprint` key to both the Rust finding JSON and `agent_vuln_ingest_service.py`'s `set_fields`. Option (b) is cleaner and matches how `cveId`/`playbook_ref` already got first-class treatment — recommend it.
**Warning signs:** A `{{finding.details.fingerprint}}` playbook template param that resolves to `None` at runtime because ingestion never persisted it.

### Pitfall 5: `remediation_actions.rs` / `vulnerability_scan.rs` are already over CLAUDE.md's 500-line cap
**What goes wrong:** `remediation_actions.rs` is already 424 lines and `vulnerability_scan.rs` is already 593 lines (already over the project's stated 500-line convention, pre-existing). Adding a full authorized_keys parse/backup/atomic-write/keygen implementation plus a weak-key scan function directly into these files pushes them further past an already-violated limit.
**How to avoid:** Split new logic into new, focused modules (`ssh_key_checks.rs` for the shared weak-key-detection predicate, `ssh_key_rotation.rs` for the parse/backup/atomic-write/keygen mechanics) that `remediation_actions.rs`/`vulnerability_scan.rs` call into with a one- or two-line integration point each — matching the existing pattern where `feed_bundle.rs` is already its own module rather than being inlined into `vulnerability_scan.rs`.
**Warning signs:** A single-file diff to `remediation_actions.rs` that adds more than ~60-70 lines.

## Code Examples

### Existing dispatch-arm registration pattern (instructions.rs) — mirror exactly for rotate_key
```rust
// Source: agent-install/omni-agent-rs/src/instructions.rs (read in full this session)
"disable_service" => {
    let service = item.get("parameters").and_then(|p| p.get("service_name")).and_then(|v| v.as_str()).unwrap_or("");
    match crate::capabilities::remediation_actions::disable_service(service).await {
        Ok(()) => serde_json::json!({"status": "success", "message": "Service disable initiated"}),
        Err(e) => serde_json::json!({"status": "error", "error": e.to_string()}),
    }
}
// rotate_key follows this exact shape — extract "fingerprint" + "authorized_keys_path"
// from item.parameters, call remediation_actions::rotate_key(...), and on Ok, the
// success JSON must include new_fingerprint/new_comment (D-09) — e.g.:
// Ok((new_fp, new_comment)) => serde_json::json!({
//     "status": "success", "message": "Key rotated",
//     "new_fingerprint": new_fp, "new_comment": new_comment
// }),
```

### Existing audit-write call pattern (unchanged, reused as-is)
```python
# Source: backend/autonomous_remediation_service.py (read in full this session)
await write_audit(db, tenant_id, {**base_record, "stage": "dispatched", "steps_dispatched": steps_dispatched})
# base_record and steps_dispatched are backend-constructed from the agent's JSON
# result — as long as the Rust arm's success JSON never includes key material
# (per the instructions.rs example above), this call site needs ZERO changes
# for D-09 compliance; the constraint is enforced upstream, not here.
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|---------------|--------|
| RSA-2048/4096 as the default newly-generated SSH key type | Ed25519 as the default | OpenSSH's own `ssh-keygen` switched its default to Ed25519 in OpenSSH 9.5 (October 2023) [CITED: multiple 2025-2026 SSH-key-best-practice sources] | This phase's newly-*generated* replacement key should be Ed25519 — smaller, faster to generate/verify, no bit-length weakness class to worry about, and the crate/primitive (`ed25519-dalek`) is already a dependency for an unrelated purpose (feed-bundle signature verification) |

**Deprecated/outdated:**
- DSA SSH keys: OpenSSH itself disabled DSA by default starting with OpenSSH 7.0 (2015) due to the fixed, now-inadequate 1024-bit key size mandated by the DSA standard — this is exactly why D-02 flags *any* DSA key as weak (not a bit-length threshold like RSA) [ASSUMED — training-knowledge historical fact, not re-verified via a live web source this session, but not disputed anywhere and consistent with CONTEXT.md's own D-02 wording].

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `ssh-key` crate's default features are sufficient to structurally parse RSA/DSA `KeyData` (for bit-length inspection) without enabling the `rsa`/`dsa` cargo features, which pull in the heavier `rsa`/`dsa` crates | Standard Stack / Don't Hand-Roll | If wrong, the weak-key scanner needs the `rsa` and/or `dsa` `ssh-key` features enabled just to *detect* weak keys (not generate them), adding compile weight to a security agent binary; must be confirmed against the pinned `ssh-key 0.6.7` docs.rs page during implementation (`cargo doc --open` or docs.rs) before the scan-check task starts |
| A2 | DSA keys should be flagged as weak by *type alone* (not a bit-length check), because OpenSSH's own DSA implementation is hardcoded to 1024 bits | State of the Art | Low — this is well-established historical fact about the DSA standard/OpenSSH's implementation, consistent with D-02's own wording, but was not independently re-verified via a live authoritative source this session |
| A3 | Option (b) in Pitfall 4 (add a first-class `fingerprint` field to the Rust finding + `agent_vuln_ingest_service.py`'s `set_fields`) is the right approach vs. Option (a) (encode into `detail` + regex-extract at dispatch time) | Common Pitfalls / Architecture Patterns | Low-medium — this is an architectural judgment call, not a verified fact; either approach functionally works, but option (b) is more consistent with how `cveId`/`playbook_ref` are already handled as first-class ingest fields |
| A4 | `restore_file`'s existing rollback action is NOT directly reusable for `rotate_key`'s rollback without modification, because it expects a whole-file `backup_path`, not a single replaced line | Architecture Patterns (Anti-Patterns) | Medium — if the planner's chosen backup strategy happens to snapshot the whole `authorized_keys` file (not just the one line) before editing, `restore_file` becomes directly reusable and this concern is moot; needs to be resolved as part of task design, not assumed either way |

**Confirmation:** A1-A4 need explicit resolution during planning/implementation, not left implicit — none of them block starting the work, but each has a concrete "check this specific thing" action attached.

## Open Questions

1. **Should the weak-key VULN scan enumerate all local users' `authorized_keys` files, or just root's / the agent-run-as user's?**
   - What we know: `scan_misconfigurations()` today only reads one fixed path (`/etc/ssh/sshd_config`). A useful weak-key scan needs to enumerate `/root/.ssh/authorized_keys` plus every `/home/*/.ssh/authorized_keys` (and honor `sshd_config`'s `AuthorizedKeysFile` directive if it's non-default, which the codebase doesn't currently parse either).
   - What's unclear: Whether v1 should handle the general multi-user case or scope to a single well-known path for simplicity, given D-04's fingerprint-exact targeting already assumes the finding *tells* the action exactly where to look (so the scan-side enumeration completeness is the actual open question, not the rotate-side targeting).
   - Recommendation: Planner should scope this explicitly (e.g., "enumerate `/root/.ssh/authorized_keys` + one level of `/home/*/.ssh/authorized_keys`, ignore custom `AuthorizedKeysFile` overrides for v1, document the limitation") rather than leaving it implicit.

2. **What exactly does D-06's "rollback = restore the backed-up old authorized_keys line" require as a mechanism — reuse `restore_file`, or a dedicated `rotate_key_rollback` action?**
   - What we know: `restore_file` exists and does whole-file backup/restore via an explicit `backup_path`. `is_destructive`/rollback dispatch in `autonomous_remediation_service.py` works generically off whatever `action` name the playbook's `rollback:` list specifies — it doesn't need to be `rotate_key` itself.
   - What's unclear: Whether the backup should be a full pre-edit snapshot of `authorized_keys` (making `restore_file` directly reusable, param-compatible) or just the single removed line (requiring a small dedicated rollback arm that re-inserts one line).
   - Recommendation: Full-file snapshot before edit is simpler to implement correctly (avoids re-deriving exact line placement/ordering on rollback) and lets the playbook's `rollback:` step literally be `{action: restore_file, params: {path: ..., backup_path: ...}}` — reusing Phase 53's existing action with zero new Rust code for the rollback path. Recommend this unless the planner has a reason to prefer line-level granularity.

3. **Compromised-key list format (D-02's "known-compromised key" half) — build now or defer?**
   - What we know: No such list/format exists anywhere in this codebase today. The `cve_feed` signed-bundle pattern (`feed_bundle.rs`) is the closest existing precedent for "a maintained blocklist delivered out-of-band," but it's CVE-shaped, not key-fingerprint-shaped.
   - What's unclear: Whether v1 needs actual known-compromised-key matching (e.g., historical Debian OpenSSL PRNG-weak-key sets) or whether "weak (RSA<2048/DSA)" alone satisfies D-02 for the initial ship.
   - Recommendation: Ship weak-*type* detection only for v1 (RSA<2048, any DSA) — it's concrete, testable, and doesn't require sourcing/maintaining an external compromised-key corpus. Note in the plan that "known-compromised key" support is a natural, additive follow-on (a local optional blocklist file, `feed_bundle`-style) rather than blocking this phase on it.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Rust toolchain (`cargo`) | Building `remediation_actions.rs`/`vulnerability_scan.rs` changes | ✓ | (project's pinned toolchain, confirmed via successful `cargo add --dry-run` this session) | — |
| `x86_64-pc-windows-gnu` rustup target + `x86_64-w64-mingw32-gcc` | `cargo check --target x86_64-pc-windows-gnu` cross-compile verification (per project memory / CONTEXT.md's ask) | ✓ (confirmed installed this session) | — | — |
| `x86_64-unknown-linux-gnu` rustup target | Native Linux build/test | ✓ | — | — |
| Backend Python venv (`backend/venv/bin/python`) | `pytest` for `remediation_playbook_service.py`/`agent_vuln_ingest_service.py` changes | ✓ (per project memory: established baseline, use this interpreter not system python) | — | — |
| crates.io registry access | `cargo add ssh-key` | ✓ (successfully resolved during this research session) | — | — |

**Missing dependencies with no fallback:** none identified.
**Missing dependencies with fallback:** none identified.

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework (Rust) | `cargo test` — built-in, `#[cfg(test)] mod tests` inline in the same file, exact convention already used in both `remediation_actions.rs` and `vulnerability_scan.rs` |
| Framework (Python) | `pytest` via `backend/venv/bin/python -m pytest` |
| Config file | none dedicated — project-wide `pytest`/`cargo test` defaults |
| Quick run command (Rust) | `cd agent-install/omni-agent-rs && cargo test remediation_actions` / `cargo test vulnerability_scan` (or a new module's own test target, e.g. `cargo test ssh_key`) |
| Quick run command (Python) | `backend/venv/bin/python -m pytest backend/tests/test_remediation_playbook.py -q` (existing file to extend) |
| Full suite command (Rust) | `cd agent-install/omni-agent-rs && cargo test` |
| Full suite command (Python) | `backend/venv/bin/python -m pytest backend -q` |

### Phase Requirement → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| AUTO-02 (rotate_key arm) | `rotate_key` refuses empty/malformed fingerprint, refuses sole-entry authorized_keys (D-05), succeeds on a real temp authorized_keys fixture with 2+ entries, never emits the private key in its return value (D-09) | unit (Rust, hermetic — matches the existing `#[cfg(test)]`-stubbed-privileged-call convention) | `cargo test rotate_key` | ❌ Wave 0 — new test module |
| AUTO-02 (weak-key VULN check) | Flags RSA<2048 and DSA keys, does not flag Ed25519/RSA≥2048; absent/unreadable authorized_keys degrades gracefully (no panic, no false finding) | unit (Rust) | `cargo test ssh_key_checks` or equivalent | ❌ Wave 0 — new test module |
| AUTO-02 (playbook selection) | `select_playbook()` routes a `vuln` finding with `playbook_ref: "rotate_key"` to the `rotate_key` playbook, NOT `disable_service`/`patch_package` | unit (Python) | `backend/venv/bin/python -m pytest backend/tests/test_remediation_playbook.py -k rotate_key -q` | ❌ Wave 0 — extend existing `test_remediation_playbook.py` |
| AUTO-02 (YAML validity) | `rotate_key.yaml` validates against `ACTION_MAP`, loads via `load_default_playbooks()` | unit (Python) | same file, `load_default_playbooks` is already exercised generically — a new playbook file is auto-covered if the existing test iterates all vendored files | ✓ (existing generic test likely already covers a new vendored YAML file — confirm during Wave 0) |
| D-09 (no key material leak) | The agent's success JSON result for `rotate_key` never contains a substring matching a private-key PEM marker (`-----BEGIN`) | unit (Rust) — mirrors the existing `aws_key_shaped_token_flagged_without_leaking_value` test pattern in `vulnerability_scan.rs` that asserts `!findings[0].to_string().contains(...)` | `cargo test rotate_key` (same target as above, one assertion) | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** the relevant `cargo test <module>` / `pytest -k <keyword>` quick command above
- **Per wave merge:** full `cargo test` (agent) + full `pytest backend -q` (backend)
- **Phase gate:** both full suites green before `/gsd-verify-work`

### Wave 0 Gaps
- [ ] New Rust test module(s) for `ssh_key_checks.rs`/`ssh_key_rotation.rs`/`rotate_key` action — none exist yet (greenfield for this feature)
- [ ] Extend `backend/tests/test_remediation_playbook.py` with a `rotate_key` selection case (existing file, existing pattern to follow — read it before writing new tests)
- [ ] Framework install: none — `cargo test`/`pytest` already fully set up project-wide

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-------------------|
| V2 Authentication | yes (indirectly) | This action *is* a credential-rotation mechanism for SSH key-based authentication — the new private key must be generated with a CSPRNG (`ssh-key`'s `rand_core`-backed `PrivateKey::random`, not a hand-rolled RNG) |
| V3 Session Management | no | Not applicable — SSH `authorized_keys` is a long-lived credential, not a session token |
| V4 Access Control | yes | D-05's sole-entry refusal IS an access-control safeguard (prevents self-inflicted lockout); D-04's fingerprint-exact targeting bounds the blast radius of a malformed/compromised playbook param |
| V5 Input Validation | yes | Fingerprint param, authorized_keys path param — both must be validated (non-empty, well-formed) before any filesystem operation, exactly mirroring `validate_ip`/`validate_service_name`'s existing pattern in `remediation_actions.rs` |
| V6 Cryptography | yes | Never hand-roll Ed25519 keygen or the OpenSSH private-key armor format — use `ssh-key` (see Don't Hand-Roll). New private key file permissions must be `0600` (owner-only) on POSIX, set explicitly (not relying on umask defaults) |
| V8 Data Protection | yes | D-09 — private key material must never appear in the agent's result payload, the `remediation_audit` collection, or any log line; this is the phase's single hard, one-way security invariant |

### Known Threat Patterns for this stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|----------------------|
| Malformed/adversarial playbook param locks the operator out of the host (removes the only valid key) | Denial of Service | D-05's hard refusal (count entries before acting) — already locked as a decision, just needs correct implementation |
| Private key material leaks via the agent→backend result payload, logs, or the audit trail | Information Disclosure | D-09 — enforced at the point the Rust code constructs its success JSON (never include the key), not by a downstream filter; verified by a dedicated unit test asserting no PEM marker appears in the result string (see Validation Architecture) |
| A crash/interrupt mid-write leaves `authorized_keys` truncated or corrupted, an even worse outcome than the original weak key | Tampering / Integrity | Atomic replace (write to temp file in the same directory, then `fs::rename`) rather than in-place truncate-and-write; back up the pre-edit state first (also serves D-06's rollback source) |
| Weak-key scan false-positives on a key type the parser doesn't fully understand, causing an unnecessary destructive rotation | Tampering (unintended) | Fail-closed: an unparseable/unrecognized `authorized_keys` line must be skipped (not flagged) — mirrors the existing `parse_ver`/`malformed_version_never_matches` "a malformed input never produces a false match" convention already established in `vulnerability_scan.rs`'s CVE-matching code |

## Project Constraints (from CLAUDE.md)

- **Keep files under 500 lines** — directly relevant: `remediation_actions.rs` (424 lines) and `vulnerability_scan.rs` (593 lines, already over) are both growth targets for this phase; plan to add new, focused modules (`ssh_key_checks.rs`, `ssh_key_rotation.rs`) rather than growing these files further (see Common Pitfalls / Recommended Project Structure).
- **NEVER create files unless absolutely necessary — prefer editing existing files.** This is in tension with the line-count constraint above for this specific phase; the recommended resolution is that the new SSH-key logic is a genuinely new capability (not an edit to existing logic), so new files are justified — but keep the count minimal (2 new Rust modules, 1 new YAML file, no new Python files — everything Python-side is an edit to `remediation_playbook_service.py`/`agent_vuln_ingest_service.py`).
- **NEVER create documentation files unless explicitly requested** — no new `.md` docs beyond the standard GSD phase artifacts (PLAN.md, SUMMARY.md) this workflow already produces.
- **ALWAYS read a file before editing it** — already followed in this research session for every file this phase will touch.
- **NEVER commit secrets, credentials, or .env files** — directly reinforces D-09; the new private key file itself must never be committed anywhere (it's runtime-generated host state, not a repo artifact) and must never appear in any test fixture checked into git.
- **Validate input at system boundaries** — the fingerprint/path params arriving via `item.parameters` in `instructions.rs` are exactly such a boundary; validate before touching the filesystem (mirrors `validate_ip`).

## Sources

### Primary (HIGH confidence)
- `agent-install/omni-agent-rs/src/capabilities/remediation_actions.rs` — read in full (424 lines), all 5 existing actions + tests
- `agent-install/omni-agent-rs/src/capabilities/vulnerability_scan.rs` — read in full (593 lines), scan/misconfig/secret-detection patterns
- `agent-install/omni-agent-rs/src/instructions.rs` (lines 400-490) — dispatch-arm registration pattern
- `agent-install/omni-agent-rs/Cargo.toml` — existing dependency set, confirms pure-Rust/no-C-deps posture
- `backend/remediation_playbook_service.py` — read in full (159 lines), `ACTION_MAP`/`select_playbook`/`validate`/`load_default_playbooks`
- `backend/remediation_audit_service.py` — read in full (45 lines), append-only audit write
- `backend/autonomous_remediation_service.py` — read in full (1028 lines), the entire orchestration loop (scan/plan/dispatch/verify/rollback/escalate/audit)
- `backend/agent_vuln_ingest_service.py` — read in full (128 lines), heartbeat→`vulnerabilities` collection ingest, `set_fields` allowlist
- `backend/vuln_service.py` (lines 1-40) — confirmed the dead `id`-synthesis code path (Pitfall 2)
- `backend/playbooks/{block_ip,restore_file,disable_service,patch_package,kill_process}.yaml` — read in full, all 5 existing playbooks
- `.planning/milestones/v3.4-phases/53-autonomous-remediation/53-02-PLAN.md`, `53-04-PLAN.md` — Phase 53 task-breakdown granularity/style
- `.planning/phases/64-rotate-key-autonomous-remediation-action/64-CONTEXT.md` — locked decisions
- crates.io registry (via `cargo add ssh-key --dry-run`, `cargo info ssh-key`) — version resolution, confirmed 0.6.7 stable vs 0.7.0-rc.11 prerelease
- `gsd-tools query package-legitimacy check --ecosystem crates ssh-key ssh-encoding` — OK verdicts

### Secondary (MEDIUM confidence)
- docs.rs `ssh-key` crate documentation (fetched via WebFetch) — confirms `AuthorizedKeys` type, `PrivateKey::from_openssh`/`PublicKey::from_openssh`, `Fingerprint` type exist; exact method signatures for `PrivateKey::random()` and RSA-modulus-bit-length inspection were not fully confirmed and should be re-checked against the pinned 0.6.7 docs during implementation
- [Microsoft Learn — OpenSSH Key Management for Windows](https://learn.microsoft.com/en-us/windows-server/administration/openssh/openssh_keymanagement) — `administrators_authorized_keys` path + ACL requirement (Pitfall 3)
- Multiple 2025-2026 SSH-key-best-practice sources (WebSearch, cross-referencing consistent claims) — Ed25519-as-default-since-OpenSSH-9.5 claim

### Tertiary (LOW confidence)
- DSA-disabled-since-OpenSSH-7.0 / 1024-bit-fixed claim — training-knowledge recall, not independently re-verified this session (see Assumptions Log A2)

## Metadata

**Confidence breakdown:**
- Standard stack (ssh-key crate choice/version): MEDIUM-HIGH — package legitimacy + registry version confirmed via tool; exact method signatures not fully confirmed, flagged for implementation-time check
- Architecture (playbook/action/audit wiring): HIGH — every integration point was read directly from the shipped source this session, not inferred
- Pitfalls (select_playbook dead-match-block, verify id-field bug, ingest field-allowlist): HIGH — all three were confirmed by reading the actual function bodies, not assumed
- Security domain: HIGH — directly derived from CONTEXT.md's own locked D-04/D-05/D-09 plus the codebase's existing validation conventions

**Research date:** 2026-08-11
**Valid until:** 30 days (stable domain — no fast-moving external API surface; the `ssh-key` crate is pre-1.0 but has a slow, stable release cadence)

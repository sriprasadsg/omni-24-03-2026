# Phase 64: rotate_key autonomous-remediation action - Context

**Gathered:** 2026-08-11
**Status:** Ready for planning

<domain>
## Phase Boundary

Add the `rotate_key` action to the autonomous remediation engine (Phase 53) — the one action class AUTO-02 originally named but Phase 53 explicitly deferred to backlog (review: "under-specified + dangerous + hard to make reversible"). This phase narrows `rotate_key` to a concrete, tested, reversible target — SSH `authorized_keys` entries — and wires it end-to-end: a new VULN check that detects a weak/compromised key, a playbook that selects and dispatches the rotation, and a new agent-side action arm that performs it, verifies it, and can roll it back.

Everything about the surrounding architecture (backend-orchestrated engine, YAML playbook format, agent action-arm dispatch via `agent_instructions`, approval gate, audit trail) is locked by Phase 53 and out of scope to re-decide here — see Canonical References.

</domain>

<decisions>
## Implementation Decisions

### Rotation target
- **D-01:** `rotate_key` rotates an SSH `authorized_keys` entry: generate a new keypair, replace the matching `authorized_keys` line, keep the old line backed up locally. Rejected alternatives: the agent's own enrollment/auth token (would risk cutting off the backend↔agent channel mid-remediation — exactly the "lock out the host" risk the original review flagged), TLS/service certs (bigger scope, needs a reissue flow), and a generic "rotate any named secret file" action (too close to the vagueness the review rejected). — **Reversibility:** costly — rationale: the action name `rotate_key` and its target semantics get referenced by the playbook YAML, `ACTION_MAP`, the Rust arm signature, and future `remediation_audit` records; redefining the target credential type later means reworking all four in lockstep, not a local change.
- **D-02:** Triggering finding is `finding_class: vuln` — a weak (RSA < 2048 / DSA) or known-compromised key detected in `authorized_keys`. The finding names the exact key so the playbook step can target it precisely. Rejected: FIM-triggered ("unauthorized key appeared") has different semantics — that case means *remove* an unexpected entry, not *regenerate* a legitimate one — out of scope for this phase. — **Reversibility:** costly — same lockstep-wiring rationale as D-01.
- **D-03:** This phase also adds the underlying VULN detection (Phase 51's scanner currently has zero coverage for weak/compromised SSH keys) — without it, nothing would ever trigger this playbook automatically. Scope is larger than "just the action," but matches what AUTO-02 originally promised.

### Allowlist / safety
- **D-04:** Targeting is by exact key fingerprint, not a path/pattern. The VULN finding identifies the specific key; the agent only ever touches the one `authorized_keys` line matching that fingerprint — same precision as the existing `kill_process` action's by-pid targeting. No separate protected-principal denylist (unlike `remediation_actions.rs`'s `CRITICAL_PROCESS_NAMES`/`CRITICAL_SERVICE_NAMES` for the other four actions) — fingerprint-exact targeting was judged sufficient on its own.
- **D-05:** Hard refusal case: if the matched key is the *only* entry in `authorized_keys`, the agent refuses (`{status: "error"}`) instead of rotating — removing someone's sole access path is the classic lockout the original review warned about. Agent counts entries before acting.

### Reversibility / verification
- **D-06:** `rotate_key` is a REVERSIBLE action (unlike `kill_process`/`patch_package`) — it gets a real rollback playbook step, not Phase 53's escalate-only path. Rollback = restore the backed-up old `authorized_keys` line, delete the new one. Mirrors `restore_file`'s baseline/backup approach. — **Reversibility:** costly — rationale: this classification determines which code branch the action takes in the approval-gate/rollback dispatcher; reclassifying to irreversible later means moving it to a different execution path, not a config flip.
- **D-07:** Verify step (per Phase 53 D-07's two-step pattern) re-scans `authorized_keys` after dispatch and confirms (a) the old fingerprint is gone and (b) the new entry passes the VULN weak-key check — grounded in actual post-action state, not just the agent's self-reported `{status: success}`.

### New-value propagation
- **D-08:** v1 scope stops at "regenerate + replace on disk." Nothing else in the platform needs the new key — whoever used the old key needs the new private key delivered out-of-band, explicitly out of scope for this phase.
- **D-09:** Hard security constraint (not a design choice): the new private key material NEVER crosses the agent→backend channel and NEVER appears in the `remediation_audit` record or any log. The agent writes the private key to disk locally with locked-down permissions and reports back only the new key's fingerprint/comment — the same shape as the old key's identifier in the finding. — **Reversibility:** one-way — rationale: this is a security invariant baked into the agent's result payload and the audit schema; relaxing it later can't cleanly "undo" any key material that was already persisted or logged in the meantime. Flag any future change to this behavior for human review, not a routine edit.

### Claude's Discretion
- Exact key algorithm for the newly generated keypair (ed25519 vs RSA-4096, etc.) — not discussed; research/planner should pick a modern default and note it.
- Exact weak-key detection thresholds (e.g., precise RSA bit-length cutoff, which compromised-key list/format) — left to research against Phase 51's existing VULN check patterns.
- Whether the new VULN check is a new standalone check or an extension of an existing SSH-related check in Phase 51's scanner — left to research/planner to determine from the actual Phase 51 code.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Phase 53 (locked architecture this phase extends — do not re-litigate)
- `.planning/milestones/v3.4-phases/53-autonomous-remediation/53-CONTEXT.md` — D-01 through D-07: backend-orchestrated engine, YAML playbook format, agent action-arm dispatch, safety guards (approval gate, rollback vs. escalate, DB-lease concurrency), immutable audit trail, verify-via-two-step pattern
- `.planning/milestones/v3.4-phases/53-autonomous-remediation/53-REVIEWS.md` — the original review verdict that deferred `rotate_key` ("which keys? ... narrow to a concrete, tested, reversible target set") — this phase's mandate is directly answering that
- `.planning/milestones/v3.4-phases/53-autonomous-remediation/53-01-PLAN.md` — playbook YAML shape `{name, finding_class, match, steps:[{action, params, destructive}], rollback:[{action, params}]}`, `remediation_playbook_service.py`'s `ACTION_MAP`/`load_playbooks()`/`select_playbook()` pattern to extend
- `.planning/milestones/v3.4-phases/53-autonomous-remediation/53-02-PLAN.md` — the exact Rust action-arm pattern to replicate (`pub fn <action>(params: &Value) -> Value` returning `{status, detail}`, bounded/validated/non-panicking, `#[cfg(test)]`-stubbed privileged calls)
- `.planning/milestones/v3.4-phases/53-autonomous-remediation/53-04-PLAN.md` — approval gate + rollback/escalate dispatcher + DB-lease concurrency cap this action must slot into

### Existing code (extend, don't fork)
- `backend/remediation_playbook_service.py` — `ACTION_MAP` has an explicit code comment marking `rotate_key` as intentionally absent; this is the line to change
- `agent-install/omni-agent-rs/src/capabilities/remediation_actions.rs` — the shipped Rust action-arm module (kill_process/restore_file/block_ip/disable_service), including `CRITICAL_PROCESS_NAMES`/`CRITICAL_SERVICE_NAMES` denylist pattern and the `run_privileged_command` test-stub convention. **Note:** `agent-rust/src/remediation_actions.rs` is a stale/older tree (download-endpoint only) — do not touch it, only `agent-install/omni-agent-rs/` is the shipped agent.
- `backend/playbooks/*.yaml` — vendored default playbook files (`block_ip.yaml`, `disable_service.yaml`, etc.) — add `rotate_key.yaml` following the identical shape
- `backend/remediation_audit_service.py` — append-only audit write pattern; ensure the new action's audit entries never include private key material (D-09)
- `backend/secrets_service.py` — checked during discussion, confirmed **unrelated**: a separate tenant-facing secrets vault (`db.secrets`, encrypted values for API keys/webhook secrets/etc.) with its own `rotate_secret()` that explicitly refuses to auto-rotate `SSH_KEY`/`CERTIFICATE` types ("manual rotation required"). No collision with this phase's host-local SSH key rotation.

### Roadmap
- `ROADMAP.md` — Phase 64 section (Goal, `**Requirements**: extends AUTO-02`, `**Depends on:** Phase 63`)

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `remediation_playbook_service.py`'s `ACTION_MAP`, `validate()`, `load_playbooks()`, `select_playbook()` — extend `ACTION_MAP` with `rotate_key`, add `rotate_key.yaml` to `backend/playbooks/`
- `remediation_actions.rs`'s `RemediationError` enum, `run_privileged_command` stub-under-test convention, and the `CRITICAL_*_NAMES` denylist pattern — reuse the same shape for the new `rotate_key` arm
- `remediation_audit_service.py` — existing append-only write path, just add `rotate_key` as a recognized action type in whatever action-taken schema it already has

### Established Patterns
- Deterministic-only execution — no LLM anywhere in the action dispatch path
- Single dispatch channel — everything goes through the existing `agent_instructions` queue the agent already polls; no new/parallel channel
- Approval gate default-on for destructive actions; reversible actions get a rollback step, irreversible actions escalate to a human alert on verify-failure
- Two-step verify: poll the dispatched instruction's status, then re-run the finding's own check to confirm it actually cleared

### Integration Points
- `backend/remediation_playbook_service.py` (`ACTION_MAP`) + new `backend/playbooks/rotate_key.yaml`
- `agent-install/omni-agent-rs/src/capabilities/remediation_actions.rs` (new `pub fn rotate_key`) + `agent-install/omni-agent-rs/src/instructions.rs` (dispatch arm registration)
- Phase 51's VULN scanner module (exact file TBD by research) — needs the new weak/compromised-SSH-key check
- `backend/remediation_audit_service.py` — audit record for the new action type, with the D-09 no-private-key-material constraint enforced

</code_context>

<specifics>
## Specific Ideas

No specific UI/UX references — this is a backend + agent action with no new frontend surface (existing Phase 54 operator console already lists remediation actions/audit generically). Other target credential types (agent's own token, TLS certs, generic secret files) were explicitly considered and rejected for v1 — see D-01 rationale — not deferred ideas, decided against.

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope. The one scope expansion (D-03, adding the VULN weak-key check) was judged necessary for this action to function at all, not a new capability outside the phase's domain.

</deferred>

---

*Phase: 64-rotate-key-autonomous-remediation-action*
*Context gathered: 2026-08-11*

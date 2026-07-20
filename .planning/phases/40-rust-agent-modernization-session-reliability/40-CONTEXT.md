# Phase 40: Rust Agent Modernization & Session Reliability - Context

**Gathered:** 2026-07-20
**Status:** Ready for planning

<domain>
## Phase Boundary

Ship the Rust endpoint agent (`agent-install/omni-agent-rs`, the shipping tree) as the 2.1.0 executable on its modernized dependency stack (reqwest 0.13, sysinfo 0.39, tokio-tungstenite 0.30, rusqlite 0.40, hostname 0.4, serde_yaml→serde_norway), and root-cause + fix the intermittent 401 Unauthorized session bug (lead: refresh-token double-consume race in `authentication_endpoints.py::refresh_access_token`). Two independent, foundational fixes carried over from HANDOFF tasks 10 and 11 — decoupled from the remediation-ops feature work in the rest of the v3.2 milestone.

</domain>

<decisions>
## Implementation Decisions

### TLS backend
- **D-01:** Use `native-tls`, explicitly pinned as a `reqwest` feature. reqwest 0.13 defaults to `rustls`, a silent behavior change from pre-0.13 — must not ship without an explicit choice. `native-tls` matches current behavior and uses the OS/Windows cert store, which existing endpoint deployments behind corporate proxies with custom root CAs rely on.

### Rollout mechanism
- **D-02:** 2.1.0 reaches already-registered agents via the existing update pipeline (`agent_download_endpoints.py`/`update_endpoints.py`) — auto-push, not manual/opt-in. The plan must verify the existing pipeline actually supports this before assuming it (check version-gating logic, download endpoint behavior).

### 401 fix scope
- **D-03:** Narrow fix only. Root-cause and fix the specific refresh-token race; do not add broader session-resilience hardening (silent retry-on-401, refresh-margin tuning) in this phase — that would be scope creep beyond what HANDOFF task 10 asked for. If the root-cause investigation surfaces a different/additional defect, fix that too, but stay within "why does 401 happen intermittently," not "make auth generally more resilient."

### Claude's Discretion
- Exact TLS pin syntax in `Cargo.toml` (default-features = false + explicit `native-tls` feature, or equivalent) — implementation detail.
- Whether the update pipeline needs a code change to push 2.1.0, or whether it already auto-serves the latest built executable — verify against actual pipeline code during planning/research, don't assume.
- Test/verification strategy for confirming the 401 race is actually fixed (e.g., concurrent-refresh regression test).

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Milestone research (v3.2)
- `.planning/research/STACK.md` — verified Rust crate bump breaking-change analysis (local `cargo check` already run against this branch's staged Cargo.toml/Cargo.lock); TLS-backend tradeoff flagged as an explicit decision point (resolved above, D-01)
- `.planning/research/PITFALLS.md` — flags the refresh-token double-consume lead for SESS-01 (10th pitfall entry, from `authentication_endpoints.py:refresh_access_token`)
- `.planning/research/ARCHITECTURE.md` — confirms Phase 40 is fully independent of the milestone's other 4 phases (no shared schema/collection)

### Project history
- `.planning/HANDOFF.json` — original source of both open tasks: task 10 (401 investigation, never started) and task 11 (Rust package updates, partial — safe semver bumps already applied in commit `7e050f6`)

### Codebase maps
- `.planning/codebase/STACK.md` — lists the pre-modernization Rust dependency versions and confirms `agent-rust/` in the architecture diagram is stale (the actual shipping tree is `agent-install/omni-agent-rs`, per prior-session memory, not `agent-rust/`)
- `.planning/codebase/ARCHITECTURE.md` — confirms JWT token lifecycle: frontend proactively refreshes 5 minutes before expiry, refresh token stored encrypted in session — relevant background for the 401 race investigation

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `agent-install/omni-agent-rs/Cargo.toml`/`Cargo.lock` — crate bumps already staged and uncommitted on this branch (`feat/rust-agent-2.1.0-and-fixes`), verified compiling via local `cargo check --offline`. Planning should treat this as "commit + finish" work, not build-from-scratch.
- `agent_download_endpoints.py`/`update_endpoints.py` — existing agent update/download pipeline; reuse for 2.1.0 rollout per D-02.

### Established Patterns
- Two Rust agent trees exist in this repo: `agent-install/omni-agent-rs/` (shipping tree, service `OmniAgent`) and `agent-rust/` (download-endpoint-only, service `OmniAgentRust`, legacy). Do not confuse them — all Phase 40 work targets `agent-install/omni-agent-rs/`.

### Integration Points
- `authentication_endpoints.py::refresh_access_token` — investigation entry point for SESS-01.
- `backend/tests/eval_langchain/` and general `backend/tests/` conventions — for any new regression test around the auth fix, if the planner decides one is needed.

</code_context>

<specifics>
## Specific Ideas

- serde_yaml migration target is `serde_norway`, not `serde_yml` — `serde_yml` is itself flagged unsound/unmaintained per RustSec RUSTSEC-2025-0068 (already confirmed in STACK.md research, not a fresh decision needed).
- Rust bumps are functionally done pending the TLS decision and a rebuild — this sub-scope of the phase should be lightweight to plan.

</specifics>

<deferred>
## Deferred Ideas

- Broader auth-session hardening (silent retry-on-401, refresh-margin tuning) — deferred per D-03; revisit only if the 401 root-cause investigation shows it's genuinely needed, as a separate future phase/todo, not folded into this one.

None — discussion stayed within phase scope otherwise.

</deferred>

---

*Phase: 40-rust-agent-modernization-session-reliability*
*Context gathered: 2026-07-20*

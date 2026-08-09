# Phase 45: Close gap: RUST-01 — TLS backend explicit decision - Context

**Gathered:** 2026-07-21
**Status:** Ready for planning

<domain>
## Phase Boundary

Close the RUST-01 gap flagged by the v3.2 milestone audit: `agent-install/omni-agent-rs/Cargo.toml`'s `reqwest` dependency has `native-tls` in its feature list but leaves `default-features` on, so reqwest's `default-tls = ["rustls"]` still compiles the full rustls stack (rustls, rustls-webpki, aws-lc-rs, rustls-platform-verifier, tokio-rustls) into the shipped Windows executable alongside native-tls — confirmed via `strings backend/static/omni-agent-2.1.3-windows.exe | grep -i rustls`. Fix: make the TLS backend an explicit, single choice; rebuild the 2.1.3 executable; re-verify rustls is gone from the binary.

</domain>

<decisions>
## Implementation Decisions

### 2.1.3 distribution status
- **D-01:** 2.1.3 has NOT been distributed to any real/production endpoint agents yet — it exists only in `backend/static/`, never pulled via the auto-update pipeline. Confirmed by user. This means the fix can rebuild and overwrite the same 2.1.3 executable in place — no version bump to 2.1.4 needed, no auto-update-pipeline compatibility concern.

### Claude's Discretion
- Exact `Cargo.toml` syntax: set `default-features = false` on the `reqwest` dependency, keep the features already confirmed in use — `json`, `blocking`, `native-tls` (verified via direct grep of `agent_update.rs`'s `.json()` call and `reqwest::blocking::Client` usage across `lib.rs`/`agent_update.rs`/`heartbeat.rs`/`instructions.rs`/`registration.rs` — no other reqwest feature appears to be needed, but the planner/executor should double-check no `.json()`/streaming/multipart call elsewhere would need an additional feature before finalizing the feature list).
- Rebuild/cross-compile mechanism: reuse whatever cross-compilation process Phase 40 already used to produce `omni-agent-2.1.3-windows.exe` (x86_64-pc-windows-gnu target, per 40-VERIFICATION.md) — don't invent a new build pipeline.
- Verification: re-run `strings backend/static/omni-agent-2.1.3-windows.exe | grep -i rustls` post-fix and confirm it returns nothing (currently returns rustls/rustls-webpki/aws-lc-rs source paths). Also re-run `cargo check --offline` for a clean compile.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

- `.planning/v3.2-MILESTONE-AUDIT.md` — the audit finding that created this phase
- `.planning/phases/40-rust-agent-modernization-session-reliability/40-VERIFICATION.md` — full gap detail (Observable Truth #2), including exact file:line citations (`Cargo.toml` line 18, `src/lib.rs:40`, `src/capabilities/agent_update.rs:34,67`) and the `strings` command used to detect the problem

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `agent-install/omni-agent-rs/Cargo.toml:18` — the exact line to fix: `reqwest = { version = "0.13", features = ["json", "blocking", "native-tls"] }` needs `default-features = false` added.
- Confirmed reqwest call sites needing `json`/`blocking`: `src/lib.rs:40`, `src/capabilities/agent_update.rs:34,43,67`, `src/heartbeat.rs:203,243`, `src/instructions.rs:5,52,419`, `src/registration.rs:6`.

### Established Patterns
- No call site anywhere calls `.use_native_tls()` explicitly — the plan should either add that explicit call at each `Client::builder()` site for defense-in-depth, or rely purely on the feature-flag-only fix (disabling default-features removes the ambiguity even without the explicit call, since `native-tls` becomes the *only* enabled TLS backend feature). Planner should decide which is more robust/appropriate — this wasn't asked of the user since it's a technical implementation choice, not a product decision.

</code_context>

<specifics>
## Specific Ideas

None beyond the decisions captured above — this is a narrow, well-scoped bug-fix phase.

</specifics>

<deferred>
## Deferred Ideas

None.

</deferred>

---

*Phase: 45-close-gap-rust-01-tls-backend-explicit-decision*
*Context gathered: 2026-07-21*

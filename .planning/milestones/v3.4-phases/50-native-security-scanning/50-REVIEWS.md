# Phase 50 — REVIEWS (self-review, 2026-07-30)

> Reviewer: claude-self (adversarial pass — NO independent external model available; not a substitute for cross-AI review).

## RESOLUTION STATUS (replan 2026-07-30, `/gsd-plan-phase --all --reviews`)

- **HIGH (Cargo-dep DAG inverted) — RESOLVED.** Each crate now lands in the wave that first needs it: `ed25519-dalek` in 50-02 (Wave 1), `yara-x` in 50-03 (Wave 2). 50-05 adds NO crates (embeds the real key + wires dispatch + full build gate).
- **HIGH (yara-x windows discovered late) — RESOLVED.** 50-03 Task 0 is now an explicit SPIKE: add yara-x + cross-check windows-gnu FIRST, resolve-or-fallback before writing engine code.
- **MED (agent auth unresolved) — RESOLVED.** feed-bundle (50-01) + scan-result (50-04) pinned to `Depends(verify_agent_key)` (the agent-key dep used by `agent_tasks_endpoints`).
- **LOW (placeholder pubkey) — carried:** 50-02 must use a valid `[u8;32]` placeholder; 50-05 swaps the real key.

---
_Original findings below._


## HIGH — Cargo-dependency DAG ordering is inverted
`50-05` (Wave 3) owns the single `Cargo.toml` edit adding `yara-x` + `ed25519-dalek`, but `50-02` (Wave 1) and `50-03` (Wave 2) both need those crates to compile. As written, 50-02's `cargo check` in Wave 1 fails. The sequencing notes acknowledge it but the "add the dep when first compiling" workaround forces the executor to edit `Cargo.toml` outside 50-05's declared file set.
**Fix:** move the Cargo dep additions to a Wave-1 prerequisite (either a tiny 50-00 "add crates" plan, or make 50-02 own the `ed25519-dalek` add and 50-03 own the `yara-x` add). Re-scope 50-05 to dispatch + key-embed only.

## HIGH — yara-x Windows cross-compile risk discovered too late
The `cargo check --target x86_64-pc-windows-gnu` gate for yara-x sits in `50-03` Task 0 (Wave 2). If yara-x cannot cross-build, Wave 1 (50-01/02) is already spent and the whole engine approach pivots to the documented fallback late.
**Fix:** run the yara-x windows cross-build as a 1-hour spike BEFORE 50-02/03 (or as the first task of Wave 1). Confirm-or-fallback before building on it.

## MED — Verify agent auth scheme for the feed-bundle + scan-result endpoints
50-01/50-04 say "auth via get_current_user OR the agent-token path used by other agent endpoints — match how agent-facing endpoints authenticate." This is unresolved. An operator-facing bundle fetch vs an agent-token fetch are different. Pin the exact auth dependency the agent endpoints use (check `agent_heartbeat_endpoints` / `agent_core_endpoints`) so the agent can actually call it.

## LOW — Placeholder FEED_PUBLIC_KEY must be a valid [u8;32]
50-02's placeholder public key must be a syntactically valid 32-byte array or the module won't compile before 50-05 swaps the real key. Trivial, but call it out.

## Accepted / non-issues
- EICAR: only the hash is bundled — safe, correct.
- No LLM / no external network at scan time — consistent across the plans.

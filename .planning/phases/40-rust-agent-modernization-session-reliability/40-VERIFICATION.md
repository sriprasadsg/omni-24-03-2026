---
phase: 40-rust-agent-modernization-session-reliability
verified: 2026-07-20T15:52:10Z
status: passed
resolved: 2026-07-29T00:00:00Z
resolution_note: "The one gap below (RUST-01 TLS-backend explicit decision) was closed by Phase 45 (close-gap-rust-01-tls-backend-explicit-decision). Fix: reqwest default-features=false + explicit feature list excluding default-tls/rustls; re-verified rustls/aws-lc-rs/webpki token count = 0 in the rebuilt omni-agent-2.1.3-windows.exe (binary 9.9MB->7.1MB). See 45-VERIFICATION.md (status: passed) and v3.2-MILESTONE-AUDIT.md."
score: 4/4 must-haves verified (3/4 at initial verification; 4th closed by Phase 45)
behavior_unverified: 0
overrides_applied: 0
gaps:
  - truth: "The reqwest TLS backend (native-tls vs. the new rustls default) is an explicit, documented decision — not a silent behavior change shipped to endpoints"
    status: resolved
    resolved_by: "Phase 45 — see resolution_note above"
    reason: "Cargo.toml adds \"native-tls\" to reqwest's feature list but leaves default-features ON. reqwest 0.13's default feature set is `default = [\"default-tls\", \"charset\", \"http2\", \"system-proxy\"]` and `default-tls = [\"rustls\"]` (confirmed by reading the vendored reqwest-0.13.4 crate source at /root/.cargo/registry/.../reqwest-0.13.4/Cargo.toml). So both native-tls AND the full rustls stack (rustls, rustls-webpki, aws-lc-rs, rustls-platform-verifier, tokio-rustls) compile into the binary. `strings backend/static/omni-agent-2.1.3-windows.exe | grep rustls` confirms rustls/rustls-webpki/aws-lc-rs source paths and TLS-handshake code are physically present in the shipped 2.1.3 executable, not merely native-tls. No call site (`src/lib.rs:40`, `src/capabilities/agent_update.rs:34,67` — all three `reqwest::Client`/`reqwest::blocking::Client` builders) ever calls `.use_native_tls()`. The TLS backend actually used at runtime is determined entirely by reqwest's internal, undocumented `tls::TlsBackend::default()` precedence rule (`src/tls.rs:620-636`): it resolves to `NativeTls` only because `__native-tls` is enabled AND `http3` is NOT enabled — a fragile, implicit contract, not a decision visible anywhere in this codebase. If a future dependency bump transitively enables reqwest's optional `http3` feature, `TlsBackend::default()` silently flips to `Rustls` with zero code change in this repo — exactly the \"silent behavior change\" D-01 and this success criterion were written to prevent. This also means every endpoint now ships and executes an additional, currently-unused TLS/crypto stack (rustls + aws-lc-rs) purely as dead-but-compiled code, widening the supply-chain/CVE surface without any functional benefit."
    artifacts:
      - path: "agent-install/omni-agent-rs/Cargo.toml"
        issue: "reqwest line 18 has default-features implicitly ON (not set to false); default-tls = [\"rustls\"] therefore still compiles the rustls stack in alongside native-tls"
      - path: "agent-install/omni-agent-rs/src/lib.rs"
        issue: "reqwest::Client::builder() (line 40) never calls .use_native_tls() — backend selection is implicit"
      - path: "agent-install/omni-agent-rs/src/capabilities/agent_update.rs"
        issue: "Both reqwest::blocking::Client::builder() call sites (lines 34 and 67) never call .use_native_tls() — same implicit reliance"
    missing:
      - "Either add default-features = false to the reqwest dependency and re-list the other needed default features explicitly (charset, http2, system-proxy) alongside native-tls so rustls is excluded from the build entirely, or add an explicit .use_native_tls() call at all three Client::builder() call sites so the TLS backend is asserted in code, not inferred from reqwest's internal feature-precedence fallback"
      - "A short code comment (Cargo.toml or the client-construction call sites) documenting which mechanism was chosen and why, so the 'documented decision' half of the criterion is actually visible to a future reader"
---

# Phase 40: Rust Agent Modernization & Session Reliability Verification Report

**Phase Goal:** Ship the Rust endpoint agent (agent-install/omni-agent-rs, the shipping tree) on its modernized dependency stack as the 2.1.3 executable, and root-cause + fix the intermittent 401 Unauthorized error that has never been investigated.
**Verified:** 2026-07-20T15:52:10Z (gap closed 2026-07-29 by Phase 45)
**Status:** passed — 3/4 at initial verification; the 4th (RUST-01 TLS-backend explicit decision) was closed by Phase 45. See resolution_note in frontmatter.
**Re-verification:** No — initial verification + Phase 45 gap closure

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | The shipping Rust agent tree builds and runs on reqwest 0.13, sysinfo 0.39, tokio-tungstenite 0.30, rusqlite 0.40, hostname 0.4, with serde_yaml fully replaced by serde_norway, packaged as the 2.1.3 executable | ✓ VERIFIED | `Cargo.toml`/`Cargo.lock` resolve reqwest 0.13.4, sysinfo 0.39.6, tokio-tungstenite 0.30.0, rusqlite 0.40.1, hostname 0.4.2; `grep -rn serde_yaml` returns nothing in `Cargo.toml`/`src/`; `[package].version = "2.1.3"`; `backend/static/omni-agent-2.1.3-windows.exe` exists, starts with `MZ`, is 9.9MB (>1MB floor); `cargo check --offline` clean (0 errors, 4 pre-existing unrelated warnings, re-confirmed this session) |
| 2 | The reqwest TLS backend (native-tls vs. the new rustls default) is an explicit, documented decision — not a silent behavior change shipped to endpoints | ✗ FAILED | See gap above — `native-tls` feature literal is present, but `default-features` stays on, rustls's full stack (rustls, rustls-webpki, aws-lc-rs, rustls-platform-verifier, tokio-rustls) is confirmed compiled into the shipped `.exe` via `strings`, and no code (`Client::builder()` call sites) explicitly asserts native-tls. The "decision" as implemented is an implicit library-internal fallback, not an explicit, documented one — the criterion's own "not a silent behavior change" clause is precisely what is not satisfied |
| 3 | A user's authenticated session no longer intermittently drops to 401 Unauthorized during normal use; the root cause is identified and fixed (or definitively ruled out with evidence) | ✓ VERIFIED | Root cause identified (missing `revoked_tokens.jti` unique index despite `find_one_and_update`'s comment claiming one exists) and fixed: `backend/database.py:306` now creates `revoked_tokens.create_index("jti", unique=True, background=True)`. Behavioral spot-check: `cd backend && venv/bin/python -m pytest tests/test_auth_refresh_race.py -q` → **1 passed** — drives the real `/api/auth/refresh` route via `httpx.AsyncClient`+`ASGITransport` against a real MongoDB, fires two concurrent calls with the identical refresh token via `asyncio.gather`, asserts exactly one 200 + one 401 + exactly one persisted `revoked_tokens` document for the `jti`. `authentication_endpoints.py`'s `refresh_access_token` logic is byte-for-byte unchanged since before this phase (`git diff 72b4843 -- backend/authentication_endpoints.py` is empty) |
| 4 | Existing agent heartbeat and evidence-parity behavior (Phase 1) is unchanged after the dependency upgrade — no regression | ✓ VERIFIED | `git diff 72b4843 --stat` shows only `backend/agent_heartbeat_endpoints.py` changed (1 line: `_LATEST_AGENT_VERSION` value only) among heartbeat/evidence files. `pytest tests/test_rust_heartbeat_parity.py -q` → 2 passed, 1 failed (`test_rust02_and_rust03_db_calls`); the same failure was independently reproduced against the pre-phase-40 baseline commit `72b4843` in a disposable worktree per the orchestrator's pre-run gates, confirming it pre-dates this phase (also explicitly documented as a known pre-existing failure in 40-01-PLAN.md's Pitfall 4/RESEARCH.md). No other heartbeat- or evidence-parity-related test regressed: `test_authentication.py` + `test_auth_mfa.py` → 34 passed |

**Score:** 3/4 truths verified (0 present, behavior-unverified)

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `agent-install/omni-agent-rs/Cargo.toml` | native-tls feature pin + version 2.1.3 | ⚠️ PARTIAL | Version and native-tls literal present, but default-features not disabled — see Gap above |
| `backend/static/omni-agent-2.1.3-windows.exe` | Cross-compiled Windows PE, version 2.1.3 | ✓ VERIFIED | MZ header confirmed, 9,901,056 bytes, cross-compiled via x86_64-pc-windows-gnu |
| `backend/agent_heartbeat_endpoints.py` | `_LATEST_AGENT_VERSION = "2.1.3"` | ✓ VERIFIED | Line 132, exact match |
| `backend/database.py` | `revoked_tokens.create_index("jti", unique=True, background=True)` | ✓ VERIFIED | Line 306, adjacent to existing TTL index, matches `software_inventory` precedent shape |
| `backend/tests/test_auth_refresh_race.py` | Live-Mongo concurrent-refresh regression test | ✓ VERIFIED | 154 lines, uses `asyncio.gather`, real Mongo (motor), real router (no mocked `find_one_and_update`); passes (1 passed in 0.81s) |

### Key Link Verification

| From | To | Via | Status | Details |
|------|-----|-----|--------|---------|
| `backend/agent_heartbeat_endpoints.py` | `backend/static/omni-agent-2.1.3-windows.exe` | `_LATEST_AGENT_VERSION` matches committed binary version | ✓ WIRED | Both are "2.1.3"; `update_endpoints.py`'s glob-based `/latest` picks max(mtime), which will resolve to the newly-committed 2.1.3 file |
| `agent-install/omni-agent-rs/Cargo.toml` | `backend/static/omni-agent-2.1.3-windows.exe` | `CARGO_PKG_VERSION` compiled into binary | ✓ WIRED | `[package].version = "2.1.3"` matches the committed filename and heartbeat gate |
| `backend/database.py` | `backend/authentication_endpoints.py` | unique index backs `find_one_and_update`'s atomicity claim | ✓ WIRED | Index created; `refresh_access_token` (lines 415-437) unchanged; regression test proves the DB, not just app logic, rejects the duplicate |
| `backend/tests/test_auth_refresh_race.py` | `backend/database.py` | test creates/relies on the jti unique index | ✓ WIRED | Test explicitly creates the same index on its own test DB and asserts `count_documents == 1` after the race |
| `agent-install/omni-agent-rs/Cargo.toml` (reqwest features) | `agent-install/omni-agent-rs/src/lib.rs`, `src/capabilities/agent_update.rs` | explicit TLS-backend selection at Client construction | ✗ NOT_WIRED | Feature flag present in `Cargo.toml`, but no call site ever invokes `.use_native_tls()` — the link from "declared feature" to "asserted runtime behavior" is missing; behavior is inferred, not wired |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Concurrent /refresh with same token → exactly one winner | `cd backend && venv/bin/python -m pytest tests/test_auth_refresh_race.py -q` | `1 passed in 0.81s` | ✓ PASS |
| Rust crate bumps compile clean with native-tls feature | `cd agent-install/omni-agent-rs && cargo check --offline` | 0 errors, 4 pre-existing unrelated warnings | ✓ PASS |
| Existing auth suite unaffected | `pytest tests/test_authentication.py tests/test_auth_mfa.py -q` | `34 passed` | ✓ PASS |
| Heartbeat/evidence-parity suite — pre-existing failure isolated | `pytest tests/test_rust_heartbeat_parity.py -q` | `2 passed, 1 failed` (pre-existing, baseline-reproduced) | ✓ PASS (expected) |
| Shipped binary's actual compiled TLS backend(s) | `strings backend/static/omni-agent-2.1.3-windows.exe \| grep -i rustls` | rustls, rustls-webpki, aws-lc-rs source paths and TLS code all present | ⚠️ Confirms Gap above — both backends shipped |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| RUST-01 | 40-01-PLAN.md | Rust agent builds/ships on modernized deps, explicit TLS decision, 2.1.3 rebuild | ⚠️ PARTIALLY SATISFIED | Dependency bumps, versioning, and binary/pipeline delivery are all verified; the "explicit TLS-backend decision" sub-clause of RUST-01's own requirement text (REQUIREMENTS.md line 233) is not met — see Gap above. REQUIREMENTS.md was checked off `[x]` at commit `9643e37`, which is premature given this sub-clause |
| SESS-01 | 40-02-PLAN.md | Root-cause and fix the intermittent 401 | ✓ SATISFIED | Root cause (Mechanism A) identified and fixed with a real regression test; Mechanism B correctly and explicitly deferred per D-05. REQUIREMENTS.md correctly checked off `[x]` at commit `62c3286` |

No orphaned requirements: RUST-01 and SESS-01 are the only two IDs mapped to Phase 40 in REQUIREMENTS.md, and both appear in the two plans' frontmatter `requirements:` fields.

### Anti-Patterns Found

None (no TBD/FIXME/XXX/TODO/HACK/PLACEHOLDER markers in any file modified by this phase: `Cargo.toml`, `agent_heartbeat_endpoints.py`, `database.py`, `test_auth_refresh_race.py`).

### Human Verification Required

None triggered by the decision tree (all human-verification items in 40-VALIDATION.md — the live heartbeat auto-push round-trip on a real Windows endpoint — were explicitly scoped as manual-only, post-deploy, non-blocking by the plan itself, consistent with `verification-overrides.md` guidance for infrastructure that cannot exist in this sandbox). The one substantive issue found (TLS backend explicitness) is a code-level, deterministically-verifiable gap, not something needing human judgment — it is reported as `gaps_found`, not `human_needed`.

### Gaps Summary

Three of four ROADMAP success criteria are solidly met with concrete, reproducible evidence: the dependency modernization shipped correctly as 2.1.3 through the proven 3-step release lockstep (crate bumps verified, binary is a real PE, version numbers advance past every prior release, `_LATEST_AGENT_VERSION` gate is wired correctly to trigger D-02's existing auto-push pipeline); the 401 session bug's root cause (missing `revoked_tokens.jti` unique index) is fixed and proven by a real, non-mocked, passing concurrency regression test; and Phase 1 heartbeat/evidence-parity behavior shows no regression beyond the expected version-constant change (the one failing test in that suite is confirmed pre-existing and baseline-reproduced, unrelated to this phase's diff).

The one gap is the TLS-backend criterion (Success Criterion #2), which is not cosmetic: `Cargo.toml` adds the `native-tls` feature but does not disable `default-features`, so reqwest's default feature set (`default-tls = ["rustls"]`) still compiles the entire rustls/aws-lc-rs/rustls-platform-verifier stack into the shipped binary (directly confirmed via `strings` on the committed `.exe`). No code anywhere in the agent's three HTTP-client construction sites calls `.use_native_tls()`. The backend actually used at runtime today is `native-tls`, but only because of an internal, undocumented reqwest precedence rule (`native-tls` wins over `rustls` when both are compiled and `http3` is not enabled) — not because this codebase makes that decision explicitly. This is the exact "silent behavior change" risk D-01 and the success criterion were written to close off, just deferred to a future dependency bump instead of eliminated now. The fix is small (either `default-features = false` + re-add needed defaults, or explicit `.use_native_tls()` calls at the three builder sites) and does not require re-doing any other part of this phase's work.

**This looks like it could be judged intentional** (the plan's Task 1 explicitly instructed "Do NOT set default-features = false", and the runtime behavior today is correct). If the maintainer wants to accept this risk as-is rather than closing it now, add to this file's frontmatter:

```yaml
overrides:
  - must_have: "The reqwest TLS backend (native-tls vs. the new rustls default) is an explicit, documented decision — not a silent behavior change shipped to endpoints"
    reason: "{why accepting reliance on reqwest's internal TlsBackend::default() precedence is acceptable}"
    accepted_by: "{name}"
    accepted_at: "{ISO timestamp}"
```

---

*Verified: 2026-07-20T15:52:10Z*
*Verifier: Claude (gsd-verifier)*

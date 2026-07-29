---
phase: 45-close-gap-rust-01-tls-backend-explicit-decision
plan: 01
subsystem: infra
tags: [rust, reqwest, tls, native-tls, rustls, cargo, cross-compile, mingw]

requires:
  - phase: 40-rust-agent-modernization-session-reliability
    provides: reqwest 0.12→0.13 dependency bump and the existing cargo build --release --target x86_64-pc-windows-gnu cross-compilation mechanism that this plan reuses unchanged
provides:
  - reqwest built with default-features=false and an explicit native-tls-only feature list (json, blocking, native-tls, charset, http2, system-proxy)
  - Documenting Cargo.toml comment explaining the TLS-backend decision
  - Rebuilt backend/static/omni-agent-2.1.3-windows.exe with the rustls/aws-lc-rs/webpki stack excluded and native-tls confirmed present via strings
affects: [rust-agent-modernization, tls-backend, supply-chain-surface]

tech-stack:
  added: []
  patterns: ["explicit feature-list pinning to eliminate implicit default-feature TLS-backend fallback"]

key-files:
  created: []
  modified:
    - agent-install/omni-agent-rs/Cargo.toml
    - backend/static/omni-agent-2.1.3-windows.exe

key-decisions:
  - "reqwest default-features disabled; native-tls is the sole TLS backend, non-TLS defaults (charset/http2/system-proxy) re-listed explicitly to avoid behavior regression"
  - "No version bump — 2.1.3 rebuilt in place per D-01 since 2.1.3 was never distributed"

patterns-established:
  - "Explicit feature-list pinning for dependencies with alternative-backend defaults, verified against the resolved crate's own [features] section rather than trusted from memory"

requirements-completed: [RUST-01]

coverage:
  - id: D1
    description: "reqwest built with a single explicit TLS backend (native-tls); default-features disabled so the rustls default-tls stack cannot compile in"
    requirement: "RUST-01"
    verification:
      - kind: unit
        ref: "cd agent-install/omni-agent-rs && cargo check --offline"
        status: pass
      - kind: other
        ref: "grep -n 'default-features = false' agent-install/omni-agent-rs/Cargo.toml; grep -n 'reqwest' Cargo.toml shows no default-tls/rustls token"
        status: pass
    human_judgment: false
  - id: D2
    description: "Rebuilt backend/static/omni-agent-2.1.3-windows.exe in place with rustls/aws-lc-rs/webpki excluded, native-tls confirmed present, MZ header intact, no version bump"
    requirement: "RUST-01"
    verification:
      - kind: other
        ref: "strings backend/static/omni-agent-2.1.3-windows.exe | grep -i rustls (empty), grep -iE 'aws.lc.rs|webpki' (empty), grep -iE 'native.tls|schannel|openssl' (non-empty), head -c 2 = MZ, size 7157760 bytes"
        status: pass
      - kind: unit
        ref: "cd agent-install/omni-agent-rs && cargo test --offline (15 passed / 6 pre-existing env-only failures, none TLS-related)"
        status: pass
    human_judgment: false

duration: 20min
completed: 2026-07-21
status: complete
---

# Phase 45 Plan 01: TLS Backend Explicit Decision Summary

**reqwest pinned to native-tls-only via `default-features = false`, and `omni-agent-2.1.3-windows.exe` rebuilt in place with the rustls/aws-lc-rs/webpki stack proven absent by `strings`.**

## Performance

- **Duration:** ~20 min
- **Started:** 2026-07-21T17:36:00Z
- **Completed:** 2026-07-21T17:56:42Z
- **Tasks:** 2 completed
- **Files modified:** 2

## Accomplishments
- Confirmed via the vendored `reqwest-0.13.4` manifest that `default = ["default-tls", "charset", "http2", "system-proxy"]` — set `default-features = false` and explicitly re-listed `json`, `blocking`, `native-tls`, `charset`, `http2`, `system-proxy`, dropping only `default-tls` (the rustls path). Audited actual API call sites first (`grep` for multipart/stream/gzip/cookie/http2/Proxy — none found), confirming only `json` + `blocking` features are actually exercised.
- Added a documenting comment directly above the reqwest dependency line explaining the TLS-backend decision, satisfying the "documented decision" success criterion.
- Cross-compiled the agent for `x86_64-pc-windows-gnu` (target + `x86_64-w64-mingw32-gcc` toolchain both present in this sandbox — no environment blocker), copied the resulting exe over `backend/static/omni-agent-2.1.3-windows.exe` in place (same filename, version stayed 2.1.3 per D-01).
- Verified via `strings`: `rustls` absent, `aws-lc-rs`/`webpki` absent, `native-tls`/`schannel`/`openssl`-adjacent strings present (native-tls/schannel source paths: `schannel-0.1.29/src/tls_stream.rs`, `tokio-native-tls-0.3.1/src/lib.rs`) — proving native-tls is still the functional backend.
- Binary sanity: `MZ` header intact, 7,157,760 bytes (well over 1MB).

## Task Commits

Each task was committed atomically:

1. **Task 1: Make reqwest TLS backend an explicit single choice in Cargo.toml** - `f1eb9d3` (fix)
2. **Task 2: Rebuild 2.1.3 Windows exe in place and prove rustls is excluded** - `15e15ca` (fix)

**Plan metadata:** (this commit, following)

## Files Created/Modified
- `agent-install/omni-agent-rs/Cargo.toml` - reqwest dependency now `default-features = false` with explicit `json`/`blocking`/`native-tls`/`charset`/`http2`/`system-proxy` feature list, plus a documenting comment on the TLS-backend decision
- `backend/static/omni-agent-2.1.3-windows.exe` - rebuilt in place from the fixed Cargo.toml; rustls/aws-lc-rs/webpki no longer present; native-tls confirmed present; version unchanged (2.1.3)

## Decisions Made
- Preserved the non-TLS defaults (`charset`, `http2`, `system-proxy`) explicitly rather than letting them silently drop with `default-features = false`, to avoid an HTTP-behavior regression (T-45-03 mitigation from the plan's threat model).
- No version bump — matches D-01: 2.1.3 was never distributed, so the fix lands in place under the same filename/version.

## Deviations from Plan

None - plan executed exactly as written. The plan's Task 2 explicitly called for STOPPING and reporting if the `x86_64-pc-windows-gnu` target/toolchain were unavailable; both were present (`rustup target list --installed` showed the target, `x86_64-w64-mingw32-gcc` was on PATH), so the build proceeded normally with no fabricated or stale binary.

## Issues Encountered
- `cargo test --offline` reported 6 failures, all pre-existing and environmental (not caused by this plan's change): OS-name assertions expecting `"Windows"` but running natively as `"Linux"` in this sandbox, and capability-count mismatches (18/20 vs expected 15) — none reference TLS, rustls, or native-tls. These match the plan's acceptance criteria allowance for "same pre-existing/unrelated failures noted in 40-VERIFICATION.md — none TLS-related."

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- RUST-01 gap fully closed: single explicit TLS backend, rustls stack excluded from the shipped binary, decision documented, native-tls functional.
- No scope creep into Mechanism B (multi-tab session race) or any version bump — both explicitly out of scope per the plan.
- Ready for phase-level verification / UAT if scheduled.

---
*Phase: 45-close-gap-rust-01-tls-backend-explicit-decision*
*Completed: 2026-07-21*

## Self-Check: PASSED

All claimed files and commits verified present on disk / in git history.

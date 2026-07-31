---
phase: 40-rust-agent-modernization-session-reliability
plan: 01
subsystem: infra
tags: [rust, reqwest, native-tls, cargo, cross-compile, windows, heartbeat, agent-update]

# Dependency graph
requires: []
provides:
  - Rust endpoint agent (agent-install/omni-agent-rs) compiling clean with reqwest pinned to native-tls
  - Cross-compiled Windows PE binary at backend/static/omni-agent-2.1.3-windows.exe
  - Backend heartbeat version gate advanced to 2.1.3, triggering auto-push for registered agents
affects: [40-02, session-reliability]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "3-step release lockstep: Cargo.toml version bump + cross-compiled binary + _LATEST_AGENT_VERSION bump, all in one atomic commit (2.0.1 through 2.1.3)"

key-files:
  created:
    - backend/static/omni-agent-2.1.3-windows.exe
    - backend/static/omni-agent-2.1.3.b64
  modified:
    - agent-install/omni-agent-rs/Cargo.toml
    - backend/agent_heartbeat_endpoints.py

key-decisions:
  - "reqwest features list extended (not replaced) with native-tls, mirroring the existing tokio-tungstenite pin — no default-features=false"
  - "Version advanced straight to 2.1.3 (never reusing 2.1.0/2.1.1/2.1.2, which are already-shipped static filenames and already the prior _LATEST_AGENT_VERSION)"
  - "Generated the optional .b64 companion for parity with every prior release, even though no code path currently reads it"

patterns-established: []

requirements-completed: [RUST-01]

coverage:
  - id: D1
    description: "reqwest explicitly pins the native-tls feature (D-01); agent-install/omni-agent-rs compiles clean"
    requirement: "RUST-01"
    verification:
      - kind: unit
        ref: "cargo check --offline (0 errors, 4 pre-existing unrelated warnings)"
        status: pass
    human_judgment: false
  - id: D2
    description: "Windows binary cross-compiled and committed at backend/static/omni-agent-2.1.3-windows.exe, embedding version 2.1.3"
    requirement: "RUST-01"
    verification:
      - kind: unit
        ref: "cargo build --release --target x86_64-pc-windows-gnu; MZ header + size >1MB check"
        status: pass
    human_judgment: false
  - id: D3
    description: "Backend heartbeat gate advanced to 2.1.3 so already-registered agents auto-update via the existing pipeline (D-02)"
    requirement: "RUST-01"
    verification:
      - kind: unit
        ref: "grep '_LATEST_AGENT_VERSION = \"2.1.3\"' backend/agent_heartbeat_endpoints.py"
        status: pass
    human_judgment: true
    rationale: "Live heartbeat auto-push round-trip requires a real Windows endpoint, unavailable in this Linux sandbox (VALIDATION.md Manual-Only Verifications) — verification-after-deploy, not a completion blocker"

# Metrics
duration: 5min
completed: 2026-07-20
status: complete
---

# Phase 40 Plan 01: Rust Agent 2.1.3 Release Summary

**Shipped modernized Rust endpoint agent as version 2.1.3 — reqwest pinned to native-tls, Windows PE cross-compiled and committed, backend heartbeat gate advanced to auto-push to registered agents**

## Performance

- **Duration:** ~5 min (git commit timestamps: 20:47:51 → 20:50:46 IST)
- **Started:** 2026-07-20T20:47:51+05:30
- **Completed:** 2026-07-20T20:50:46+05:30
- **Tasks:** 2/2
- **Files modified:** 4 (Cargo.toml, agent_heartbeat_endpoints.py, omni-agent-2.1.3-windows.exe, omni-agent-2.1.3.b64)

## Accomplishments
- reqwest now explicitly declares `["json", "blocking", "native-tls"]` — closing the T-40-01 threat (reqwest 0.13's implicit rustls default silently changing trust-anchor behavior behind TLS-inspecting corporate proxies)
- Cross-compiled a valid Windows PE (`x86_64-pc-windows-gnu` target, MZ header confirmed, ~9.4MB, well over the 1MB sanity floor) and committed it to `backend/static/omni-agent-2.1.3-windows.exe`
- `backend/agent_heartbeat_endpoints.py::_LATEST_AGENT_VERSION` advanced from "2.1.2" to "2.1.3", so the existing D-02 auto-push pipeline instructs any Windows agent reporting an older version to self-update — zero pipeline code touched
- No prior static binary (2.1.0/2.1.1/2.1.2) overwritten or deleted; `update_endpoints.py` and `agent_download_endpoints.py` confirmed unmodified

## Task Commits

Each task was committed atomically:

1. **Task 1: Pin native-tls as an explicit reqwest feature (D-01)** - `9c3287e` (fix)
2. **Task 2: Release 2.1.3 — version bump, cross-compile, commit binary, advance heartbeat gate** - `44cf4f1` (feat)

**Plan metadata:** (this commit, follows)

## Files Created/Modified
- `agent-install/omni-agent-rs/Cargo.toml` - reqwest native-tls feature pin; [package] version 2.1.2 -> 2.1.3
- `backend/static/omni-agent-2.1.3-windows.exe` - cross-compiled Windows PE for the 2.1.3 release
- `backend/static/omni-agent-2.1.3.b64` - base64 companion, generated for parity with prior releases
- `backend/agent_heartbeat_endpoints.py` - `_LATEST_AGENT_VERSION` advanced to "2.1.3"

## Decisions Made
- Extended reqwest's feature array rather than replacing it, and did not set `default-features = false`, per D-01 and the plan's explicit constraint
- Advanced straight to 2.1.3, confirmed via `ls` that the filename was genuinely unused before building, avoiding the Pitfall 1 downgrade-gate failure mode
- Generated the optional `.b64` companion even though research confirmed no code path reads it, purely for parity with every prior release (2.0.5 through 2.1.2 all shipped one)

## Deviations from Plan

None - plan executed exactly as written. One incidental note: Task 1's `git add` on `Cargo.toml` picked up the file's full working-tree diff, which included the already-staged, already-compiling-clean crate bumps (reqwest 0.12→0.13, serde_yaml→serde_norway, sysinfo 0.32→0.39, rusqlite 0.32→0.40, hostname 0.3→0.4, tokio-tungstenite 0.23→0.30) that the plan itself describes as pre-existing uncommitted work on this branch. These landed in the Task 1 commit alongside the native-tls pin since git stages at file granularity — this is expected given the plan's own framing ("the crate bumps are already staged and compiling clean on this branch") and is not a scope deviation; no additional dependency changes were introduced beyond what the plan already assumed as baseline.

## Issues Encountered
None.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- RUST-01 fully delivered for this plan's scope: version 2.1.3 shipped across Cargo.toml, the committed binary, and the heartbeat gate
- Manual/UAT verification remains outstanding per 40-VALIDATION.md's Manual-Only gate: confirming a live Windows endpoint reporting 2.1.2 or earlier actually receives and applies the agent_update instruction on its next heartbeat — not exercisable in this Linux sandbox, not a blocker for plan completion
- Plan 40-02 (SESS-01, session refresh-race) is independent of this plan's changes and can proceed

---
*Phase: 40-rust-agent-modernization-session-reliability*
*Completed: 2026-07-20*

## Self-Check: PASSED

- FOUND: backend/static/omni-agent-2.1.3-windows.exe
- FOUND: backend/static/omni-agent-2.1.3.b64
- FOUND: 9c3287e (Task 1 commit)
- FOUND: 44cf4f1 (Task 2 commit)

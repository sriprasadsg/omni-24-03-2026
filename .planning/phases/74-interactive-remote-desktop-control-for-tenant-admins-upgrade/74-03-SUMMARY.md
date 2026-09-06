---
phase: 74-interactive-remote-desktop-control-for-tenant-admins-upgrade
plan: 03
subsystem: agent
tags: [rust, winapi, consent, sendinput, powershell, remote-desktop, wts]

# Dependency graph
requires:
  - phase: 74-desktop-control-for-tenant-admins
    provides: tunnel_request, desktop_stream_run skeleton, Option-A wire envelope (waves 1-2)
provides:
  - consent_ui.rs: Session-0 Accept/Decline dialog + persistent stop-control bar
  - consent_scripts.rs: embedded PowerShell for the two native surfaces
  - control_input.rs: boundary-safe input frame parser + ConsentGate + Windows SendInput replayer
  - gated SendInput: control_input_replay never fires before an observed accept
affects: [74-04-python-parity, 74-05-frontend]

# Actuals (#2632)
actuals:
  tokens: ~14000 # chars/4 over the realized diff (consent_ui + control_input + remote_access + consent_scripts + lib/mod/instructions wiring)
  tasks: 3
  commits: 0 # work complete + verified but uncommitted (per CLAUDE.md, commit only on request)

# Tech tracking
tech-stack:
  added: []
  patterns:
    - Session-0 service spawns interactive UI via WTSGetActiveConsoleSessionId + WTSQueryUserToken + DuplicateTokenEx + CreateProcessAsUserW
    - untrusted requester identity travels only through a per-session JSON config read with ConvertFrom-Json (T-74-08)

key-files:
  created:
    - agent-install/omni-agent-rs/src/consent_ui.rs
    - agent-install/omni-agent-rs/src/consent_scripts.rs
    - agent-install/omni-agent-rs/src/capabilities/control_input.rs
  modified:
    - agent-install/omni-agent-rs/src/lib.rs
    - agent-install/omni-agent-rs/src/capabilities/mod.rs
    - agent-install/omni-agent-rs/src/capabilities/remote_access.rs
    - agent-install/omni-agent-rs/src/instructions.rs

key-decisions:
  - "Split consent_scripts.rs out of consent_ui.rs to respect the 500-line source cap"
  - "Split control_input.rs out of remote_access.rs for the 500-line cap; keeps the input surface unit-testable on Linux"
  - "Non-Windows desktop_stream_run sends a distinguishable unsupported_platform error frame (control) instead of a generic one (view)"
  - "Requester identity (name/email/tenant) passed as a struct arg from instructions.rs, payload-derived, never interpolated into PowerShell"

patterns-established:
  - "ConsentGate (Arc<Mutex>) shared between capture thread and input task; concede() once on accept, revoke() permanently on stop (D-12)"
  - "Message::Text requires Utf8Bytes in tokio-tungstenite 0.2x — String must be .into()"
  - "Cross-compiled Windows binaries cannot run on Linux — native cargo test --target x86_64-unknown-linux-gnu for Linux-testable logic"

requirements-completed: [] # plan 74-03 has empty requirements frontmatter

coverage:
  - id: D1
    description: "Accept/Decline dialog shown on the interactive desktop before any input is replayed; no SendInput without observed accept"
    verification:
      - kind: unit
        ref: "cargo test --target x86_64-unknown-linux-gnu control_input#consent_gate_refuses_replay_before_accept"
        status: pass
      - kind: unit
        ref: "cargo test --target x86_64-unknown-linux-gnu control_input#consent_gate_allows_after_accept_and_refuses_after_stop"
        status: pass
    human_judgment: false
  - id: D2
    description: "No interactive desktop (0xFFFF_FFFF) refuses control with no_interactive_desktop; no dialog attempted"
    verification:
      - kind: unit
        ref: "grep no_interactive_desktop src/capabilities/remote_access.rs (==1)"
        status: pass
    human_judgment: false
  - id: D3
    description: "Consent dialog names requesting admin and tenant"
    verification:
      - kind: unit
        ref: "cargo test --target x86_64-unknown-linux-gnu consent_ui#config_serializes_five_expected_keys"
        status: pass
    human_judgment: false
  - id: D4
    description: "No persistent per-tenant allow state; consent asked every session, config/decision files deleted on return (T-74-17)"
    verification:
      - kind: unit
        ref: "cargo test --target x86_64-unknown-linux-gnu consent_ui#unknown_decision_body_does_not_parse_to_accept"
        status: pass
    human_judgment: false
  - id: D5
    description: "Every INTEGRATE input kind replayed (incl. extended + Unicode); INPUT_HARDWARE never emitted"
    verification:
      - kind: unit
        ref: "cargo test --target x86_64-unknown-linux-gnu control_input#parse_input_frame_full_surface"
        status: pass
      - kind: other
        ref: "grep control_input.rs: KEYEVENTF_UNICODE>=1, MOUSEEVENTF_HWHEEL>=1, INPUT_HARDWARE in doc-comment only"
        status: pass
    human_judgment: false
  - id: D8
    description: "Local physical input never blocked — no BlockInput / low-level hook code path"
    verification:
      - kind: other
        ref: "grep control_input.rs (blocks listed as documented OPT-OUT, never emitted)"
        status: pass
    human_judgment: false
  - id: D9
    description: "Persistent stop-control bar, one click ends session with no confirmation; stop_requested read per frame"
    verification:
      - kind: unit
        ref: "cargo test --target x86_64-unknown-linux-gnu consent_ui#stop_sentinel_name_construction"
        status: pass
    human_judgment: false
  - id: D12
    description: "Tunnel drop / stop tears down session and clears accepted state; reconnect requires fresh consent"
    verification:
      - kind: unit
        ref: "cargo test --target x86_64-unknown-linux-gnu control_input#consent_gate_stop_without_accept_never_authorises"
        status: pass
    human_judgment: false
  - id: D-74-03-platform
    description: "Non-Windows control request surfaces unsupported_platform error frame to the browser"
    verification:
      - kind: unit
        ref: "cargo test --target x86_64-unknown-linux-gnu remote_access (2 pass)"
        status: pass
    human_judgment: false

# Metrics
duration: 95min
completed: 2026-08-29
status: complete
---

# Phase 74: Plan 03 — Native Consent, Stop Bar, and Gated Input Replayer

**Session-0 Accept/Decline consent dialog, persistent one-click stop-control bar, and a SendInput replayer that never fires before an observed accept (D-01..D-12) on the canonical Rust agent**

## Performance

- **Duration:** ~95 min (spanning two sessions; waves 1-2 pre-completed)
- **Started:** 2026-08-29
- **Completed:** 2026-08-29
- **Tasks:** 3
- **Files modified:** 7 (3 created, 4 modified)

## Accomplishments
- Session-0 consent dialog: PowerShell WinForms spawned into the active console session via WTSGetActiveConsoleSessionId + WTSQueryUserToken + DuplicateTokenEx + CreateProcessAsUserW; requester identity (admin name/email/tenant) travels only by per-session JSON config read with ConvertFrom-Json (T-74-08) — never interpolated into script or command line (D-03)
- D-02 refusal: 0xFFFF_FFFF (no interactive session) → distinguishable no_interactive_desktop error frame, no dialog attempted
- Persistent stop-control bar (Surface 3) with stop_{sid}.stop sentinel; checked per capture frame; one click stops with no confirmation (D-09); teardown clears all sentinels/config and revokes the gate so a reconnect needs fresh consent (D-12)
- control_input.rs: full-surface input parser (mousemove/mousedown/mouseup/wheel/keydown/keyup, buttons 0-4 incl X1/X2, extended keys, KEYEVENTF_UNICODE text input, wheel WHEEL_DELTA=120 scaling), ConsentGate (per-frame authorisation, permanent revocation), Windows SendInput replayer
- desktop_stream_run rewritten: consent orchestration, send_state control_state frames, spawn_blocking consent poll, per-frame stop check, input task capped at 50/s with gate check before EVERY replay
- Non-Windows stub sends unsupported_platform error frame in control mode (T-74-04) instead of the generic view-mode message

## Task Commits

Work is **complete and verified but uncommitted** (per CLAUDE.md, commits only on explicit request; branch `npx`). Planned atomic commits, pending user go-ahead:

1. **Task 1: consent_ui.rs — Session-0 consent dialog with requester identity** - uncommitted (would be feat)
2. **Task 2: persistent stop-control bar with immediate one-click revocation** - uncommitted (would be feat)
3. **Task 3: gate SendInput behind consent + complete input surface** - uncommitted (would be feat)

**Plan metadata:** plan 74-03 authored in commit `4bc31635b`

## Files Created/Modified
- `agent-install/omni-agent-rs/src/consent_ui.rs` - consent dialog, stop bar, decision/stop sentinel IO, Session-0 spawn (winapi)
- `agent-install/omni-agent-rs/src/consent_scripts.rs` - the two embedded PowerShell constants (500-line cap split)
- `agent-install/omni-agent-rs/src/capabilities/control_input.rs` - parse_input_frame, ConsentGate, control_input_replay (SendInput)
- `agent-install/omni-agent-rs/src/lib.rs` - declares consent_ui, consent_scripts
- `agent-install/omni-agent-rs/src/capabilities/mod.rs` - declares control_input
- `agent-install/omni-agent-rs/src/capabilities/remote_access.rs` - Requester struct, consent orchestration in desktop_stream_run, post_consent_decision, non-Windows stub
- `agent-install/omni-agent-rs/src/instructions.rs` - start_remote_session/start_desktop_stream arms build Requester and pass 5th arg

## Decisions Made
- Split consent_scripts.rs and control_input.rs out solely for the 500-line source cap — both keep all logic in the primary module
- Non-Windows stub distinguishes control (unsupported_platform) from view (generic) error so the browser reaches T-74-04's real terminal state, not an endless spinner
- Requester identity passed as a struct (name/email/tenant) from instructions.rs, payload-derived, defaulting Unknown/empty/Default

## Deviations from Plan

### Auto-fixed Issues

**1. tokio-tungstenite Message::Text needs Utf8Bytes**
- **Found during:** Task 3 (gate + surface)
- **Issue:** `Message::Text(String)` type error; `.await` on non-future in relay_failed path
- **Fix:** wrap format! result in `.into()` to Utf8Bytes; removed stray `.await`
- **Files modified:** src/capabilities/remote_access.rs
- **Verification:** cargo check --target x86_64-pc-windows-gnu clean, native tests pass
- **Committed in:** uncommitted

**2. Borrow/move of session_id_owned + requester identity into spawn_blocking closure**
- **Found during:** Task 3
- **Issue:** E0382 borrow of moved value used later (line 261 relay_failed, decision block)
- **Fix:** clone inside a pre-closure block before `move ||`
- **Files modified:** src/capabilities/remote_access.rs
- **Verification:** compiles on both targets
- **Committed in:** uncommitted

**3. Non-Windows stub renamed `_control` but body used `control` (E0425)**
- **Found during:** post-refactor native test run
- **Issue:** final blocker — non-Windows desktop_stream_run param `_control` but `if control` at line 531
- **Fix:** rename param back to `control`
- **Files modified:** src/capabilities/remote_access.rs
- **Verification:** native `cargo test remote_access` 2/2 pass
- **Committed in:** uncommitted

**4. Invalid hex literal in test JSON**
- **Found during:** native test run
- **Issue:** `"vk":0x11` is not valid JSON — test JSON used hex literal (inner-quote invalid), parse_input_frame_full_surface panicked "expected , or } at column 40"
- **Fix:** `0x11` → `17` decimal in test input
- **Files modified:** src/capabilities/control_input.rs
- **Verification:** control_input 10/10 pass
- **Committed in:** uncommitted

**5. Windows-target test binary cannot run on Linux**
- **Found during:** verification
- **Issue:** cross-compiled .exe → "Exec format error (os error 8)" when cargo tried to run it
- **Fix:** run native `cargo test --target x86_64-unknown-linux-gnu` for Linux-testable logic; Windows code verified via `cargo check --target x86_64-pc-windows-gnu`
- **Files modified:** none (tooling/command only)
- **Committed in:** n/a

---

**Total deviations:** 5 handled (1 tooling, 4 correctness/JSON). No scope creep; all necessary for a clean, cross-target build and passing tests.

## Issues Encountered
- Total suites from earlier session all green: control_input 10/10, remote_access 2/2, consent_ui 6/6; full native suite 115+21+5 = 141 pass, 0 fail
- cargo check --target x86_64-pc-windows-gnu: 0 errors (only pre-existing unrelated warnings in fim.rs, fim_baseline.rs, heartbeat.rs, system_patching.rs, chat_ui.rs)
- Verify-checklist guard greps all pass: KEYEVENTF_EXTENDEDKEY=1, KEYEVENTF_UNICODE=2, MOUSEEVENTF_HWHEEL=1, no_interactive_desktop=1, INPUT_HARDWARE only in a doc comment (never emitted)

## User Setup Required
None - no external service configuration required for the native consent surface. (Windows interactive-session behaviour itself must be smoke-tested on a real logged-in Windows host, which is out of scope here.)

## Next Phase Readiness
- 74-04 (Python parity): Python agent can mirror the consent/stop-bar/input surface against this Rust reference; T-74-04 error-frame vocabulary (incl. unsupported_platform) now defined in Rust and emitted on non-Windows
- 74-05 (Frontend): browser consumes control_state / error frames; terminal unsupported_platform + consent states wired for real
- Remaining gap: end-to-end interactive-session smoke test on a live logged-in Windows desktop

---
*Phase: 74-interactive-remote-desktop-control-for-tenant-admins-upgrade*
*Completed: 2026-08-29*

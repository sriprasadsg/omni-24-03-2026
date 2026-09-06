---
phase: 74-interactive-remote-desktop-control-for-tenant-admins-upgrade
plan: 04
type: execute
wave: 3
depends_on: ["74-01", "74-02"]
files_modified:
  - agent/capabilities/consent_ui.py
  - agent/capabilities/consent_scripts.py
  - agent/capabilities/remote_access.py
  - agent/capabilities/win_input.py
  - agent/agent.py
  - agent/test_remote_input.py
autonomous: true
requirements: []

estimate:
  tokens: 70000
  raw_tokens: 70000
  tasks: 3
  confidence: low

must_haves:
  truths:
    - "The legacy Python agent speaks the same input and control_state frame contract that the Rust agent speaks."
    - "The Python agent's desktop-stream WebSocket now surfaces inbound frames via on_message callback."
    - "The Python agent blocks control until the interactive endpoint user clicks Accept."
    - "Requester identity reaches the consent dialog through a JSON config file, never through PowerShell string interpolation."
  artifacts:
    - agent/capabilities/consent_ui.py (request_consent, show_stop_bar, hide_stop_bar, stop_requested)
    - agent/capabilities/remote_access.py (on_message callback, ctypes SendInput replayer)
    - agent/test_remote_input.py (platform-independent tests)
  key_links:
    - "agent/agent.py execute_remote_session must branch on session type control"
    - "WebSocketApp construction in start_desktop_stream must gain on_message callback"
---

# Phase 74-04: Python Agent Parity

Brought the legacy Python agent to parity with the Rust agent on interactive control.

## Accomplishments
- Created `agent/capabilities/consent_ui.py` with Session-0 consent dialog and stop bar using pywin32.
- Implemented input frame parsing (`parse_input_frame`) matching Rust validation rules.
- Created ctypes `SendInput` replayer covering all INTEGRATE input kinds from COVERAGE.md.
- Added `on_message` callback to desktop-stream `WebSocketApp` (closes Pitfall 2 from RESEARCH.md).
- Implemented consent gate in input relay — consults `ConsentGate` and `stop_requested` before every `SendInput`.
- Added control-mode flag and identity args to `start_desktop_stream` signature.
- Extended `agent/agent.py` execute_remote_session to route control sessions.
- Created `agent/test_remote_input.py` with platform-independent tests (Linux-runnable).

## Files Created/Modified
- `agent/capabilities/consent_ui.py`: Consent dialog, stop bar, session-0 spawn.
- `agent/capabilities/consent_scripts.py`: Embedded PowerShell WinForms scripts (extracted for 500-line cap).
- `agent/capabilities/remote_access.py`: Input relay, on_message callback, consent flow.
- `agent/capabilities/win_input.py`: ctypes structures and SendInput replayer.
- `agent/agent.py`: Control dispatch in execute_remote_session.
- `agent/test_remote_input.py`: Platform-independent test coverage.

## Threat Mitigations (from plan)
- T-74-08b: Requester identity via JSON config file, not command line.
- T-74-04b: Boundary validation on all input frames.
- T-74-02b: Per-frame consent gate check.
- T-74-11b: on_message only wired for control mode.
- T-74-23: ctypes.wintypes for struct safety.
- T-74-18b: Per-second replay ceiling.
- T-74-24: No new dependencies (pywin32, websocket-client already pinned).

## Verification
- `pytest agent/test_remote_input.py -q` — 10+ tests pass.
- `pytest agent/ -q` — full suite passes.
- `git diff --stat agent/requirements.txt` — no changes.
- Modules import cleanly on Linux.

## Status
Complete.
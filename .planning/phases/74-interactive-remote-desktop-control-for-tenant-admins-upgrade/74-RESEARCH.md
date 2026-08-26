# Phase 74: Interactive Remote Desktop Control - Research

**Researched:** 2026-08-26
**Domain:** Windows input injection (SendInput), Session-0 service-to-interactive-desktop UI, WebSocket tunnel protocol extension, RBAC permission addition, append-only audit trail
**Confidence:** HIGH (all core protocol/RBAC/UI-injection claims verified by reading the actual source this session; a few external API details are CITED from official docs; no claim in this document is pure training-knowledge guesswork)

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Consent flow**
- **D-01:** When an interactive user is logged into the target Windows session, control is blocked until that user clicks Accept on a dialog. This is a hard gate — the RBAC permission alone does not grant control. — **Reversibility:** costly — rationale: this is the load-bearing security/UX guarantee the rest of the decisions in this phase (D-04, D-09, D-12) are built around; loosening it later means redesigning the consent state machine those decisions depend on, not a local flag flip.
- **D-02:** When there is no interactive user logged in (headless/Session-0 — common for monitored servers), the control request is refused gracefully, using the same "no interactive desktop available" failure shape the existing `desktop_stream_run` already returns for view-only streaming.
- **D-03:** The consent dialog shows the requesting admin's identity (name/email) and tenant, not a generic message — matches the Zoho Assist/TeamViewer convention and strengthens the audit trail.
- **D-04:** Consent is required every session — no "always allow this tenant" persistent opt-out. — **Reversibility:** costly — rationale: adding a persistent-trust toggle later is a real feature (new storage, new UI, new bypass path through D-01's gate), not a config change, and it directly weakens the per-session consent guarantee this phase establishes.

**Input scope**
- **D-05:** Full, unrestricted keyboard and mouse passthrough — no blocklist for OS-level combos (e.g., Ctrl+Alt+Del, which SendInput cannot inject anyway due to Windows' Secure Attention Sequence protection).
- **D-06:** Binary permission model only — `view:remote_access` (screenshot stream, unchanged) or `control:remote_access` (full input). No intermediate "mouse-only" tier. — **Reversibility:** costly — rationale: adding a third tier later means a new permission constant plus a new code path through the RBAC check, the frontend mode switcher, and the agent's input dispatcher — not a local change.
- **D-07:** Clipboard sync (admin↔endpoint copy/paste) is explicitly out of scope for this phase — real Zoho Assist feature, but it opens its own data-exfiltration threat-model questions and belongs in a follow-up phase.
- **D-08:** The local physical user's own mouse/keyboard keeps working during a control session — both parties can act simultaneously, matching Zoho Assist's default attended mode. No local-input lockout mechanism. — **Reversibility:** costly — rationale: adding a lockout later requires new low-level OS input-blocking code that doesn't exist today; this decision means no such code path gets built in this phase.

**Endpoint-side kill switch**
- **D-09:** The endpoint (local) user gets a persistent on-screen indicator during a control session with a one-click "stop control" affordance — matches Zoho Assist. This is what makes D-01's consent meaningful (consent that can't be revoked mid-session isn't real consent).
- **D-10:** The tenant admin can also disconnect the session unilaterally from `RemoteAccessDashboard.tsx`.
- **D-11:** A platform-admin/super-admin gets a cross-tenant force-kill for any active control session — reuses the existing `_REMOTE_SUPER_ROLES` bypass pattern already in `backend/remote_endpoints.py`.
- **D-12:** If the WebSocket tunnel drops mid-session, the session is treated as ended — reconnecting requires the endpoint user to accept a fresh consent prompt. No silent auto-resume. — **Reversibility:** costly — rationale: this is the mechanism that makes the per-session consent guarantee (D-04) hold across network interruptions; adding an auto-resume grace window later reopens exactly the "was control silently regranted?" ambiguity this decision closes.

**Agent scope**
- **D-13:** Interactive control is built for **both** the canonical Rust agent (`agent-install/omni-agent-rs`) and the legacy Python agent (`agent/capabilities/remote_access.py`) — not Rust-only, despite Rust-only being the lower-cost recommendation (the Python agent isn't the primary install path per Phase 50+ and this doubles the SendInput/consent-dialog implementation surface across two languages). — **Reversibility:** costly — rationale: once both trees implement the same WS frame contract and consent-dialog behavior, dropping the Python side later means deprecating a shipped code path some installed base may depend on, not deleting dead code.
- **D-14:** Faster/continuous screen capture (replacing the current periodic PowerShell screenshot loop with something like Windows Graphics Capture API / DXGI Desktop Duplication) remains a stretch goal only — not required for this phase to be considered complete.

### Claude's Discretion
- Exact wording/shape of the Windows-only rejection response for control requests on non-Windows agents — whether it reuses the identical error string `desktop_stream_run` already returns, or gets a distinct message so the dashboard can tell "wrong OS" apart from "no active session." Left to planner/research.
- Exact Windows input-injection mechanism on the Python agent side (raw `ctypes` call to `user32.SendInput`, or a library like `pywin32`) — Rust side uses the `windows` crate per the existing `remote_access.rs` pattern; Python's equivalent isn't decided. Research should check what's already a dependency before adding one. **[Research correction: the Rust side actually uses the `winapi` crate, not the `windows` crate — see State of the Art section below.]**
- Exact consent-dialog implementation on the endpoint (native Win32 `MessageBox`-style modal vs. a custom always-on-top window) for both agent languages.
- Exact audit-log record shape for control sessions — reuse the append-only pattern from `backend/remediation_audit_service.py` (cited by prior phases as the house pattern); exact fields (session_id, requester, tenant, start/end timestamps, consent-decision, disconnect-reason) left to planner.
- The `control:remote_access` permission name itself is already locked by the ROADMAP.md Phase 74 goal (written before this discussion) — not re-litigated here, just carried forward.

### Deferred Ideas (OUT OF SCOPE)
- Clipboard sync (admin↔endpoint copy/paste) — considered and explicitly deferred to a future phase, see D-07. Not lost, just out of this phase's scope due to its own data-exfiltration threat-model questions.
</user_constraints>

<phase_requirements>
## Phase Requirements

No REQUIREMENTS.md exists for this phase — it was added standalone via `/gsd-phase` after the v4.1 milestone shipped, with no open milestone tracking REQ-IDs. There are no requirement IDs to map. The planner should treat ROADMAP.md's Phase 74 goal text and this document's `## User Constraints` (D-01 through D-14) as the substitute acceptance criteria.
</phase_requirements>

## Summary

This phase extends an existing, working view-only remote-desktop feature into full interactive control, across **two** independently-implemented agents (Rust canonical, Python legacy) plus the backend WS relay and RBAC layer. The single most important discovery this session is that **the Rust agent already contains a fully-built, battle-tested solution to the hardest problem in this phase** — showing UI from a Session-0 Windows service into the interactive user's desktop — in `agent-install/omni-agent-rs/src/chat_ui.rs`. That module's `win::spawn_in_active_session()` uses `WTSGetActiveConsoleSessionId` → `WTSQueryUserToken` → `DuplicateTokenEx` → `CreateProcessAsUserW` to launch a PowerShell WinForms window into the active console session, and `heartbeat.rs::logged_in_user()` already detects "no interactive session" via the same `0xFFFFFFFF` sentinel that D-02's refusal path needs. The consent dialog should be built as a near-copy of this exact pattern (a new PowerShell WinForms Accept/Decline script launched the same way), not invented from scratch.

The second major discovery is a **protocol gap that blocks the entire phase if missed**: the WebSocket endpoint `RemoteDesktop.tsx` currently connects to (`/api/tunnel/{session_id}/viewer`) is deliberately **receive-only** on the backend — `tunnel_endpoints.py`'s `tunnel_viewer_side` reads anything the browser sends into a **throwaway `asyncio.Queue()` that nothing drains**, so any mouse/keyboard frame the viewer sends today vanishes silently. The bidirectional relay already exists and already works — it's the `/api/tunnel/{session_id}/user` endpoint, proven daily by `RemoteTerminal.tsx`. The plan should route control-mode desktop sessions through `/user` (not `/viewer`), and extend each agent's desktop-stream loop to also read a concurrent WS input channel (the Rust agent's own `reverse_shell_run` already demonstrates the split-read/write-with-two-tasks pattern to copy).

Third, a corroborating correction to `74-CONTEXT.md`'s canonical-refs list: `backend/remote_access_service.py` (`ConnectionManager`) is **dead code** — grepping the entire `backend/` tree found zero importers. The live relay backend logic — the one to actually extend — is `tunnel_endpoints.py`'s module-level `_tunnels` dict of `asyncio.Queue` pairs.

Fourth, `74-CONTEXT.md`'s "Claude's Discretion" note says the Rust side "uses the `windows` crate" — verified false: `remote_access.rs`, `heartbeat.rs`, and `chat_ui.rs` all use the older, frozen **`winapi` 0.3** crate exclusively (already a dependency, already linking `wtsapi32`/`userenv`/`advapi32` via its enabled feature list), and `chat_ui.rs`'s own header comment explains why: `"winapi (frozen 0.3 API) is used rather than the windows crate to keep the FFI surface stable."` `SendInput`/`INPUT`/`MOUSEINPUT`/`KEYBDINPUT` live in winapi's `winuser` module, which is **not yet** in the crate's enabled feature list and must be added.

**Primary recommendation:** Build the consent dialog and mouse/keyboard input relay as structural copies of two patterns that already exist and already work in this exact codebase — `chat_ui.rs`'s CreateProcessAsUserW session-injection for the UI, and `reverse_shell_run`'s split-read/write task pattern for bidirectional WS I/O — rather than researching or inventing new mechanisms. On the Python side, both equivalents (`win32ts`/`win32process`/`win32security` for session injection, raw `ctypes` `SendInput` structs for input replay) require zero new pip dependencies — `pywin32` is already a Windows-only requirement.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Mouse/keyboard capture (viewer canvas) | Browser / Client | — | `RemoteDesktop.tsx`'s `<canvas>` is the only place raw DOM mouse/key events exist; must serialize to JSON and send over the existing WS |
| Input-frame relay (viewer ↔ agent) | API / Backend (WS relay) | — | `tunnel_endpoints.py`'s `_tunnels` queue pair is the transport; no new endpoint, reuse `/user` not `/viewer` |
| Win32 `SendInput` replay | Endpoint Agent (Rust + Python) | — | Only the agent process, running on the target Windows host, can call `user32.dll SendInput` |
| Consent dialog rendering | Endpoint Agent → interactive user session | — | Must run as the logged-in user (`winsta0\default`), not as the SYSTEM service — `CreateProcessAsUserW` is the only path out of Session-0 isolation |
| Consent decision transport | Endpoint Agent → API / Backend | — | Accept/Decline in the PS-spawned window must reach the backend (poll-and-report, mirroring `chat_ui.rs`'s `Invoke-RestMethod` pattern) before the agent starts injecting input |
| `control:remote_access` RBAC gate | API / Backend | — | `rbac_utils.py`'s `require_permission()` dependency factory — same mechanism `view:remote_access` already uses |
| Session audit trail | API / Backend | Database / Storage | New append-only collection modeled on `remediation_audit_service.py`'s `write_audit`/`list_audit` shape |
| Endpoint-side "stop control" affordance (D-09) | Endpoint Agent → interactive user session | — | Same `CreateProcessAsUserW`-spawned always-on-top window; needs a persistent (not one-shot) UI element |
| Admin-side disconnect (D-10) / super-admin force-kill (D-11) | API / Backend | Browser / Client (button) | New endpoint reaching into `tunnel_endpoints.py`'s module-level `_tunnels` dict — see Pitfall 3 |
| Session-drop-ends-session (D-12) | API / Backend | Endpoint Agent | Backend already flips `remote_sessions.status` to `"closed"` on `/user` disconnect (`tunnel_endpoints.py:141-145`); reconnect must be a fresh `start_remote_session` call, not a resume |

## Standard Stack

No new external packages are required in **either** ecosystem. This phase is additive to already-present dependencies.

### Core (already present — verify no version bump needed)

| Library | Version (as pinned) | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `winapi` (Rust, Windows-only target) | `0.3` [VERIFIED: agent-install/omni-agent-rs/Cargo.toml:58-61] | Win32 FFI — needs the `winuser` feature added for `SendInput`/`INPUT`/`MOUSEINPUT`/`KEYBDINPUT` | Already used for `wtsapi32`/`userenv`/`processthreadsapi` in `chat_ui.rs`/`heartbeat.rs`; adding one more module (`winuser`) is a one-line Cargo.toml change, not a new crate |
| `pywin32` (Python, Windows-only) | `>=306; sys_platform=="win32"` [VERIFIED: agent/requirements.txt:25] | `win32ts` (`WTSGetActiveConsoleSessionId`, `WTSQueryUserToken`), `win32process` (`CreateProcessAsUser`), `win32security` (`DuplicateTokenEx`) | Already a dependency for the Windows service/ETW path; ships the exact modules needed for session-injection, no new install |
| `ctypes` (Python stdlib) | n/a | `user32.dll SendInput` via raw `INPUT`/`MOUSEINPUT`/`KEYBDINPUT` ctypes structures | Zero footprint — lower cost than adding a `pywin32`-based input-injection wrapper (pywin32 does not itself wrap `SendInput`; only the legacy `mouse_event`/`keybd_event` calls are exposed via `win32api`, which Microsoft's own docs mark superseded by `SendInput`) [CITED: docs.rs/winapi, MS Learn `SendInput`] |
| `websocket-client` | `>=1.7.0` [VERIFIED: agent/requirements.txt:21] | Python agent's existing WS client for the tunnel (`start_desktop_stream`/`start_reverse_shell`) | Already carries the desktop-stream traffic; the new input-relay channel is additional message types on the same socket, not a new library |
| `tokio-tungstenite` (Rust) | already a dependency (used throughout `remote_access.rs`) | Rust agent's WS client | Same reasoning — extend, don't add |

### Cargo.toml change required

```toml
[target.'cfg(windows)'.dependencies]
winreg = "0.52"
windows-service = "0.7"
winapi = { version = "0.3", features = [
    "minwindef", "winnt", "handleapi", "errhandlingapi", "processthreadsapi",
    "securitybaseapi", "userenv", "winbase", "wtsapi32",
    "winuser",   # <-- ADD: SendInput, INPUT, MOUSEINPUT, KEYBDINPUT, virtual-key constants
] }
```
[VERIFIED: agent-install/omni-agent-rs/Cargo.toml:55-61 — exact current block quoted above minus the new line]

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Raw `winapi::um::winuser::SendInput` (Rust) | The `windows` crate (Microsoft's modern generated bindings) | `chat_ui.rs`'s own header comment already made this call for the whole agent: `"winapi (frozen 0.3 API) is used rather than the windows crate to keep the FFI surface stable."` [VERIFIED: agent-install/omni-agent-rs/src/chat_ui.rs:12-13] Introducing `windows` alongside `winapi` for one feature would fragment the FFI surface the rest of the agent deliberately avoids fragmenting. Stay on `winapi`. |
| Raw `ctypes` `SendInput` (Python) | A third-party automation lib (`pyautogui`, `pynput`) | New dependency, larger attack surface, and neither is a stdlib/already-present dependency; per CONTEXT.md's own framing this should be "the lowest-footprint way," which raw `ctypes` is |
| `CreateProcessAsUserW` for consent dialog | `WTSSendMessage` (message-box-only, no buttons/interactivity — this is what `chat_display.rs`'s one-way `msg.exe` fallback already uses) | `WTSSendMessage`/`msg.exe` cannot render an Accept/Decline choice or the requester-identity-rich dialog D-03 requires — it is one-way text only. Confirmed by `chat_display.rs`'s own doc comment: `"Delivery is one-way (msg.exe has no reply input)."` [VERIFIED: agent-install/omni-agent-rs/src/chat_display.rs:1-8] Use it only as the last-resort fallback if `CreateProcessAsUserW` itself fails (e.g. no console session — which is exactly D-02's refusal case, so no fallback is actually needed there). |

## Package Legitimacy Audit

**No new external packages are introduced by this phase in either ecosystem.** The Package Legitimacy Gate does not apply — `winapi` and `pywin32` are pre-existing, long-established dependencies (verified present in `Cargo.toml`/`requirements.txt` this session), and `ctypes` is Python stdlib. The only dependency-manifest change is a Cargo **feature-flag** addition (`winuser`) to the already-vetted `winapi` crate, not a new crate.

| Package | Registry | Status this phase | Disposition |
|---------|----------|-------|-------------|
| `winapi` | crates.io | Already present; add `winuser` feature | No audit needed — pre-existing dependency |
| `pywin32` | PyPI | Already present, unchanged | No audit needed — pre-existing dependency |
| `ctypes` | stdlib | N/A | Not a package |

**Packages removed due to [SLOP] verdict:** none
**Packages flagged as suspicious [SUS]:** none

## Architecture Patterns

### System Architecture Diagram

```
┌─────────────────────────┐         ┌──────────────────────────────────────────┐
│  Browser (Tenant Admin) │         │              Backend (FastAPI)             │
│                          │         │                                            │
│  RemoteDesktop.tsx       │  WSS    │  tunnel_endpoints.py                       │
│  ┌────────────────────┐ │ ──────► │  ┌──────────────────────────────────────┐ │
│  │ <canvas> renderFrame│ │ /user   │  │ _tunnels[session_id] = {u2a, a2u}    │ │
│  │ onMouseDown/Move/Up │ │ (NOT    │  │  tunnel_user_side:  recv→u2a, a2u→send│ │
│  │ onWheel/onKeyDown/Up│ │ /viewer)│  │  tunnel_agent_side: recv→a2u, u2a→send│ │
│  │  → JSON input frame │ │         │  └──────────────────────────────────────┘ │
│  │  → ws.send(frame)   │ │         │                                            │
│  └────────────────────┘ │         │  remote_endpoints.py                       │
│                          │         │   POST /session/start → agent_instructions │
│  RemoteAccessDashboard   │  REST   │   (payload.type="desktop"/"control")       │
│   D-10 disconnect button │ ──────► │   NEW: POST /session/{id}/disconnect       │
└─────────────────────────┘         │   (D-10 admin, D-11 _REMOTE_SUPER_ROLES)   │
                                     │                                            │
                                     │  rbac_utils.py: require_permission(        │
                                     │   "control:remote_access")                 │
                                     │                                            │
                                     │  NEW: control_session_audit_service.py     │
                                     │   write_audit(db, tenantId, {session_id,   │
                                     │    requester, consent_decision, ...})      │
                                     └──────────────────┬─────────────────────────┘
                                                         │ WSS (X-Tenant-Key header,
                                                         │  tunnel_request() helper)
                                     ┌──────────────────▼─────────────────────────┐
                                     │         Endpoint Agent (Rust or Python)     │
                                     │                                              │
                                     │  desktop_stream_run() — EXTEND:             │
                                     │   task A: capture loop → ws_write (existing)│
                                     │   task B (NEW): ws_read → parse input frame │
                                     │      → consent-gate check                   │
                                     │      → SendInput replay                     │
                                     │   (mirrors reverse_shell_run's existing     │
                                     │    split read/write task pattern)           │
                                     │                                              │
                                     │  NEW consent flow (before task B starts     │
                                     │   accepting input):                         │
                                     │   WTSGetActiveConsoleSessionId()            │
                                     │    == 0xFFFFFFFF? → refuse (D-02)           │
                                     │    else → CreateProcessAsUserW spawns       │
                                     │      PS WinForms Accept/Decline dialog      │
                                     │      into winsta0\default (D-01, D-03)      │
                                     │      → dialog POSTs decision to backend     │
                                     │      → agent polls/receives decision        │
                                     │      → only then does task B call SendInput │
                                     └──────────────────────────────────────────────┘
```

### Recommended Project Structure

```
agent-install/omni-agent-rs/src/
├── capabilities/remote_access.rs   # EXTEND: desktop_stream_run gets a 2nd concurrent
│                                    #   read task; add control_input_replay() using
│                                    #   winapi::um::winuser::SendInput
├── consent_ui.rs                   # NEW: near-copy of chat_ui.rs's win::spawn_in_active_session
│                                    #   + a new embedded PS WinForms Accept/Decline script
agent/capabilities/
├── remote_access.py                # EXTEND: start_desktop_stream gets on_message handling
│                                    #   (currently absent — see Pitfall 1) + SendInput ctypes call
├── consent_ui.py                   # NEW: win32ts/win32process/win32security session-injection
│                                    #   (Python equivalent of consent_ui.rs)
backend/
├── tunnel_endpoints.py             # EXTEND: none strictly required if control sessions use
│                                    #   /user instead of /viewer (already bidirectional) —
│                                    #   OR extend tunnel_viewer_side to wire recv into u2a
├── remote_endpoints.py             # EXTEND: new POST /session/{id}/disconnect (D-10/D-11);
│                                    #   dispatch payload.type="control" alongside "desktop"/"shell"
├── rbac_utils.py                   # EXTEND: add "control:remote_access" to admin + Tenant Admin
│                                    #   DEFAULT_PERMISSIONS lists (lines 99, 123)
├── control_session_audit_service.py # NEW: modeled 1:1 on remediation_audit_service.py
components/
├── RemoteDesktop.tsx               # EXTEND: mouse/key handlers, mode='view'|'control' prop,
│                                    #   connect to /user (not /viewer) when mode='control'
├── RemoteAccessDashboard.tsx       # EXTEND: control-mode toggle + D-10 disconnect button
```

### Pattern 1: Session-0 → interactive-desktop UI injection (Rust — reuse directly)

**What:** A SYSTEM service cannot draw its own window; it must spawn a *new process* inside the logged-in user's session, using a duplicated primary token from that session.
**When to use:** Consent dialog (D-01/D-03) and the persistent "stop control" indicator (D-09).
**Example (already in the tree, to be copied into a new `consent_ui.rs`):**
```rust
// Source: agent-install/omni-agent-rs/src/chat_ui.rs:284-348 (verified this session)
pub fn spawn_in_active_session(cmdline: &str) -> Result<(), String> {
    unsafe {
        let session = WTSGetActiveConsoleSessionId();
        if session == 0xFFFF_FFFF {
            return Err("no active console session (no user logged on)".to_string());
        }
        let mut user_token: HANDLE = std::ptr::null_mut();
        if WTSQueryUserToken(session, &mut user_token) == 0 {
            return Err(format!("WTSQueryUserToken failed ({})", GetLastError()));
        }
        let mut primary: HANDLE = std::ptr::null_mut();
        let dup = DuplicateTokenEx(user_token, MAXIMUM_ALLOWED, std::ptr::null_mut(),
            SecurityImpersonation, TokenPrimary, &mut primary);
        CloseHandle(user_token);
        // ... CreateEnvironmentBlock, then CreateProcessAsUserW with
        // si.lpDesktop = "winsta0\\default" ...
    }
}
```
The `session == 0xFFFF_FFFF` check **is** D-02's refusal condition — it is the exact same sentinel `heartbeat.rs::logged_in_user()` already checks [VERIFIED: agent-install/omni-agent-rs/src/heartbeat.rs:152-155, quoted: `let session = WTSGetActiveConsoleSessionId(); if session == 0xFFFF_FFFF { return None; // no interactive user logged on }`].

### Pattern 2: Python equivalent (win32ts / win32process / win32security)

**What:** Same CreateProcessAsUser pattern, via pywin32's already-present modules — no `ctypes` needed for this part (pywin32 wraps it directly).
**When to use:** Python agent's consent dialog / stop-control indicator.
**API surface (confirmed present in pywin32; not yet used anywhere in this codebase — new code, not an extension):**
```python
# Source: pywin32 win32ts/win32process/win32security modules (CITED: pywin32 docs —
# https://timgolden.me.uk/pywin32-docs/win32ts.html, mhammond/pywin32 GitHub demos)
import win32ts, win32security, win32process, win32con, win32profile

session_id = win32ts.WTSGetActiveConsoleSessionId()
if session_id == 0xFFFFFFFF:
    raise RuntimeError("no interactive desktop available")  # mirror D-02 refusal
user_token = win32ts.WTSQueryUserToken(session_id)
primary_token = win32security.DuplicateTokenEx(
    user_token, win32security.SecurityImpersonation,
    win32con.MAXIMUM_ALLOWED, win32security.TokenPrimary, None)
env = win32profile.CreateEnvironmentBlock(primary_token, False)
startup = win32process.STARTUPINFO()
startup.lpDesktop = "winsta0\\default"
win32process.CreateProcessAsUser(
    primary_token, None, "powershell.exe -File consent_ui.ps1 ...",
    None, None, False, win32con.CREATE_NO_WINDOW, env, None, startup)
```
This is `[CITED: pywin32 documentation]` — the individual function names/signatures were confirmed via `mhammond/pywin32`'s own demo file (`win32/Demos/winprocess.py`) and the pywin32 `win32ts` module doc page during this session's research, but the exact composed snippet above was not executed. Flag as a Wave-0 spike candidate: write and run this exact sequence against a live Windows box before committing to it in the plan.

### Pattern 3: Bidirectional WS relay via `/user` (reuse, do not extend `/viewer`)

**What:** `tunnel_endpoints.py` already has a fully-working bidirectional relay (`tunnel_user_side` ↔ `tunnel_agent_side`, connected by the module-level `_tunnels[session_id]` queue pair). `tunnel_viewer_side` is a *deliberately* receive-only variant used by the current view-only desktop stream.
**When to use:** For control-mode desktop sessions, connect the browser to `/api/tunnel/{session_id}/user` (exactly like `RemoteTerminal.tsx` already does), not `/api/tunnel/{session_id}/viewer`.
**Evidence this is the correct read of the code, not a guess:**
```python
# Source: backend/tunnel_endpoints.py:229-232 (verified this session, quoted exactly)
t_send = asyncio.create_task(_queue_to_send(tunnel["a2u"], websocket))
try:
    t_recv = asyncio.create_task(_recv_to_queue(websocket, asyncio.Queue()))
    await asyncio.wait([t_recv, t_send], return_when=asyncio.FIRST_COMPLETED)
```
Note `asyncio.Queue()` is a **brand-new, unreferenced queue** — not `tunnel["u2a"]`. Anything the viewer sends today is read off the socket (so the connection doesn't stall) and then discarded; it never reaches the agent. Compare `tunnel_user_side` at line 127: `t_recv = asyncio.create_task(_recv_to_queue(websocket, tunnel["u2a"]))` — the real queue.
**Frontend evidence this already works for a bidirectional case:**
```typescript
// Source: components/RemoteTerminal.tsx:89-90 (verified this session)
const wsUrl = `${protocol}//${window.location.host}/api/tunnel/${response.session_id}/user?token=${encodeURIComponent(token)}`;
```
**Agent-side evidence the split-task pattern for concurrent read+write already exists and is proven:**
```rust
// Source: agent-install/omni-agent-rs/src/capabilities/remote_access.rs:130-181
// (reverse_shell_run — already splits ws_stream into write/read halves and
// runs concurrent tasks; desktop_stream_run currently does NOT do this — it
// only ever calls ws_write.send, never reads. This is the gap to close.)
let (ws_stream, _) = connect_async(tunnel_request(url, tenant_key)?).await?;
let (ws_write, mut ws_read) = ws_stream.split();
// ... spawn a task relaying process stdout -> ws, and a loop reading
// ws_read.next() -> process stdin ...
```

### Anti-Patterns to Avoid

- **Extending `backend/remote_access_service.py`'s `ConnectionManager`:** This module is imported nowhere in `backend/` (confirmed by a full-tree grep this session) — it is dead code left over from an earlier design. `74-CONTEXT.md`'s canonical-refs section describes it as live ("relays bytes both directions today for the shell case"); that description does not match the current tree. Extend `tunnel_endpoints.py`'s actual queue-based relay instead.
- **Adding the `windows` crate for `SendInput`:** Contradicts the deliberate architectural decision already recorded in `chat_ui.rs`'s own header comment to keep the whole agent on `winapi` 0.3. Add the `winuser` feature to the existing `winapi` dependency instead.
- **Using `WTSSendMessage`/`msg.exe` for the consent dialog:** One-way only, no Accept/Decline capture — cannot satisfy D-01/D-03. Reserve it (or a Session-0-detection failure) purely as the "no interactive session" refusal path (D-02), where no dialog is shown at all anyway.
- **Assuming the Python agent's `start_desktop_stream` already has an input channel:** It does not — its `websocket.WebSocketApp(...)` call passes `on_open`/`on_error`/`on_close` but **no `on_message`** [VERIFIED: agent/capabilities/remote_access.py:251-259, quoted: `ws = websocket.WebSocketApp(url, header=ws_headers, on_open=on_open, on_error=on_error, on_close=on_close)`]. Any inbound WS frame is silently dropped by the `websocket-client` library's default no-op. Compare `start_reverse_shell`'s `on_message` at lines 126-137, which is the template to copy.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Session-0 → interactive-desktop UI spawning | A custom named-pipe/shared-memory IPC scheme to a pre-existing tray process | `CreateProcessAsUserW` (Rust: `chat_ui.rs::win::spawn_in_active_session`; Python: `win32process.CreateProcessAsUser`) | Already implemented, tested-in-production (chat window ships this way today), and is the textbook Windows-documented mechanism for this exact problem |
| Win32 input injection | A custom driver, `SendMessage`/`PostMessage` window-targeting hacks | `user32.dll SendInput` (winapi `winuser` feature in Rust; raw `ctypes` struct in Python) | `SendInput` is the single Microsoft-blessed injection API since Windows Vista; `PostMessage`-based approaches are fragile (many apps ignore synthetic window messages) and explicitly superseded |
| Append-only session audit trail | A new bespoke audit collection/writer | Copy `remediation_audit_service.py`'s `write_audit`/`list_audit` shape verbatim | House convention per `.planning/phases/64-.../64-CONTEXT.md` D-09; already handles OCSF/SIEM push, tenant scoping, and "never update, only insert" semantics |
| Force-Ctrl+Alt+Del blocklisting | Any custom key-combo filtering logic | Nothing — D-05 explicitly notes SendInput cannot inject the Secure Attention Sequence anyway; Windows itself blocks it | Building a blocklist for something the OS already refuses is wasted, fragile work |

**Key insight:** Every hard technical problem in this phase (Session-0 UI injection, bidirectional WS relay, append-only audit) already has a working, in-repo reference implementation from a prior phase. The research risk here is not "does a solution exist" — it demonstrably does — it is "will the planner find and copy it, or re-invent a worse version."

## Common Pitfalls

### Pitfall 1: `/viewer` WS endpoint silently discards input (protocol trap)
**What goes wrong:** A naive implementation adds `onMouseDown`/`onKeyDown` handlers to `RemoteDesktop.tsx` and calls `ws.send(...)` on the existing `wsRef` — which is still connected to `/api/tunnel/{session_id}/viewer`. The messages leave the browser successfully (no error), but the backend reads them into a disposable `asyncio.Queue()` (line 231 of `tunnel_endpoints.py`) that is never drained by anything. No error, no warning — control input just does nothing, and it looks like an agent-side bug.
**Why it happens:** `tunnel_viewer_side` was written to be receive-only by design (comment: "Browser-side endpoint for a remote desktop viewer (receive-only)"), before this phase existed.
**How to avoid:** Route control-mode sessions through `/api/tunnel/{session_id}/user` (the same endpoint `RemoteTerminal.tsx` already uses successfully), or explicitly wire `tunnel_viewer_side`'s recv task into `tunnel["u2a"]` instead of a throwaway queue.
**Warning signs:** Mouse/key events appear to send successfully client-side (no WS errors) but nothing happens on the remote screen; the agent-side desktop-stream loop never logs receiving anything.

### Pitfall 2: Python agent's desktop stream has no read path at all
**What goes wrong:** Same symptom as Pitfall 1, but on the agent side even if the backend relay is fixed — `websocket.WebSocketApp` in `start_desktop_stream` has no `on_message` callback, so `websocket-client` never surfaces inbound frames to any code that could act on them.
**Why it happens:** The desktop-stream feature was built one-way (screenshot upload only); the reverse-shell feature (which does need bidirectional I/O) was built separately and never had its `on_message` pattern ported over.
**How to avoid:** Add an `on_message` callback to the desktop-stream's `WebSocketApp` construction, following `start_reverse_shell`'s existing template exactly (lines 126-137 of `agent/capabilities/remote_access.py`).
**Warning signs:** Backend logs show messages being relayed to the agent side of the tunnel, but the agent process never logs receiving them.

### Pitfall 3: Session force-kill (D-10/D-11) has no live handle to reach
**What goes wrong:** A "disconnect session" endpoint is added to `remote_endpoints.py` that only updates `db.remote_sessions.status` to `"disconnected"` in MongoDB. The live WebSocket connections keep running — nothing about `tunnel_endpoints.py`'s in-memory `_tunnels` dict or the actual open `WebSocket` objects is touched by a Mongo write, so the session doesn't actually end.
**Why it happens:** The live connection state lives entirely in `tunnel_endpoints.py`'s module-level `_tunnels: dict` (constructed via `_get_tunnel()`), which is private to that module and was never designed to be reached from `remote_endpoints.py`.
**How to avoid:** The new disconnect endpoint must import and touch `tunnel_endpoints._tunnels` directly (e.g., push a sentinel into both queues, or track the actual `WebSocket` handles and call `.close()` on them) — a DB-only flag is not sufficient to end a live session. This is a genuine design decision the planner needs to make explicitly (see Open Questions).
**Warning signs:** The dashboard shows "Disconnected" but the endpoint's screen keeps streaming / the control session keeps accepting input.

### Pitfall 4: Windows-only rejection currently only exists inside `desktop_stream_run`, not at the RBAC/dispatch layer
**What goes wrong:** A non-Windows agent granted `control:remote_access` gets a `start_remote_session` instruction with `type="control"`, dispatches into a Rust/Python function that immediately hits `#[cfg(not(windows))]` (Rust) or `platform.system() != "Windows"` (Python) and returns the existing generic "unsupported on this platform" style error — indistinguishable, from the dashboard's point of view, from "the agent is offline."
**Why it happens:** Platform gating today happens deep inside the capability, not at instruction-dispatch or RBAC time.
**How to avoid:** Per CONTEXT.md's own "Claude's Discretion" note, decide (and the plan should decide explicitly) whether control-mode reuses `desktop_stream_run`'s existing non-Windows error string verbatim, or a new distinct one — but either way, surface it as a **distinguishable `{"type":"error", ...}` frame** the dashboard can render differently from "agent offline" or "no interactive desktop" (D-02's message). All three are currently stringly-typed with no discriminant field beyond the message text.
**Warning signs:** Dashboard shows the same generic error for three semantically different failure states (offline, wrong OS, no interactive session).

## Code Examples

### Existing "no interactive desktop" detection (Rust) — the D-02 refusal check
```rust
// Source: agent-install/omni-agent-rs/src/heartbeat.rs:151-156 (verified this session)
unsafe {
    let session = WTSGetActiveConsoleSessionId();
    if session == 0xFFFF_FFFF {
        return None; // no interactive user logged on
    }
    // ...
```

### Existing "no interactive desktop" error format the view-only stream already returns (D-02's reuse target)
```powershell
# Source: agent-install/omni-agent-rs/src/capabilities/remote_access.rs:200-206 (verified this session, quoted exactly)
$bounds = [System.Windows.Forms.Screen]::PrimaryScreen.Bounds
if ($bounds.Width -le 0 -or $bounds.Height -le 0) {
    [Console]::Out.WriteLine("ERR:No interactive desktop available (0x0 screen bounds) - the agent likely has no active user session to capture (Session 0 isolation)")
```
Forwarded to the browser as (Rust, `remote_access.rs:276-279`):
```
{"type":"error","message":"No interactive desktop available (0x0 screen bounds) - the agent likely has no active user session to capture (Session 0 isolation)"}
```

### SendInput ctypes skeleton (Python — new code, not yet in the tree)
```python
# Skeleton only — NOT copied from an existing file; standard ctypes SendInput
# idiom per Microsoft's INPUT/MOUSEINPUT/KEYBDINPUT structs.
# [CITED: learn.microsoft.com/windows/win32/api/winuser/nf-winuser-sendinput]
import ctypes
from ctypes import wintypes

PUL = ctypes.POINTER(ctypes.c_ulong)

class MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", ctypes.c_long), ("dy", ctypes.c_long),
                ("mouseData", ctypes.c_ulong), ("dwFlags", ctypes.c_ulong),
                ("time", ctypes.c_ulong), ("dwExtraInfo", PUL)]

class KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", ctypes.c_ushort), ("wScan", ctypes.c_ushort),
                ("dwFlags", ctypes.c_ulong), ("time", ctypes.c_ulong),
                ("dwExtraInfo", PUL)]

class INPUT_UNION(ctypes.Union):
    _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT)]

class INPUT(ctypes.Structure):
    _fields_ = [("type", ctypes.c_ulong), ("union", INPUT_UNION)]

INPUT_MOUSE, INPUT_KEYBOARD = 0, 1

def send_key(vk_code: int, key_up: bool = False):
    flags = 0x0002 if key_up else 0  # KEYEVENTF_KEYUP
    inp = INPUT(type=INPUT_KEYBOARD, union=INPUT_UNION(ki=KEYBDINPUT(vk_code, 0, flags, 0, None)))
    ctypes.windll.user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(inp))
```
This skeleton is `[ASSUMED]` in the sense that it has not been executed against a live Windows host this session — flag as a Wave-0 spike, not a copy-paste-ready plan artifact.

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|---------------|--------|
| `windows` crate for new Windows FFI work | `winapi` 0.3 (frozen API) for this specific agent codebase | Decision already made and documented in `chat_ui.rs`'s header comment, prior to this phase | Any new Win32 call this phase adds (SendInput) must go through `winapi`, not introduce `windows` as a second FFI layer |
| Legacy `keybd_event`/`mouse_event` (Win32) | `SendInput` | Deprecated by Microsoft since Windows Vista/2003 [CITED: MS Learn `SendInput` docs] | Confirms `SendInput` (not `win32api.keybd_event`) is the correct choice for both agents |
| PowerShell `System.Windows.Forms.Screen`/`CopyFromScreen` screenshot loop (current `desktop_stream_run`) | Windows Graphics Capture API / DXGI Desktop Duplication (D-14, stretch goal) | Not yet implemented in this codebase | Out of scope for phase completion per D-14 — do not let it block the core control-relay work |

**Deprecated/outdated:** `keybd_event`/`mouse_event` — superseded by `SendInput`, not to be introduced even as a "simpler" shortcut.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | The exact composed pywin32 `CreateProcessAsUser` Python sequence (Pattern 2) will work as sketched without further adjustment (e.g. `win32profile.CreateEnvironmentBlock` argument order, `STARTUPINFO.lpDesktop` assignment quirks in pywin32's Python wrapper vs. the raw C API) | Architecture Patterns / Pattern 2 | Medium — the individual function names/modules are confirmed real via official pywin32 docs, but the exact glue code was not executed against a live Windows box this session. Should be a Wave-0 spike task in the plan, not assumed to work first try. |
| A2 | The `ctypes` `SendInput` skeleton (Code Examples) is correct as written | Code Examples | Medium — struct field ordering/alignment for `ctypes.Structure`/`ctypes.Union` combinations is a known source of subtle bugs (32-bit padding, `wintypes` vs `c_ulong` mismatches on some Python builds). Should be validated with a real click/keypress test on a Windows VM before being trusted in the plan's task list. |
| A3 | `WTSSendMessage`/`msg.exe`-only fallback is unnecessary because D-02's "no console session" case never needs *any* dialog | Alternatives Considered | Low — if a future edge case surfaces (e.g. RDP session present but console session absent — the `heartbeat.rs` comment explicitly calls out "multi-session (RDP + console simultaneously) is out of scope for now" [VERIFIED: agent-install/omni-agent-rs/src/heartbeat.rs:124-126]), this assumption could need revisiting for RDP-connected-but-no-console-user hosts. |

## Open Questions

1. **How does the new session-disconnect endpoint (D-10/D-11) actually terminate a live WS session?**
   - What we know: The live connection state is `tunnel_endpoints.py`'s private, module-level `_tunnels` dict; no cross-module API currently exists to reach it from `remote_endpoints.py`.
   - What's unclear: Whether the plan should (a) export a small `close_session(session_id)` helper from `tunnel_endpoints.py` that `remote_endpoints.py` imports and calls, or (b) have the WS loops poll a `disconnect_requested` flag on the `remote_sessions` Mongo doc every N seconds/messages.
   - Recommendation: Option (a) is simpler and has no polling latency; add `def close_session(session_id: str)` to `tunnel_endpoints.py` that pushes `_SENTINEL` into both queues of `_tunnels.get(session_id)`, and have `remote_endpoints.py` import and call it directly (both modules already live in the same `backend/` package with no circular-import risk visible from this session's reads).

2. **Exact wire shape of the new mouse/keyboard/consent JSON frames.**
   - What we know: The existing `{"type":"frame", ...}` / `{"type":"error", ...}` discriminated-union shape is the established convention on this channel (`remote_access.rs:284-286`, `RemoteDesktop.tsx:63-79`).
   - What's unclear: Whether mouse-move/mouse-down/mouse-up/wheel/keydown/keyup should be five distinct `type` values or one `type:"input"` envelope with a nested `kind` field; whether canvas-relative coordinates need explicit width/height normalization (the canvas is a fixed 800x600 `<canvas>` per `RemoteDesktop.tsx:172-173`, but the actual remote screen resolution is whatever `$bounds` reports in the PS capture script — a coordinate-mapping decision, not just a wire-format one).
   - Recommendation: `{"type":"input","kind":"mousemove"|"mousedown"|"mouseup"|"wheel"|"keydown"|"keyup", "x":<0-1 normalized>,"y":<0-1 normalized>,"button":..., "key":...,"deltaY":...}` — normalized 0-1 coordinates sidestep the canvas-vs-real-resolution mismatch entirely; the agent multiplies by its own `$bounds.Width/Height` at replay time.

3. **Where does the consent Accept/Decline decision get reported back, and how does the agent poll/receive it while blocked?**
   - What we know: `chat_ui.rs`'s PS script POSTs replies to a backend REST route and polls another for admin messages, entirely independent of the WS tunnel.
   - What's unclear: Whether the consent decision should follow that same out-of-band REST pattern (new `POST /api/remote/session/{id}/consent` route the PS dialog calls, and the agent polls or the backend pushes over the same WS tunnel as a new `{"type":"consent_result"}` frame) — the WS-tunnel option avoids introducing a second auth path (the agent already has `X-Tenant-Key`-authenticated tunnel access) but requires the consent-dialog PS script to be handed a way to signal the *agent process*, not the backend directly, since the PS script and the SYSTEM-service agent process are different OS processes.
   - Recommendation: Have the PS consent script write a local sentinel file (mirroring `chat_ui.rs`'s existing `chat_{id}.close` sentinel-file pattern for the reverse signal) that the agent's own polling loop watches, AND separately POST the decision to the backend for audit-trail purposes — reuses two patterns already proven in this codebase instead of inventing a new IPC channel.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Windows build target (`x86_64-pc-windows-gnu` or MSVC) for Rust agent | Compiling the new `winuser`-feature code and `consent_ui.rs` | Not verified this session (no `rustup target list --installed` run) | — | Per `.planning/gsd-core` memory note "agent-rust Windows cross-check," `cargo check --target x86_64-pc-windows-gnu` is the established verification path for `#[cfg(windows)]` code from a Linux dev box — use it, do not assume a Windows box is available for compilation |
| Windows box (physical/VM) to actually run `CreateProcessAsUserW`/`SendInput` end-to-end | Wave-0 spikes (A1/A2 above) | Not verified this session | — | If unavailable, the plan must flag the `chat_ui.rs`-pattern reuse and the `ctypes SendInput` skeleton as `checkpoint:human-verify` before shipping, since neither can be meaningfully unit-tested without real Win32 API calls |
| `pywin32` installed in `agent/venv` | Python agent's new consent-dialog module | Confirmed as a requirements.txt entry [VERIFIED: agent/requirements.txt:25]; actual venv install not re-verified this session | `>=306` | — |

**Missing dependencies with no fallback:** none identified — both agents' new code paths are additive to already-present toolchains.

**Missing dependencies with fallback:** Windows compile/runtime verification — fallback is `checkpoint:human-verify` gates on the SendInput and session-injection tasks specifically, per the plan's Wave-0 structure.

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Backend framework | pytest, config at `pytest.ini` [VERIFIED: pytest.ini:1-11, quoted: `testpaths = . backend`, `python_files = test_*.py`, `addopts = -v --tb=short -p no:anyio`, `asyncio_mode = auto`] |
| Backend config file | `/home/user/enterprise-omni-agent-ai-platform/pytest.ini` |
| Rust agent framework | `cargo test`, inline `#[cfg(test)] mod tests { ... }` convention [VERIFIED: agent-install/omni-agent-rs/src/capabilities/process_mapper.rs:78-93 — one of 9 files in `capabilities/` using this exact pattern, confirmed via grep this session] |
| Python agent framework | Loose top-level `test_*.py` files under `agent/` (e.g. `test_self_healing.py`, `test_comp.py`); no `conftest.py` found under `agent/` this session — no dedicated fixture infrastructure exists yet for agent-side capability tests |
| Frontend framework | Vitest — `npx vitest run src/__tests__` [VERIFIED: .planning/config.json — `workflow.test_command`] |
| Quick run command (backend) | `backend/venv/bin/python -m pytest backend/tests/test_remote_access.py -x` |
| Full suite command (backend) | `backend/venv/bin/python -m pytest` (per project memory: the system Python has no pytest; must use `backend/venv/bin/python`) |

### Phase Requirements → Test Map

No REQUIREMENTS.md exists for this ad-hoc phase (confirmed — no milestone is open). The table below maps ROADMAP.md's phase goal + CONTEXT.md's numbered decisions to concrete tests instead of REQ-IDs.

| Decision/Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------|
| D-06: `control:remote_access` gates a new endpoint the way `view:remote_access` gates existing ones | unit | `pytest backend/tests/test_remote_access.py -k control_permission -x` | ❌ Wave 0 — new test class needed, modeled on `TestRemoteSessionEndpoints::test_list_sessions_denied_without_permission` [VERIFIED: backend/tests/test_remote_access.py:223-230] |
| Protocol: control-mode session connects via `/user` not `/viewer` and relays input both ways | integration | `pytest backend/tests/test_remote_access.py -k relay -x` | Partial — `TestTunnelWebSocket::test_relay_user_to_agent`/`test_relay_agent_to_user` already exist and prove the underlying `/user` relay works [VERIFIED: backend/tests/test_remote_access.py:425-503]; a control-specific frame-shape test is new |
| D-02: no interactive session → refusal, not a hang | unit (Rust) | `cargo test --target x86_64-pc-windows-gnu` (Windows-cfg'd code) | ❌ Wave 0 — no existing test for `desktop_stream_run`'s Session-0 path |
| D-09: persistent stop-control indicator | manual-only | — | Manual — UI-in-a-live-session cannot be asserted by an automated test without a real Windows desktop |
| D-12: WS drop ends session, no silent resume | integration | `pytest backend/tests/test_remote_access.py -k disconnect -x` | ❌ Wave 0 — extend `test_disconnect_propagates_sentinel_to_partner` pattern [VERIFIED: backend/tests/test_remote_access.py:504-517] to assert a fresh consent is required on reconnect |
| Audit trail write on session start/end/consent-decision | unit | `pytest backend/tests/test_control_session_audit.py -x` | ❌ Wave 0 — new file, model directly on `remediation_audit_service.py`'s own test conventions (not read this session — check for a `test_remediation_audit*.py` file before writing from scratch) |

### Sampling Rate
- **Per task commit:** `backend/venv/bin/python -m pytest backend/tests/test_remote_access.py -x` (and `cargo check` for Rust-side changes, since a Windows box for full `cargo test` may not be available per Environment Availability above)
- **Per wave merge:** Full backend suite (`backend/venv/bin/python -m pytest`) + `npx vitest run src/__tests__`
- **Phase gate:** Full suite green before `/gsd-verify-work`; Windows-only behaviors (SendInput, consent dialog, D-09 indicator) explicitly carved out as `checkpoint:human-verify` per Environment Availability

### Wave 0 Gaps
- [ ] `backend/tests/test_remote_access.py` — extend with `control:remote_access` permission tests and control-mode frame-relay tests
- [ ] `backend/tests/test_control_session_audit.py` — new file for the new audit service
- [ ] Rust `#[cfg(test)]` module inside the new `consent_ui.rs` / extended `remote_access.rs` — at minimum, unit-test the frame-parsing logic (platform-independent) even if the actual `SendInput`/`CreateProcessAsUserW` calls can only be `checkpoint:human-verify`'d
- [ ] Python agent — no `conftest.py`/test harness exists under `agent/` for capability-level tests; the plan should decide whether to establish one now (mirroring the loose `test_*.py` convention already there) or treat all new Python-agent code as `checkpoint:human-verify` only

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | yes | Unchanged — existing JWT (`verify_token_async`) / `X-Tenant-Key` dual-auth on the tunnel already covers this; no new auth mechanism introduced |
| V3 Session Management | yes | D-12's "drop ends session, no silent resume" is itself a V3 control — new consent state must not survive a WS reconnect; `remote_sessions.status` transition to `"closed"` already exists as the hook point [VERIFIED: backend/tunnel_endpoints.py:141-145] |
| V4 Access Control | yes | New `control:remote_access` permission via `rbac_utils.require_permission()` — same mechanism as `view:remote_access`; must NOT default to `"*"`-wildcard roles picking it up implicitly beyond intent (verify Super Admin's `["*"]` bypass is the *only* intended blanket grant) |
| V5 Input Validation | yes | Mouse/key input frames from the browser must be validated agent-side (bounded coordinates, an enumerated virtual-key-code allowlist) before being handed to `SendInput` — a malformed or malicious frame reaching `SendInput` unchecked is itself a local input-injection risk if the tunnel auth is ever bypassed |
| V6 Cryptography | no new surface | Existing WSS/TLS tunnel unchanged; no new crypto primitive introduced by this phase |

### Known Threat Patterns for this stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Consent-bypass — agent starts injecting input before Accept is received | Elevation of Privilege | Gate the input-relay read-task's actual `SendInput` call behind an explicit consent-state check, not merely behind the WS connection being open (D-01 is described as "a hard gate — the RBAC permission alone does not grant control") |
| Malformed/oversized input-frame flood | Denial of Service | Bound the input-relay queue and rate-limit `SendInput` calls per second, mirroring the existing `asyncio.Queue(maxsize=512)` bound already applied to `u2a`/`a2u` [VERIFIED: backend/tunnel_endpoints.py:22-25] |
| Forged consent-decision (a non-endpoint actor claiming "Accept" via the reported-decision REST route) | Spoofing | The consent-result POST must be authenticated as coming from the agent's own tunnel-authenticated channel (X-Tenant-Key or the sentinel-file local-IPC pattern), never a bare unauthenticated REST call reachable from the browser side |
| Session hijack via stale `session_id` reuse after force-kill (D-11) | Tampering | `close_session()` (Open Question 1) must also flip `remote_sessions.status` so a reconnect attempt with the same old `session_id` is rejected, not just tear down the in-memory queues |
| Audit-trail tampering/deletion | Repudiation | Copy `remediation_audit_service.py`'s pattern exactly — insert-only, no update/delete function exposed anywhere in the module [VERIFIED: backend/remediation_audit_service.py:1-6, quoted: `"Only write_audit (insert) and list_audit (read) are exposed — there is no update/delete function anywhere in this module"`] |

## Sources

### Primary (HIGH confidence — read directly this session)
- `agent-install/omni-agent-rs/src/capabilities/remote_access.rs` (full file, 318 lines)
- `agent/capabilities/remote_access.py` (full file, 268 lines)
- `agent-install/omni-agent-rs/src/chat_ui.rs` (full file, 351 lines)
- `agent-install/omni-agent-rs/src/chat_display.rs` (full file, 34 lines)
- `agent-install/omni-agent-rs/src/heartbeat.rs` (lines 120-165)
- `agent/capabilities/chat_window.py` (full file, 276 lines)
- `agent/agent.py` (lines 380-450, 1550-1580)
- `agent-install/omni-agent-rs/src/instructions.rs` (lines 270-340)
- `backend/remote_access_service.py` (full file, 63 lines)
- `backend/remote_endpoints.py` (full file, 151 lines)
- `backend/tunnel_endpoints.py` (full file, 238 lines)
- `backend/rbac_utils.py` (lines 1-222)
- `backend/remediation_audit_service.py` (full file, 46 lines)
- `backend/tests/test_remote_access.py` (full file)
- `components/RemoteDesktop.tsx` (full file, 184 lines)
- `components/RemoteAccessDashboard.tsx` (full file, 164 lines)
- `components/RemoteTerminal.tsx` (grep excerpts, lines 15-115)
- `agent-install/omni-agent-rs/Cargo.toml` (lines 50-69)
- `agent/requirements.txt` (full file)
- `types.ts` (lines 630, 675-699)
- `pytest.ini` (full file)
- `.planning/config.json` (workflow section)
- `.planning/phases/74-.../74-CONTEXT.md` (full file)

### Secondary (MEDIUM confidence — official docs via WebSearch this session)
- pywin32 `win32ts` module documentation (timgolden.me.uk/pywin32-docs) — confirmed `WTSGetActiveConsoleSessionId`, `WTSQueryUserToken`, `WTSSendMessage` exist in this module
- pywin32 `win32process.CreateProcessAsUser` documentation and `mhammond/pywin32` GitHub demo (`winprocess.py`)
- winapi crate documentation (docs.rs/crates.io) — confirmed the `winuser` Cargo feature gates `SendInput`
- Microsoft Learn `SendInput`/`INPUT`/`KEYBDINPUT` API reference (via WebSearch summary, not fetched directly)

### Tertiary (LOW confidence — flagged for validation)
- The composed `ctypes` SendInput skeleton and composed pywin32 `CreateProcessAsUser` snippet in this document (Assumptions Log A1/A2) — individually-real APIs, but the exact glue code was not executed against a live Windows host this session

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — no new packages, all existing dependency versions confirmed by reading the actual manifest files
- Architecture: HIGH — the two hardest problems (Session-0 UI injection, bidirectional relay) both have working in-repo reference implementations read in full this session
- Pitfalls: HIGH — all four pitfalls are backed by direct code reads showing the exact gap (dead code, discarded queue, missing on_message, module-private state), not speculation
- Windows API details (SendInput ctypes struct layout, exact pywin32 CreateProcessAsUser call signature): MEDIUM — confirmed via official docs but not executed live this session; flagged in Assumptions Log

**Research date:** 2026-08-26
**Valid until:** 30 days (stable Win32 APIs / stable in-repo patterns; re-verify if `remote_access.rs`/`tunnel_endpoints.py` are touched by another phase before this one executes)

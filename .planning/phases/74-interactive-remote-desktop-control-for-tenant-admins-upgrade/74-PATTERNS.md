# Phase 74: Interactive Remote Desktop Control - Pattern Map

**Mapped:** 2026-08-27
**Files analyzed:** 14 (10 create/modify + 2 test + 1 config + 1 types)
**Analogs found:** 13 / 14 (1 partial-only — Python consent UI has no working in-repo precedent for the session-injection mechanism specifically, see "No Analog Found")

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|--------------------|------|-----------|-----------------|----------------|
| `agent-install/omni-agent-rs/src/capabilities/remote_access.rs` | service (agent capability) | streaming + event-driven | itself — `reverse_shell_run` (same file) | exact (self, cross-function copy) |
| `agent-install/omni-agent-rs/src/consent_ui.rs` (NEW) | utility (Session-0 UI injection) | request-response | `agent-install/omni-agent-rs/src/chat_ui.rs` | exact |
| `agent-install/omni-agent-rs/Cargo.toml` | config | n/a | itself (one-line feature addition) | exact |
| `agent/capabilities/remote_access.py` | service (agent capability) | streaming + event-driven | itself — `start_reverse_shell`'s `on_message` (same file) | exact (self, cross-function copy) |
| `agent/capabilities/consent_ui.py` (NEW) | utility (Session-0 UI injection) | request-response | `agent/capabilities/chat_window.py` | role-match only — wrong session mechanism, see note below |
| `backend/tunnel_endpoints.py` | middleware (WS relay) | streaming / pub-sub | itself | exact |
| `backend/remote_endpoints.py` | controller (REST) | CRUD + request-response | itself | exact |
| `backend/rbac_utils.py` | middleware (RBAC) | request-response | itself | exact |
| `backend/control_session_audit_service.py` (NEW) | service (audit) | event-driven (append-only) | `backend/remediation_audit_service.py` | exact |
| `components/RemoteDesktop.tsx` | component | streaming + event-driven | itself; `components/RemoteTerminal.tsx` (bidirectional WS + input-send reference) | exact (self) / role-match (RemoteTerminal) |
| `components/RemoteAccessDashboard.tsx` | component | request-response | itself | exact |
| `types.ts` | model (type defs) | n/a | itself | exact |
| `backend/tests/test_remote_access.py` | test | request-response + streaming | itself | exact |
| `backend/tests/test_control_session_audit.py` (NEW) | test | event-driven | `backend/tests/test_remote_access.py`'s mock-collection helpers (`_col`/`_db`) — no standalone `test_remediation_audit*.py` exists to copy directly | role-match |

**Reference-only files** (read for pattern extraction, not modified by this phase): `agent-install/omni-agent-rs/src/chat_ui.rs`, `agent-install/omni-agent-rs/src/chat_display.rs`, `agent/capabilities/chat_window.py`, `components/RemoteTerminal.tsx`.

---

## Pattern Assignments

### `agent-install/omni-agent-rs/src/capabilities/remote_access.rs` (service, streaming+event-driven — EXTEND)

**Analog:** itself — `reverse_shell_run` (lines 130-181) is the split-read/write concurrent-task pattern `desktop_stream_run` (lines 185-298) needs to copy.

**Imports pattern** (lines 1-3, top of file):
```rust
use super::Capability;
use serde_json::{json, Value};
use sysinfo::System;
```

**Tunnel auth pattern — MUST reuse for any new WS traffic** (lines 72-89):
```rust
/// Build a WebSocket client request carrying the tenant's `X-Tenant-Key`
/// header. `tunnel_agent_side` (backend/tunnel_endpoints.py) requires either
/// a valid JWT `?token=` or this header to authenticate the agent side of
/// the tunnel...
fn tunnel_request(
    url: &str,
    tenant_key: &str,
) -> Result<tokio_tungstenite::tungstenite::handshake::client::Request, Box<dyn std::error::Error + Send + Sync>> {
    use tokio_tungstenite::tungstenite::client::IntoClientRequest;
    let mut req = url.into_client_request()?;
    req.headers_mut().insert(
        "X-Tenant-Key",
        tokio_tungstenite::tungstenite::http::HeaderValue::from_str(tenant_key)?,
    );
    Ok(req)
}
```

**Core split read/write task pattern to copy into `desktop_stream_run`** (lines 130-181, `reverse_shell_run`):
```rust
async fn reverse_shell_run(url: &str, tenant_key: &str) -> Result<(), Box<dyn std::error::Error + Send + Sync>> {
    use futures_util::{SinkExt, StreamExt};
    use tokio::io::{AsyncReadExt, AsyncWriteExt};
    use tokio::sync::mpsc;
    use tokio_tungstenite::{connect_async, tungstenite::Message};

    let (ws_stream, _) = connect_async(tunnel_request(url, tenant_key)?).await?;
    let (ws_write, mut ws_read) = ws_stream.split();
    let mut child = spawn_local_shell()?;
    let mut proc_stdin = child.stdin.take().ok_or("no stdin")?;
    let proc_stdout = child.stdout.take().ok_or("no stdout")?;
    let (tx, mut rx) = mpsc::channel::<Message>(32);

    // Relay process stdout → WebSocket
    tokio::spawn(async move {
        let mut buf = [0u8; 4096];
        let mut reader = proc_stdout;
        loop {
            match reader.read(&mut buf).await {
                Ok(0) | Err(_) => break,
                Ok(n) => {
                    let text = String::from_utf8_lossy(&buf[..n]).to_string();
                    if tx.send(Message::Text(text.into())).await.is_err() { break; }
                }
            }
        }
    });

    tokio::spawn(async move {
        let mut sink = ws_write;
        while let Some(msg) = rx.recv().await {
            if sink.send(msg).await.is_err() { break; }
        }
    });

    // Relay WebSocket input → process stdin
    while let Some(Ok(msg)) = ws_read.next().await {
        match msg {
            Message::Text(text) => { /* ... */ }
            Message::Binary(data) => { /* ... */ }
            Message::Close(_) => break,
            _ => {}
        }
    }
    let _ = child.kill().await;
    Ok(())
}
```
**Apply to `desktop_stream_run`:** currently (lines 191-192) does `let (mut ws_write, _) = ws_stream.split();` and discards the read half entirely. Change to `let (mut ws_write, mut ws_read) = ws_stream.split();`, keep the existing PS-capture-process stdout→`ws_write` loop as one task/branch, and add a second task/branch reading `ws_read.next()` → parse `{"type":"input",...}` JSON → consent-gate check → `SendInput` replay (new `control_input_replay()` function, `winapi::um::winuser::SendInput`).

**Error-frame wire shape already established — reuse the discriminant, don't invent a new one** (lines 236-238, 246-249, 264-267, 276-279, 311-315):
```rust
let payload = format!(r#"{{"type":"error","message":"{}"}}"#, msg);
let _ = ws_write.send(Message::Text(payload.into())).await;
```
```rust
// D-02's existing "no interactive desktop" refusal (PS script, lines 200-206):
if ($bounds.Width -le 0 -or $bounds.Height -le 0) {
    [Console]::Out.WriteLine("ERR:No interactive desktop available (0x0 screen bounds) - the agent likely has no active user session to capture (Session 0 isolation)")
```
```rust
// Non-Windows stub pattern (lines 300-317) — model for any non-Windows
// control-mode rejection; per Pitfall 4, give it a distinguishable frame:
#[cfg(not(windows))]
async fn desktop_stream_run(...) -> Result<...> {
    let (ws_stream, _) = connect_async(tunnel_request(url, tenant_key)?).await?;
    let (mut ws_write, _) = ws_stream.split();
    let _ = ws_write.send(Message::Text(
        r#"{"type":"error","message":"Desktop streaming is only supported on Windows agents"}"#.into(),
    )).await;
    Err("desktop streaming is only supported on Windows".into())
}
```

**Frame (success) wire shape** (lines 283-288):
```rust
let payload = format!(
    r#"{{"type":"frame","timestamp":{},"data":"{}"}}"#,
    ts, line
);
```

---

### `agent-install/omni-agent-rs/src/consent_ui.rs` (utility, request-response — NEW)

**Analog:** `agent-install/omni-agent-rs/src/chat_ui.rs` (full file, 350 lines) — near-copy target per RESEARCH.md's primary recommendation.

**Module header comment convention to copy** (lines 1-13):
```rust
//! Two-way interactive chat window for the endpoint user.
//!
//! The agent runs as a session-0 service and cannot draw an interactive window
//! itself. This module spawns a PowerShell WinForms chat UI *into the active
//! console session* using `CreateProcessAsUserW` with a token obtained from
//! `WTSQueryUserToken(WTSGetActiveConsoleSessionId())`. ...
//!
//! `winapi` (frozen 0.3 API) is used rather than the `windows` crate to keep the
//! FFI surface stable.
```

**Session-bookkeeping pattern (Active/mark_active/mark_closed)** (lines 15-38):
```rust
use std::collections::HashSet;
use std::sync::{Mutex, OnceLock};

fn active() -> &'static Mutex<HashSet<String>> {
    static ACTIVE: OnceLock<Mutex<HashSet<String>>> = OnceLock::new();
    ACTIVE.get_or_init(|| Mutex::new(HashSet::new()))
}
pub fn is_active(session_id: &str) -> bool {
    active().lock().map(|s| s.contains(session_id)).unwrap_or(false)
}
fn mark_active(session_id: &str) { /* insert */ }
pub fn mark_closed(session_id: &str) { /* remove */ }
```

**Script materialization + per-session config-drop + spawn lifecycle** (lines 40-108, `data_dir`/`script_path`/`ensure_script_installed`/`launch_interactive`):
```rust
#[cfg(windows)]
pub fn data_dir() -> std::path::PathBuf {
    let base = std::env::var("ProgramData").unwrap_or_else(|_| r"C:\ProgramData".to_string());
    std::path::Path::new(&base).join("OmniAgent")
}

#[cfg(windows)]
pub fn launch_interactive(session_id: &str, /* ...consent-specific args... */) -> Result<(), String> {
    if is_active(session_id) { return Ok(()); }
    let dir = data_dir();
    let script_path = ensure_script_installed()?;
    // Per-session config carries auth/identity off the command line (not
    // visible in process list) — same reasoning applies to consent dialog's
    // requester identity (D-03).
    let cfg = serde_json::json!({ "session_id": session_id, /* requester_name, requester_email, tenant, backend_url, token */ });
    let cfg_path = dir.join(format!("consent_{session_id}.json"));
    std::fs::write(&cfg_path, serde_json::to_vec(&cfg).unwrap_or_default())?;
    let cmdline = format!(
        "powershell.exe -NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File \"{}\" \"{}\"",
        script_path.display(), cfg_path.display()
    );
    win::spawn_in_active_session(&cmdline)?;
    mark_active(session_id);
    Ok(())
}
```

**Sentinel-file close-signal pattern — reuse for RESEARCH.md Open Question 3's "how does the agent learn the Accept/Decline decision" answer** (lines 110-121):
```rust
#[cfg(windows)]
pub fn signal_close(session_id: &str) -> Result<(), String> {
    let dir = data_dir();
    let sentinel = dir.join(format!("chat_{session_id}.close"));
    let _ = std::fs::create_dir_all(&dir);
    std::fs::write(&sentinel, b"close").map_err(|e| format!("write close sentinel: {e}"))?;
    mark_closed(session_id);
    Ok(())
}
```
Apply the same idea in reverse for consent: the PS dialog writes a `consent_{id}.decision` sentinel file (`accept`/`decline`) that the agent's Rust-side polling loop watches before starting `SendInput` — mirrors this exact close-sentinel mechanic.

**Non-Windows stub pattern** (lines 123-140):
```rust
#[cfg(not(windows))]
pub fn launch_interactive(/* ... */) -> Result<(), String> {
    Err("interactive chat window is Windows-only".to_string())
}
```

**The core `CreateProcessAsUserW` session-injection function — copy near-verbatim** (lines 264-350, `mod win { ... spawn_in_active_session ... }`):
```rust
#[cfg(windows)]
mod win {
    use std::os::windows::ffi::OsStrExt;
    use winapi::shared::minwindef::{DWORD, FALSE, LPVOID};
    use winapi::um::errhandlingapi::GetLastError;
    use winapi::um::handleapi::CloseHandle;
    use winapi::um::processthreadsapi::{CreateProcessAsUserW, PROCESS_INFORMATION, STARTUPINFOW};
    use winapi::um::securitybaseapi::DuplicateTokenEx;
    use winapi::um::userenv::{CreateEnvironmentBlock, DestroyEnvironmentBlock};
    use winapi::um::winbase::{WTSGetActiveConsoleSessionId, CREATE_NO_WINDOW, CREATE_UNICODE_ENVIRONMENT};
    use winapi::um::winnt::{SecurityImpersonation, TokenPrimary, HANDLE, MAXIMUM_ALLOWED};
    use winapi::um::wtsapi32::WTSQueryUserToken;

    pub fn spawn_in_active_session(cmdline: &str) -> Result<(), String> {
        unsafe {
            let session = WTSGetActiveConsoleSessionId();
            if session == 0xFFFF_FFFF {
                return Err("no active console session (no user logged on)".to_string());
                // ^ this IS D-02's refusal condition — same sentinel heartbeat.rs checks
            }
            let mut user_token: HANDLE = std::ptr::null_mut();
            if WTSQueryUserToken(session, &mut user_token) == 0 {
                return Err(format!("WTSQueryUserToken failed ({})", GetLastError()));
            }
            let mut primary: HANDLE = std::ptr::null_mut();
            let dup = DuplicateTokenEx(user_token, MAXIMUM_ALLOWED, std::ptr::null_mut(),
                SecurityImpersonation, TokenPrimary, &mut primary);
            CloseHandle(user_token);
            // ... CreateEnvironmentBlock, STARTUPINFOW.lpDesktop = "winsta0\\default",
            // CreateProcessAsUserW(primary, ..., flags=CREATE_UNICODE_ENVIRONMENT|CREATE_NO_WINDOW, &mut si, &mut pi) ...
        }
    }
}
```

**Embedded PS WinForms script structure to copy (swap chat log/textbox for Accept/Decline buttons + requester-identity labels per D-03)** (lines 144-262, `CHAT_UI_PS` const): shows the `param([string]$ConfigPath)` → `Get-Content | ConvertFrom-Json` config-read pattern, `Add-Type -AssemblyName System.Windows.Forms`, `Invoke-RestMethod` with `[Net.ServicePointManager]::SecurityProtocol`/`ServerCertificateValidationCallback` TLS setup (lines 158-164), a `System.Windows.Forms.Timer` poll loop watching a close-sentinel file (lines 230-253), and `$form.Add_FormClosed` cleanup (lines 256-260).

---

### `agent-install/omni-agent-rs/Cargo.toml` (config — EXTEND)

**Current block** (lines 55-61):
```toml
[target.'cfg(windows)'.dependencies]
winreg = "0.52"
windows-service = "0.7"
winapi = { version = "0.3", features = [
    "minwindef", "winnt", "handleapi", "errhandlingapi", "processthreadsapi",
    "securitybaseapi", "userenv", "winbase", "wtsapi32",
] }
```
**Change:** add `"winuser"` to the feature list (gates `SendInput`/`INPUT`/`MOUSEINPUT`/`KEYBDINPUT`). One line, no new crate.

---

### `agent/capabilities/remote_access.py` (service, streaming+event-driven — EXTEND)

**Analog:** itself — `start_reverse_shell`'s `on_message` (lines 126-137) is the pattern `start_desktop_stream` (lines 183-267) is currently missing entirely.

**Imports/class-header pattern** (lines 1-16):
```python
import platform
import logging
import subprocess
from typing import Dict, Any
from .base import BaseCapability

if platform.system() == "Windows":
    import winreg
else:
    winreg = None

logger = logging.getLogger(__name__)

class RemoteAccessCapability(BaseCapability):
```

**Platform-gate pattern (already established, extend don't reinvent)** (lines 33-35):
```python
def is_compatible(self, system_info: Dict[str, Any]) -> bool:
    return system_info.get("os") == "Windows"
```

**The `on_message` pattern to copy into `start_desktop_stream`'s `WebSocketApp`** (lines 126-137, from `start_reverse_shell`):
```python
def on_message(ws, message):
    try:
        if process.poll() is not None:
            ws.close()
            return
        if isinstance(message, str):
            message = message.encode('utf-8')
        process.stdin.write(message)
        process.stdin.flush()
    except Exception as e:
        logger.error(f"Shell Input Error: {e}")
```

**Current (broken for control-mode) `WebSocketApp` construction — the exact gap to close** (lines 251-259):
```python
ws = websocket.WebSocketApp(
    url,
    header=ws_headers,
    on_open=on_open,
    on_error=on_error,
    on_close=on_close
    # NO on_message — any inbound frame (e.g. a mouse/key input frame) is
    # silently dropped by websocket-client's default no-op.
)
ws.run_forever()
```
**Apply:** add `on_message=on_message` (parse JSON `{"type":"input",...}`, consent-gate check, then call the new `ctypes` `SendInput` wrapper — see RESEARCH.md's Code Examples section for the `INPUT`/`MOUSEINPUT`/`KEYBDINPUT` ctypes-struct skeleton, flagged there as `[ASSUMED]`/Wave-0-spike, not copy-paste-ready).

**Frame-send pattern already in place (unchanged, keep as-is)** (lines 236-241):
```python
payload = {
    "type": "frame",
    "timestamp": time.time(),
    "data": b64_data
}
ws.send(json.dumps(payload))
```

**Error-handling convention throughout the file** — every public method returns `{"status": "success"|"error", ...}`, never raises past its own boundary (lines 55-56, 74-77, 89-92):
```python
except Exception as e:
    logger.error(f"Failed to enable RDP: {e}")
    return {"status": "error", "error": str(e)}
```

---

### `agent/capabilities/consent_ui.py` (utility, request-response — NEW)

**Analog:** `agent/capabilities/chat_window.py` (role-match only — see note below). RESEARCH.md's Pattern 2 (pywin32 `win32ts`/`win32process`/`win32security`) is the *mechanism* that must actually be used; it has **no existing in-repo implementation to copy** on the Python side.

**IMPORTANT discrepancy found this session (not previously flagged):** `agent/agent.py` imports `win32serviceutil` — the Python agent **does** run as a Windows service (Session-0), same as the Rust agent. `chat_window.py`'s `_run_window` (lines 78-251) spawns `tkinter` **directly in a background thread of the agent process itself** — it does **not** use `CreateProcessAsUser`/session injection at all. Under Session-0 isolation, a SYSTEM service's own thread cannot draw a window the interactive user can see, so `chat_window.py`'s tkinter approach would not actually appear on the endpoint's desktop when the agent runs as a service. Treat `chat_window.py` as a **UX/structure reference only** (message layout, polling loop, close-signal watchdog) — **not** as a working session-injection example. The planner should budget `consent_ui.py` as new code built from RESEARCH.md's Pattern 2 citation (pywin32 docs), flagged `checkpoint:human-verify` per RESEARCH.md's Assumptions Log A1, not a copy of existing working code.

**Reusable structural patterns from `chat_window.py`** (session bookkeeping, threading, poll loop):
```python
# Session bookkeeping (lines 25-26, 55-58, 70-74)
_active_sessions: Dict[str, Dict[str, Any]] = {}

def start_chat(self, session_id, ...):
    if session_id in _active_sessions:
        return {"status": "already_active", "session_id": session_id}
    _active_sessions[session_id] = {"running": True}
    t = threading.Thread(target=self._run_window, args=(...), daemon=True, name=f"agent-chat-{session_id[:8]}")
    t.start()
    return {"status": "started", "session_id": session_id}

def close_chat(self, session_id):
    if session_id in _active_sessions:
        _active_sessions[session_id]["running"] = False
    return {"status": "close_signal_sent"}
```
```python
# Watchdog pattern for external close signal (lines 239-247) — same idea as
# the Rust sentinel-file poll, but via a shared dict instead of a file.
def _watchdog():
    if not state.get("running"):
        try: root.destroy()
        except Exception: pass
        return
    root.after(1000, _watchdog)
```
```python
# Reply-post pattern (lines 265-276) — model for POSTing the consent decision:
def _post_reply(session_id, content, backend_url, auth_headers):
    try:
        requests.post(f"{backend_url}/api/agent-chat/sessions/{session_id}/user-message",
                      json={"content": content}, headers=auth_headers, timeout=10)
    except Exception as e:
        logger.error("[ChatWindow] Failed to send reply: %s", e)
```

**The actual session-injection sequence to build (cited, not copied — RESEARCH.md Pattern 2, `[CITED: pywin32 docs]`, flag as Wave-0 spike):**
```python
import win32ts, win32security, win32process, win32con, win32profile

session_id = win32ts.WTSGetActiveConsoleSessionId()
if session_id == 0xFFFFFFFF:
    raise RuntimeError("no interactive desktop available")  # mirrors D-02 / Rust's 0xFFFF_FFFF check
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

---

### `backend/tunnel_endpoints.py` (middleware, streaming/pub-sub — EXTEND)

**Analog:** itself — the queue-pair relay is the live transport; extend it directly rather than the dead `remote_access_service.py`.

**Module header + queue-pair primitives** (lines 1-26):
```python
"""WebSocket tunnel relay and remote shell endpoints.

Registers routes directly on the FastAPI app (not an APIRouter) because
FastAPI WebSocket handlers must be decorated on the app instance.
"""
import asyncio
import logging
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from database import get_database, mongodb

logger = logging.getLogger(__name__)
_tunnels: dict = {}
_SENTINEL = object()

def _get_tunnel(session_id: str) -> dict:
    if session_id not in _tunnels:
        _tunnels[session_id] = {
            "u2a": asyncio.Queue(maxsize=512),
            "a2u": asyncio.Queue(maxsize=512),
        }
    return _tunnels[session_id]
```

**Auth pattern for the browser-facing `/user` endpoint (JWT + IDOR tenant check)** (lines 93-119):
```python
@app.websocket("/api/tunnel/{session_id}/user")
async def tunnel_user_side(websocket: WebSocket, session_id: str, token: str = ""):
    from authentication_service import verify_token_async
    if not token:
        token = websocket.query_params.get("token", "")
    try:
        user = await verify_token_async(token)
    except Exception:
        await websocket.close(code=4401)
        return
    # IDOR guard: raw Motor db used here — TenantIsolatedDatabase cannot be used
    # before websocket.accept() because the tenant ContextVar is not populated yet.
    session = await mongodb.db.remote_sessions.find_one({"session_id": session_id})
    if not session:
        await websocket.close(code=4403)
        return
    user_tenant = getattr(user, "tenant_id", None)
    if user_tenant and user_tenant != "platform-admin" and session.get("tenantId") != user_tenant:
        await websocket.close(code=4403)
        return
    await websocket.accept()
    tunnel = _get_tunnel(session_id)
    # status -> "active" in db, then two concurrent tasks:
    t_recv = asyncio.create_task(_recv_to_queue(websocket, tunnel["u2a"]))
    t_send = asyncio.create_task(_queue_to_send(tunnel["a2u"], websocket))
    try:
        await asyncio.wait([t_recv, t_send], return_when=asyncio.FIRST_COMPLETED)
    finally:
        t_recv.cancel(); t_send.cancel()
        tunnel["u2a"].put_nowait(_SENTINEL)  # unblock partner
        _tunnels.pop(session_id, None)
        # status -> "closed" in db (this is D-12's hook point)
```

**Auth pattern for the agent-facing `/agent` endpoint (dual JWT-or-X-Tenant-Key)** (lines 147-199) — reuse verbatim, no changes needed for control-mode since it's protocol-agnostic.

**Anti-pattern already identified — do NOT extend `/viewer`, it is deliberately receive-only** (lines 201-238, `tunnel_viewer_side`):
```python
@app.websocket("/api/tunnel/{session_id}/viewer")
async def tunnel_viewer_side(websocket: WebSocket, session_id: str, token: str = ""):
    """Browser-side endpoint for a remote desktop viewer (receive-only)."""
    # ...
    t_send = asyncio.create_task(_queue_to_send(tunnel["a2u"], websocket))
    try:
        t_recv = asyncio.create_task(_recv_to_queue(websocket, asyncio.Queue()))
        #                                                        ^^^^^^^^^^^^^^^
        # brand-new, unreferenced queue — NOT tunnel["u2a"]. Anything the
        # viewer sends today is read (so the socket doesn't stall) then discarded.
```
**Apply:** route control-mode desktop sessions through the existing `/user` endpoint (identical to `RemoteTerminal.tsx`'s usage) instead of `/viewer` — no backend code change needed for the relay itself, only for `RemoteDesktop.tsx`'s connection URL and `remote_endpoints.py`'s dispatch.

**New code needed — `close_session()` helper (Open Question 1's recommended answer), modeled directly on the existing `finally` teardown block above** (pattern to follow, not existing code):
```python
def close_session(session_id: str) -> bool:
    """Push _SENTINEL into both queues of an active tunnel to force both
    WS loops to exit — used by D-10 (admin disconnect) / D-11 (force-kill)."""
    tunnel = _tunnels.get(session_id)
    if not tunnel:
        return False
    for q in (tunnel["u2a"], tunnel["a2u"]):
        try:
            q.put_nowait(_SENTINEL)
        except asyncio.QueueFull:
            pass
    return True
```

---

### `backend/remote_endpoints.py` (controller, CRUD+request-response — EXTEND)

**Analog:** itself.

**Imports + router + super-role bypass set (D-11's reuse target)** (lines 1-22):
```python
from fastapi import APIRouter, HTTPException, Depends, Request
from database import get_database
from authentication_service import get_current_user
from rbac_utils import require_permission
from models import User
import uuid, os, socket
from datetime import datetime, timezone

router = APIRouter(prefix="/api/remote", tags=["Remote Access"])

_REMOTE_SUPER_ROLES = {"Super Admin", "super_admin", "platform-admin"}

def _remote_tenant(current_user) -> dict:
    role = current_user.get("role", "") if isinstance(current_user, dict) else getattr(current_user, "role", "")
    if role in _REMOTE_SUPER_ROLES:
        return {}
    tid = (current_user.get("tenantId") or current_user.get("tenant_id")) if isinstance(current_user, dict) \
        else (getattr(current_user, "tenantId", None) or getattr(current_user, "tenant_id", None))
    return {"tenantId": tid} if tid else {}
```

**RBAC-gated GET pattern (model for the new disconnect endpoint's dependency)** (lines 25-30):
```python
@router.get("")
@router.get("/")
async def list_remote_sessions(
    limit: int = 50,
    current_user=Depends(require_permission("view:remote_access"))
):
```

**Session-start pattern — `start_remote_session` (lines 87-150)** — this is what needs to dispatch `payload.type` (currently decorative, per RESEARCH.md):
```python
@router.post("/session/start")
async def start_remote_session(request: Request, payload: dict, current_user: User = Depends(get_current_user)):
    agent_id = payload.get("agent_id")
    protocol = payload.get("protocol", "ssh")
    session_type = payload.get("type", "shell")
    # ... session_data written to db.remote_sessions with status="pending" ...
    instruction = {
        "id": str(uuid.uuid4()), "agent_id": agent_id,
        "instruction": "start_remote_session", "type": "start_remote_session",
        "payload": {
            "session_id": session_id, "protocol": protocol, "type": session_type,
            "url": f"{agent_ws_base}/api/tunnel/{session_id}/agent",
        },
        "status": "pending", "tenantId": agent_tenant_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.agent_instructions.insert_one(instruction)
    return {"session_id": session_id, "status": "pending", "websocket_url": f"/api/tunnel/{session_id}/user"}
```
**Apply:** `payload.get("type")` becoming `"control"` (vs. existing `"desktop"`/`"shell"`) needs (a) a new `require_permission("control:remote_access")` gate before this handler proceeds for control-type requests, and (b) that same `"control"` value threaded into the agent instruction's `payload["type"]` so the agent's dispatch logic (both Rust and Python) can tell view vs. control apart — this is the "currently decorative" gap RESEARCH.md flags.

**New endpoint to add — `POST /session/{id}/disconnect` (D-10/D-11)** — model on the existing GET handlers' shape + `_REMOTE_SUPER_ROLES`/`_remote_tenant` reuse, plus a call into the new `tunnel_endpoints.close_session()` helper (see above) since a DB-only status flip does not end a live WS session (Pitfall 3).

---

### `backend/rbac_utils.py` (middleware, request-response — EXTEND)

**Analog:** itself — `control:remote_access` slots in exactly where `view:remote_access` already sits.

**Existing permission-list pattern, `admin` role block** (line 99, inside the list starting line 82):
```python
"admin": [
    # ...
    "view:secrets", "manage:agents", "view:approvals", "view:remote_access",
],
```
**Existing permission-list pattern, `Tenant Admin` role block** (line 123, inside the list starting line 101):
```python
"Tenant Admin": [
    # ...
    "view:secrets", "manage:secrets", "view:approvals", "manage:approvals", "view:remote_access",
],
```
**Apply:** append `"control:remote_access"` to both lists (lines 99 and 123). Do **not** add it to `"user"`, `"analyst"`, `"viewer"`, or the ITAM-specific roles — matches the existing scoping of `view:remote_access` itself.

**`require_permission` dependency factory — the mechanism `control:remote_access` will be gated through, identical to `view:remote_access`** (lines 201-211):
```python
def require_permission(permission: str):
    async def dependency(user: TokenData = Depends(get_current_user)):
        allowed = await verify_permission(user, permission)
        if not allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Missing required permission: {permission}"
            )
        return user
    return dependency
```
**Super-admin wildcard bypass — verify `control:remote_access` is picked up only via this path, not an unintended second wildcard** (lines 76-80):
```python
"Super Admin":    ["*"],
"super_admin":    ["*"],
"superadmin":     ["*"],
"platform-admin": ["*"],
```

---

### `backend/control_session_audit_service.py` (service, event-driven append-only — NEW)

**Analog:** `backend/remediation_audit_service.py` (full file, 46 lines) — copy 1:1 per RESEARCH.md's "Don't Hand-Roll" table and CONTEXT.md's own citation.

**Full pattern to copy (module docstring + write_audit + list_audit)** (lines 1-46):
```python
"""Append-only remediation audit trail (Phase 53-03/53-04, AUTO-04).

Only `write_audit` (insert) and `list_audit` (read) are exposed — there is
no update/delete function anywhere in this module, so a record, once
written, can never be altered or removed by anything importing it.
"""
import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


async def write_audit(db, tenant_id: str, record: Dict[str, Any]) -> str:
    """Inserts one immutable audit record. Never updates an existing one —
    each transition (selected/dispatched/verified/override) is its own
    fresh document."""
    doc = dict(record)
    doc.setdefault("tenantId", tenant_id)
    doc.setdefault("ts", datetime.now(timezone.utc).isoformat())
    result = await db.remediation_audit.insert_one(doc)

    # Push OCSF event to subscribed external SIEM webhooks (COMM-01).
    # Fire-and-forget; never raises into the remediation pipeline.
    try:
        from soc_integration_service import push_ocsf_event
        asyncio.create_task(push_ocsf_event("remediation.event", doc))
    except Exception as e:
        logger.debug("Remediation OCSF push failed (non-fatal): %s", e)

    return str(result.inserted_id)


async def list_audit(
    db, tenant_id: str, filters: Optional[Dict[str, Any]] = None, limit: int = 100,
) -> List[Dict[str, Any]]:
    query: Dict[str, Any] = {"tenantId": tenant_id}
    if filters:
        query.update(filters)
    cursor = db.remediation_audit.find(query, {"_id": 0}).sort("ts", -1).limit(limit)
    return await cursor.to_list(length=limit)
```
**Apply:** rename `db.remediation_audit` → `db.control_session_audit` (new collection); keep the exact insert-only/no-delete shape and the `tenantId`/`ts` defaulting. Fields per CONTEXT.md's discretion note: `session_id`, `requester` (name/email — D-03), `tenantId`, `start_ts`/`end_ts`, `consent_decision` (accept/decline/timeout), `disconnect_reason`. The OCSF/SIEM push block is optional to carry over — evaluate whether `soc_integration_service.push_ocsf_event` should also fire for control-session events, or whether that's scope creep for this phase.

**Testing note:** `remediation_audit_service.py` itself has no standalone unit-test file — it's exercised indirectly via `backend/tests/test_autonomous_remediation_loop.py` and `backend/tests/test_soc_integration.py`. `test_control_session_audit.py` should instead follow `test_remote_access.py`'s own `_col()`/`_db()` MagicMock-collection helper pattern (see Test section below) since that's the established direct-unit-test convention for this phase's neighboring module.

---

### `components/RemoteDesktop.tsx` (component, streaming+event-driven — EXTEND)

**Analog:** itself for the WS/render plumbing; `components/RemoteTerminal.tsx` for the bidirectional-connection + input-send reference (proves the `/user` endpoint pattern works end-to-end today).

**Current imports + props** (lines 1-8):
```typescript
import React, { useEffect, useRef, useState } from 'react';
import { AlertTriangleIcon, MonitorIcon } from './icons';
import { startRemoteSession } from '../services/apiService';

interface RemoteDesktopProps {
    agentId: string;
    sessionId?: string;
}
```

**Current WS-connect pattern — `openWs`, connects to `/viewer` today (must become conditional on view vs. control mode)** (lines 46-58):
```typescript
const openWs = (sid: string) => {
    hasFramesRef.current = false;
    const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const token = sessionStorage.getItem('token') || '';
    const wsUrl = `${wsProtocol}//${window.location.host}/api/tunnel/${sid}/viewer?token=${encodeURIComponent(token)}`;
    // ^ for control mode, this must become .../${sid}/user?token=... (per Pitfall 1)
    if (cancelled) return;
    setStatusMsg('Connecting to desktop stream…');
    const ws = new WebSocket(wsUrl);
    wsRef.current = ws;
    ws.onopen = () => { setIsConnected(true); setError(null); setStatusMsg('Waiting for agent to start streaming…'); };
```

**Message-dispatch pattern (discriminated union on `payload.type`) — extend with `input`/`consent_request`/`consent_result` cases** (lines 60-81):
```typescript
ws.onmessage = (event) => {
    try {
        const payload = JSON.parse(event.data);
        if (payload.type === 'frame' && payload.data) {
            renderFrame(payload.data);
            // ...fps bookkeeping...
        } else if (payload.type === 'error' && payload.message) {
            setError(String(payload.message));
            setStatusMsg('');
        }
    } catch { /* ignore non-JSON */ }
};
```

**Bidirectional `/user` endpoint proof-of-pattern — copy this connection URL shape for control mode** (`components/RemoteTerminal.tsx` lines 87-90):
```typescript
const response = await startRemoteSession(agent.id || agent.hostname, 'ssh', 'shell');
const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
const token = sessionStorage.getItem('token') || '';
const wsUrl = `${protocol}//${window.location.host}/api/tunnel/${response.session_id}/user?token=${encodeURIComponent(token)}`;
```

**Input-send-on-`ws.send()` pattern — `RemoteTerminal.tsx`'s `terminal.onData` is the exact shape for canvas `onMouseDown/Move/Up/onWheel/onKeyDown/Up` handlers to follow** (`RemoteTerminal.tsx` lines 72-74):
```typescript
terminal.onData((data) => {
    if (ws.readyState === WebSocket.OPEN) ws.send(data);
});
```
Apply as: `canvas.onMouseMove = (e) => { if (wsRef.current?.readyState === WebSocket.OPEN) wsRef.current.send(JSON.stringify({type:'input', kind:'mousemove', x: normX, y: normY})); }` per RESEARCH.md Open Question 2's recommended normalized-0-1-coordinate wire shape.

**Canvas element — currently zero event handlers, fixed 800×600** (lines 170-175):
```typescript
<canvas
    ref={canvasRef}
    width={800}
    height={600}
    className={`max-w-full max-h-full object-contain ${!hasFrames ? 'hidden' : ''}`}
/>
```

**No-signal defense-in-depth timeout pattern (45s) — model for a similar "consent not yet accepted" timeout UX** (lines 93-97):
```typescript
setTimeout(() => {
    if (!cancelled && !hasFramesRef.current) {
        setError((prev) => prev ?? 'No video received from the agent within 45s — ...');
    }
}, 45000);
```

---

### `components/RemoteAccessDashboard.tsx` (component, request-response — EXTEND)

**Analog:** itself.

**Existing mode-switcher pattern — `AccessMode` toggle (Terminal/Desktop). NOTE: view-vs-control is an orthogonal sub-mode of Desktop, not a third `AccessMode` value** (lines 8, 86-97):
```typescript
type AccessMode = 'desktop' | 'terminal';
// ...
<div style={{ display: 'flex', background: 'rgba(255,255,255,.06)', borderRadius: 8, padding: 3, gap: 2 }}>
    {(['terminal', 'desktop'] as AccessMode[]).map(m => (
        <button key={m} onClick={() => setMode(m)} style={{ /* active/inactive styling */ }}>
            {m === 'terminal' ? <Terminal size={13} /> : <Monitor size={13} />}
            {m === 'terminal' ? 'Terminal' : 'Desktop'}
        </button>
    ))}
</div>
```
**Apply:** add a separate boolean/enum (e.g. `controlEnabled` or `desktopSubMode: 'view'|'control'`) passed as a prop into `<RemoteDesktop>` when `mode === 'desktop'`, gated client-side by whether the current user has `control:remote_access` (see "No Analog Found" below — no existing client-side permission check to copy).

**Desktop-panel render branch — where the D-10 disconnect button and control-mode toggle attach** (lines 43-58):
```typescript
if (mode === 'desktop') {
    return (
        <div style={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '12px 24px', background: 'rgba(255,255,255,.04)', borderBottom: '1px solid rgba(255,255,255,.08)' }}>
                <button onClick={() => setSelectedAgent(null)} style={{ /* ... */ }}>← Back</button>
                <Monitor size={16} color="#6366f1" />
                <span style={{ color: '#f1f5f9', fontWeight: 600 }}>Remote Desktop — {selectedAgent.hostname || selectedAgent.id}</span>
                {/* D-10 disconnect button goes here, alongside the Back button */}
            </div>
            <div style={{ flex: 1, overflow: 'hidden' }}>
                <RemoteDesktop agentId={selectedAgent.id} />
            </div>
        </div>
    );
}
```

**Data-fetch pattern (`authFetch` + `AbortController`) — model for the new disconnect-button's POST call** (lines 16-30):
```typescript
const fetchAgents = useCallback(async (signal?: AbortSignal) => {
    setLoading(true);
    try {
        const res = await authFetch('/api/agents', { signal } as RequestInit);
        if (res.ok) {
            const data = await res.json();
            setAgents(Array.isArray(data) ? data : data.items || data.agents || []);
        }
    } catch (e) {
        if ((e as any)?.name !== 'AbortError') console.error('Failed to load remote agents:', e);
    }
    setLoading(false);
}, []);
```

---

### `types.ts` (model/types — EXTEND)

**Analog:** itself — existing string-literal-union convention for extensible enums.

**`AgentCapability` union pattern — `'remote_access'` already exists as a capability flag (line 661); no new capability entry needed, but the pattern shows the project convention for typed string unions** (lines 632-672):
```typescript
export type AgentCapability =
  // Core telemetry
  | 'metrics_collection'
  // ...
  | 'remote_access'
  | 'agent_update'
  // ...
  | 'deception_monitor';
```
**Apply:** add new interfaces for the input/consent frame shapes (mirroring RESEARCH.md Open Question 2's recommendation) so `RemoteDesktop.tsx` and any new consent-UI component share one typed contract, e.g. `interface RemoteInputFrame { type: 'input'; kind: 'mousemove'|'mousedown'|'mouseup'|'wheel'|'keydown'|'keyup'; x?: number; y?: number; button?: number; key?: string; deltaY?: number; }`. Follow the existing `export interface`/`export type` placement convention near the other `Agent*` types (this block starts at line 630).

---

### `backend/tests/test_remote_access.py` (test — EXTEND)

**Analog:** itself.

**Module docstring + mock-collection helper pattern (`_col`/`_db`) — reuse for `test_control_session_audit.py` too** (lines 1-40):
```python
"""
Comprehensive tests for the remote access subsystem:
  - remote_endpoints.py    — session REST CRUD
  - tunnel_endpoints.py    — WebSocket relay (user ↔ agent)
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import asyncio, threading, uuid, pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import FastAPI
from fastapi.testclient import TestClient
from authentication_service import get_current_user
from auth_types import TokenData

def _col(**kw):
    col = MagicMock()
    col.find_one = AsyncMock(return_value=None)
    col.insert_one = AsyncMock(return_value=MagicMock(inserted_id="fake-id"))
    col.update_one = AsyncMock(return_value=MagicMock(matched_count=1))
    # ...
    for k, v in kw.items():
        setattr(col, k, v)
    return col

def _user(role="super_admin", tenant_id="tenant-1"):
    return TokenData(username="tester@example.com", role=role, tenant_id=tenant_id, mfa_verified=True)

def _app(router, user=None):
    app = FastAPI()
    app.include_router(router)
    if user is not None:
        app.dependency_overrides[get_current_user] = lambda: user
    return app
```

**Permission-denial test pattern — direct model for `control:remote_access` gating tests** (lines 223-230):
```python
def test_list_sessions_denied_without_permission(self):
    with patch("remote_endpoints.get_database", return_value=self.db):
        with patch("rbac_utils.verify_permission", AsyncMock(return_value=False)):
            self.app.dependency_overrides[get_current_user] = lambda: _user(role="viewer")
            with TestClient(self.app) as c:
                r = c.get("/api/remote")
    assert r.status_code == 403
```

**WebSocket relay test setup + dual-DB-patch helper (`_patch_tunnel_db`, `_user_token`)** (lines 237-294):
```python
def _tunnel_db(session_tenant="tenant-1"):
    """Returns a (raw_db, tenant_isolated_db) pair for tunnel tests."""
    raw_db = MagicMock()
    raw_db.remote_sessions.find_one = AsyncMock(
        return_value={"session_id": "any", "tenantId": session_tenant, "status": "pending"})
    raw_db.tenants.find_one = AsyncMock(return_value={"id": "tenant-1", "registrationKey": "valid-reg-key"})
    # ...

def _patch_tunnel_db(session_tenant="tenant-1"):
    from contextlib import ExitStack, contextmanager
    @contextmanager
    def _ctx():
        raw_db, idb = _tunnel_db(session_tenant)
        mock_mongodb = MagicMock(); mock_mongodb.db = raw_db
        with ExitStack() as stack:
            stack.enter_context(patch("tunnel_endpoints.mongodb", mock_mongodb))
            stack.enter_context(patch("tunnel_endpoints.get_database", return_value=idb))
            yield raw_db
    return _ctx()

def _user_token(tenant_id="tenant-1"):
    return AsyncMock(return_value=TokenData(username="user@t1.com", role="admin", tenant_id=tenant_id, mfa_verified=True))

class TestTunnelWebSocket:
    @pytest.fixture(autouse=True)
    def setup(self):
        from tunnel_endpoints import register_tunnel_routes, _tunnels
        _tunnels.clear()
        self.app = FastAPI()
        register_tunnel_routes(self.app)
        yield
        _tunnels.clear()
```

**Bidirectional-relay test pattern (threaded WS peers) — model for a control-mode input-frame relay test** (lines 425-463, `test_relay_user_to_agent`):
```python
def test_relay_user_to_agent(self):
    """Message sent by the user side arrives at the agent side."""
    sid = "u2a-" + uuid.uuid4().hex[:8]
    received = []
    agent_ready = threading.Event()
    agent_done = threading.Event()
    errors = []
    with patch("authentication_service.verify_token_async", _user_token()):
        with _patch_tunnel_db():
            with TestClient(self.app) as client:
                def run_agent():
                    try:
                        with client.websocket_connect(f"/api/tunnel/{sid}/agent?token=tok") as ws:
                            agent_ready.set()
                            msg = ws.receive_text()
                            received.append(msg)
                    except Exception as exc:
                        errors.append(str(exc))
                    finally:
                        agent_done.set()
                t = threading.Thread(target=run_agent, daemon=True)
                t.start()
                assert agent_ready.wait(timeout=3), "Agent did not connect in time"
                with client.websocket_connect(f"/api/tunnel/{sid}/user?token=tok") as user_ws:
                    user_ws.send_text("ping from user")
                assert agent_done.wait(timeout=3), "Agent did not finish in time"
                t.join(timeout=2)
    assert not errors, f"Agent thread raised: {errors}"
    assert received == ["ping from user"]
```
**Apply:** an equivalent test sending a JSON `{"type":"input",...}` frame instead of a bare string, asserting the agent side receives the exact JSON payload — proves the relay-level plumbing (not the actual `SendInput` call, which needs `checkpoint:human-verify`).

**Disconnect/sentinel-propagation test pattern — model for D-12 (fresh consent required after drop) and the new disconnect endpoint** (lines 504-517):
```python
def test_disconnect_propagates_sentinel_to_partner(self):
    """When user disconnects, the sentinel unblocks the agent's send queue."""
    from tunnel_endpoints import _tunnels
    sid = "sentinel-" + uuid.uuid4().hex[:8]
    with patch("authentication_service.verify_token_async", _user_token()):
        with _patch_tunnel_db():
            with TestClient(self.app) as client:
                with client.websocket_connect(f"/api/tunnel/{sid}/user?token=tok"):
                    pass  # Disconnect immediately
    assert sid not in _tunnels  # Tunnel cleaned up after disconnect
```

---

### `backend/tests/test_control_session_audit.py` (test — NEW)

**Analog:** No direct sibling exists (`remediation_audit_service.py` itself has no standalone test file — see note under `control_session_audit_service.py` above). Follow `test_remote_access.py`'s `_col()`/`_db()` MagicMock-collection pattern (reproduced above) to construct a fake `db.control_session_audit` collection, then assert `write_audit`/`list_audit` call `insert_one`/`find` with the expected `tenantId`/`ts`-defaulted document shape — same assertions style as `test_list_sessions_denied_without_permission`'s direct status-code/JSON-shape checks.

---

## Shared Patterns

### Tunnel authentication (`X-Tenant-Key` header for agent-side WS)
**Source:** `agent-install/omni-agent-rs/src/capabilities/remote_access.rs:78-89` (`tunnel_request`)
**Apply to:** Any new Rust-side WS connection this phase adds — never use a bare `connect_async(url)`.

### Discriminated-union WS frame shape (`{"type": ...}`)
**Source:** established by `remote_access.rs:284-288` (`frame`/`error`) and consumed by `RemoteDesktop.tsx:62-79`.
**Apply to:** all new frame types this phase adds (`input`, `consent_request`, `consent_result`) — keep the same flat `{"type": "...", ...fields}` shape, add a distinguishing discriminant per Pitfall 4 (don't reuse the same generic `"error"` string for three different failure states — offline vs. wrong-OS vs. no-interactive-session).

### Session-0 → interactive-desktop UI injection (`CreateProcessAsUserW` / Rust; pywin32 equivalent / Python)
**Source:** `agent-install/omni-agent-rs/src/chat_ui.rs:284-350` (Rust, proven/working); RESEARCH.md Pattern 2 (Python, cited-but-unexecuted).
**Apply to:** `consent_ui.rs` and `consent_ui.py` — this is the load-bearing mechanism for D-01/D-03/D-09.
**Do NOT use:** `WTSSendMessage`/`msg.exe` (`chat_display.rs:1-38`) for the consent dialog itself — one-way only, no Accept/Decline capture. Reserve it only as a last-resort fallback if `CreateProcessAsUserW` fails outright (which for D-02's no-console-session case means no dialog at all, not a fallback dialog).

### RBAC permission-list + `require_permission()` dependency factory
**Source:** `backend/rbac_utils.py:75-181` (DEFAULT_PERMISSIONS dict), `:201-211` (`require_permission`).
**Apply to:** `control:remote_access` — add to `admin` (line 99) and `Tenant Admin` (line 123) lists only; gate the new disconnect endpoint and control-mode dispatch in `remote_endpoints.py` through `Depends(require_permission("control:remote_access"))`, identical to the existing `view:remote_access` usage at `remote_endpoints.py:29,43`.

### Append-only audit trail (`write_audit`/`list_audit`, insert-only)
**Source:** `backend/remediation_audit_service.py` (full file, 46 lines).
**Apply to:** `control_session_audit_service.py` — copy verbatim, rename the collection, adjust the record schema.

### `_REMOTE_SUPER_ROLES` cross-tenant bypass set
**Source:** `backend/remote_endpoints.py:13-22` (`_REMOTE_SUPER_ROLES`, `_remote_tenant`).
**Apply to:** D-11's force-kill — the new disconnect endpoint should accept a request from any role in this set regardless of the session's own `tenantId`, mirroring how `_remote_tenant()` returns `{}` (no tenant filter) for those roles today.

### Bidirectional WS relay via `/user` (not `/viewer`)
**Source:** `backend/tunnel_endpoints.py:93-145` (`tunnel_user_side`); proven end-to-end by `components/RemoteTerminal.tsx:87-90,72-74`.
**Apply to:** `RemoteDesktop.tsx` must connect to `/api/tunnel/{session_id}/user` (not `/viewer`) whenever the session is control-mode — this is Pitfall 1, the single most consequential wiring decision in the phase.

---

## No Analog Found

| File / Concern | Role | Data Flow | Reason |
|------|------|-----------|--------|
| `agent/capabilities/consent_ui.py`'s actual `CreateProcessAsUser` sequence | utility | request-response | `chat_window.py` is the only existing Python UI-spawning code, but it runs `tkinter` in-process rather than session-injecting via `CreateProcessAsUser` — and `agent/agent.py`'s `win32serviceutil` import confirms the Python agent runs as a Session-0 service, meaning `chat_window.py`'s approach would not actually surface on the interactive desktop. RESEARCH.md's Pattern 2 (pywin32) is cited from official docs, not from working repo code — flag as Wave-0 spike, `checkpoint:human-verify`. |
| Client-side RBAC permission check (frontend) | component | request-response | Neither `RemoteAccessDashboard.tsx` nor `RemoteDesktop.tsx` currently perform any client-side `view:remote_access`/permission gating (confirmed via grep this session — zero matches) — the mode toggle is purely UI state, with all enforcement happening backend-side via `require_permission()`. The planner should decide whether the new control-mode toggle needs a client-side capability check (e.g. from a `/api/auth/me` permissions list already loaded elsewhere in the app) to hide the affordance for users who lack `control:remote_access`, or whether it's acceptable to let the backend 403 on session-start and show that error — no existing frontend pattern to copy either way. |
| Win32 `SendInput` replay itself (both languages) | utility | event-driven | Genuinely new code in both Rust and Python — no existing capability in this codebase calls `SendInput`. The `winapi`/`ctypes` struct layouts are `[CITED]`/`[ASSUMED]` per RESEARCH.md's Assumptions Log (A2), not copied from a working example. Treat as `checkpoint:human-verify` on a real Windows host before trusting in the plan's task list. |

---

## Metadata

**Analog search scope:** `agent-install/omni-agent-rs/src/`, `agent/capabilities/`, `agent/agent.py`, `backend/*.py`, `backend/tests/test_remote_access.py`, `components/*.tsx`, `types.ts`, `Cargo.toml`
**Files scanned (full or targeted read):** 15 — `remote_access.rs`, `chat_ui.rs`, `chat_display.rs`, `Cargo.toml`, `remote_access.py` (agent), `chat_window.py`, `agent.py` (grep only), `tunnel_endpoints.py`, `remote_endpoints.py`, `rbac_utils.py`, `remediation_audit_service.py`, `RemoteDesktop.tsx`, `RemoteAccessDashboard.tsx`, `RemoteTerminal.tsx`, `types.ts`, `test_remote_access.py`
**Pattern extraction date:** 2026-08-27
**Note on CONTEXT.md correction carried forward:** `backend/remote_access_service.py` (`ConnectionManager`) confirmed dead code this session — zero importers found via full-tree grep (only unrelated `LDAPConnectionManager`/pymongo `_ConnectionManager` hits). Do not treat it as an analog for anything; the live relay is `tunnel_endpoints.py`'s `_tunnels` dict.

//! Two-way interactive chat window for the endpoint user.
//!
//! The agent runs as a session-0 service and cannot draw an interactive window
//! itself. This module spawns a PowerShell WinForms chat UI *into the active
//! console session* using `CreateProcessAsUserW` with a token obtained from
//! `WTSQueryUserToken(WTSGetActiveConsoleSessionId())`. The spawned UI polls the
//! backend for admin messages and POSTs the user's typed replies, giving a real
//! two-way conversation. When no interactive session exists (no logged-on user),
//! `launch_interactive` returns Err so the caller falls back to the one-way
//! `chat_display::show_message` path.
//!
//! `winapi` (frozen 0.3 API) is used rather than the `windows` crate to keep the
//! FFI surface stable.

use std::collections::HashSet;
use std::sync::{Mutex, OnceLock};

/// Session IDs that currently have an interactive UI process running.
fn active() -> &'static Mutex<HashSet<String>> {
    static ACTIVE: OnceLock<Mutex<HashSet<String>>> = OnceLock::new();
    ACTIVE.get_or_init(|| Mutex::new(HashSet::new()))
}

pub fn is_active(session_id: &str) -> bool {
    active().lock().map(|s| s.contains(session_id)).unwrap_or(false)
}

fn mark_active(session_id: &str) {
    if let Ok(mut s) = active().lock() {
        s.insert(session_id.to_string());
    }
}

pub fn mark_closed(session_id: &str) {
    if let Ok(mut s) = active().lock() {
        s.remove(session_id);
    }
}

/// Directory that holds the per-session config and the UI script.
#[cfg(windows)]
pub fn data_dir() -> std::path::PathBuf {
    let base = std::env::var("ProgramData").unwrap_or_else(|_| r"C:\ProgramData".to_string());
    std::path::Path::new(&base).join("OmniAgent")
}

/// Path where the chat-window script is materialized.
#[cfg(windows)]
pub fn script_path() -> std::path::PathBuf {
    data_dir().join("chat_ui.ps1")
}

/// Write the embedded chat-window script to ProgramData so both the agent
/// (admin-initiated) and the tray (endpoint-initiated) can launch it. Idempotent.
#[cfg(windows)]
pub fn ensure_script_installed() -> Result<std::path::PathBuf, String> {
    let dir = data_dir();
    std::fs::create_dir_all(&dir).map_err(|e| format!("create {}: {e}", dir.display()))?;
    let p = script_path();
    std::fs::write(&p, CHAT_UI_PS).map_err(|e| format!("write chat script: {e}"))?;
    Ok(p)
}

/// Launch (or refresh) the interactive chat window in the active user session.
#[cfg(windows)]
pub fn launch_interactive(
    session_id: &str,
    subject: &str,
    initial: &str,
    sender: &str,
    backend_url: &str,
    token: &str,
) -> Result<(), String> {
    // Already showing this session's window — the UI polls new admin messages
    // itself, so nothing to spawn again.
    if is_active(session_id) {
        return Ok(());
    }

    let dir = data_dir();
    let script_path = ensure_script_installed()?;

    // Per-session config carries the bearer token off the command line so it is
    // not visible in the process list / task definition.
    let cfg = serde_json::json!({
        "session_id": session_id,
        "backend_url": backend_url.trim_end_matches('/'),
        "token": token,
        "subject": subject,
        "initial": initial,
        "sender": sender,
    });
    let cfg_path = dir.join(format!("chat_{session_id}.json"));
    std::fs::write(&cfg_path, serde_json::to_vec(&cfg).unwrap_or_default())
        .map_err(|e| format!("write session config: {e}"))?;

    let cmdline = format!(
        "powershell.exe -NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File \"{}\" \"{}\"",
        script_path.display(),
        cfg_path.display()
    );

    win::spawn_in_active_session(&cmdline)?;
    mark_active(session_id);
    Ok(())
}

/// Signal the interactive window (if any) to close promptly and drop bookkeeping.
/// The UI watches for `chat_{id}.close` and tears itself down on the next tick.
#[cfg(windows)]
pub fn signal_close(session_id: &str) -> Result<(), String> {
    let dir = data_dir();
    let sentinel = dir.join(format!("chat_{session_id}.close"));
    // Best-effort: create the dir if the window was never opened here.
    let _ = std::fs::create_dir_all(&dir);
    std::fs::write(&sentinel, b"close").map_err(|e| format!("write close sentinel: {e}"))?;
    mark_closed(session_id);
    Ok(())
}

#[cfg(not(windows))]
pub fn signal_close(session_id: &str) -> Result<(), String> {
    mark_closed(session_id);
    Ok(())
}

#[cfg(not(windows))]
pub fn launch_interactive(
    _session_id: &str,
    _subject: &str,
    _initial: &str,
    _sender: &str,
    _backend_url: &str,
    _token: &str,
) -> Result<(), String> {
    Err("interactive chat window is Windows-only".to_string())
}

/// Embedded PowerShell WinForms chat UI. Arg 1 is the per-session config JSON path.
#[cfg(windows)]
const CHAT_UI_PS: &str = r#"
param([Parameter(Mandatory=$true)][string]$ConfigPath)
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

$cfg      = Get-Content -Raw -Path $ConfigPath | ConvertFrom-Json
$Session  = $cfg.session_id
$Base     = $cfg.backend_url
$Token    = $cfg.token
$Headers  = @{ Authorization = "Bearer $Token" }
$MsgUrl   = "$Base/api/agent-chat/sessions/$Session/user-message"
$PollUrl  = "$Base/api/agent-chat/sessions/$Session/messages"
# The agent drops this file when the admin closes the session, for prompt teardown.
$CloseSig = [System.IO.Path]::Combine([System.IO.Path]::GetDirectoryName($ConfigPath), "chat_$Session.close")

# Only admin messages strictly newer than $Since are appended, so the window
# does not re-print history each poll. Start at "now" and show the opener below.
$Since = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds()

$form               = New-Object System.Windows.Forms.Form
$form.Text          = "IT Support Chat" + $(if ($cfg.subject) { " - " + $cfg.subject } else { "" })
$form.Size          = New-Object System.Drawing.Size(460, 560)
$form.StartPosition = 'CenterScreen'
$form.TopMost       = $true

$log                = New-Object System.Windows.Forms.RichTextBox
$log.Location       = New-Object System.Drawing.Point(10, 10)
$log.Size           = New-Object System.Drawing.Size(425, 430)
$log.ReadOnly       = $true
$log.BackColor      = [System.Drawing.Color]::White
$form.Controls.Add($log)

$input              = New-Object System.Windows.Forms.TextBox
$input.Location     = New-Object System.Drawing.Point(10, 450)
$input.Size         = New-Object System.Drawing.Size(330, 50)
$input.Multiline    = $true
$form.Controls.Add($input)

$send               = New-Object System.Windows.Forms.Button
$send.Location      = New-Object System.Drawing.Point(348, 450)
$send.Size          = New-Object System.Drawing.Size(87, 50)
$send.Text          = "Send"
$form.Controls.Add($send)

function Append([string]$who, [string]$text, $color) {
    $log.SelectionColor = $color
    $log.AppendText("$who`: ")
    $log.SelectionColor = [System.Drawing.Color]::Black
    $log.AppendText("$text`r`n")
    $log.ScrollToCaret()
}

if ($cfg.initial) {
    $who = if ($cfg.sender) { $cfg.sender } else { "Administrator" }
    Append $who $cfg.initial ([System.Drawing.Color]::Blue)
}

$sendAction = {
    $text = $input.Text.Trim()
    if ($text.Length -eq 0) { return }
    try {
        $body = @{ content = $text } | ConvertTo-Json
        Invoke-RestMethod -Method Post -Uri $MsgUrl -Headers $Headers -ContentType 'application/json' -Body $body | Out-Null
        Append "You" $text ([System.Drawing.Color]::DarkGreen)
        $input.Clear()
    } catch {
        Append "System" "Failed to send - check connection." ([System.Drawing.Color]::Red)
    }
}
$send.Add_Click($sendAction)
$input.Add_KeyDown({
    if ($_.KeyCode -eq 'Return' -and -not $_.Shift) { $_.SuppressKeyPress = $true; & $sendAction }
})

$timer          = New-Object System.Windows.Forms.Timer
$timer.Interval = 3000
$timer.Add_Tick({
    if (Test-Path -Path $CloseSig) {
        Remove-Item -Path $CloseSig -ErrorAction SilentlyContinue
        Append "System" "This chat has been closed by the administrator." ([System.Drawing.Color]::Gray)
        $input.Enabled = $false; $send.Enabled = $false; $timer.Stop()
        return
    }
    try {
        $resp = Invoke-RestMethod -Method Get -Uri "$PollUrl`?since=$Since" -Headers $Headers
        if ($resp.messages) {
            foreach ($m in $resp.messages) {
                $who = if ($m.sender_name) { $m.sender_name } else { "Administrator" }
                Append $who $m.content ([System.Drawing.Color]::Blue)
            }
            $Since = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds()
        }
        if ($resp.status -and $resp.status -ne 'active') {
            Append "System" "This chat has been closed by the administrator." ([System.Drawing.Color]::Gray)
            $input.Enabled = $false; $send.Enabled = $false; $timer.Stop()
        }
    } catch { }
})
$timer.Start()

$form.Add_FormClosed({
    $timer.Stop()
    Remove-Item -Path $ConfigPath -ErrorAction SilentlyContinue
    Remove-Item -Path $CloseSig -ErrorAction SilentlyContinue
})
[System.Windows.Forms.Application]::Run($form)
"#;

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
    use winapi::um::winnt::{
        SecurityImpersonation, TokenPrimary, HANDLE, MAXIMUM_ALLOWED,
    };
    use winapi::um::wtsapi32::WTSQueryUserToken;

    fn wide(s: &str) -> Vec<u16> {
        std::ffi::OsStr::new(s).encode_wide().chain(std::iter::once(0)).collect()
    }

    /// Launch `cmdline` as the interactive console user on winsta0\default.
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
            let dup = DuplicateTokenEx(
                user_token,
                MAXIMUM_ALLOWED,
                std::ptr::null_mut(),
                SecurityImpersonation,
                TokenPrimary,
                &mut primary,
            );
            CloseHandle(user_token);
            if dup == 0 {
                return Err(format!("DuplicateTokenEx failed ({})", GetLastError()));
            }

            let mut env: LPVOID = std::ptr::null_mut();
            let have_env = CreateEnvironmentBlock(&mut env, primary, FALSE) != 0;

            let mut si: STARTUPINFOW = std::mem::zeroed();
            si.cb = std::mem::size_of::<STARTUPINFOW>() as DWORD;
            let mut desktop = wide(r"winsta0\default");
            si.lpDesktop = desktop.as_mut_ptr();

            let mut pi: PROCESS_INFORMATION = std::mem::zeroed();
            let mut cmd = wide(cmdline);
            let flags = CREATE_UNICODE_ENVIRONMENT | CREATE_NO_WINDOW;

            let ok = CreateProcessAsUserW(
                primary,
                std::ptr::null(),
                cmd.as_mut_ptr(),
                std::ptr::null_mut(),
                std::ptr::null_mut(),
                FALSE,
                flags,
                if have_env { env } else { std::ptr::null_mut() },
                std::ptr::null(),
                &mut si,
                &mut pi,
            );
            let err = GetLastError();

            if have_env {
                DestroyEnvironmentBlock(env);
            }
            CloseHandle(primary);

            if ok == 0 {
                return Err(format!("CreateProcessAsUserW failed ({err})"));
            }
            CloseHandle(pi.hThread);
            CloseHandle(pi.hProcess);
            Ok(())
        }
    }
}

//! On-screen delivery of admin chat messages for the headless service agent.
//!
//! The agent runs as a Windows service in session 0 and cannot draw its own
//! window on the interactive desktop. `msg.exe` (built into Windows) is the one
//! mechanism a LocalSystem service can use to surface text on the active console
//! session, so admin chat messages are shown as a native message box there.
//! Delivery is one-way (msg.exe has no reply input); the endpoint user reply
//! path is handled separately by the backend `/user-message` route.

/// Show an admin chat message on the endpoint's active desktop session.
/// Returns Ok(()) when the message was dispatched to a session, Err otherwise.
#[cfg(windows)]
pub fn show_message(sender: &str, content: &str) -> Result<(), String> {
    let body = format!("{sender}: {content}");
    // `msg * /time:300` targets every session on this host; from session 0 the
    // active console session receives the box. 300s keeps it visible without
    // hanging the agent thread (msg.exe returns immediately, box stays up).
    let out = std::process::Command::new("msg")
        .args(["*", "/time:300", &body])
        .output()
        .map_err(|e| format!("msg.exe spawn failed: {e}"))?;
    if out.status.success() {
        Ok(())
    } else {
        Err(format!(
            "msg.exe exited {}: {}",
            out.status.code().unwrap_or(-1),
            String::from_utf8_lossy(&out.stderr).trim()
        ))
    }
}

#[cfg(not(windows))]
pub fn show_message(sender: &str, content: &str) -> Result<(), String> {
    // Non-Windows endpoints have no msg.exe; log-only so the round-trip still acks.
    log::info!("[chat] (no on-screen display on this platform) {sender}: {content}");
    Ok(())
}

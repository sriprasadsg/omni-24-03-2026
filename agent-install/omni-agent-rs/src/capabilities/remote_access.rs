use super::Capability;
use serde_json::{json, Value};
use sysinfo::System;

/// Identity of the admin requesting interactive control. Rendered in the consent
/// dialog and stop bar, and POSTed with the consent decision (T-74-19 audit).
#[derive(Default, Clone)]
pub struct Requester {
    pub name: String,
    pub email: String,
    pub tenant: String,
}

pub struct RemoteAccessCapability;

impl Capability for RemoteAccessCapability {
    fn id(&self) -> &'static str { "remote_access" }
    fn name(&self) -> &'static str { "Remote Access Control" }

    fn collect(&self, _sys: &System) -> Value {
        let status = rdp_status();
        json!({
            "rdp_enabled": status.0,
            "rdp_port": 3389,
            "status": if status.1.is_empty() { "success" } else { "error" },
            "error": status.1,
            "timestamp": chrono::Utc::now().to_rfc3339(),
        })
    }
}

fn rdp_status() -> (bool, String) {
    #[cfg(windows)]
    {
        use winreg::enums::*;
        use winreg::RegKey;
        match RegKey::predef(HKEY_LOCAL_MACHINE)
            .open_subkey(r"SYSTEM\CurrentControlSet\Control\Terminal Server")
            .and_then(|k| k.get_value::<u32, _>("fDenyTSConnections"))
        {
            Ok(val) => (val == 0, String::new()),
            Err(e) => (false, e.to_string()),
        }
    }
    #[cfg(not(windows))]
    {
        (false, "unsupported on this platform".to_string())
    }
}

pub fn set_rdp(enable: bool) -> Result<(), String> {
    #[cfg(windows)]
    {
        use winreg::enums::*;
        use winreg::RegKey;
        let key = RegKey::predef(HKEY_LOCAL_MACHINE)
            .open_subkey_with_flags(
                r"SYSTEM\CurrentControlSet\Control\Terminal Server",
                KEY_SET_VALUE,
            )
            .map_err(|e| e.to_string())?;
        let deny: u32 = if enable { 0 } else { 1 };
        key.set_value("fDenyTSConnections", &deny)
            .map_err(|e| e.to_string())?;
        let action = if enable { "Yes" } else { "No" };
        let _ = std::process::Command::new("netsh")
            .args([
                "advfirewall", "firewall", "set", "rule",
                "group=remote desktop", "new", &format!("enable={}", action),
            ])
            .output();
        log::info!("RDP {}", if enable { "enabled" } else { "disabled" });
        Ok(())
    }
    #[cfg(not(windows))]
    {
        Err("unsupported on this platform".to_string())
    }
}

/// Credentials for the agent side of a tunnel. The platform accepts this
/// agent's own token; servers from before that only take the tenant key.
#[derive(Clone)]
pub struct TunnelAuth {
    pub agent_token: String,
    pub tenant_key: String,
}

/// The tunnel endpoint on the platform this agent is enrolled with.
///
/// The URL inside the instruction is deliberately not used. The server built
/// it from its own settings, and a stale BACKEND_WS_HOST sent every desktop
/// session to a retired host over plain ws:// (no video, and the tenant key in
/// clear text). An instruction must not be able to point the screen stream
/// and credentials at another address. None for a malformed session id.
pub fn tunnel_url(api_base_url: &str, session_id: &str) -> Option<String> {
    if session_id.is_empty() || !session_id.chars().all(|c| c.is_ascii_alphanumeric() || c == '-') {
        return None;
    }
    let base = api_base_url.trim_end_matches('/');
    let ws_base = if let Some(rest) = base.strip_prefix("https://") {
        format!("wss://{rest}")
    } else if let Some(rest) = base.strip_prefix("http://") {
        format!("ws://{rest}")
    } else {
        return None;
    };
    Some(format!("{ws_base}/api/tunnel/{session_id}/agent"))
}

/// Where the agent reports its user's consent decision for a control session
/// (backend remote_endpoints.report_consent), on the same platform as the tunnel.
fn consent_url(tunnel_url: &str, session_id: &str) -> Option<String> {
    let (base, _) = tunnel_url.split_once("/api/tunnel/")?;
    let base = base.replacen("wss://", "https://", 1).replacen("ws://", "http://", 1);
    Some(format!("{base}/api/remote/session/{session_id}/consent"))
}

/// Build the tunnel WebSocket request with this agent's token and, for older
/// platforms, the tenant's `X-Tenant-Key` header. `tunnel_agent_side`
/// (backend/tunnel_endpoints.py) refuses a connection that carries neither.
fn tunnel_request(
    url: &str,
    auth: &TunnelAuth,
) -> Result<tokio_tungstenite::tungstenite::handshake::client::Request, Box<dyn std::error::Error + Send + Sync>> {
    use tokio_tungstenite::tungstenite::client::IntoClientRequest;
    use tokio_tungstenite::tungstenite::http::HeaderValue;
    let mut req = url.into_client_request()?;
    if !auth.agent_token.is_empty() {
        req.headers_mut().insert(
            "Authorization",
            HeaderValue::from_str(&format!("Bearer {}", auth.agent_token))?,
        );
    }
    if !auth.tenant_key.is_empty() {
        req.headers_mut().insert("X-Tenant-Key", HeaderValue::from_str(&auth.tenant_key)?);
    }
    Ok(req)
}

/// Open a tunnel WebSocket to the platform, trusting it the way every other
/// platform connection does (pinned certificate, see crate::tls).
async fn connect_tunnel(
    url: &str,
    auth: &TunnelAuth,
) -> Result<
    tokio_tungstenite::WebSocketStream<tokio_tungstenite::MaybeTlsStream<tokio::net::TcpStream>>,
    Box<dyn std::error::Error + Send + Sync>,
> {
    let connector = crate::tls::platform_ws_connector()?;
    let (ws_stream, _) =
        tokio_tungstenite::connect_async_tls_with_config(tunnel_request(url, auth)?, None, false, connector)
            .await?;
    Ok(ws_stream)
}

/// Spawn a WebSocket-based reverse shell in a background tokio task.
pub fn start_reverse_shell(session_id: String, url: String, auth: TunnelAuth) {
    tokio::spawn(async move {
        log::info!("Reverse shell starting: session={session_id} url={url}");
        if let Err(e) = reverse_shell_run(&url, &auth).await {
            log::error!("Reverse shell error: {e}");
        }
        log::info!("Reverse shell ended: session={session_id}");
    });
}

/// Spawn a desktop streaming task that sends JPEG frames over WebSocket.
/// When `control` is true the same tunnel also relays browser input frames
/// back to the agent, gated behind endpoint-user consent (D-01).
pub fn start_desktop_stream(
    session_id: String,
    url: String,
    auth: TunnelAuth,
    control: bool,
    requester: Requester,
) {
    tokio::spawn(async move {
        log::info!(
            "Desktop stream starting: session={session_id} url={url} control={control}"
        );
        if let Err(e) = desktop_stream_run(&session_id, &url, &auth, control, &requester).await {
            log::error!("Desktop stream error: {e}");
        }
        log::info!("Desktop stream ended: session={session_id}");
    });
}

fn spawn_local_shell() -> std::io::Result<tokio::process::Child> {
    #[cfg(windows)]
    return tokio::process::Command::new("powershell.exe")
        .args(["-NoLogo", "-NonInteractive"])
        .stdin(std::process::Stdio::piped())
        .stdout(std::process::Stdio::piped())
        .stderr(std::process::Stdio::piped())
        .spawn();

    #[cfg(not(windows))]
    tokio::process::Command::new("/bin/bash")
        .stdin(std::process::Stdio::piped())
        .stdout(std::process::Stdio::piped())
        .stderr(std::process::Stdio::piped())
        .spawn()
}

async fn reverse_shell_run(url: &str, auth: &TunnelAuth) -> Result<(), Box<dyn std::error::Error + Send + Sync>> {
    use futures_util::{SinkExt, StreamExt};
    use tokio::io::{AsyncReadExt, AsyncWriteExt};
    use tokio::sync::mpsc;
    use tokio_tungstenite::tungstenite::Message;

    let ws_stream = connect_tunnel(url, auth).await?;
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
            Message::Text(text) => {
                if proc_stdin.write_all(text.as_bytes()).await.is_err() { break; }
            }
            Message::Binary(data) => {
                if proc_stdin.write_all(&data).await.is_err() { break; }
            }
            Message::Close(_) => break,
            _ => {}
        }
    }

    let _ = child.kill().await;
    Ok(())
}


// Windows: long-lived PowerShell process captures JPEG frames and emits base64 lines.
// Phase 74 consent-gate flow:
//   1. Connect tunnel, send control_state:"awaiting_consent"
//   2. spawn_blocking request_consent (blocks on endpoint user)
//   3. POST decision to backend audit endpoint (T-74-19)
//   4. On accept: show_stop_bar, send control_state:"active", start capture + input loop
//   5. Input loop: rate cap 50/s, ConsentGate.authorised() per frame, stop_requested() per frame
//   6. On decline/timeout/stop: send control_state:"ended", cleanup, exit
#[cfg(windows)]
async fn desktop_stream_run(
    session_id: &str,
    url: &str,
    auth: &TunnelAuth,
    control: bool,
    requester: &Requester,
) -> Result<(), Box<dyn std::error::Error + Send + Sync>> {
    use crate::capabilities::control_input::{control_input_replay, parse_input_frame, ConsentGate};
    use crate::consent_ui::{request_consent, show_stop_bar, hide_stop_bar, stop_requested, ConsentDecision, ConsentError};
    use futures_util::{SinkExt, StreamExt};
    use tokio::time::{timeout, Duration, interval};
    use tokio_tungstenite::tungstenite::Message;

    let ws_stream = connect_tunnel(url, auth).await?;
    let (mut ws_write, ws_read) = ws_stream.split();

    // Build a control_state frame. The message can carry PowerShell output
    // (Windows paths), so it is JSON-encoded rather than spliced in.
    let send_state = |state: &str, reason: Option<&str>, message: Option<&str>| {
        let mut payload = json!({"type": "control_state", "state": state});
        if let Some(r) = reason { payload["reason"] = json!(r); }
        if let Some(m) = message { payload["message"] = json!(m); }
        Message::Text(payload.to_string().into())
    };

    // 1. Signal awaiting consent
    let _ = ws_write.send(send_state("awaiting_consent", None, Some("Waiting for endpoint user consent"))).await;

    // 2. Request consent via spawn_blocking (blocks on endpoint UI)
    let session_id_owned = session_id.to_string();
    let requester_name = requester.name.clone();
    let requester_email = requester.email.clone();
    let tenant_name = requester.tenant.clone();
    let decision = tokio::task::spawn_blocking({
        let session_id = session_id_owned.clone();
        let name = requester_name.clone();
        let email = requester_email.clone();
        let tenant = tenant_name.clone();
        move || {
            request_consent(&session_id, &name, &email, &tenant, 60)
        }
    }).await.unwrap_or(Err(ConsentError::SpawnFailed("task join failed".into())));

    let decision = match decision {
        Ok(ConsentDecision::Accept) => ConsentDecision::Accept,
        Ok(ConsentDecision::Decline) => ConsentDecision::Decline,
        Ok(ConsentDecision::Timeout) => ConsentDecision::Timeout,
        Err(ConsentError::NoInteractiveSession) => {
            let _ = ws_write.send(Message::Text(r#"{"type":"error","reason":"no_interactive_desktop","message":"No interactive desktop session available (Session 0 isolation)"}"#.into())).await;
            return Err("no interactive desktop session".into());
        }
        Err(ConsentError::SpawnFailed(e)) => {
            let msg = e.replace('"', "'");
            let _ = ws_write.send(Message::Text(format!(r#"{{"type":"error","reason":"relay_failed","message":"{}"}}"#, msg).into())).await;
            return Err(e.into());
        }
    };

    // 3. POST decision to backend audit endpoint (T-74-19)
    let _ = post_consent_decision(url, auth, &session_id_owned, &decision, requester).await;

    match decision {
        ConsentDecision::Decline => {
            let _ = ws_write.send(send_state("ended", Some("consent_declined"), Some("Endpoint user declined control"))).await;
            return Ok(());
        }
        ConsentDecision::Timeout => {
            let _ = ws_write.send(send_state("ended", Some("consent_timeout"), Some("Consent request timed out"))).await;
            return Ok(());
        }
        ConsentDecision::Accept => {}
    }

    // 4. Consent accepted — show stop bar, signal active
    if let Err(e) = show_stop_bar(&session_id_owned, &requester_name) {
        log::warn!("Failed to show stop bar: {e}");
    }
    let _ = ws_write.send(send_state("active", None, Some("Interactive control active"))).await;

    // 5. Start the capture process: the agent re-launches ITSELF with
    //    --desktop-capture, which grabs the screen with the Win32 GDI APIs and
    //    writes base64 JPEG frames to stdout (src/capabilities/screen_capture.rs).
    //    This replaced a hidden `powershell.exe -EncodedCommand` screen-grabber
    //    that Microsoft Defender quarantined as a PUA before it produced a frame
    //    (EILT0197, 2026-10-12). The child must run in the user's session: this
    //    service lives in session 0, whose desktop is not the one on screen.
    let capture_cmd = match crate::user_session::self_desktop_capture_cmdline() {
        Ok(cmd) => cmd,
        Err(e) => {
            let payload = json!({"type": "error", "message": format!("Cannot locate the agent executable for capture: {e}")});
            let _ = ws_write.send(Message::Text(payload.to_string().into())).await;
            let _ = hide_stop_bar(&session_id_owned);
            return Err(format!("resolve agent exe for capture: {e}").into());
        }
    };
    let mut child = match crate::user_session::spawn_piped(&capture_cmd) {
        Ok(child) => child,
        Err(e) => {
            let msg = format!("Failed to launch capture process in the user's session: {}", e);
            let payload = json!({"type": "error", "message": msg});
            let _ = ws_write.send(Message::Text(payload.to_string().into())).await;
            let _ = hide_stop_bar(&session_id_owned);
            return Err(format!("failed to start capture in the user session: {}", e).into());
        }
    };
    let Some(stdout) = child.stdout.take() else {
        let _ = hide_stop_bar(&session_id_owned);
        return Err("no stdout from capture process".into());
    };
    // Lines arrive from a blocking pipe; a small channel keeps at most a few
    // frames buffered when the relay is slower than the capture. Read bytes,
    // not lines(): one non-UTF-8 byte in a PowerShell error (OEM code page)
    // made lines() fail, which ended the stream as if the capture had exited.
    let (line_tx, mut line_rx) = tokio::sync::mpsc::channel::<String>(4);
    std::thread::spawn(move || {
        use std::io::BufRead;
        let mut reader = std::io::BufReader::new(stdout);
        let mut buf = Vec::new();
        loop {
            buf.clear();
            match reader.read_until(b'\n', &mut buf) {
                Ok(0) | Err(_) => break,
                Ok(_) => {
                    let line = String::from_utf8_lossy(&buf).trim_end_matches(&['\r', '\n'][..]).to_string();
                    if line_tx.blocking_send(line).is_err() { break }
                }
            }
        }
    });

    // First line must arrive within 15s (PowerShell start-up in the user's
    // session, loading System.Drawing, can take several seconds).
    let first_line = timeout(Duration::from_secs(15), line_rx.recv()).await;
    let mut pending: Option<String> = match first_line {
        Ok(next) => next,
        Err(_) => {
            let _ = ws_write
                .send(Message::Text(
                    r#"{"type":"error","message":"No response from desktop capture process within 15s - it may lack an interactive desktop session"}"#.into(),
                ))
                .await;
            child.kill();
            let _ = hide_stop_bar(&session_id_owned);
            return Err("desktop capture timed out with no output".into());
        }
    };

    // 6. Authorisation gate, shared between the input loop and this loop so a
    //    revocation (stop sentinel / capture failure) is visible to the running,
    //    spawned input task. Concede ONCE after accept; every later SendInput is
    //    re-checked against the gate (D-01) before replay.
    let gate = std::sync::Arc::new(std::sync::Mutex::new(ConsentGate::new()));
    gate.lock().unwrap().concede(); // consent accepted

    let input_task = if control {
        let mut ws_read = ws_read;
        let gate_input = gate.clone();
        tokio::spawn(async move {
            let mut rate_limiter = interval(Duration::from_millis(20)); // 50 frames/sec cap
            while let Some(Ok(msg)) = ws_read.next().await {
                rate_limiter.tick().await;
                // Re-check authorisation before EVERY SendInput (D-01). The gate
                // is revoked by the capture loop on stop — a revoked gate refuses
                // further replay permanently within this session (D-12).
                if !gate_input.lock().unwrap().authorised() {
                    log::info!("Input gate revoked, ending input loop");
                    break;
                }
                let text = match msg {
                    Message::Text(t) => t.to_string(),
                    Message::Binary(b) => match String::from_utf8(b.to_vec()) {
                        Ok(t) => t,
                        Err(_) => {
                            log::warn!("control input: non-UTF8 binary frame dropped");
                            continue;
                        }
                    },
                    Message::Close(_) => break,
                    _ => continue,
                };
                match parse_input_frame(&text) {
                    Ok(ev) => control_input_replay(&ev),
                    Err(e) => log::warn!("control input: rejected frame: {e}"),
                }
            }
        })
    } else {
        tokio::spawn(async {})
    };

    // 7. Frame capture loop
    let end_reason: &str;
    let end_message: String;
    // Whatever the capture printed besides frames: PowerShell errors share the
    // pipe, and used to be relayed to the viewer as (undrawable) frames.
    let mut output: Vec<String> = Vec::new();
    let mut logged_output = 0u32;
    loop {
        // Check stop sentinel each frame (D-09/D-12): the endpoint user's Stop
        // Control click writes stop_{session}.stop. On fire, revoke the gate so
        // the concurrent input task stops replaying immediately.
        if stop_requested(&session_id_owned) {
            end_reason = "stop_requested";
            end_message = "Endpoint user stopped control".into();
            gate.lock().unwrap().revoke();
            break;
        }

        let Some(line) = pending else {
            // The pipe closed: the capture process exited (or was killed).
            // Its exit code may lag the pipe by a moment.
            let mut code = child.exit_code();
            for _ in 0..10 {
                if code.is_some() { break }
                tokio::time::sleep(Duration::from_millis(100)).await;
                code = child.exit_code();
            }
            let detail = capture_exit_detail(code, &output);
            log::warn!("Desktop capture ended: session={session_id_owned} {detail}");
            let payload = json!({"type": "error", "message": format!("Desktop capture process ended ({detail})")});
            let _ = ws_write.send(Message::Text(payload.to_string().into())).await;
            end_reason = "capture_ended";
            end_message = format!("Desktop capture process ended ({detail})");
            gate.lock().unwrap().revoke();
            break;
        };
        match classify_capture_line(&line) {
            CaptureLine::Error(msg) => {
                log::warn!("Desktop capture failed: session={session_id_owned} {msg}");
                let payload = json!({"type": "error", "message": msg});
                let _ = ws_write.send(Message::Text(payload.to_string().into())).await;
                end_reason = "capture_error";
                end_message = "Desktop capture failed".into();
                gate.lock().unwrap().revoke();
                break;
            }
            CaptureLine::Frame(data) => {
                let ts = chrono::Utc::now().timestamp_millis();
                let payload = format!(
                    r#"{{"type":"frame","timestamp":{},"data":"{}"}}"#,
                    ts, data
                );
                if ws_write.send(Message::Text(payload.into())).await.is_err() {
                    end_reason = "relay_failed";
                    end_message = "WebSocket relay failed".into();
                    gate.lock().unwrap().revoke();
                    break;
                }
            }
            CaptureLine::Other(text) if !text.is_empty() => {
                // Log the first few only: a script stuck printing must not flood the log.
                logged_output += 1;
                if logged_output <= 20 {
                    log::warn!("Desktop capture output: session={session_id_owned} {text}");
                }
                remember_capture_output(&mut output, text);
            }
            CaptureLine::Other(_) => {}
        }
        pending = line_rx.recv().await;
    }

    // 8. Cleanup: abort input task, kill capture, hide stop bar, send ended state
    input_task.abort();
    child.kill();
    let _ = hide_stop_bar(&session_id_owned);
    let _ = ws_write.send(send_state("ended", Some(end_reason), Some(&end_message))).await;

    Ok(())
}

/// One line from the desktop capture helper's pipe, which carries its stdout
/// and stderr: a base64 JPEG frame, an error the script reported itself, or
/// anything else (a PowerShell error, for one).
#[derive(Debug, PartialEq)]
#[cfg_attr(not(windows), allow(dead_code))]
enum CaptureLine<'a> {
    Frame(&'a str),
    Error(&'a str),
    Other(&'a str),
}

#[cfg_attr(not(windows), allow(dead_code))]
fn classify_capture_line(line: &str) -> CaptureLine<'_> {
    let line = line.trim_start_matches('\u{feff}').trim();
    if let Some(msg) = line.strip_prefix("ERR:") {
        return CaptureLine::Error(msg.trim());
    }
    // A JPEG starts FF D8 FF, which is "/9j/" in base64.
    if line.starts_with("/9j/") && line.bytes().all(|b| b.is_ascii_alphanumeric() || matches!(b, b'+' | b'/' | b'=')) {
        return CaptureLine::Frame(line);
    }
    CaptureLine::Other(line)
}

/// Test hook: whether the relay would treat a capture line as a video frame.
/// Used by `screen_capture`'s tests to prove its encoder output is accepted.
#[cfg(test)]
pub(crate) fn line_is_frame(line: &str) -> bool {
    matches!(classify_capture_line(line), CaptureLine::Frame(_))
}

/// Keep the last few non-frame lines the capture printed, each shortened.
#[cfg_attr(not(windows), allow(dead_code))]
fn remember_capture_output(output: &mut Vec<String>, text: &str) {
    const KEEP: usize = 6;
    const MAX_CHARS: usize = 200;
    if output.len() == KEEP {
        output.remove(0);
    }
    output.push(text.chars().take(MAX_CHARS).collect());
}

/// Why the capture process stopped, for the admin's viewer and the agent log.
#[cfg_attr(not(windows), allow(dead_code))]
fn capture_exit_detail(exit_code: Option<u32>, output: &[String]) -> String {
    let mut detail = match exit_code {
        Some(code) => format!("exit code 0x{code:08X}"),
        None => "exit code unknown".to_string(),
    };
    if output.is_empty() {
        detail.push_str(", no output");
    } else {
        detail.push_str(": ");
        detail.push_str(&output.join(" | "));
    }
    detail
}

/// POST consent decision to the backend audit endpoint (T-74-19), as this
/// agent. It used to go to a made-up /consent-decision path with no token, so
/// no decision was ever recorded and accepted sessions never became active.
#[cfg_attr(not(windows), allow(dead_code))]
async fn post_consent_decision(
    tunnel_url: &str,
    auth: &TunnelAuth,
    session_id: &str,
    decision: &crate::consent_ui::ConsentDecision,
    requester: &Requester,
) {
    let Some(http_url) = consent_url(tunnel_url, session_id) else {
        log::warn!("Failed to POST consent decision: no platform address in {tunnel_url}");
        return;
    };

    let body = serde_json::json!({
        "session_id": session_id,
        "decision": match decision {
            crate::consent_ui::ConsentDecision::Accept => "accept",
            crate::consent_ui::ConsentDecision::Decline => "decline",
            crate::consent_ui::ConsentDecision::Timeout => "timeout",
        },
        "requester_name": &requester.name,
        "requester_email": &requester.email,
        "tenant": &requester.tenant,
        "timestamp": chrono::Utc::now().to_rfc3339(),
    });

    let client = match crate::tls::platform_client().build() {
        Ok(c) => c,
        Err(e) => {
            log::warn!("Failed to POST consent decision: {e}");
            return;
        }
    };
    match client
        .post(&http_url)
        .bearer_auth(&auth.agent_token)
        .json(&body)
        .timeout(std::time::Duration::from_secs(5))
        .send()
        .await
    {
        Ok(r) if !r.status().is_success() => log::warn!("Consent decision refused: {}", r.status()),
        Ok(_) => {}
        Err(e) => log::warn!("Failed to POST consent decision: {e}"),
    }
}

#[cfg(not(windows))]
async fn desktop_stream_run(
    _session_id: &str,
    url: &str,
    auth: &TunnelAuth,
    control: bool,
    _requester: &Requester,
) -> Result<(), Box<dyn std::error::Error + Send + Sync>> {
    use futures_util::{SinkExt, StreamExt};
    use tokio_tungstenite::tungstenite::Message;

    // Open the tunnel just long enough to tell the viewer why no frames are
    // coming, instead of leaving it connected-but-silent forever (the
    // previous behavior: returning Err before ever calling connect_async
    // meant the viewer had zero signal that streaming would never start).
    let ws_stream = connect_tunnel(url, auth).await?;
    let (mut ws_write, _) = ws_stream.split();
    // Control mode must say WHY it cannot proceed, so the browser can show a
    // real terminal state (T-74-04) rather than an endless spinner. View mode
    // keeps its original message untouched.
    let body = if control {
        r#"{"type":"error","reason":"unsupported_platform","message":"Interactive control is only supported on Windows agents"}"#
    } else {
        r#"{"type":"error","message":"Desktop streaming is only supported on Windows agents"}"#
    };
    let _ = ws_write.send(Message::Text(body.into())).await;
    Err("desktop streaming is only supported on Windows".into())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn tunnel_goes_to_the_enrolled_platform_not_the_instruction_url() {
        assert_eq!(
            tunnel_url("https://57.154.210.55/", "76f428aa-08b7-4991-b813-33fa9f5dc77a").as_deref(),
            Some("wss://57.154.210.55/api/tunnel/76f428aa-08b7-4991-b813-33fa9f5dc77a/agent")
        );
        assert_eq!(
            tunnel_url("http://10.0.0.5:5000", "abc-1").as_deref(),
            Some("ws://10.0.0.5:5000/api/tunnel/abc-1/agent")
        );
        // A session id cannot steer the agent to another path or host.
        assert_eq!(tunnel_url("https://p.example", "../../x"), None);
        assert_eq!(tunnel_url("https://p.example", "a/b?c"), None);
        assert_eq!(tunnel_url("https://p.example", ""), None);
        assert_eq!(tunnel_url("ftp://p.example", "abc"), None);
    }

    #[test]
    fn consent_is_reported_to_the_session_consent_route() {
        let t = tunnel_url("https://p.example", "s-1").unwrap();
        assert_eq!(consent_url(&t, "s-1").as_deref(), Some("https://p.example/api/remote/session/s-1/consent"));
        let t = tunnel_url("http://10.0.0.5:5000", "s-2").unwrap();
        assert_eq!(consent_url(&t, "s-2").as_deref(), Some("http://10.0.0.5:5000/api/remote/session/s-2/consent"));
    }

    #[test]
    fn tunnel_request_carries_the_agent_token_and_the_legacy_key() {
        let auth = TunnelAuth { agent_token: "tok".into(), tenant_key: "reg".into() };
        let req = tunnel_request("wss://p.example/api/tunnel/s/agent", &auth).unwrap();
        assert_eq!(req.headers()["Authorization"], "Bearer tok");
        assert_eq!(req.headers()["X-Tenant-Key"], "reg");
        let none = TunnelAuth { agent_token: String::new(), tenant_key: String::new() };
        let req = tunnel_request("wss://p.example/api/tunnel/s/agent", &none).unwrap();
        assert!(req.headers().get("Authorization").is_none() && req.headers().get("X-Tenant-Key").is_none());
    }
    #[test]
    fn capture_lines_are_told_apart() {
        assert_eq!(classify_capture_line("/9j/4AAQSkZJRg+/="), CaptureLine::Frame("/9j/4AAQSkZJRg+/="));
        // A UTF-8 BOM before the first frame is not part of the image.
        assert_eq!(classify_capture_line("\u{feff}/9j/4AAQ"), CaptureLine::Frame("/9j/4AAQ"));
        assert_eq!(classify_capture_line("ERR: The handle is invalid"), CaptureLine::Error("The handle is invalid"));
        // PowerShell's own errors share the pipe and must not reach the viewer as frames.
        for line in [
            "Add-Type : Cannot add type. Definition of new types is not supported in this language mode.",
            "At line:1 char:1",
            "/9j/ but \"quoted\" text",
            "#< CLIXML",
        ] {
            assert_eq!(classify_capture_line(line), CaptureLine::Other(line));
        }
    }

    #[test]
    fn capture_output_keeps_the_last_lines_shortened() {
        let mut out = Vec::new();
        for i in 0..8 {
            remember_capture_output(&mut out, &format!("line {i}"));
        }
        assert_eq!(out, ["line 2", "line 3", "line 4", "line 5", "line 6", "line 7"]);
        remember_capture_output(&mut out, &"x".repeat(500));
        assert_eq!(out.last().unwrap().chars().count(), 200);
    }

    #[test]
    fn capture_exit_detail_names_the_code_and_output() {
        assert_eq!(capture_exit_detail(Some(1), &[]), "exit code 0x00000001, no output");
        assert_eq!(capture_exit_detail(None, &[]), "exit code unknown, no output");
        let out = vec!["At line:1 char:1".to_string(), r"C:\Users\x is blocked".to_string()];
        assert_eq!(
            capture_exit_detail(Some(0xC000_0142), &out),
            r"exit code 0xC0000142: At line:1 char:1 | C:\Users\x is blocked"
        );
    }
}

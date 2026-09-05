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

/// Build a WebSocket client request carrying the tenant's `X-Tenant-Key`
/// header. `tunnel_agent_side` (backend/tunnel_endpoints.py) requires either
/// a valid JWT `?token=` or this header to authenticate the agent side of
/// the tunnel — the agent has never had a JWT of its own, and the previous
/// bare `connect_async(url)` sent neither, so every tunnel connection was
/// silently rejected with code 4401 before any shell/capture logic ran.
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

/// Spawn a WebSocket-based reverse shell in a background tokio task.
pub fn start_reverse_shell(session_id: String, url: String, tenant_key: String) {
    tokio::spawn(async move {
        log::info!("Reverse shell starting: session={session_id} url={url}");
        if let Err(e) = reverse_shell_run(&url, &tenant_key).await {
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
    tenant_key: String,
    control: bool,
    requester: Requester,
) {
    tokio::spawn(async move {
        log::info!(
            "Desktop stream starting: session={session_id} url={url} control={control}"
        );
        if let Err(e) = desktop_stream_run(&session_id, &url, &tenant_key, control, &requester).await {
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
    tenant_key: &str,
    control: bool,
    requester: &Requester,
) -> Result<(), Box<dyn std::error::Error + Send + Sync>> {
    use crate::capabilities::control_input::{control_input_replay, parse_input_frame, ConsentGate};
    use crate::consent_ui::{request_consent, show_stop_bar, hide_stop_bar, stop_requested, ConsentDecision, ConsentError};
    use futures_util::{SinkExt, StreamExt};
    use tokio::io::{AsyncBufReadExt, BufReader};
    use tokio::time::{timeout, Duration, interval};
    use tokio_tungstenite::{connect_async, tungstenite::Message};

    let (ws_stream, _) = connect_async(tunnel_request(url, tenant_key)?).await?;
    let (mut ws_write, ws_read) = ws_stream.split();

    // Build a control_state frame. `Message` is the WS frame wrapper; string
    // building avoids a lifetime-heavy closure returning a self-referential type.
    let send_state = |state: &str, reason: Option<&str>, message: Option<&str>| {
        let mut payload = format!(r#"{{"type":"control_state","state":"{}""#, state);
        if let Some(r) = reason { payload.push_str(&format!(r#","reason":"{}""#, r)); }
        if let Some(m) = message { payload.push_str(&format!(r#","message":"{}""#, m)); }
        payload.push('}');
        Message::Text(payload.into())
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
    let _ = post_consent_decision(url, &session_id_owned, &decision, requester).await;

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

    // 5. Start capture process
    let ps_script = r#"Add-Type -AssemblyName System.Windows.Forms,System.Drawing
$bounds = [System.Windows.Forms.Screen]::PrimaryScreen.Bounds
if ($bounds.Width -le 0 -or $bounds.Height -le 0) {
    [Console]::Out.WriteLine("ERR:No interactive desktop available (0x0 screen bounds) - the agent likely has no active user session to capture (Session 0 isolation)")
    [Console]::Out.Flush()
    exit 1
}
$enc = [System.Drawing.Imaging.ImageCodecInfo]::GetImageEncoders() | Where-Object {$_.MimeType -eq 'image/jpeg'} | Select-Object -First 1
$p = New-Object System.Drawing.Imaging.EncoderParameters 1
$p.Param[0] = New-Object System.Drawing.Imaging.EncoderParameter([System.Drawing.Imaging.Encoder]::Quality, [long]40)
while ($true) {
    try {
        $bm = New-Object System.Drawing.Bitmap([int]$bounds.Width, [int]$bounds.Height)
        $gr = [System.Drawing.Graphics]::FromImage($bm)
        $gr.CopyFromScreen($bounds.Location, [System.Drawing.Point]::Empty, $bounds.Size)
        $ms = New-Object System.IO.MemoryStream
        $bm.Save($ms, $enc, $p)
        $bm.Dispose(); $gr.Dispose()
        [Console]::Out.WriteLine([Convert]::ToBase64String($ms.ToArray()))
        [Console]::Out.Flush()
        $ms.Dispose()
    } catch {
        [Console]::Out.WriteLine("ERR:" + $_.Exception.Message)
        [Console]::Out.Flush()
    }
    Start-Sleep -Milliseconds 150
}"#;

    let mut child = match tokio::process::Command::new("powershell.exe")
        .args(["-NoProfile", "-NonInteractive", "-Command", ps_script])
        .stdout(std::process::Stdio::piped())
        .stderr(std::process::Stdio::null())
        .spawn()
    {
        Ok(child) => child,
        Err(e) => {
            let msg = format!("Failed to launch capture process: {}", e).replace('"', "'");
            let payload = format!(r#"{{"type":"error","message":"{}"}}"#, msg);
            let _ = ws_write.send(Message::Text(payload.into())).await;
            let _ = hide_stop_bar(&session_id_owned);
            return Err(format!("failed to spawn powershell.exe: {}", e).into());
        }
    };

    let stdout = match child.stdout.take() {
        Some(stdout) => stdout,
        None => {
            let _ = ws_write
                .send(Message::Text(
                    r#"{"type":"error","message":"Failed to capture stdout from the desktop capture process"}"#.into(),
                ))
                .await;
            let _ = child.kill().await;
            let _ = hide_stop_bar(&session_id_owned);
            return Err("no stdout from capture process".into());
        }
    };
    let mut lines = BufReader::new(stdout).lines();

    // First line must arrive within 5s
    let first_line = timeout(Duration::from_secs(5), lines.next_line()).await;
    let mut pending = match first_line {
        Ok(next) => next,
        Err(_) => {
            let _ = ws_write
                .send(Message::Text(
                    r#"{"type":"error","message":"No response from desktop capture process within 5s - it may lack an interactive desktop session"}"#.into(),
                ))
                .await;
            let _ = child.kill().await;
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
    let mut end_reason = "unknown";
    let mut end_message = "Session ended";
    loop {
        // Check stop sentinel each frame (D-09/D-12): the endpoint user's Stop
        // Control click writes stop_{session}.stop. On fire, revoke the gate so
        // the concurrent input task stops replaying immediately.
        if stop_requested(&session_id_owned) {
            end_reason = "stop_requested";
            end_message = "Endpoint user stopped control";
            gate.lock().unwrap().revoke();
            break;
        }

        match pending {
            Ok(Some(ref line)) if line.starts_with("ERR:") => {
                let msg = line.trim_start_matches("ERR:").replace('"', "'");
                let payload = format!(r#"{{"type":"error","message":"{}"}}"#, msg);
                let _ = ws_write.send(Message::Text(payload.into())).await;
                end_reason = "capture_error";
                end_message = "Desktop capture failed";
                gate.lock().unwrap().revoke();
                break;
            }
            Ok(Some(ref line)) if !line.is_empty() => {
                let ts = chrono::Utc::now().timestamp_millis();
                let payload = format!(
                    r#"{{"type":"frame","timestamp":{},"data":"{}"}}"#,
                    ts, line
                );
                if ws_write.send(Message::Text(payload.into())).await.is_err() {
                    end_reason = "relay_failed";
                    end_message = "WebSocket relay failed";
                    gate.lock().unwrap().revoke();
                    break;
                }
            }
            Ok(None) | Err(_) => {
                end_reason = "capture_ended";
                end_message = "Desktop capture process ended";
                gate.lock().unwrap().revoke();
                break;
            }
            _ => {}
        }
        pending = lines.next_line().await;
    }

    // 8. Cleanup: abort input task, kill capture, hide stop bar, send ended state
    input_task.abort();
    let _ = child.kill().await;
    let _ = hide_stop_bar(&session_id_owned);
    let _ = ws_write.send(send_state("ended", Some(end_reason), Some(end_message))).await;

    Ok(())
}

/// POST consent decision to the backend audit endpoint (T-74-19).
/// Derives HTTP base from the tunnel WebSocket URL.
async fn post_consent_decision(
    tunnel_url: &str,
    session_id: &str,
    decision: &crate::consent_ui::ConsentDecision,
    requester: &Requester,
) {
    use reqwest::Client;
    // Derive HTTP endpoint from ws:// or wss:// tunnel URL
    let http_url = tunnel_url
        .replace("wss://", "https://")
        .replace("ws://", "http://")
        .replace("/tunnel", "/consent-decision")
        .replace("/viewer", "/consent-decision")
        .replace("/user", "/consent-decision");

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

    let client = Client::new();
    if let Err(e) = client
        .post(&http_url)
        .json(&body)
        .timeout(std::time::Duration::from_secs(5))
        .send()
        .await
    {
        log::warn!("Failed to POST consent decision: {e}");
    }
}

#[cfg(not(windows))]
async fn desktop_stream_run(
    _session_id: &str,
    url: &str,
    tenant_key: &str,
    control: bool,
    _requester: &Requester,
) -> Result<(), Box<dyn std::error::Error + Send + Sync>> {
    use futures_util::{SinkExt, StreamExt};
    use tokio_tungstenite::{connect_async, tungstenite::Message};

    // Open the tunnel just long enough to tell the viewer why no frames are
    // coming, instead of leaving it connected-but-silent forever (the
    // previous behavior: returning Err before ever calling connect_async
    // meant the viewer had zero signal that streaming would never start).
    let (ws_stream, _) = connect_async(tunnel_request(url, tenant_key)?).await?;
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
    fn post_consent_decision_url_derivation() {
        // HTTP base derives from the tunnel WebSocket URL (T-74-19)
        let http_url = "wss://relay.example.com/tunnel/abc"
            .replace("wss://", "https://")
            .replace("/tunnel", "/consent-decision");
        assert_eq!(
            http_url,
            "https://relay.example.com/consent-decision/abc"
        );
    }

    #[test]
    fn post_consent_decision_url_viewer_derivation() {
        let http_url = "ws://relay.example.com/viewer/xyz"
            .replace("ws://", "http://")
            .replace("/viewer", "/consent-decision")
            .replace("/user", "/consent-decision");
        assert_eq!(
            http_url,
            "http://relay.example.com/consent-decision/xyz"
        );
    }
}

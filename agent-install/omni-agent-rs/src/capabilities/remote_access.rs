use super::Capability;
use serde_json::{json, Value};
use sysinfo::System;

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
/// back to the agent (`parse_input_frame` → `control_input_replay`).
pub fn start_desktop_stream(session_id: String, url: String, tenant_key: String, control: bool) {
    tokio::spawn(async move {
        log::info!("Desktop stream starting: session={session_id} url={url} control={control}");
        if let Err(e) = desktop_stream_run(&url, &tenant_key, control).await {
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

/// One decoded interactive-control input frame (Phase 74 wire contract,
/// Option A): an `input` frame with a nested `kind`, normalized absolute
/// coordinates, and Windows virtual-key codes. Parsed at the boundary by
/// `parse_input_frame`; replayed by `control_input_replay` on Windows.
#[derive(Debug, PartialEq)]
pub enum InputEvent {
    MouseMove { x: f64, y: f64 },
    MouseButton { down: bool, button: u8 },
    Wheel { delta_x: i64, delta_y: i64 },
    Key { down: bool, vk: u8, extended: bool, unicode: Option<u16> },
}

const INPUT_KINDS: &[&str] = &["mousemove", "mousedown", "mouseup", "wheel", "keydown", "keyup"];

/// Parse and validate one browser→agent input frame. Rejects at the boundary:
/// any `kind` outside the enumerated set, `x`/`y` outside 0.0..=1.0 inclusive,
/// `vk` outside 0..=254, or a non-`input` `type` — returning `Err` with a
/// short reason rather than panicking or silently clamping into a
/// valid-looking event (T-74-04).
pub fn parse_input_frame(raw: &str) -> Result<InputEvent, String> {
    let value: Value = serde_json::from_str(raw).map_err(|e| format!("invalid JSON: {e}"))?;
    if value.get("type").and_then(|v| v.as_str()) != Some("input") {
        return Err("frame type is not 'input'".to_string());
    }
    let kind = value.get("kind").and_then(|v| v.as_str()).unwrap_or("");
    if !INPUT_KINDS.contains(&kind) {
        return Err(format!("unknown input kind: {kind}"));
    }

    let coord = |key: &str| -> Result<f64, String> {
        match value.get(key).and_then(|v| v.as_f64()) {
            Some(n) if (0.0..=1.0).contains(&n) => Ok(n),
            Some(n) => Err(format!("{key} {n} out of range 0.0..=1.0")),
            None => Err(format!("missing or non-numeric {key}")),
        }
    };
    let int = |key: &str| -> Result<Option<i64>, String> {
        Ok(value.get(key).and_then(|v| v.as_i64()))
    };
    let vk = |key: &str| -> Result<Option<u8>, String> {
        match int(key)? {
            Some(n) if (0..=254).contains(&n) => Ok(Some(n as u8)),
            Some(n) => Err(format!("{key} {n} out of range 0..=254")),
            None => Ok(None),
        }
    };

    Ok(match kind {
        "mousemove" => InputEvent::MouseMove { x: coord("x")?, y: coord("y")? },
        "mousedown" => InputEvent::MouseButton { down: true, button: vk("button")?.unwrap_or(0) },
        "mouseup" => InputEvent::MouseButton { down: false, button: vk("button")?.unwrap_or(0) },
        "wheel" => InputEvent::Wheel {
            delta_x: int("deltaX")?.unwrap_or(0),
            delta_y: int("deltaY")?.unwrap_or(0),
        },
        "keydown" => InputEvent::Key {
            down: true,
            vk: vk("vk")?.ok_or("missing vk")?,
            extended: matches!(value.get("extended"), Some(Value::Bool(true))),
            unicode: int("unicode")?.and_then(|n| u16::try_from(n).ok()),
        },
        "keyup" => InputEvent::Key {
            down: false,
            vk: vk("vk")?.ok_or("missing vk")?,
            extended: matches!(value.get("extended"), Some(Value::Bool(true))),
            unicode: int("unicode")?.and_then(|n| u16::try_from(n).ok()),
        },
        _ => unreachable!("kind validated above"),
    })
}

#[cfg(windows)]
fn control_input_replay(ev: &InputEvent) {
    use std::mem::size_of;
    use winapi::um::winuser::*;

    match ev {
        InputEvent::MouseMove { x, y } => {
            // winapi 0.3: INPUT has no Default impl and the union method is
            // `mi()` (not `mouse_mut`, which is Windows-rs style). `zeroed`
            // is the canonical init for a raw union that is fully written by
            // the assignment below.
            let mut input: INPUT = unsafe { std::mem::zeroed() };
            input.type_ = INPUT_MOUSE;
            // winapi 0.3: INPUT has a MOUSEINPUT as the first field of the
            // internal union. Form the pointer from the INPUT pointer itself
            // (avoids the `&mut -> *mut` reborrow error E0606) and write the
            // mouse event fields through that mutable view. The shared bytes
            // are immediately reborrowed as `&mut INPUT` for SendInput.
            let mi: &mut MOUSEINPUT = unsafe {
                &mut *(&mut input as *mut INPUT as *mut MOUSEINPUT)
            };
            mi.dwFlags = MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE | MOUSEEVENTF_VIRTUALDESK;
            mi.dx = (x * 65535.0).round() as i32;
            mi.dy = (y * 65535.0).round() as i32;
            let sent = unsafe { SendInput(1, &mut input, size_of::<INPUT>() as i32) };
            if sent == 0 {
                log::warn!("SendInput failed for mousemove ({x}, {y}): error {}", unsafe {
                    winapi::um::errhandlingapi::GetLastError()
                });
            }
        }
        // Tracer slice: only mousemove is replayed. Every other accepted
        // variant is dropped for now; Plan 03 (consent-gated full input) and
        // Plan 05 (full browser keymap) fill these in.
        _ => log::debug!("control_input_replay: dropping unsupported variant {ev:?}"),
    }
}

// Windows: long-lived PowerShell process captures JPEG frames and emits base64 lines
#[cfg(windows)]
async fn desktop_stream_run(
    url: &str,
    tenant_key: &str,
    control: bool,
) -> Result<(), Box<dyn std::error::Error + Send + Sync>> {
    use futures_util::{SinkExt, StreamExt};
    use tokio::io::{AsyncBufReadExt, BufReader};
    use tokio::time::{timeout, Duration};
    use tokio_tungstenite::{connect_async, tungstenite::Message};

    let (ws_stream, _) = connect_async(tunnel_request(url, tenant_key)?).await?;
    let (mut ws_write, mut ws_read) = ws_stream.split();

    // Phase 74 control path: spawn a writer-concurrent reader over the same
    // tunnel the frames flow out on. The `/user` → `/agent` relay is
    // bidirectional (T-74-01), so browser `input` frames arrive here and are
    // replayed via SendInput. View-only mode never spawns this — no input
    // frames are ever sent on a `/viewer` connection.
    if control {
        tokio::spawn(async move {
            while let Some(Ok(msg)) = ws_read.next().await {
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
        });
    }

    // Single PS process that emits one base64 JPEG per line at ~7 FPS. The
    // capture branch reports failures as "ERR:<message>" instead of the
    // previous bare `catch {}` — a service running as LocalSystem (Session 0)
    // has no interactive desktop to capture, and CopyFromScreen either
    // throws or silently yields a 0x0 bitmap there; either way the operator
    // needs a real signal instead of an infinite "waiting for stream" spinner.
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
            return Err("no stdout from capture process".into());
        }
    };
    let mut lines = BufReader::new(stdout).lines();

    // First line must arrive within 5s — if PowerShell never produces output
    // at all (e.g. it fails before its own try/catch can run), the viewer
    // would otherwise wait forever with zero signal.
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
            return Err("desktop capture timed out with no output".into());
        }
    };

    loop {
        match pending {
            Ok(Some(ref line)) if line.starts_with("ERR:") => {
                let msg = line.trim_start_matches("ERR:").replace('"', "'");
                let payload = format!(r#"{{"type":"error","message":"{}"}}"#, msg);
                let _ = ws_write.send(Message::Text(payload.into())).await;
                break;
            }
            Ok(Some(ref line)) if !line.is_empty() => {
                let ts = chrono::Utc::now().timestamp_millis();
                let payload = format!(
                    r#"{{"type":"frame","timestamp":{},"data":"{}"}}"#,
                    ts, line
                );
                if ws_write.send(Message::Text(payload.into())).await.is_err() { break; }
            }
            Ok(None) | Err(_) => break,
            _ => {}
        }
        pending = lines.next_line().await;
    }

    let _ = child.kill().await;
    Ok(())
}

#[cfg(not(windows))]
async fn desktop_stream_run(
    url: &str,
    tenant_key: &str,
    control: bool,
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
    fn parse_input_frame_rejects_unknown_kind() {
        let raw = r#"{"type":"input","kind":"teleport","x":0.5,"y":0.5}"#;
        assert!(parse_input_frame(raw).is_err());
    }

    #[test]
    fn parse_input_frame_rejects_out_of_range_coords() {
        let raw = r#"{"type":"input","kind":"mousemove","x":1.5,"y":0.5}"#;
        assert!(parse_input_frame(raw).is_err());
    }

    #[test]
    fn parse_input_frame_rejects_non_input_type() {
        let raw = r#"{"type":"frame","kind":"mousemove","x":0.5,"y":0.5}"#;
        assert!(parse_input_frame(raw).is_err());
    }

    #[test]
    fn parse_input_frame_accepts_valid_mousemove() {
        let raw = r#"{"type":"input","kind":"mousemove","x":0.25,"y":0.75}"#;
        assert_eq!(
            parse_input_frame(raw).unwrap(),
            InputEvent::MouseMove { x: 0.25, y: 0.75 }
        );
    }

    #[test]
    fn parse_input_frame_rejects_bad_vk() {
        let raw = r#"{"type":"input","kind":"keydown","vk":300}"#;
        assert!(parse_input_frame(raw).is_err());
    }
}

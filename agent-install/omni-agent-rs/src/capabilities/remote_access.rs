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
pub fn start_desktop_stream(session_id: String, url: String, tenant_key: String) {
    tokio::spawn(async move {
        log::info!("Desktop stream starting: session={session_id} url={url}");
        if let Err(e) = desktop_stream_run(&url, &tenant_key).await {
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

// Windows: long-lived PowerShell process captures JPEG frames and emits base64 lines
#[cfg(windows)]
async fn desktop_stream_run(url: &str, tenant_key: &str) -> Result<(), Box<dyn std::error::Error + Send + Sync>> {
    use futures_util::{SinkExt, StreamExt};
    use tokio::io::{AsyncBufReadExt, BufReader};
    use tokio::time::{timeout, Duration};
    use tokio_tungstenite::{connect_async, tungstenite::Message};

    let (ws_stream, _) = connect_async(tunnel_request(url, tenant_key)?).await?;
    let (mut ws_write, _) = ws_stream.split();

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

    let mut child = tokio::process::Command::new("powershell.exe")
        .args(["-NoProfile", "-NonInteractive", "-Command", ps_script])
        .stdout(std::process::Stdio::piped())
        .stderr(std::process::Stdio::null())
        .spawn()?;

    let stdout = child.stdout.take().ok_or("no stdout")?;
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
async fn desktop_stream_run(url: &str, tenant_key: &str) -> Result<(), Box<dyn std::error::Error + Send + Sync>> {
    use futures_util::{SinkExt, StreamExt};
    use tokio_tungstenite::{connect_async, tungstenite::Message};

    // Open the tunnel just long enough to tell the viewer why no frames are
    // coming, instead of leaving it connected-but-silent forever (the
    // previous behavior: returning Err before ever calling connect_async
    // meant the viewer had zero signal that streaming would never start).
    let (ws_stream, _) = connect_async(tunnel_request(url, tenant_key)?).await?;
    let (mut ws_write, _) = ws_stream.split();
    let _ = ws_write
        .send(Message::Text(
            r#"{"type":"error","message":"Desktop streaming is only supported on Windows agents"}"#.into(),
        ))
        .await;
    Err("desktop streaming is only supported on Windows".into())
}

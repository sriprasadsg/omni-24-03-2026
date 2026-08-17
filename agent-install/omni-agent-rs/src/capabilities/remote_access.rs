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

/// Spawn a WebSocket-based reverse shell in a background tokio task.
pub fn start_reverse_shell(session_id: String, url: String) {
    tokio::spawn(async move {
        log::info!("Reverse shell starting: session={session_id} url={url}");
        if let Err(e) = reverse_shell_run(&url).await {
            log::error!("Reverse shell error: {e}");
        }
        log::info!("Reverse shell ended: session={session_id}");
    });
}

/// Spawn a desktop streaming task that sends JPEG frames over WebSocket.
pub fn start_desktop_stream(session_id: String, url: String) {
    tokio::spawn(async move {
        log::info!("Desktop stream starting: session={session_id} url={url}");
        if let Err(e) = desktop_stream_run(&url).await {
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

async fn reverse_shell_run(url: &str) -> Result<(), Box<dyn std::error::Error + Send + Sync>> {
    use futures_util::{SinkExt, StreamExt};
    use tokio::io::{AsyncReadExt, AsyncWriteExt};
    use tokio::sync::mpsc;
    use tokio_tungstenite::{connect_async, tungstenite::Message};

    let (ws_stream, _) = connect_async(url).await?;
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
async fn desktop_stream_run(url: &str) -> Result<(), Box<dyn std::error::Error + Send + Sync>> {
    use futures_util::{SinkExt, StreamExt};
    use tokio::io::{AsyncBufReadExt, BufReader};
    use tokio_tungstenite::{connect_async, tungstenite::Message};

    let (ws_stream, _) = connect_async(url).await?;
    let (mut ws_write, _) = ws_stream.split();

    // Single PS process that emits one base64 JPEG per line at ~7 FPS
    let ps_script = r#"Add-Type -AssemblyName System.Windows.Forms,System.Drawing
$bounds = [System.Windows.Forms.Screen]::PrimaryScreen.Bounds
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
    } catch {}
    Start-Sleep -Milliseconds 150
}"#;

    let mut child = tokio::process::Command::new("powershell.exe")
        .args(["-NoProfile", "-NonInteractive", "-Command", ps_script])
        .stdout(std::process::Stdio::piped())
        .stderr(std::process::Stdio::null())
        .spawn()?;

    let stdout = child.stdout.take().ok_or("no stdout")?;
    let mut lines = BufReader::new(stdout).lines();

    loop {
        match lines.next_line().await {
            Ok(Some(line)) if !line.is_empty() => {
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
    }

    let _ = child.kill().await;
    Ok(())
}

#[cfg(not(windows))]
async fn desktop_stream_run(_url: &str) -> Result<(), Box<dyn std::error::Error + Send + Sync>> {
    Err("desktop streaming is only supported on Windows".into())
}

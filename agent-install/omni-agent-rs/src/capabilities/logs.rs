use super::Capability;
use serde_json::{json, Value};
use std::process::Command;
use sysinfo::System;

pub struct LogsCapability;

impl Capability for LogsCapability {
    fn id(&self) -> &'static str { "log_collection" }
    fn name(&self) -> &'static str { "Log Collection" }

    fn collect(&self, _sys: &System) -> Value {
        let events = collect_events();
        let error_count = events
            .iter()
            .filter(|e| e["level"].as_str() == Some("Error"))
            .count();
        let warning_count = events
            .iter()
            .filter(|e| e["level"].as_str() == Some("Warning"))
            .count();

        json!({
            "recent_events": events,
            "error_count": error_count,
            "warning_count": warning_count,
            "timestamp": chrono::Utc::now().to_rfc3339(),
        })
    }
}

fn collect_events() -> Vec<Value> {
    let ps = r#"
$logs = @('System','Application') | ForEach-Object {
    try {
        Get-EventLog -LogName $_ -Newest 25 -ErrorAction SilentlyContinue |
        Select-Object Source,EventID,EntryType,TimeGenerated,Message
    } catch {}
}
$logs | Select-Object -First 50 | ForEach-Object {
    [PSCustomObject]@{
        source = $_.Source
        event_id = $_.EventID
        level = $_.EntryType.ToString()
        time = $_.TimeGenerated.ToString('o')
        message = ($_.Message -replace '\r?\n',' ').Substring(0, [Math]::Min(200, $_.Message.Length))
    }
} | ConvertTo-Json -Compress
"#;

    let output = Command::new("powershell")
        .args(["-NoProfile", "-NonInteractive", "-Command", ps])
        .output();

    let text = match output {
        Ok(o) => String::from_utf8_lossy(&o.stdout).trim().to_string(),
        Err(_) => return vec![],
    };

    if text.is_empty() {
        return vec![];
    }

    // PowerShell may return a single object (not array) for one result
    let parsed: serde_json::Value = match serde_json::from_str(&text) {
        Ok(v) => v,
        Err(_) => return vec![],
    };

    match parsed {
        Value::Array(arr) => arr,
        obj @ Value::Object(_) => vec![obj],
        _ => vec![],
    }
}

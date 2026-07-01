use super::Capability;
use serde_json::{json, Value};
use std::process::Command;
use sysinfo::System;

pub struct UebaCapability;

impl Capability for UebaCapability {
    fn id(&self) -> &'static str { "ueba" }
    fn name(&self) -> &'static str { "User and Entity Behavior Analytics" }

    fn collect(&self, _sys: &System) -> Value {
        let events = collect_login_events();
        let failed = events
            .iter()
            .filter(|e| e["type"].as_str() == Some("failure"))
            .count();
        let mut active_users: Vec<String> = events
            .iter()
            .filter(|e| e["type"].as_str() == Some("success"))
            .filter_map(|e| e["user"].as_str().map(|s| s.to_string()))
            .collect();
        active_users.sort();
        active_users.dedup();

        let anomalies: Vec<Value> = if failed > 5 {
            vec![json!({
                "type": "brute_force_attempt",
                "message": format!("{} failed logins detected", failed),
                "severity": "medium",
            })]
        } else {
            vec![]
        };

        json!({
            "login_events": events,
            "failed_logins": failed,
            "active_users": active_users,
            "anomalies": anomalies,
            "timestamp": chrono::Utc::now().to_rfc3339(),
        })
    }
}

fn collect_login_events() -> Vec<Value> {
    // EventID 4624 = successful logon, 4625 = failed logon
    let ps = r#"
$events = Get-WinEvent -FilterHashtable @{LogName='Security';Id=4624,4625} -MaxEvents 20 -ErrorAction SilentlyContinue
$events | ForEach-Object {
    $xml = [xml]$_.ToXml()
    $data = @{}
    $xml.Event.EventData.Data | ForEach-Object { $data[$_.Name] = $_.'#text' }
    [PSCustomObject]@{
        type      = if ($_.Id -eq 4624) { 'success' } else { 'failure' }
        user      = $data['TargetUserName']
        domain    = $data['TargetDomainName']
        logon_type = $data['LogonType']
        ip        = $data['IpAddress']
        time      = $_.TimeCreated.ToString('o')
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

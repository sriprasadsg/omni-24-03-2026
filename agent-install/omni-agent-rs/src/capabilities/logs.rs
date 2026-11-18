use super::Capability;
use serde_json::{json, Value};
use std::process::Command;
use std::sync::Mutex;
use std::time::{Duration, Instant};
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
            "security_events": security_events(),
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

    match output {
        Ok(o) => parse_array(&String::from_utf8_lossy(&o.stdout)),
        Err(_) => vec![],
    }
}

/// PowerShell's JSON as a list: it prints a single object, not an array, for one result.
fn parse_array(text: &str) -> Vec<Value> {
    match serde_json::from_str(text.trim()) {
        Ok(Value::Array(arr)) => arr,
        Ok(obj @ Value::Object(_)) => vec![obj],
        _ => vec![],
    }
}

// ── Security log ────────────────────────────────────────────────────────────
// The events the platform's SIEM rules read: 4625 failed sign-in, 4740 lockout, 4720 account created, 4728/4732/
// 4756 member added to a group, 1102 Security log cleared, and 7045 service installed (System log). 4624, every
// successful sign-in, is left out: it is most of the Security log and no rule uses it. Each event carries its
// record number and its event data fields, not the message text (a 4625's account and address sit past the first
// 200 characters). It runs in its own PowerShell, so a failure here leaves the System/Application events alone.

const SECURITY_IDS: &str = "4625,4720,4728,4732,4740,4756,1102";
const SECURITY_EVERY: Duration = Duration::from_secs(120);
const OVERLAP_SECS: u64 = 300;
const FIRST_WINDOW_SECS: u64 = 3600;
const MAX_WINDOW_SECS: u64 = 86_400;

const SECURITY_SCRIPT: &str = r#"
$since = (Get-Date).AddSeconds(-__WINDOW__)
$keep = @('TargetUserName','TargetDomainName','TargetSid','SubjectUserName','IpAddress','LogonType','WorkstationName','MemberName','MemberSid','ServiceName','ImagePath','AccountName','Status','SubStatus')
$out = @()
foreach ($f in @(@{ LogName = 'Security'; Id = @(__IDS__); StartTime = $since }, @{ LogName = 'System'; Id = 7045; StartTime = $since })) {
    try {
        $out += @(Get-WinEvent -FilterHashtable $f -MaxEvents 300 -ErrorAction Stop | ForEach-Object {
            $x = [xml]$_.ToXml()
            $d = @{}
            foreach ($n in @($x.Event.EventData.Data)) { if ($n -and $n.Name -and ($keep -contains $n.Name)) { $d[$n.Name] = [string]$n.InnerText } }
            if ($x.Event.UserData) { foreach ($n in @($x.Event.UserData.FirstChild.ChildNodes)) { if ($keep -contains $n.LocalName) { $d[$n.LocalName] = [string]$n.InnerText } } }
            [PSCustomObject]@{ log = $_.LogName; source = $_.ProviderName; event_id = $_.Id; record_id = $_.RecordId; time = $_.TimeCreated.ToUniversalTime().ToString('o'); data = $d }
        })
    } catch {}
}
ConvertTo-Json -InputObject @($out) -Compress -Depth 4
"#;

struct SecurityState {
    last: Option<Instant>,
    events: Vec<Value>,
}

static SECURITY: Mutex<SecurityState> = Mutex::new(SecurityState { last: None, events: Vec::new() });

/// The Security events of the latest query. The log is read at most every two minutes, over the time since the
/// previous read plus five minutes, and the result is resent in between, so every heartbeat carries it and the
/// platform (which drops repeats by record number) misses none. The first read covers the last hour.
fn security_events() -> Vec<Value> {
    let mut state = SECURITY.lock().unwrap_or_else(|p| p.into_inner());
    let now = Instant::now();
    if let Some(window) = security_window(state.last, now) {
        state.events = query_security(window);
        state.last = Some(now);
    }
    state.events.clone()
}

/// Seconds to read back, or None while the previous read is recent enough to resend.
fn security_window(last: Option<Instant>, now: Instant) -> Option<u64> {
    match last {
        None => Some(FIRST_WINDOW_SECS),
        Some(t) if now.duration_since(t) < SECURITY_EVERY => None,
        Some(t) => Some((now.duration_since(t).as_secs() + OVERLAP_SECS).min(MAX_WINDOW_SECS)),
    }
}

#[cfg_attr(not(windows), allow(dead_code))]
fn security_script(window_secs: u64) -> String {
    SECURITY_SCRIPT.replace("__WINDOW__", &window_secs.to_string()).replace("__IDS__", SECURITY_IDS)
}

#[cfg(windows)]
fn query_security(window_secs: u64) -> Vec<Value> {
    Command::new("powershell")
        .args(["-NoProfile", "-NonInteractive", "-Command", &security_script(window_secs)])
        .output()
        .map(|o| parse_array(&String::from_utf8_lossy(&o.stdout)))
        .unwrap_or_default()
}

#[cfg(not(windows))]
fn query_security(_window_secs: u64) -> Vec<Value> {
    Vec::new()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn powershell_json_is_always_a_list() {
        assert_eq!(parse_array("[{\"event_id\":4625},{\"event_id\":1102}]").len(), 2);
        assert_eq!(parse_array(" {\"event_id\":4625}\r\n")[0]["event_id"], 4625);
        assert!(parse_array("").is_empty());
        assert!(parse_array("Get-WinEvent : No events were found").is_empty());
    }

    #[test]
    fn the_security_log_is_read_every_two_minutes_with_overlap() {
        let t0 = Instant::now();
        assert_eq!(security_window(None, t0), Some(FIRST_WINDOW_SECS));
        assert_eq!(security_window(Some(t0), t0 + Duration::from_secs(30)), None);
        assert_eq!(security_window(Some(t0), t0 + Duration::from_secs(150)), Some(150 + OVERLAP_SECS));
        assert_eq!(security_window(Some(t0), t0 + Duration::from_secs(200_000)), Some(MAX_WINDOW_SECS));
    }

    #[test]
    fn the_script_asks_for_the_events_the_rules_read() {
        let script = security_script(420);
        assert!(script.contains("AddSeconds(-420)"));
        assert!(script.contains("Id = @(4625,4720,4728,4732,4740,4756,1102)"));
        assert!(script.contains("Id = 7045"));
        assert!(!script.contains("__"));
        assert!(!script.contains("4624"));
    }
}

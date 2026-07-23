/*!
 * ETW event → `RawEvent` decoding.
 *
 * Phase 2 covers three manifest (user-mode) providers, consumed via a `UserTrace`:
 *   - Microsoft-Windows-Kernel-Process   (process start/stop)
 *   - Microsoft-Windows-Kernel-Network   (TCP connect/accept)
 *   - Microsoft-Windows-Kernel-Registry  (key create / value set)
 *
 * The `RawEvent` enum is the provider-agnostic boundary: the engine/correlator/upload
 * layers never touch ETW types, so later providers add a variant + a decoder here only.
 *
 * Field names follow each provider's manifest. Parsing is defensive (try_parse → None on
 * absence) so a schema difference across Windows versions degrades a field to empty
 * rather than crashing. Exact field/event-id coverage is validated on a Windows host.
 *
 * Windows-only: depends on ferrisetw ETW types.
 */
use std::net::IpAddr;

use ferrisetw::parser::Parser;
use ferrisetw::schema_locator::SchemaLocator;
use ferrisetw::EventRecord;
use serde_json::{json, Value};

// Manifest provider GUIDs.
pub const KERNEL_PROCESS_GUID: &str = "22fb2cd6-0e7b-422b-a0c7-2fad1fd0e716";
pub const KERNEL_NETWORK_GUID: &str = "7dd42a49-5329-4832-8dfd-43d979153a88";
pub const KERNEL_REGISTRY_GUID: &str = "70eb4f03-c1de-4f73-a051-33d13d5413bd";

/// A normalized host event ready for correlation + upload.
pub enum RawEvent {
    Process {
        kind: &'static str,
        pid: u32,
        ppid: Option<u32>,
        image: Option<String>,
        cmdline: Option<String>,
        ts_unix: i64,
    },
    Network {
        kind: &'static str,
        pid: u32,
        proto: &'static str,
        src: Option<String>,
        dst: Option<String>,
        ts_unix: i64,
    },
    Registry {
        kind: &'static str,
        pid: u32,
        key: Option<String>,
        value_name: Option<String>,
        ts_unix: i64,
    },
}

impl RawEvent {
    /// Owning process id — the correlator uses this to attach process lineage.
    pub fn pid(&self) -> u32 {
        match self {
            RawEvent::Process { pid, .. } => *pid,
            RawEvent::Network { pid, .. } => *pid,
            RawEvent::Registry { pid, .. } => *pid,
        }
    }

    pub fn to_json(&self) -> Value {
        match self {
            RawEvent::Process { kind, pid, ppid, image, cmdline, ts_unix } => json!({
                "kind": kind, "pid": pid, "ppid": ppid,
                "image": image, "cmdline": cmdline, "ts_unix": ts_unix,
            }),
            RawEvent::Network { kind, pid, proto, src, dst, ts_unix } => json!({
                "kind": kind, "pid": pid, "proto": proto,
                "src": src, "dst": dst, "ts_unix": ts_unix,
            }),
            RawEvent::Registry { kind, pid, key, value_name, ts_unix } => json!({
                "kind": kind, "pid": pid, "key": key,
                "value_name": value_name, "ts_unix": ts_unix,
            }),
        }
    }
}

fn ts(record: &EventRecord) -> i64 {
    record.timestamp().unix_timestamp()
}

/// Microsoft-Windows-Kernel-Process. Event ids: 1=ProcessStart, 2=ProcessStop.
pub fn decode_process(record: &EventRecord, schema_locator: &SchemaLocator) -> Option<RawEvent> {
    let kind = match record.event_id() {
        1 => "process_start",
        2 => "process_stop",
        _ => return None,
    };
    let schema = schema_locator.event_schema(record).ok()?;
    let parser = Parser::create(record, &schema);
    // Payload ProcessID is the subject process; header process_id() is the reporter.
    let pid = parser.try_parse::<u32>("ProcessID").unwrap_or_else(|_| record.process_id());
    Some(RawEvent::Process {
        kind,
        pid,
        ppid: parser.try_parse::<u32>("ParentProcessID").ok(),
        image: parser.try_parse::<String>("ImageName").ok(),
        cmdline: parser.try_parse::<String>("CommandLine").ok(),
        ts_unix: ts(record),
    })
}

/// Microsoft-Windows-Kernel-Network. Event ids: 12/28=TCP connect (v4/v6),
/// 15/31=TCP accept (v4/v6). Fields: saddr/sport/daddr/dport.
pub fn decode_network(record: &EventRecord, schema_locator: &SchemaLocator) -> Option<RawEvent> {
    let kind = match record.event_id() {
        12 | 28 => "net_connect",
        15 | 31 => "net_accept",
        _ => return None,
    };
    let schema = schema_locator.event_schema(record).ok()?;
    let parser = Parser::create(record, &schema);
    let endpoint = |addr: &str, port: &str| -> Option<String> {
        let ip = parser.try_parse::<IpAddr>(addr).ok()?;
        let p = parser.try_parse::<u16>(port).unwrap_or(0);
        Some(format!("{}:{}", ip, p))
    };
    Some(RawEvent::Network {
        kind,
        pid: record.process_id(),
        proto: "tcp",
        src: endpoint("saddr", "sport"),
        dst: endpoint("daddr", "dport"),
        ts_unix: ts(record),
    })
}

/// Microsoft-Windows-Kernel-Registry. Event ids: 1=CreateKey, 5=SetValueKey.
/// Full key-path resolution (KeyObject → name) needs a rundown table — a later phase;
/// here we surface the relative key name + value name when the manifest provides them.
pub fn decode_registry(record: &EventRecord, schema_locator: &SchemaLocator) -> Option<RawEvent> {
    let kind = match record.event_id() {
        1 => "reg_create_key",
        5 => "reg_set_value",
        _ => return None,
    };
    let schema = schema_locator.event_schema(record).ok()?;
    let parser = Parser::create(record, &schema);
    let key = parser
        .try_parse::<String>("KeyName")
        .or_else(|_| parser.try_parse::<String>("RelativeName"))
        .ok();
    Some(RawEvent::Registry {
        kind,
        pid: record.process_id(),
        key,
        value_name: parser.try_parse::<String>("ValueName").ok(),
        ts_unix: ts(record),
    })
}

/*!
 * ETW event → `RawEvent` decoding (Phase 1: Kernel-Process).
 *
 * Kept provider-agnostic at the `RawEvent` boundary so later phases (network, registry,
 * file, DNS) add decoders without touching the engine/correlator/upload layers.
 *
 * Windows-only: depends on ferrisetw ETW types.
 */
use ferrisetw::parser::Parser;
use ferrisetw::schema_locator::SchemaLocator;
use ferrisetw::EventRecord;
use serde_json::{json, Value};

/// A normalized host event ready for correlation + upload.
pub struct RawEvent {
    pub kind: &'static str,
    pub pid: u32,
    pub ppid: Option<u32>,
    pub image: Option<String>,
    pub cmdline: Option<String>,
    /// Event time as a Unix timestamp (seconds), from the ETW record.
    pub ts_unix: i64,
}

impl RawEvent {
    pub fn to_json(&self) -> Value {
        json!({
            "kind":    self.kind,
            "pid":     self.pid,
            "ppid":    self.ppid,
            "image":   self.image,
            "cmdline": self.cmdline,
            "ts_unix": self.ts_unix,
        })
    }
}

/// Decode a Kernel-Process event. Opcodes: 1=Start, 2=End, 3=DCStart, 4=DCEnd
/// (3/4 are rundown snapshots of already-running processes at session start).
/// Returns `None` for opcodes we don't model.
pub fn decode_process(record: &EventRecord, schema_locator: &SchemaLocator) -> Option<RawEvent> {
    let kind = match record.opcode() {
        1 | 3 => "process_start",
        2 | 4 => "process_stop",
        _ => return None,
    };

    let schema = schema_locator.event_schema(record).ok()?;
    let parser = Parser::create(record, &schema);

    // Field names come from the Process MOF schema. Parse defensively: fall back to the
    // record's own owning-pid if the payload field is absent on this Windows version.
    let pid = parser.try_parse::<u32>("ProcessId").unwrap_or_else(|_| record.process_id());
    let ppid = parser.try_parse::<u32>("ParentId").ok();
    let image = parser.try_parse::<String>("ImageFileName").ok();
    let cmdline = parser.try_parse::<String>("CommandLine").ok();

    Some(RawEvent {
        kind,
        pid,
        ppid,
        image,
        cmdline,
        ts_unix: record.timestamp().unix_timestamp(),
    })
}

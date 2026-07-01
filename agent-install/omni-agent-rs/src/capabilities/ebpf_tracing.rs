use super::Capability;
use serde_json::{json, Value};
use sysinfo::System;

pub struct EbpfTracingCapability;

impl Capability for EbpfTracingCapability {
    fn id(&self) -> &'static str { "ebpf_tracing" }
    fn name(&self) -> &'static str { "eBPF Tracing" }

    fn collect(&self, _sys: &System) -> Value {
        json!({
            "status": "not_supported",
            "platform": std::env::consts::OS,
            "reason": "eBPF is Linux-only; not supported on Windows",
            "timestamp": chrono::Utc::now().to_rfc3339(),
        })
    }
}

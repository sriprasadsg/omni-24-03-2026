/*!
 * Behavioural rule engine (ETW Phase 3).
 *
 * Stateless rules evaluated against enriched telemetry events (process lineage already
 * attached by the correlator). Each match produces a `Detection` carrying a severity and
 * MITRE technique. Rules are pure functions of one event's JSON, so adding a rule is a
 * single entry in `evaluate` — no engine changes.
 *
 * Design note: detections are *reported* to the backend, not auto-actioned on the host.
 * Automated response (kill/isolate on high severity) is deliberately left to the backend
 * playbook path to avoid a false positive killing a legitimate process locally.
 */
use serde_json::{json, Value};

/// Windows binaries commonly abused as living-off-the-land execution proxies.
const LOLBINS: &[&str] = &[
    "certutil.exe", "mshta.exe", "rundll32.exe", "regsvr32.exe", "bitsadmin.exe",
    "wmic.exe", "cscript.exe", "wscript.exe", "installutil.exe", "msbuild.exe",
    "regasm.exe", "regsvcs.exe", "hh.exe", "cmstp.exe",
];
const OFFICE: &[&str] = &["winword.exe", "excel.exe", "powerpnt.exe", "outlook.exe", "msaccess.exe"];
const SHELLS: &[&str] = &["cmd.exe", "powershell.exe", "pwsh.exe", "wscript.exe", "cscript.exe", "mshta.exe"];

pub struct Detection {
    pub rule: &'static str,
    pub severity: &'static str,
    pub mitre: &'static str,
    pub pid: Option<u64>,
    pub evidence: String,
}

impl Detection {
    pub fn to_json(&self) -> Value {
        json!({
            "rule": self.rule,
            "severity": self.severity,
            "mitre": self.mitre,
            "pid": self.pid,
            "evidence": self.evidence,
        })
    }
}

/// Lowercased final path component of a Windows path.
fn basename(path: &str) -> String {
    path.rsplit(['\\', '/']).next().unwrap_or(path).to_ascii_lowercase()
}

fn str_field<'a>(ev: &'a Value, key: &str) -> Option<&'a str> {
    ev.get(key).and_then(|v| v.as_str())
}

/// Evaluate every rule against one enriched event.
pub fn evaluate(ev: &Value) -> Vec<Detection> {
    let mut out = Vec::new();
    let kind = str_field(ev, "kind").unwrap_or("");
    let pid = ev.get("pid").and_then(|v| v.as_u64());

    match kind {
        "process_start" => {
            let image = basename(str_field(ev, "image").unwrap_or(""));
            let parent = basename(str_field(ev, "parent_image").unwrap_or(""));

            if LOLBINS.contains(&image.as_str()) {
                out.push(Detection {
                    rule: "lolbin_spawn",
                    severity: "high",
                    mitre: "T1218",
                    pid,
                    evidence: format!("LOLBin {} spawned (parent {})", image, parent),
                });
            }
            if OFFICE.contains(&parent.as_str()) && SHELLS.contains(&image.as_str()) {
                out.push(Detection {
                    rule: "office_spawns_shell",
                    severity: "high",
                    mitre: "T1566",
                    pid,
                    evidence: format!("{} spawned {}", parent, image),
                });
            }
            if parent == "lsass.exe" {
                out.push(Detection {
                    rule: "lsass_child_process",
                    severity: "critical",
                    mitre: "T1055",
                    pid,
                    evidence: format!("lsass.exe spawned {}", image),
                });
            }
        }
        "reg_set_value" => {
            let key = str_field(ev, "key").unwrap_or("").to_ascii_lowercase();
            if key.contains("currentversion\\run") {
                out.push(Detection {
                    rule: "run_key_persistence",
                    severity: "high",
                    mitre: "T1547.001",
                    pid,
                    evidence: format!(
                        "Run-key write: {} = {}",
                        str_field(ev, "key").unwrap_or(""),
                        str_field(ev, "value_name").unwrap_or(""),
                    ),
                });
            }
        }
        "dns_query" => {
            if let Some(q) = str_field(ev, "qname") {
                // Cheap tunnelling heuristic: an over-long qname or a very long single
                // label (high-entropy exfil channel). Stateful volume/entropy scoring is
                // a later enhancement.
                let longest_label = q.split('.').map(|l| l.len()).max().unwrap_or(0);
                if q.len() > 100 || longest_label > 50 {
                    out.push(Detection {
                        rule: "dns_tunneling_suspect",
                        severity: "medium",
                        mitre: "T1071.004",
                        pid,
                        evidence: format!("suspicious DNS query (len {}): {}", q.len(), q),
                    });
                }
            }
        }
        _ => {}
    }

    out
}

/*!
 * Option B — agent-side VirusTotal enrichment.
 *
 * When a `virustotal_api_key` is present in config, the agent looks up each
 * malware-scan hit's SHA256 directly against VirusTotal API v3 and annotates the
 * match with the verdict before reporting. This is the alternative to backend
 * server-side enrichment (Option A) — do not deploy both against the same key
 * unless you account for the doubled request volume.
 *
 * The public VirusTotal tier allows ~4 lookups/minute, so enrichment spends a
 * bounded budget per scan; excess hashes are marked "Deferred".
 */
use serde_json::{json, Value};

const VT_BASE: &str = "https://www.virustotal.com/api/v3";
const MAX_LOOKUPS_PER_SCAN: usize = 4;

/// Look up a single SHA256 on VirusTotal. Returns a verdict object mirroring the
/// backend's shape: `{verdict, malicious, suspicious, detectionRatio}`.
pub async fn lookup_hash(client: &reqwest::Client, api_key: &str, sha256: &str) -> Value {
    let url = format!("{}/files/{}", VT_BASE, sha256);
    let resp = client.get(&url).header("x-apikey", api_key).send().await;

    let resp = match resp {
        Ok(r) => r,
        Err(e) => return json!({"verdict": "Error", "error": e.to_string()}),
    };

    match resp.status().as_u16() {
        200 => {
            let body: Value = resp.json().await.unwrap_or(Value::Null);
            let stats = body.pointer("/data/attributes/last_analysis_stats").cloned().unwrap_or(json!({}));
            let g = |k: &str| stats.get(k).and_then(|v| v.as_u64()).unwrap_or(0);
            let (mal, susp, harmless, undet) = (g("malicious"), g("suspicious"), g("harmless"), g("undetected"));
            let total = mal + susp + harmless + undet;
            let verdict = if mal > 0 { "Malicious" } else if susp > 0 { "Suspicious" } else { "Harmless" };
            json!({
                "verdict": verdict,
                "malicious": mal,
                "suspicious": susp,
                "detectionRatio": format!("{}/{}", mal + susp, total),
            })
        }
        404 => json!({"verdict": "Unknown", "detectionRatio": "0/0",
                      "message": "Artifact not found in VirusTotal database"}),
        code => json!({"verdict": "Error", "error": format!("VirusTotal API returned {}", code)}),
    }
}

/// Enrich a mutable `matches` array (from `run_yara_scan`) in place, annotating each
/// hit that carries a non-empty `sha256` with `vt_verdict`, `vt_detection_ratio`,
/// and `vt_malicious`. Deduplicates hashes and respects the per-scan lookup budget.
pub async fn enrich_matches(client: &reqwest::Client, api_key: &str, matches: &mut Vec<Value>) {
    use std::collections::HashMap;
    let mut cache: HashMap<String, Value> = HashMap::new();
    let mut budget = MAX_LOOKUPS_PER_SCAN;

    for m in matches.iter_mut() {
        let sha = m.get("sha256").and_then(|v| v.as_str()).unwrap_or("").trim().to_lowercase();
        if sha.is_empty() { continue; }

        let verdict = if let Some(v) = cache.get(&sha) {
            v.clone()
        } else if budget == 0 {
            json!({"verdict": "Deferred", "message": "Lookup budget exhausted; backend may enrich"})
        } else {
            let v = lookup_hash(client, api_key, &sha).await;
            budget -= 1;
            cache.insert(sha.clone(), v.clone());
            v
        };

        if let Some(obj) = m.as_object_mut() {
            obj.insert("vt_verdict".into(), verdict.get("verdict").cloned().unwrap_or(Value::Null));
            obj.insert("vt_detection_ratio".into(), verdict.get("detectionRatio").cloned().unwrap_or(Value::Null));
            obj.insert("vt_malicious".into(), verdict.get("malicious").cloned().unwrap_or(json!(0)));
        }
    }
}

//! Native security scan engine (Phase 50, NSCAN-01/02).
//!
//! Offline file scanning + URL/IP/hash reputation, all against the locally
//! cached signed feed (feed_bundle) — no network at scan time.
//!
//! ENGINE NOTE (review/50-03 fallback): the full yara-x YARA engine was
//! rejected for the agent because it pulls wasmtime + cranelift (a JIT engine)
//! — unacceptable bloat/cross-compile risk for a lean cross-platform agent.
//! Instead, file scanning uses (1) the SHA256 hash-signature DB and (2)
//! aho-corasick literal byte-pattern matching over the string literals carried
//! in the feed's `yara_rules.source`. Full YARA-rule support is deferred to a
//! backlog item. This stays pure-Rust, air-gapped, and cross-compiles cleanly.

use crate::capabilities::feed_bundle;
use aho_corasick::AhoCorasick;
use serde_json::{json, Value};
use sha2::{Digest, Sha256};

/// Bound the fully-read scan size; larger files are hashed only.
const MAX_SCAN_BYTES: u64 = 64 * 1024 * 1024;

/// Scan a file: hash-signature lookup, then literal-pattern matching.
pub fn scan_file(path: &str) -> Value {
    let meta = match std::fs::metadata(path) {
        Ok(m) => m,
        Err(e) => return json!({"verdict": "error", "error": format!("stat: {e}"), "engine": "native"}),
    };

    // Hash the file (streamed) regardless of size.
    let sha256 = match hash_file(path) {
        Ok(h) => h,
        Err(e) => return json!({"verdict": "error", "error": format!("read: {e}"), "engine": "native"}),
    };

    // 1) hash-signature DB.
    let hv = feed_bundle::lookup_hash(&sha256);
    if hv.verdict == "Malicious" {
        return json!({"verdict": "Malicious", "confidence": 0.95, "matched": ["hash"],
                      "sha256": sha256, "engine": "native"});
    }
    if hv.verdict == "unknown" && hv.confidence == 0.0 {
        // Feed absent → degraded (still report the hash).
        return json!({"verdict": "unknown", "degraded": true, "sha256": sha256, "engine": "native"});
    }

    // 2) literal-pattern matching (skip full read for oversized files).
    if meta.len() > MAX_SCAN_BYTES {
        return json!({"verdict": "Suspicious", "confidence": 0.4,
                      "matched": ["too-large-to-fully-scan"], "sha256": sha256, "engine": "native"});
    }
    let bytes = match std::fs::read(path) {
        Ok(b) => b,
        Err(e) => return json!({"verdict": "error", "error": format!("read: {e}"), "engine": "native"}),
    };
    match match_patterns(&bytes) {
        Some((verdict, conf, name)) => json!({"verdict": verdict, "confidence": conf,
            "matched": [name], "sha256": sha256, "engine": "native"}),
        None => json!({"verdict": "Clean", "confidence": 1.0, "sha256": sha256, "engine": "native"}),
    }
}

pub fn scan_hash(sha256: &str) -> Value {
    verdict_json(feed_bundle::lookup_hash(sha256), sha256)
}
pub fn scan_url(url: &str) -> Value {
    verdict_json(feed_bundle::lookup_url(url), url)
}
pub fn scan_ip(ip: &str) -> Value {
    verdict_json(feed_bundle::lookup_ip(ip), ip)
}

fn verdict_json(v: feed_bundle::Verdict, target: &str) -> Value {
    if v.verdict == "unknown" && v.confidence == 0.0 {
        return json!({"verdict": "unknown", "degraded": true, "target": target, "source": "native"});
    }
    json!({"verdict": v.verdict, "confidence": v.confidence, "target": target, "source": v.source})
}

fn hash_file(path: &str) -> std::io::Result<String> {
    use std::io::Read;
    let mut f = std::fs::File::open(path)?;
    let mut hasher = Sha256::new();
    let mut buf = [0u8; 65536];
    loop {
        let n = f.read(&mut buf)?;
        if n == 0 {
            break;
        }
        hasher.update(&buf[..n]);
    }
    Ok(hex::encode(hasher.finalize()))
}

/// Build patterns from the feed's yara_rules string literals and scan `bytes`.
/// Returns (verdict, confidence, rule_name) on the first match.
fn match_patterns(bytes: &[u8]) -> Option<(String, f32, String)> {
    let con = feed_bundle::open_cache()?;
    let mut stmt = con.prepare("SELECT name, severity, source FROM yara_rules").ok()?;
    let rows = stmt
        .query_map([], |r| {
            Ok((
                r.get::<_, String>(0)?,
                r.get::<_, String>(1)?,
                r.get::<_, String>(2)?,
            ))
        })
        .ok()?;

    let mut patterns: Vec<Vec<u8>> = Vec::new();
    let mut meta: Vec<(String, f32)> = Vec::new(); // (rule_name, confidence) aligned with each literal
    let mut verdicts: Vec<String> = Vec::new();
    for row in rows.flatten() {
        let (name, severity, source) = row;
        let (verdict, conf) = severity_to_verdict(&severity);
        for lit in extract_string_literals(&source) {
            patterns.push(lit.into_bytes());
            meta.push((name.clone(), conf));
            verdicts.push(verdict.clone());
        }
    }
    if patterns.is_empty() {
        return None;
    }
    let ac = AhoCorasick::new(&patterns).ok()?;
    let m = ac.find(bytes)?;
    let idx = m.pattern().as_usize();
    Some((verdicts[idx].clone(), meta[idx].1, meta[idx].0.clone()))
}

fn severity_to_verdict(severity: &str) -> (String, f32) {
    match severity.to_ascii_lowercase().as_str() {
        "critical" | "high" => ("Malicious".to_string(), 0.9),
        _ => ("Suspicious".to_string(), 0.6),
    }
}

/// Extract double-quoted string literals from a YARA rule source.
fn extract_string_literals(source: &str) -> Vec<String> {
    let mut out = Vec::new();
    let bytes = source.as_bytes();
    let mut i = 0;
    while i < bytes.len() {
        if bytes[i] == b'"' {
            let start = i + 1;
            let mut j = start;
            while j < bytes.len() && bytes[j] != b'"' {
                j += 1;
            }
            if j <= bytes.len() && j > start {
                if let Ok(s) = std::str::from_utf8(&bytes[start..j]) {
                    if !s.is_empty() {
                        out.push(s.to_string());
                    }
                }
            }
            i = j + 1;
        } else {
            i += 1;
        }
    }
    out
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn extract_literals() {
        let src = r#"rule R { strings: $a = "EICAR-STANDARD-ANTIVIRUS-TEST-FILE" condition: $a }"#;
        let lits = extract_string_literals(src);
        assert_eq!(lits, vec!["EICAR-STANDARD-ANTIVIRUS-TEST-FILE".to_string()]);
    }

    #[test]
    fn severity_mapping() {
        assert_eq!(severity_to_verdict("high").0, "Malicious");
        assert_eq!(severity_to_verdict("low").0, "Suspicious");
    }

    #[test]
    fn aho_corasick_matches_literal() {
        let pats = vec![b"BADSTRING".to_vec()];
        let ac = AhoCorasick::new(&pats).unwrap();
        assert!(ac.find(b"xx BADSTRING yy").is_some());
        assert!(ac.find(b"clean content").is_none());
    }

    #[test]
    fn scan_file_missing_path_is_error_not_panic() {
        let v = scan_file("/no/such/file/here.bin");
        assert_eq!(v["verdict"], "error");
    }
}

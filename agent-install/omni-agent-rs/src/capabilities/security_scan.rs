//! Native security scan engine (Phase 50 NSCAN-01/02; Phase 66 YARA engine).
//!
//! Offline file scanning + URL/IP/hash reputation, all against the locally
//! cached signed feed (feed_bundle) — no network at scan time.
//!
//! ENGINE NOTE (Phase 66, supersedes review/50-03): file scanning now compiles
//! and evaluates the feed's `yara_rules.source` as real YARA rules via yara-x,
//! rather than the aho-corasick literal-substring matching Phase 50 shipped as
//! a stopgap. This is a deliberate reversal of Phase 50's rejection of yara-x
//! — that decision was made to avoid the wasmtime+cranelift (JIT) dependency
//! yara-x pulls in, which grows the shipped agent binary and adds cross-compile
//! risk on some targets. Accepting that cost was a conscious call (not made by
//! this file) in exchange for real YARA semantics: wildcards, hex patterns,
//! regex, and boolean rule conditions, none of which literal matching could
//! ever express. Re-verify cross-compilation on any target this hasn't been
//! built for yet before shipping.
//!
//! Compiling YARA rules is far more expensive than building an aho-corasick
//! automaton was, so the compiled `Rules` are cached process-wide and only
//! rebuilt when the feed's rule content actually changes (see
//! `compiled_rules`) — scan_file is called per on-demand scan instruction
//! (src/instructions.rs), not in a hot per-file loop, but a directory-sized
//! batch of scans must not recompile the whole rule set on every file.

use crate::capabilities::feed_bundle;
use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use std::hash::{Hash, Hasher};
use std::sync::{Arc, Mutex, OnceLock};
use yara_x::{Compiler, Rules, Scanner};

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

/// Compiles the feed's `yara_rules` as real YARA rules (cached — see
/// `compiled_rules`), scans `bytes`, and returns the highest-severity match.
/// Ties keep whichever rule matched first.
fn match_patterns(bytes: &[u8]) -> Option<(String, f32, String)> {
    let con = feed_bundle::open_cache()?;
    let mut stmt = con.prepare("SELECT name, severity, source FROM yara_rules").ok()?;
    let rows: Vec<(String, String, String)> = stmt
        .query_map([], |r| {
            Ok((
                r.get::<_, String>(0)?,
                r.get::<_, String>(1)?,
                r.get::<_, String>(2)?,
            ))
        })
        .ok()?
        .flatten()
        .collect();
    if rows.is_empty() {
        return None;
    }

    let rules = compiled_rules(&rows)?;
    let mut scanner = Scanner::new(&rules);
    let results = scanner.scan(bytes).ok()?;

    let mut best: Option<(String, f32, String)> = None;
    for matched in results.matching_rules() {
        let name = matched.identifier();
        let Some((_, severity, _)) = rows.iter().find(|(n, _, _)| n == name) else {
            continue; // compiled but no longer present in the feed row set — ignore
        };
        let (verdict, conf) = severity_to_verdict(severity);
        let is_better = match &best {
            None => true,
            Some((_, best_conf, _)) => conf > *best_conf,
        };
        if is_better {
            best = Some((verdict, conf, name.to_string()));
        }
    }
    best
}

/// Returns the compiled rule set for the given feed rows, rebuilding only
/// when the rule content has actually changed since the last scan. Rules
/// that fail to compile (malformed feed content) are logged and skipped
/// rather than aborting the whole engine.
fn compiled_rules(rows: &[(String, String, String)]) -> Option<Arc<Rules>> {
    static CACHE: OnceLock<Mutex<Option<(u64, Arc<Rules>)>>> = OnceLock::new();

    let mut hasher = std::collections::hash_map::DefaultHasher::new();
    for (name, _, source) in rows {
        name.hash(&mut hasher);
        source.hash(&mut hasher);
    }
    let key = hasher.finish();

    let cache = CACHE.get_or_init(|| Mutex::new(None));
    let mut guard = cache.lock().ok()?;
    if let Some((cached_key, cached_rules)) = guard.as_ref() {
        if *cached_key == key {
            return Some(Arc::clone(cached_rules));
        }
    }

    let mut compiler = Compiler::new();
    for (name, _, source) in rows {
        if let Err(e) = compiler.add_source(source.as_str()) {
            log::warn!("YARA rule '{name}' failed to compile, skipping: {e}");
        }
    }
    let rules = Arc::new(compiler.build());
    *guard = Some((key, Arc::clone(&rules)));
    Some(rules)
}

fn severity_to_verdict(severity: &str) -> (String, f32) {
    match severity.to_ascii_lowercase().as_str() {
        "critical" | "high" => ("Malicious".to_string(), 0.9),
        _ => ("Suspicious".to_string(), 0.6),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn severity_mapping() {
        assert_eq!(severity_to_verdict("high").0, "Malicious");
        assert_eq!(severity_to_verdict("low").0, "Suspicious");
    }

    /// Real YARA rule syntax literal matching could never express: a hex
    /// byte pattern with a wildcard nibble, condition on the pattern being
    /// present. This is the actual gap Phase 66 exists to close.
    #[test]
    fn compiles_and_matches_hex_wildcard_pattern() {
        let src = r#"
            rule HexWildcard {
                strings:
                    $a = { 4D 5A ?? 00 03 00 00 00 }
                condition:
                    $a
            }
        "#;
        let mut compiler = Compiler::new();
        compiler.add_source(src).expect("valid YARA source must compile");
        let rules = compiler.build();
        let mut scanner = Scanner::new(&rules);

        let matching = [0x4D, 0x5A, 0xAB, 0x00, 0x03, 0x00, 0x00, 0x00];
        let results = scanner.scan(&matching).unwrap();
        assert_eq!(results.matching_rules().count(), 1);

        let mut scanner = Scanner::new(&rules);
        let non_matching = [0x00, 0x01, 0x02];
        let results = scanner.scan(&non_matching).unwrap();
        assert_eq!(results.matching_rules().count(), 0);
    }

    /// Real YARA boolean condition logic (`$a and $b`) — also inexpressible
    /// with plain substring matching.
    #[test]
    fn compiles_and_matches_boolean_condition() {
        let src = r#"
            rule NeedsBoth {
                strings:
                    $a = "MALICIOUS_MARKER_A"
                    $b = "MALICIOUS_MARKER_B"
                condition:
                    $a and $b
            }
        "#;
        let mut compiler = Compiler::new();
        compiler.add_source(src).unwrap();
        let rules = compiler.build();

        let mut scanner = Scanner::new(&rules);
        let both = b"...MALICIOUS_MARKER_A...MALICIOUS_MARKER_B...";
        assert_eq!(scanner.scan(both).unwrap().matching_rules().count(), 1);

        let mut scanner = Scanner::new(&rules);
        let only_one = b"...MALICIOUS_MARKER_A...";
        assert_eq!(scanner.scan(only_one).unwrap().matching_rules().count(), 0);
    }

    #[test]
    fn match_patterns_skips_malformed_rule_without_aborting_others() {
        let rows = vec![
            ("Broken".to_string(), "high".to_string(), "this is not valid YARA".to_string()),
            (
                "Good".to_string(),
                "critical".to_string(),
                r#"rule Good { strings: $a = "FINDME" condition: $a }"#.to_string(),
            ),
        ];
        let rules = compiled_rules(&rows).expect("build must succeed by skipping the bad rule");
        let mut scanner = Scanner::new(&rules);
        let results = scanner.scan(b"...FINDME...").unwrap();
        let names: Vec<&str> = results.matching_rules().map(|r| r.identifier()).collect();
        assert_eq!(names, vec!["Good"]);
    }

    #[test]
    fn scan_file_missing_path_is_error_not_panic() {
        let v = scan_file("/no/such/file/here.bin");
        assert_eq!(v["verdict"], "error");
    }
}

//! PII Scanner capability — scans a bounded set of user/data directories for
//! common sensitive-data patterns (email, US SSN, credit-card numbers). Ports
//! agent/capabilities/pii_scanner.py. Privacy-safe: reports only the match COUNT
//! and type per file, never the matched values themselves.

use super::Capability;
use regex::Regex;
use serde_json::{json, Value};
use std::sync::OnceLock;

const MAX_FILES: usize = 50;
const MAX_SIZE_BYTES: u64 = 5 * 1024 * 1024;
const SCAN_EXTS: &[&str] = &["txt", "log", "csv", "json", "md"];

fn patterns() -> &'static [(&'static str, Regex)] {
    static P: OnceLock<Vec<(&'static str, Regex)>> = OnceLock::new();
    P.get_or_init(|| {
        vec![
            ("EMAIL", Regex::new(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b").unwrap()),
            ("SSN", Regex::new(r"\b\d{3}-\d{2}-\d{4}\b").unwrap()),
            ("CREDIT_CARD", Regex::new(r"\b(?:\d{4}[-\s]?){3}\d{4}\b").unwrap()),
        ]
    })
}

fn scan_dirs() -> Vec<String> {
    let mut dirs: Vec<String> = Vec::new();
    let home = std::env::var("USERPROFILE")
        .or_else(|_| std::env::var("HOME"))
        .unwrap_or_default();
    if !home.is_empty() {
        dirs.push(format!("{}/Documents", home));
        dirs.push(format!("{}/Desktop", home));
    }
    #[cfg(windows)]
    dirs.push(r"C:\ProgramData\OmniAgent\data".to_string());
    #[cfg(not(windows))]
    dirs.push("/var/lib/omniagent/data".to_string());
    dirs
}

/// Recursively collect scannable files under `dir`, stopping once `limit` is hit.
fn collect_files(dir: &std::path::Path, limit: usize, out: &mut Vec<std::path::PathBuf>) {
    if out.len() >= limit {
        return;
    }
    let Ok(entries) = std::fs::read_dir(dir) else { return };
    for entry in entries.flatten() {
        if out.len() >= limit {
            return;
        }
        let path = entry.path();
        if path.is_dir() {
            collect_files(&path, limit, out);
        } else if let Some(ext) = path.extension().and_then(|e| e.to_str()) {
            if SCAN_EXTS.contains(&ext.to_lowercase().as_str()) {
                out.push(path);
            }
        }
    }
}

pub struct PiiScannerCapability;

impl Capability for PiiScannerCapability {
    fn id(&self) -> &'static str { "pii_scanner" }
    fn name(&self) -> &'static str { "PII Scanner" }

    fn collect(&self, _sys: &sysinfo::System) -> Value {
        let mut files: Vec<std::path::PathBuf> = Vec::new();
        for dir in scan_dirs() {
            let p = std::path::Path::new(&dir);
            if p.exists() {
                collect_files(p, MAX_FILES, &mut files);
            }
            if files.len() >= MAX_FILES {
                break;
            }
        }
        files.truncate(MAX_FILES);

        let mut findings: Vec<Value> = Vec::new();
        let mut scanned = 0usize;

        for path in &files {
            let too_big = std::fs::metadata(path).map(|m| m.len() > MAX_SIZE_BYTES).unwrap_or(true);
            if too_big {
                continue;
            }
            // Read lossily so a non-UTF8 file doesn't abort the scan (mirrors
            // Python's errors='ignore').
            let content = match std::fs::read(path) {
                Ok(bytes) => String::from_utf8_lossy(&bytes).into_owned(),
                Err(_) => continue,
            };

            let mut file_matches: Vec<String> = Vec::new();
            for (label, re) in patterns() {
                let n = re.find_iter(&content).count();
                if n > 0 {
                    file_matches.push(format!("{}: {}", label, n));
                }
            }
            if !file_matches.is_empty() {
                findings.push(json!({
                    "file": path.to_string_lossy(),
                    "matches": file_matches.join(", "),
                    "details": "Sensitive data patterns detected",
                }));
            }
            scanned += 1;
        }

        json!({
            "pii_found": !findings.is_empty(),
            "findings_count": findings.len(),
            "findings": findings,
            "scanned_count": scanned,
        })
    }
}

/*!
 * Cross-platform malware/YARA-equivalent scanner (Phase 65, promoted from
 * backlog 999.4 research 2026-09-29).
 *
 * The previous implementation (see git history) was Windows-only end to
 * end: it shelled out to PowerShell for both process enumeration and
 * directory listing, and matched each of the 6 rules' string patterns via
 * a nested `.contains()` loop. This version:
 *   - Enumerates real process state via `sysinfo` (the same crate
 *     `caps::collect_processes` already uses) instead of `Get-Process`.
 *   - Walks real directories via `walkdir` (already used by
 *     `caps::run_pii_scan`) instead of `Get-ChildItem`.
 *   - Matches all patterns in one pass per haystack via an Aho-Corasick
 *     automaton instead of a nested `.contains()` loop per rule — this is
 *     the actual "leaner alternative to yara-x" this phase's research
 *     recommended: no JIT/wasmtime, pure Rust, proven clean cross-compile.
 *   - Runs identically on Linux and Windows; only the default scan
 *     directories differ by platform.
 *
 * The output JSON shape (`status`/`threats_found`/`match_count`/
 * `rules_applied`/`matches`/`scan_paths`, with each match carrying `rule`/
 * `category`/`target`/`match_type`/`sha256`) is unchanged from the
 * previous implementation on purpose — `vt::enrich_matches` (reads
 * `sha256` per match) and the backend's `POST /{agent_id}/malware-scan`
 * ingest endpoint (reads all six top-level fields) both depend on it.
 *
 * CAVEAT: written without a Rust toolchain available (no cargo/rustc in
 * the authoring environment) — never compiled. Run `cargo check`/
 * `cargo build`/`cargo test` on a real host before trusting this.
 */
use std::fs;

use aho_corasick::{AhoCorasick, AhoCorasickBuilder};
use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use sysinfo::System;
use walkdir::WalkDir;

struct Rule {
    name: &'static str,
    category: &'static str,
    strings: &'static [&'static str],
}

static RULES: &[Rule] = &[
    Rule { name: "MimikatzSignatures",      category: "credential_dumper",
           strings: &["sekurlsa", "lsadump", "mimikatz", "logonpasswords", "wdigest"] },
    Rule { name: "LaZagneCredentialDumper", category: "credential_dumper",
           strings: &["lazagne", "credentialfiles", "wlancredentials", "pypykatz"] },
    Rule { name: "RansomwareGeneric",       category: "ransomware",
           strings: &["your files are encrypted", "how_to_restore", "ransomnote", ".locked"] },
    Rule { name: "WannaCryIndicators",      category: "ransomware",
           strings: &["wannacry", "wncry", "tasksche", "wcry@123", "wanadecryptor"] },
    Rule { name: "ProcessInjectionAPIs",    category: "injection",
           strings: &["virtualallocex", "writeprocessmemory", "createremotethread", "ntqueueapcthread"] },
    Rule { name: "ReflectiveDLLInjection", category: "injection",
           strings: &["reflectivedllinjection", "reflectiveloader", "loadremotelibraryr"] },
];

#[cfg(windows)]
const DEFAULT_SCAN_DIRS: &[&str] = &[r"C:\Temp", r"C:\Users\Public\Downloads", r"C:\Windows\Temp"];
#[cfg(not(windows))]
const DEFAULT_SCAN_DIRS: &[&str] = &["/tmp", "/var/tmp", "/dev/shm"];

const MAX_SCAN_FILE_BYTES: u64 = 2 * 1_048_576;
const MAX_WALK_DEPTH: usize = 3;

/// Builds one Aho-Corasick automaton over every rule's string patterns,
/// plus a parallel table mapping each pattern's position back to its rule
/// index (RULES and the automaton are built in the same iteration order,
/// so `owner[pattern_id]` is always in bounds for a match this automaton
/// itself produced).
fn build_matcher() -> (AhoCorasick, Vec<usize>) {
    let mut patterns: Vec<&str> = Vec::new();
    let mut owner: Vec<usize> = Vec::new();
    for (rule_idx, rule) in RULES.iter().enumerate() {
        for s in rule.strings {
            patterns.push(s);
            owner.push(rule_idx);
        }
    }
    let ac = AhoCorasickBuilder::new()
        .ascii_case_insensitive(true)
        .build(&patterns)
        .expect("RULES patterns are static ASCII literals — building the automaton cannot fail");
    (ac, owner)
}

/// Returns the sorted, deduplicated set of rule indices whose patterns
/// appear anywhere in `haystack`.
fn matched_rule_indices(ac: &AhoCorasick, owner: &[usize], haystack: &str) -> Vec<usize> {
    let mut matched: Vec<usize> = ac.find_iter(haystack).map(|m| owner[m.pattern().as_usize()]).collect();
    matched.sort_unstable();
    matched.dedup();
    matched
}

fn sha256_of_file(path: &str) -> String {
    fs::read(path)
        .ok()
        .map(|data| {
            let mut h = Sha256::new();
            h.update(&data);
            hex::encode(h.finalize())
        })
        .unwrap_or_default()
}

/// Scans running processes: matches against name + executable path, and
/// hashes the executable when its path is resolvable. Process name is
/// round-tripped through `serde_json::to_value` rather than assumed to be
/// `&str` — the same value `caps::collect_processes` already places
/// directly into a `json!()`, so whatever type `sysinfo::Process::name()`
/// returns in this crate's pinned version, this handles it identically.
fn scan_processes(ac: &AhoCorasick, owner: &[usize]) -> Vec<Value> {
    let mut hits = Vec::new();
    let mut sys = System::new_all();
    sys.refresh_processes(sysinfo::ProcessesToUpdate::All, true);

    for proc in sys.processes().values() {
        let name = serde_json::to_value(proc.name())
            .ok()
            .and_then(|v| v.as_str().map(str::to_string))
            .unwrap_or_default();
        let exe_path = proc.exe().map(|p| p.display().to_string()).unwrap_or_default();

        let haystack = format!("{} {}", name, exe_path);
        let matched = matched_rule_indices(ac, owner, &haystack);
        if matched.is_empty() {
            continue;
        }

        let target = if exe_path.is_empty() { name.clone() } else { exe_path.clone() };
        let sha256 = if exe_path.is_empty() { String::new() } else { sha256_of_file(&exe_path) };

        for rule_idx in matched {
            let rule = &RULES[rule_idx];
            hits.push(json!({
                "rule": rule.name, "category": rule.category,
                "target": target, "match_type": "process_name", "sha256": sha256,
            }));
        }
    }
    hits
}

/// Scans file contents under the given directories (or the platform
/// defaults). Binary/unreadable-as-UTF8 files are skipped, matching the
/// previous implementation's try/catch-empty behavior for unreadable
/// content — a real hit against a plaintext dropper script or config still
/// matches; this was never meant to parse arbitrary binaries.
fn scan_files(ac: &AhoCorasick, owner: &[usize], extra_paths: &[&str]) -> (Vec<Value>, Vec<String>) {
    let dirs: Vec<&str> = if extra_paths.is_empty() { DEFAULT_SCAN_DIRS.to_vec() } else { extra_paths.to_vec() };
    let mut hits = Vec::new();

    for &dir in &dirs {
        for entry in WalkDir::new(dir).max_depth(MAX_WALK_DEPTH).into_iter().filter_map(|e| e.ok()) {
            if !entry.file_type().is_file() {
                continue;
            }
            let too_big = entry.metadata().map(|m| m.len() > MAX_SCAN_FILE_BYTES).unwrap_or(true);
            if too_big {
                continue;
            }
            let path = entry.path();
            let content = match fs::read_to_string(path) {
                Ok(c) => c,
                Err(_) => continue,
            };

            let matched = matched_rule_indices(ac, owner, &content);
            if matched.is_empty() {
                continue;
            }

            let path_str = path.display().to_string();
            let sha256 = sha256_of_file(&path_str);
            for rule_idx in matched {
                let rule = &RULES[rule_idx];
                hits.push(json!({
                    "rule": rule.name, "category": rule.category,
                    "target": path_str, "match_type": "file_content", "sha256": sha256,
                }));
            }
        }
    }
    (hits, dirs.into_iter().map(String::from).collect())
}

pub async fn run_yara_scan(extra_paths: &[&str]) -> Value {
    let (ac, owner) = build_matcher();

    let mut hits = scan_processes(&ac, &owner);
    let (file_hits, scan_dirs) = scan_files(&ac, &owner, extra_paths);
    hits.extend(file_hits);

    json!({
        "status": "success",
        "threats_found": !hits.is_empty(),
        "match_count": hits.len(),
        "rules_applied": RULES.len(),
        "matches": hits,
        "scan_paths": scan_dirs,
    })
}

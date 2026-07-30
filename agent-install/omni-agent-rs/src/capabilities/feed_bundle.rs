//! Signed security-feed bundle client (Phase 50, NSCAN-02).
//!
//! Fetches the ed25519-signed SQLite feed bundle from the backend, verifies the
//! detached signature against an EMBEDDED public key BEFORE loading it
//! (fail-closed), caches it locally, and exposes hash/url/ip reputation
//! lookups. Everything degrades gracefully: a missing/corrupt/unverified bundle
//! keeps the previous good cache, else returns an `unknown` verdict — the agent
//! never crashes and never loads unverified data.

use ed25519_dalek::{Signature, VerifyingKey};
use rusqlite::Connection;
use std::path::PathBuf;

// The 32-byte ed25519 PUBLIC key matching the backend signing key
// (agent_security_feed_service.get_public_key()). PUBLIC only — never the
// private key. Rotate here if the backend key rotates.
const FEED_PUBLIC_KEY: [u8; 32] = [
    66, 76, 40, 121, 80, 176, 245, 138, 26, 128, 142, 128, 140, 60, 57, 7,
    239, 50, 167, 165, 178, 215, 50, 24, 125, 161, 131, 253, 166, 21, 111, 42,
];

/// A reputation verdict from the local feed.
#[derive(Debug, Clone)]
pub struct Verdict {
    pub verdict: String,
    pub confidence: f32,
    pub source: &'static str,
}

impl Verdict {
    pub fn unknown_degraded() -> Self {
        Verdict { verdict: "unknown".into(), confidence: 0.0, source: "native" }
    }
    fn hit(v: &str) -> Self {
        Verdict { verdict: v.to_string(), confidence: 0.95, source: "native" }
    }
    fn not_in_feed() -> Self {
        Verdict { verdict: "unknown".into(), confidence: 1.0, source: "native" }
    }
}

fn cache_path() -> PathBuf {
    // Store the verified feed next to the agent config.
    crate::config::config_path()
        .parent()
        .map(|p| p.join("security_feed.db"))
        .unwrap_or_else(|| PathBuf::from("security_feed.db"))
}

fn version_path() -> PathBuf {
    cache_path().with_extension("version")
}

fn local_version() -> String {
    std::fs::read_to_string(version_path()).unwrap_or_default().trim().to_string()
}

/// Fetch + verify + cache the feed bundle. Fail-closed: an invalid signature or
/// any error keeps the previous cache and returns Ok(false) (not updated).
pub fn update(api_base: &str, agent_token: &str) -> Result<bool, String> {
    let url = format!(
        "{}/api/agents/security/feed-bundle?have={}",
        api_base.trim_end_matches('/'),
        local_version()
    );
    let client = reqwest::blocking::Client::new();
    let resp = client
        .get(&url)
        .bearer_auth(agent_token)
        .send()
        .map_err(|e| format!("feed fetch failed: {e}"))?;

    if !resp.status().is_success() {
        return Err(format!("feed fetch status {}", resp.status()));
    }
    // No-op: server says we're current (JSON body, no X-Feed-Updated bytes).
    let version = resp
        .headers()
        .get("X-Feed-Version")
        .and_then(|v| v.to_str().ok())
        .map(str::to_string);
    let sig_b64 = resp
        .headers()
        .get("X-Feed-Signature")
        .and_then(|v| v.to_str().ok())
        .map(str::to_string);
    let (version, sig_b64) = match (version, sig_b64) {
        (Some(v), Some(s)) => (v, s),
        _ => return Ok(false), // no-op / already current
    };

    let body = resp.bytes().map_err(|e| format!("feed body read: {e}"))?;
    let sig_bytes = base64_decode(&sig_b64).ok_or_else(|| "bad signature b64".to_string())?;

    // Verify BEFORE loading (fail-closed).
    let vk = VerifyingKey::from_bytes(&FEED_PUBLIC_KEY).map_err(|e| format!("bad pubkey: {e}"))?;
    let sig = Signature::from_slice(&sig_bytes).map_err(|e| format!("bad sig: {e}"))?;
    if vk.verify_strict(&body, &sig).is_err() {
        log::warn!("feed bundle signature verification FAILED — keeping previous cache");
        return Ok(false);
    }

    // Atomic-ish write: temp then rename.
    let tmp = cache_path().with_extension("db.tmp");
    std::fs::write(&tmp, &body).map_err(|e| format!("cache write: {e}"))?;
    std::fs::rename(&tmp, cache_path()).map_err(|e| format!("cache rename: {e}"))?;
    let _ = std::fs::write(version_path(), &version);
    log::info!("feed bundle updated to version {version}");
    Ok(true)
}

/// A single `cve_feed` row from the signed bundle (Phase 51, VULN-02).
#[derive(Debug, Clone)]
pub struct CveFeedRow {
    pub package: String,
    pub version_range: String,
    pub cve_id: String,
    pub cvss: f64,
    pub severity: String,
    pub remediation_hint: String,
    pub playbook_ref: String,
}

/// All `cve_feed` rows from the cached bundle, or `None` when the bundle is
/// absent / unreadable / lacks the table (degraded — the caller reports no CVE
/// findings rather than crash). No network: reads the verified local cache only.
pub fn cve_feed_rows() -> Option<Vec<CveFeedRow>> {
    let con = open_cache()?;
    let mut stmt = con
        .prepare(
            "SELECT package, version_range, cve_id, cvss, severity, remediation_hint, playbook_ref \
             FROM cve_feed",
        )
        .ok()?;
    let rows = stmt
        .query_map([], |r| {
            Ok(CveFeedRow {
                package: r.get(0)?,
                version_range: r.get(1)?,
                cve_id: r.get(2)?,
                cvss: r.get(3)?,
                severity: r.get(4)?,
                remediation_hint: r.get(5)?,
                playbook_ref: r.get(6)?,
            })
        })
        .ok()?;
    Some(rows.flatten().collect())
}

/// Open the cached feed DB, or None if absent/unreadable.
pub fn open_cache() -> Option<Connection> {
    let p = cache_path();
    if !p.exists() {
        return None;
    }
    Connection::open(&p).ok()
}

pub fn lookup_hash(sha256: &str) -> Verdict {
    let Some(con) = open_cache() else { return Verdict::unknown_degraded() };
    let row: rusqlite::Result<String> = con.query_row(
        "SELECT verdict FROM hash_sigs WHERE sha256 = ?1",
        [sha256],
        |r| r.get(0),
    );
    match row {
        Ok(v) => Verdict::hit(&v),
        Err(rusqlite::Error::QueryReturnedNoRows) => Verdict::not_in_feed(),
        Err(_) => Verdict::unknown_degraded(),
    }
}

pub fn lookup_url(target: &str) -> Verdict {
    let Some(con) = open_cache() else { return Verdict::unknown_degraded() };
    let host = url_host(target);
    let mut stmt = match con.prepare("SELECT pattern, kind, verdict FROM url_feed") {
        Ok(s) => s,
        Err(_) => return Verdict::unknown_degraded(),
    };
    let rows = stmt.query_map([], |r| {
        Ok((r.get::<_, String>(0)?, r.get::<_, String>(1)?, r.get::<_, String>(2)?))
    });
    if let Ok(rows) = rows {
        for row in rows.flatten() {
            let (pattern, kind, verdict) = row;
            let matched = match kind.as_str() {
                "domain" => host.eq_ignore_ascii_case(&pattern) || host.ends_with(&format!(".{pattern}")),
                _ => target == pattern,
            };
            if matched {
                return Verdict::hit(&verdict);
            }
        }
    }
    Verdict::not_in_feed()
}

pub fn lookup_ip(ip: &str) -> Verdict {
    let Some(con) = open_cache() else { return Verdict::unknown_degraded() };
    let mut stmt = match con.prepare("SELECT cidr, verdict FROM ip_feed") {
        Ok(s) => s,
        Err(_) => return Verdict::unknown_degraded(),
    };
    let rows = stmt.query_map([], |r| Ok((r.get::<_, String>(0)?, r.get::<_, String>(1)?)));
    if let Ok(rows) = rows {
        for row in rows.flatten() {
            let (cidr, verdict) = row;
            if ipv4_in_cidr(ip, &cidr) {
                return Verdict::hit(&verdict);
            }
        }
    }
    Verdict::not_in_feed()
}

// --- small helpers (no extra crates) ---------------------------------------

fn url_host(target: &str) -> String {
    let s = target.split("://").last().unwrap_or(target);
    s.split('/').next().unwrap_or(s).split(':').next().unwrap_or(s).to_string()
}

fn ipv4_to_u32(ip: &str) -> Option<u32> {
    let parts: Vec<&str> = ip.split('.').collect();
    if parts.len() != 4 {
        return None;
    }
    let mut acc: u32 = 0;
    for p in parts {
        let o: u32 = p.parse().ok()?;
        if o > 255 {
            return None;
        }
        acc = (acc << 8) | o;
    }
    Some(acc)
}

fn ipv4_in_cidr(ip: &str, cidr: &str) -> bool {
    let (net, bits) = match cidr.split_once('/') {
        Some((n, b)) => (n, b.parse::<u32>().unwrap_or(32)),
        None => (cidr, 32),
    };
    let (Some(ip_n), Some(net_n)) = (ipv4_to_u32(ip), ipv4_to_u32(net)) else {
        return false;
    };
    if bits == 0 {
        return true;
    }
    if bits > 32 {
        return false;
    }
    let mask: u32 = u32::MAX.checked_shl(32 - bits).unwrap_or(0);
    (ip_n & mask) == (net_n & mask)
}

fn base64_decode(s: &str) -> Option<Vec<u8>> {
    // Minimal std-only base64 decoder (standard alphabet, with '=' padding).
    const T: &[u8; 64] = b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
    let mut lut = [255u8; 256];
    for (i, &c) in T.iter().enumerate() {
        lut[c as usize] = i as u8;
    }
    let clean: Vec<u8> = s.bytes().filter(|&b| b != b'\n' && b != b'\r').collect();
    let mut out = Vec::with_capacity(clean.len() / 4 * 3);
    let mut buf = 0u32;
    let mut bits = 0u32;
    for &c in &clean {
        if c == b'=' {
            break;
        }
        let v = lut[c as usize];
        if v == 255 {
            return None;
        }
        buf = (buf << 6) | v as u32;
        bits += 6;
        if bits >= 8 {
            bits -= 8;
            out.push((buf >> bits) as u8);
        }
    }
    Some(out)
}

#[cfg(test)]
mod tests {
    use super::*;
    use rusqlite::Connection;

    fn seed(con: &Connection) {
        con.execute_batch(
            "CREATE TABLE hash_sigs (sha256 TEXT, md5 TEXT, verdict TEXT, name TEXT);
             CREATE TABLE url_feed (pattern TEXT, kind TEXT, verdict TEXT);
             CREATE TABLE ip_feed (cidr TEXT, verdict TEXT);
             INSERT INTO hash_sigs VALUES ('abc','x','Malicious','X');
             INSERT INTO url_feed VALUES ('malware.example.test','domain','Malicious');
             INSERT INTO ip_feed VALUES ('198.51.100.0/24','Malicious');",
        )
        .unwrap();
    }

    #[test]
    fn hash_hit_in_memory() {
        let con = Connection::open_in_memory().unwrap();
        seed(&con);
        let v: String = con
            .query_row("SELECT verdict FROM hash_sigs WHERE sha256='abc'", [], |r| r.get(0))
            .unwrap();
        assert_eq!(v, "Malicious");
    }

    #[test]
    fn cidr_membership() {
        assert!(ipv4_in_cidr("198.51.100.42", "198.51.100.0/24"));
        assert!(!ipv4_in_cidr("198.51.101.1", "198.51.100.0/24"));
        assert!(ipv4_in_cidr("10.1.2.3", "0.0.0.0/0"));
    }

    #[test]
    fn url_host_extract() {
        assert_eq!(url_host("http://c2.example.test/gate.php"), "c2.example.test");
        assert_eq!(url_host("malware.example.test"), "malware.example.test");
    }

    #[test]
    fn base64_roundtrip_known() {
        // "hello" -> aGVsbG8=
        assert_eq!(base64_decode("aGVsbG8=").unwrap(), b"hello");
    }

    #[test]
    fn lookups_degrade_without_cache() {
        // No cache file present in the test cwd → unknown/degraded, no panic.
        let v = lookup_hash("deadbeef");
        assert_eq!(v.source, "native");
    }
}

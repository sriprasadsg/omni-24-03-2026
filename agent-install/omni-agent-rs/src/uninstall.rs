//! Uninstall protection (backend `agent_uninstall_endpoints.py`).
//!
//! The platform sends a salted PBKDF2-SHA256 hash of this agent's uninstall
//! code with every heartbeat response; it is kept in config.yaml. Uninstallers
//! (NSIS, uninstall_agent.ps1) run these CLI modes before removing anything:
//!
//! ```text
//! omni-agent.exe --verify-uninstall-code CODE   exit 0 valid, 1 wrong code, 3 not protected yet
//! omni-agent.exe --report-uninstall CODE [--method NAME]
//! ```

use hmac::{Hmac, Mac};
use serde_json::Value;
use sha2::Sha256;

use crate::config::{self, Config, UninstallProtection};

pub const EXIT_VALID: i32 = 0;
pub const EXIT_INVALID: i32 = 1;
pub const EXIT_UNPROTECTED: i32 = 3;

/// Codes are shown as XXXX-XXXX-XXXX; accept any case, spaces or dashes.
pub fn normalize(code: &str) -> String {
    code.chars()
        .filter(|c| c.is_ascii_alphanumeric())
        .map(|c| c.to_ascii_uppercase())
        .collect()
}

/// PBKDF2-HMAC-SHA256 with a 32-byte output (a single block).
fn pbkdf2_sha256(password: &[u8], salt: &[u8], iterations: u32) -> [u8; 32] {
    let prf = |data: &[&[u8]]| -> [u8; 32] {
        let mut mac = Hmac::<Sha256>::new_from_slice(password).expect("HMAC accepts any key length");
        for d in data {
            mac.update(d);
        }
        mac.finalize().into_bytes().into()
    };
    let mut u = prf(&[salt, &1u32.to_be_bytes()]);
    let mut out = u;
    for _ in 1..iterations {
        u = prf(&[&u]);
        out.iter_mut().zip(u.iter()).for_each(|(o, x)| *o ^= x);
    }
    out
}

/// `Some(true/false)` for a protected agent, `None` if no code was issued yet.
pub fn verify(protection: Option<&UninstallProtection>, code: &str) -> Option<bool> {
    let p = protection?;
    let (Ok(salt), Ok(expected)) = (hex::decode(&p.salt), hex::decode(&p.hash)) else {
        return Some(false);
    };
    let digest = pbkdf2_sha256(normalize(code).as_bytes(), &salt, p.iterations);
    // Constant-time comparison.
    Some(expected.len() == digest.len() && expected.iter().zip(digest.iter()).fold(0u8, |acc, (a, b)| acc | (a ^ b)) == 0)
}

/// Store new verification data from a heartbeat response (first issue or rotation).
pub fn update_from_heartbeat(cfg: &mut Config, body: &Value) {
    let Some(p) = body
        .get("uninstall_protection")
        .and_then(|v| serde_json::from_value::<UninstallProtection>(v.clone()).ok())
    else {
        return;
    };
    if cfg.uninstall_protection.as_ref() != Some(&p) {
        log::info!("Uninstall protection updated (version {})", p.version);
        cfg.uninstall_protection = Some(p);
        if let Err(e) = config::save(cfg) {
            log::warn!("Could not persist uninstall protection to config.yaml: {e}");
        }
    }
}

/// Tell the platform the agent is being removed. Best effort: an offline
/// endpoint still uninstalls, and the platform sees it go Offline.
pub async fn report(cfg: &Config, code: &str, method: &str) -> bool {
    if cfg.agent_id.is_empty() || cfg.agent_token.is_empty() {
        return false;
    }
    crate::tls::init(cfg);
    let Ok(client) = crate::tls::platform_client()
        .timeout(std::time::Duration::from_secs(10))
        .build()
    else {
        return false;
    };
    let url = format!(
        "{}/api/agents/{}/uninstall-report",
        cfg.api_base_url.trim_end_matches('/'),
        cfg.agent_id
    );
    match client
        .post(&url)
        .bearer_auth(&cfg.agent_token)
        .json(&serde_json::json!({ "code": code, "method": method }))
        .send()
        .await
    {
        Ok(r) => r.status().is_success(),
        Err(e) => {
            log::warn!("Could not report the uninstall to the platform: {e}");
            false
        }
    }
}

fn arg_after<'a>(args: &'a [String], flag: &str) -> Option<&'a str> {
    let i = args.iter().position(|a| a == flag)?;
    args.get(i + 1).map(String::as_str)
}

/// Handle the uninstaller CLI modes; `None` when `args` asks for neither.
pub async fn cli(args: &[String]) -> Option<i32> {
    let verify_mode = args.iter().any(|a| a == "--verify-uninstall-code");
    let report_mode = args.iter().any(|a| a == "--report-uninstall");
    if !verify_mode && !report_mode {
        return None;
    }
    let cfg = match config::load() {
        Ok(c) => c,
        Err(e) => {
            eprintln!("Cannot read config.yaml: {e}");
            return Some(EXIT_INVALID);
        }
    };
    if verify_mode {
        let code = arg_after(args, "--verify-uninstall-code").unwrap_or("");
        return Some(match verify(cfg.uninstall_protection.as_ref(), code) {
            None => EXIT_UNPROTECTED,
            Some(true) => EXIT_VALID,
            Some(false) => EXIT_INVALID,
        });
    }
    let code = arg_after(args, "--report-uninstall").unwrap_or("");
    let method = arg_after(args, "--method").unwrap_or("uninstaller");
    Some(if report(&cfg, code, method).await { 0 } else { 1 })
}

#[cfg(test)]
mod tests {
    use super::*;

    // Shared with agent/test_uninstall_guard.py and backend hash_code.
    fn vector() -> UninstallProtection {
        UninstallProtection {
            version: 1,
            salt: "00112233445566778899aabbccddeeff".into(),
            iterations: 1000,
            hash: "b85f55c4887a7b5fc80a3669c0758177811c0bcb45b2a70583f91311b1529372".into(),
        }
    }

    #[test]
    fn accepts_the_code_in_any_format() {
        for typed in ["ABCD-EFGH-JKMN", "abcd efgh jkmn", "ABCDEFGHJKMN"] {
            assert_eq!(verify(Some(&vector()), typed), Some(true));
        }
    }

    #[test]
    fn rejects_wrong_or_missing_code() {
        assert_eq!(verify(Some(&vector()), "ABCD-EFGH-JKMP"), Some(false));
        assert_eq!(verify(Some(&vector()), ""), Some(false));
    }

    #[test]
    fn unprotected_agent_reports_none() {
        assert_eq!(verify(None, "anything"), None);
    }
}

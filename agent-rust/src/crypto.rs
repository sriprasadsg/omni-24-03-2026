/*!
 * At-rest encryption for agent secrets in config.yaml, via Windows DPAPI.
 *
 * `agent_token` and `registration_key` are otherwise stored as plaintext (ACL-restricted
 * to SYSTEM, WR-04). DPAPI with **machine scope** binds the ciphertext to this host, so a
 * copied config.yaml is useless off-box. Encrypted values are stored hex-encoded behind a
 * `dpapi:` marker; unmarked (legacy plaintext) values still load and are upgraded to
 * ciphertext on the next save.
 *
 * Availability over hardening: if encryption fails the plaintext is stored unchanged, and
 * if decryption fails the marked value is returned unchanged (the caller then hits an auth
 * failure and re-registers) — a crypto error never bricks the agent.
 *
 * Non-Windows builds are passthrough stubs so the crate checks/builds on Linux CI.
 */

pub const MARKER: &str = "dpapi:";

/// Encrypt a secret for at-rest storage. Returns `dpapi:<hex>` on success, or the input
/// unchanged if it is empty, already marked, or encryption is unavailable/failed.
pub fn protect(plain: &str) -> String {
    if plain.is_empty() || plain.starts_with(MARKER) {
        return plain.to_string();
    }
    #[cfg(windows)]
    {
        if let Some(hexed) = imp::protect(plain.as_bytes()) {
            return format!("{MARKER}{hexed}");
        }
    }
    plain.to_string()
}

/// Decrypt a stored secret. A `dpapi:`-marked value is DPAPI-decrypted; anything else
/// (legacy plaintext) is returned as-is. On decrypt failure the marked value is returned
/// unchanged rather than a broken credential.
pub fn unprotect(stored: &str) -> String {
    match stored.strip_prefix(MARKER) {
        Some(hexed) => {
            #[cfg(windows)]
            {
                if let Some(plain) = imp::unprotect(hexed) {
                    return plain;
                }
            }
            #[cfg(not(windows))]
            let _ = hexed;
            stored.to_string()
        }
        None => stored.to_string(),
    }
}

#[cfg(windows)]
mod imp {
    use windows::core::PCWSTR;
    use windows::Win32::Foundation::{HLOCAL, LocalFree};
    use windows::Win32::Security::Cryptography::{
        CryptProtectData, CryptUnprotectData, CRYPTPROTECT_LOCAL_MACHINE, CRYPT_INTEGER_BLOB,
    };

    fn blob(data: &[u8]) -> CRYPT_INTEGER_BLOB {
        CRYPT_INTEGER_BLOB {
            cbData: data.len() as u32,
            pbData: data.as_ptr() as *mut u8,
        }
    }

    /// Copy DPAPI's output blob into an owned Vec and free the LocalAlloc'd buffer.
    unsafe fn take(out: CRYPT_INTEGER_BLOB) -> Vec<u8> {
        let bytes = std::slice::from_raw_parts(out.pbData, out.cbData as usize).to_vec();
        let _ = LocalFree(HLOCAL(out.pbData as *mut core::ffi::c_void));
        bytes
    }

    pub fn protect(plain: &[u8]) -> Option<String> {
        unsafe {
            let input = blob(plain);
            let mut out = CRYPT_INTEGER_BLOB::default();
            CryptProtectData(
                &input,
                PCWSTR::null(),
                None,
                None,
                None,
                CRYPTPROTECT_LOCAL_MACHINE,
                &mut out,
            )
            .ok()?;
            Some(hex::encode(take(out)))
        }
    }

    pub fn unprotect(hexed: &str) -> Option<String> {
        let bytes = hex::decode(hexed).ok()?;
        unsafe {
            let input = blob(&bytes);
            let mut out = CRYPT_INTEGER_BLOB::default();
            CryptUnprotectData(
                &input,
                None,
                None,
                None,
                None,
                CRYPTPROTECT_LOCAL_MACHINE,
                &mut out,
            )
            .ok()?;
            String::from_utf8(take(out)).ok()
        }
    }
}

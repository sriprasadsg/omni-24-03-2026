use super::Capability;
use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use std::fs;
use sysinfo::System;

pub struct FimCapability;

// Critical Windows system files to monitor (executables + key config files)
static MONITORED_PATHS: &[&str] = &[
    // Binaries commonly abused in living-off-the-land attacks
    r"System32\notepad.exe",
    r"System32\cmd.exe",
    r"System32\powershell.exe",
    r"System32\wscript.exe",
    r"System32\cscript.exe",
    r"System32\regsvr32.exe",
    r"System32\mshta.exe",
    r"System32\certutil.exe",
    r"System32\bitsadmin.exe",
    r"System32\rundll32.exe",
    // Critical configuration files (matches Python agent monitoring)
    r"System32\drivers\etc\hosts",
];

impl Capability for FimCapability {
    fn id(&self) -> &'static str { "fim" }
    fn name(&self) -> &'static str { "File Integrity Monitoring" }

    fn collect(&self, _sys: &System) -> Value {
        let windir = std::env::var("WINDIR").unwrap_or_else(|_| r"C:\Windows".to_string());
        let mut files: Vec<Value> = vec![];
        let mut changed = 0usize;

        for rel in MONITORED_PATHS {
            let path = format!(r"{}\{}", windir, rel);
            match hash_file(&path) {
                Ok((hash, size, modified)) => {
                    files.push(json!({
                        "path": path,
                        "hash": hash,
                        "size_bytes": size,
                        "modified": modified,
                        "status": "ok",
                    }));
                }
                Err(e) => {
                    changed += 1;
                    files.push(json!({
                        "path": path,
                        "status": "error",
                        "error": e.to_string(),
                    }));
                }
            }
        }

        json!({
            "monitored_files": files.len(),
            "changed_files": changed,
            "files": files,
            "timestamp": chrono::Utc::now().to_rfc3339(),
        })
    }
}

fn hash_file(path: &str) -> Result<(String, u64, String), Box<dyn std::error::Error>> {
    let data = fs::read(path)?;
    let mut hasher = Sha256::new();
    hasher.update(&data);
    let hash = hex::encode(hasher.finalize());
    let meta = fs::metadata(path)?;
    let size = meta.len();
    let modified = meta
        .modified()
        .ok()
        .and_then(|t| {
            t.duration_since(std::time::UNIX_EPOCH)
                .ok()
                .map(|d| chrono::DateTime::<chrono::Utc>::from(std::time::UNIX_EPOCH + d).to_rfc3339())
        })
        .unwrap_or_default();
    Ok((hash, size, modified))
}

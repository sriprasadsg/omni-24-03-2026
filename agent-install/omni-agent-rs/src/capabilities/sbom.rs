use super::Capability;
use serde_json::{json, Value};
use hex;
use sha2::{Digest, Sha256};
use sysinfo::System;

pub struct SbomCapability;

impl Capability for SbomCapability {
    fn id(&self) -> &'static str { "sbom_analysis" }
    fn name(&self) -> &'static str { "Software Bill of Materials" }

    fn collect(&self, _sys: &System) -> Value {
        let components = collect_sbom();
        let total = components.len();

        // Compute SBOM hash from sorted (name, version) pairs
        let mut sorted_pairs: Vec<(String, String)> = components.iter()
            .map(|c| (
                c["name"].as_str().unwrap_or("").to_string(),
                c["version"].as_str().unwrap_or("").to_string(),
            ))
            .collect();
        sorted_pairs.sort();
        let mut hasher = Sha256::new();
        for (name, ver) in &sorted_pairs {
            hasher.update(format!("{}{}", name, ver).as_bytes());
        }
        let sbom_hash = hex::encode(hasher.finalize())[..16].to_string();

        // Categorize component types
        let mut type_counts: serde_json::Map<String, Value> = serde_json::Map::new();
        for c in &components {
            let t = c["type"].as_str().unwrap_or("unknown").to_string();
            let n = type_counts.get(&t).and_then(|v| v.as_u64()).unwrap_or(0) + 1;
            type_counts.insert(t, json!(n));
        }

        let preview: Vec<&Value> = components.iter().take(20).collect();

        json!({
            "sbom_version": "1.0",
            "format": "CycloneDX-Simplified",
            "generated_at": chrono::Utc::now().to_rfc3339(),
            "total_components": total,
            "components": preview,
            "sbom_hash": sbom_hash,
            "component_types": type_counts,
        })
    }
}

fn collect_sbom() -> Vec<Value> {
    let mut components: Vec<Value> = vec![];

    #[cfg(windows)]
    {
        use winreg::enums::*;
        use winreg::RegKey;

        let paths = [
            (
                HKEY_LOCAL_MACHINE,
                r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall",
                "application",
            ),
            (
                HKEY_LOCAL_MACHINE,
                r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall",
                "application_32bit",
            ),
            (
                HKEY_CURRENT_USER,
                r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall",
                "application_user",
            ),
        ];

        for (hive, path, comp_type) in &paths {
            if let Ok(key) = RegKey::predef(*hive).open_subkey(path) {
                for subkey_name in key.enum_keys().flatten() {
                    if let Ok(subkey) = key.open_subkey(&subkey_name) {
                        let name: String = subkey.get_value("DisplayName").unwrap_or_default();
                        let version: String =
                            subkey.get_value("DisplayVersion").unwrap_or_default();
                        let publisher: String =
                            subkey.get_value("Publisher").unwrap_or_default();
                        if !name.is_empty() {
                            components.push(json!({
                                "name": name,
                                "version": if version.is_empty() { "unknown".to_string() } else { version },
                                "publisher": publisher,
                                "type": comp_type,
                            }));
                        }
                    }
                }
            }
        }

        components.sort_by(|a, b| {
            a["name"]
                .as_str()
                .unwrap_or("")
                .cmp(b["name"].as_str().unwrap_or(""))
        });
    }

    components
}

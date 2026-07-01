use super::Capability;
use serde_json::{json, Value};
use sysinfo::{Disks, Networks, System};

pub struct MetricsCapability;

impl Capability for MetricsCapability {
    fn id(&self) -> &'static str { "metrics_collection" }
    fn name(&self) -> &'static str { "Metric Collection" }

    fn collect(&self, sys: &System) -> Value {
        let cpus = sys.cpus();
        let cpu_pct = if cpus.is_empty() {
            0.0_f32
        } else {
            cpus.iter().map(|c| c.cpu_usage()).sum::<f32>() / cpus.len() as f32
        };
        let cpu_brand = cpus.first().map(|c| c.brand().to_string()).unwrap_or_default();
        let cpu_freq = cpus.first().map(|c| c.frequency()).unwrap_or(0);

        let total_mem = sys.total_memory();
        let used_mem = sys.used_memory();
        let mem_pct = if total_mem > 0 {
            used_mem as f64 / total_mem as f64 * 100.0
        } else {
            0.0
        };

        let disks = Disks::new_with_refreshed_list();
        let disk_list: Vec<Value> = disks
            .iter()
            .map(|d| {
                let total = d.total_space();
                let free = d.available_space();
                let used = total.saturating_sub(free);
                let pct = if total > 0 { used as f64 / total as f64 * 100.0 } else { 0.0 };
                json!({
                    "device": d.name().to_string_lossy(),
                    "mountpoint": d.mount_point().to_string_lossy(),
                    "total_bytes": total,
                    "used_bytes": used,
                    "free_bytes": free,
                    "percent": (pct * 10.0).round() / 10.0,
                    "fs_type": d.file_system().to_string_lossy(),
                })
            })
            .collect();

        let networks = Networks::new_with_refreshed_list();
        let mut bytes_sent = 0u64;
        let mut bytes_recv = 0u64;
        let mut net_ifaces: Vec<Value> = vec![];
        for (name, data) in networks.iter() {
            bytes_sent += data.total_transmitted();
            bytes_recv += data.total_received();
            net_ifaces.push(json!({
                "name": name,
                "bytes_sent": data.total_transmitted(),
                "bytes_recv": data.total_received(),
                "packets_sent": data.total_packets_transmitted(),
                "packets_recv": data.total_packets_received(),
            }));
        }

        let software = get_installed_software();

        json!({
            "cpu": {
                "percent": (cpu_pct * 10.0).round() / 10.0,
                "count": cpus.len(),
                "brand": cpu_brand,
                "frequency_mhz": cpu_freq,
            },
            "memory": {
                "total_bytes": total_mem,
                "used_bytes": used_mem,
                "available_bytes": sys.available_memory(),
                "percent": (mem_pct * 10.0).round() / 10.0,
                "total_mb": total_mem / 1024 / 1024,
                "used_mb": used_mem / 1024 / 1024,
            },
            "disks": disk_list,
            "network": {
                "bytes_sent": bytes_sent,
                "bytes_recv": bytes_recv,
                "interfaces": net_ifaces,
            },
            "software": software,
            "process_count": sys.processes().len(),
            "timestamp": chrono::Utc::now().to_rfc3339(),
        })
    }
}

fn get_installed_software() -> Vec<Value> {
    #[cfg(windows)]
    {
        use winreg::enums::*;
        use winreg::RegKey;

        let mut software: Vec<Value> = vec![];
        let paths = [
            r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall",
            r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall",
        ];

        for path in &paths {
            if let Ok(key) = RegKey::predef(HKEY_LOCAL_MACHINE).open_subkey(path) {
                for subkey_name in key.enum_keys().flatten() {
                    if let Ok(subkey) = key.open_subkey(&subkey_name) {
                        let name: String = subkey.get_value("DisplayName").unwrap_or_default();
                        let version: String =
                            subkey.get_value("DisplayVersion").unwrap_or_default();
                        let publisher: String =
                            subkey.get_value("Publisher").unwrap_or_default();
                        let install_date: String =
                            subkey.get_value("InstallDate").unwrap_or_default();
                        if !name.is_empty() {
                            software.push(json!({
                                "name": name,
                                "version": version,
                                "publisher": publisher,
                                "installDate": install_date,
                                "updateAvailable": false,
                            }));
                        }
                    }
                }
            }
        }

        software.sort_by(|a, b| {
            a["name"]
                .as_str()
                .unwrap_or("")
                .cmp(b["name"].as_str().unwrap_or(""))
        });
        software.truncate(100);
        software
    }
    #[cfg(not(windows))]
    vec![]
}

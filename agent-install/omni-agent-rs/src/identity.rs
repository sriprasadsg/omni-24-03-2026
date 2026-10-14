//! Hardware identity for agent seat licensing (spec C2/C3).
//!
//! The platform binds a license seat to the machine, not its hostname: BIOS
//! serial first, then SMBIOS UUID, then a physical MAC, so renames and
//! reinstalls keep their seat. Values are sent raw; the platform drops firmware
//! placeholders ("To Be Filled By O.E.M." and the like). Never put a made-up
//! value here (such as the heartbeat's display fallback serial): it would
//! become the seat key.

use serde_json::{json, Value};
use std::sync::OnceLock;
use sysinfo::{Networks, System};

struct Firmware {
    serial: Option<String>,
    uuid: Option<String>,
}

static FIRMWARE: OnceLock<Firmware> = OnceLock::new();

/// Firmware values never change while the agent runs; the Windows lookup
/// spawns PowerShell, so it runs once.
fn firmware() -> &'static Firmware {
    FIRMWARE.get_or_init(detect_firmware)
}

fn clean(value: &str) -> Option<String> {
    let v = value.trim();
    if v.is_empty() {
        None
    } else {
        Some(v.to_string())
    }
}

/// "<serial>|<uuid>" as printed by the Windows lookup below.
fn parse_serial_uuid(text: &str) -> Firmware {
    let text = text.trim();
    let (serial, uuid) = text.split_once('|').unwrap_or((text, ""));
    Firmware { serial: clean(serial), uuid: clean(uuid) }
}

#[cfg(windows)]
fn detect_firmware() -> Firmware {
    // wmic.exe is gone from Windows 11 24H2; Get-CimInstance reads the same
    // WMI classes. One spawn for both values.
    let out = std::process::Command::new("powershell")
        .args([
            "-NoProfile",
            "-NonInteractive",
            "-Command",
            "$b=(Get-CimInstance -ClassName Win32_BIOS).SerialNumber; \
             $u=(Get-CimInstance -ClassName Win32_ComputerSystemProduct).UUID; \"$b|$u\"",
        ])
        .output();
    match out {
        Ok(o) => parse_serial_uuid(&String::from_utf8_lossy(&o.stdout)),
        Err(_) => Firmware { serial: None, uuid: None },
    }
}

#[cfg(target_os = "linux")]
fn detect_firmware() -> Firmware {
    let read = |path: &str| std::fs::read_to_string(path).ok().and_then(|s| clean(&s));
    Firmware {
        serial: read("/sys/class/dmi/id/product_serial"),
        // product_uuid is root-only (the agent runs as root); machine-id is the
        // spec's fallback for hosts without DMI.
        uuid: read("/sys/class/dmi/id/product_uuid").or_else(|| read("/etc/machine-id")),
    }
}

/// The quoted value of `"key" = "value"` in `ioreg -rd1 -c IOPlatformExpertDevice` output.
#[cfg(any(test, target_os = "macos"))]
fn ioreg_value(text: &str, key: &str) -> Option<String> {
    let needle = format!("\"{key}\"");
    text.lines()
        .find(|line| line.contains(&needle))
        .and_then(|line| line.split_once('='))
        .and_then(|(_, value)| clean(value.trim().trim_matches('"')))
}

#[cfg(target_os = "macos")]
fn detect_firmware() -> Firmware {
    let text = std::process::Command::new("ioreg")
        .args(["-rd1", "-c", "IOPlatformExpertDevice"])
        .output()
        .map(|o| String::from_utf8_lossy(&o.stdout).into_owned())
        .unwrap_or_default();
    Firmware {
        serial: ioreg_value(&text, "IOPlatformSerialNumber"),
        uuid: ioreg_value(&text, "IOPlatformUUID"),
    }
}

#[cfg(not(any(windows, target_os = "linux", target_os = "macos")))]
fn detect_firmware() -> Firmware {
    Firmware { serial: None, uuid: None }
}

/// The BIOS serial as the firmware reports it, if any.
pub fn bios_serial() -> Option<String> {
    firmware().serial.clone()
}

/// A MAC that names one physical adapter: six octets, not all zero, not
/// multicast and not locally administered (Hyper-V, Docker and VPN adapters
/// set that bit).
pub fn is_physical_mac(mac: &str) -> bool {
    let octets: Vec<u8> = mac
        .split(|c| c == ':' || c == '-')
        .filter_map(|o| if o.len() == 2 { u8::from_str_radix(o, 16).ok() } else { None })
        .collect();
    octets.len() == 6 && octets.iter().any(|&b| b != 0) && octets[0] & 0x03 == 0
}

/// Physical adapter MACs, lower-case and sorted so the list (and a MAC-based
/// seat key) is the same on every run.
pub fn physical_macs() -> Vec<String> {
    let networks = Networks::new_with_refreshed_list();
    let mut macs: Vec<String> = networks
        .iter()
        .map(|(_, data)| data.mac_address().to_string().to_lowercase())
        .filter(|mac| is_physical_mac(mac))
        .collect();
    macs.sort();
    macs.dedup();
    macs
}

/// The `hardware` block of the register request (and of heartbeats, so a
/// Pending agent can be identified from either).
pub fn hardware_block() -> Value {
    let fw = firmware();
    let mut hw = json!({
        "serialNumber": fw.serial,
        "smbiosUuid": fw.uuid,
        "macAddresses": physical_macs(),
        "osFamily": std::env::consts::OS,
        // e.g. "Windows Server 2022 Datacenter": tells servers from workstations even
        // when they run as VMs (OS sub-limits, spec C4).
        "osName": System::long_os_version().unwrap_or_default(),
        "osVersion": System::os_version().unwrap_or_default(),
        "deviceType": crate::heartbeat::device_type_info()["device_type"].clone(),
    });
    if let Some(user) = crate::heartbeat::logged_in_user() {
        hw["loggedInUser"] = json!(user);
    }
    hw
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn serial_and_uuid_are_split_and_blanks_dropped() {
        let fw = parse_serial_uuid("PF3ABC12|4C4C4544-0042-3010-8051-B4C04F4D3132\r\n");
        assert_eq!(fw.serial.as_deref(), Some("PF3ABC12"));
        assert_eq!(fw.uuid.as_deref(), Some("4C4C4544-0042-3010-8051-B4C04F4D3132"));
        let none = parse_serial_uuid(" | ");
        assert!(none.serial.is_none() && none.uuid.is_none());
        assert_eq!(parse_serial_uuid("ONLYSERIAL").serial.as_deref(), Some("ONLYSERIAL"));
    }

    #[test]
    fn only_physical_macs_count() {
        assert!(is_physical_mac("3c:52:82:aa:bb:cc"));
        assert!(is_physical_mac("3C-52-82-AA-BB-CC"));
        assert!(!is_physical_mac("00:00:00:00:00:00"));
        assert!(!is_physical_mac("02:42:ac:11:00:02")); // locally administered (Docker)
        assert!(!is_physical_mac("01:00:5e:00:00:fb")); // multicast
        assert!(!is_physical_mac("3c:52:82:aa:bb")); // five octets
        assert!(!is_physical_mac("3c:52:82:aa:bb:ccc"));
    }

    #[test]
    fn ioreg_values_are_unquoted() {
        let text = "  | \"IOPlatformSerialNumber\" = \"C02XL0GHJGH5\"\n  | \"IOPlatformUUID\" = \"0A1B2C3D-0000-1111-2222-333344445555\"\n";
        assert_eq!(ioreg_value(text, "IOPlatformSerialNumber").as_deref(), Some("C02XL0GHJGH5"));
        assert_eq!(ioreg_value(text, "IOPlatformUUID").as_deref(), Some("0A1B2C3D-0000-1111-2222-333344445555"));
        assert!(ioreg_value(text, "Missing").is_none());
    }

    #[test]
    fn hardware_block_has_the_fields_the_platform_reads() {
        let hw = hardware_block();
        for key in ["serialNumber", "smbiosUuid", "macAddresses", "osFamily", "osName", "osVersion", "deviceType"] {
            assert!(hw.get(key).is_some(), "missing {key}");
        }
        assert!(hw["macAddresses"].as_array().unwrap().iter().all(|m| is_physical_mac(m.as_str().unwrap())));
    }
}

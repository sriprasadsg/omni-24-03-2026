// src/fim_process_mapper.rs
use std::{fs, path::PathBuf};

pub fn get_process_name(pid: u32) -> Option<String> {
    let comm_path = PathBuf::from(format!("/proc/{}/comm", pid));
    if comm_path.exists() {
        if let Ok(name) = fs::read_to_string(&comm_path) {
            return Some(name.trim().to_string());
        }
    }

    let cmdline_path = PathBuf::from(format!("/proc/{}/cmdline", pid));
    if cmdline_path.exists() {
        if let Ok(cmdline) = fs::read_to_string(&cmdline_path) {
            // cmdline is null-separated, take the first part
            return cmdline.split('\0').next().map(|s| s.to_string());
        }
    }
    None
}

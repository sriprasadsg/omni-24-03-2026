
use std::{fs, io};
use std::path::Path;
use crate::olog;

pub fn get_process_name(pid: u32) -> Option<String> {
    let comm_path = Path::new("/proc").join(pid.to_string()).join("comm");
    let cmdline_path = Path::new("/proc").join(pid.to_string()).join("cmdline");

    if comm_path.exists() {
        match fs::read_to_string(&comm_path) {
            Ok(name) => {
                let name = name.trim();
                if !name.is_empty() { return Some(name.to_string()); }
            }
            Err(e) => olog!("Failed to read {:?}: {}", comm_path, e),
        }
    }

    if cmdline_path.exists() {
        match fs::read_to_string(&cmdline_path) {
            Ok(cmdline) => {
                let cmdline_parts: Vec<&str> = cmdline.split('\0').filter(|s| !s.is_empty()).collect();
                if let Some(name) = cmdline_parts.first() {
                    let name = name.trim();
                    if !name.is_empty() { return Some(name.to_string()); }
                }
            }
            Err(e) => olog!("Failed to read {:?}: {}", cmdline_path, e),
        }
    }

    None
}

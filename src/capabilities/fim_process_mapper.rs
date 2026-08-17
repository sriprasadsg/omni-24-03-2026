// src/capabilities/fim_process_mapper.rs
use std::{fs, path::PathBuf};

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ProcessInfo {
    pub pid: u32,
    pub name: String,
}

pub fn get_process_name(pid: u32) -> Option<String> {
    let comm_path = PathBuf::from(format!("/proc/{}/comm", pid));
    if let Ok(name) = fs::read_to_string(&comm_path) {
        return Some(name.trim().to_string());
    }

    let cmdline_path = PathBuf::from(format!("/proc/{}/cmdline", pid));
    if let Ok(cmdline) = fs::read_to_string(&cmdline_path) {
        return cmdline.split('\0').next().map(|s| s.to_string());
    }
    None
}

pub fn get_parent_pid(pid: u32) -> Option<u32> {
    let status_path = PathBuf::from(format!("/proc/{}/status", pid));
    if let Ok(content) = fs::read_to_string(&status_path) {
        for line in content.lines() {
            if line.starts_with("PPid:") {
                let ppid_str = line.trim_start_matches("PPid:").trim();
                return ppid_str.parse::<u32>().ok();
            }
        }
    }
    None
}

pub fn get_process_tree(pid: u32) -> Vec<ProcessInfo> {
    let mut tree = Vec::new();
    let mut current_pid = Some(pid);

    while let Some(pid) = current_pid {
        if let Some(name) = get_process_name(pid) {
            tree.push(ProcessInfo { pid, name });
        } else {
            // Process might have exited or we can't get its name.
            // Still try to find its parent, but don't add this one to the tree.
        }
        current_pid = get_parent_pid(pid);
        if current_pid == Some(0) || current_pid == Some(1) { // Stop at init or kernel process
            if let Some(pid_val) = current_pid {
                 if let Some(name) = get_process_name(pid_val) {
                    tree.push(ProcessInfo { pid: pid_val, name });
                }
            }
            break;
        }
    }
    tree.reverse(); // From root to child
    tree
}

use std::fs;
use std::io;
use std::path::Path;

pub fn get_process_name(pid: u32) -> Option<String> {
    let cmdline_path = format!("/proc/{}/cmdline", pid);
    let comm_path = format!("/proc/{}/comm", pid);

    if let Ok(cmdline) = fs::read_to_string(&cmdline_path) {
        let name = cmdline.split('\0').next().unwrap_or("");
        if !name.is_empty() {
            return Some(name.to_string());
        }
    }

    if let Ok(comm) = fs::read_to_string(&comm_path) {
        let name = comm.trim();
        if !name.is_empty() {
            return Some(name.to_string());
        }
    }

    None
}

pub fn get_parent_pid(pid: u32) -> Option<u32> {
    let status_path = format!("/proc/{}/status", pid);
    let content = fs::read_to_string(&status_path).ok()?;

    for line in content.lines() {
        if line.starts_with("PPid:") {
            let parts: Vec<&str> = line.split_whitespace().collect();
            if parts.len() >= 2 {
                return parts[1].parse().ok();
            }
        }
    }

    let stat_path = format!("/proc/{}/stat", pid);
    let content = fs::read_to_string(&stat_path).ok()?;
    let parts: Vec<&str> = content.split_whitespace().collect();
    if parts.len() >= 4 {
        return parts[3].parse().ok();
    }

    None
}

#[derive(Debug, Clone)]
pub struct ProcessInfo {
    pub pid: u32,
    pub name: String,
}

pub fn get_process_tree(pid: u32) -> Vec<ProcessInfo> {
    let mut tree = Vec::new();
    let mut current_pid = Some(pid);

    while let Some(pid) = current_pid {
        if let Some(name) = get_process_name(pid) {
            tree.push(ProcessInfo { pid, name });
        } else {
            tree.push(ProcessInfo {
                pid,
                name: "unknown".to_string(),
            });
        }

        if pid == 1 {
            break;
        }

        current_pid = get_parent_pid(pid);
    }

    tree
}
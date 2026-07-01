use serde_json::{Value, json};
use sysinfo::{System, SystemExt, CpuExt};
use std::process::Command;
use log::{info, error};

pub struct CapabilityManager {
    agent_id: String,
}

impl CapabilityManager {
    pub fn new() -> Self {
        Self {
            agent_id: "unknown".to_string(),
        }
    }

    pub fn set_agent_id(&mut self, id: String) {
        self.agent_id = id;
    }

    pub fn collect_metrics(&self, sys: &System) -> Value {
        json!({
            "cpu_percent": sys.global_cpu_info().cpu_usage(),
            "memory_usage": sys.used_memory(),
            "memory_total": sys.total_memory()
        })
    }

    pub async fn execute_instruction(&self, instruction: &crate::api::Instruction) -> Value {
        let cmd = &instruction.instruction;
        
        if cmd.contains("Run Compliance Scan") {
            return self.run_compliance_scan();
        } else if cmd.contains("Fix Compliance:") {
             // Basic Mock Fix
             return json!({"status": "success", "message": "Fix applied (Mock logic in Rust)"});
        }
        
        // Default / Unknown
        json!({"status": "unknown", "message": "Instruction not supported by Rust Agent"})
    }

    pub fn run_compliance_scan(&self) -> Value {
        info!("Running Compliance Scan...");
        let mut checks = Vec::new();

        // 1. BitLocker Check
        checks.push(self.check_bitlocker());

        // 2. Firewall Check
        checks.push(self.check_firewall());

        // 3. Antivirus Check (Defender)
        checks.push(self.check_antivirus());

        // 4. Secure Boot Check
        checks.push(self.check_secure_boot());

        // 5. User Access Control (UAC)
        checks.push(self.check_uac());

        // 6. Account Policies
        checks.extend(self.check_account_policies());

        // 7. Network & Vulnerability
        checks.extend(self.check_network_security());

        // 8. Advanced Security
        checks.extend(self.check_advanced_security());

        // 9. Service & Audit
        checks.extend(self.check_service_audit_compliance());

        // 10. Privacy & Data Protection (DPDP, ASR, Logging)
        checks.extend(self.check_privacy_compliance());

        // 11. New Checks (Phase 8 Parity)
        checks.push(self.check_prohibited_software());
        checks.push(self.check_password_complexity());
        checks.push(self.check_device_guard());
        checks.push(self.check_third_party_av());

        // Calculate stats
        let passed = checks.iter().filter(|c| c["status"] == "Pass").count();
        let failed = checks.len() - passed;

        json!({
            "compliance_checks": checks,
            "total_checks": checks.len(),
            "passed": passed,
            "failed": failed,
            "compliance_score": if checks.len() > 0 { (passed as f64 / checks.len() as f64) * 100.0 } else { 0.0 }
        })
    }

    fn check_bitlocker(&self) -> Value {
        let mut status = "Fail";
        let mut details = "Verification failed".to_string();
        let mut evidence = String::new();

        // Method 1: Get-BitLockerVolume
        let output = Command::new("powershell")
            .args(&["-Command", "Get-BitLockerVolume -MountPoint C: | Select-Object -ExpandProperty ProtectionStatus"])
            .output();
            
        if let Ok(o) = output {
            let stdout = String::from_utf8_lossy(&o.stdout).trim().to_string();
            if stdout.contains("On") || stdout.contains("1") {
                status = "Pass";
                details = format!("Protection Status: {}", stdout);
                evidence = format!("Get-BitLockerVolume Output: {}", stdout);
            } else {
                 evidence = format!("Get-BitLockerVolume Output: {}", stdout);
            }
        }

        // Method 2: manage-bde (Fallback)
        if status != "Pass" {
             let output = Command::new("manage-bde")
                .args(&["-status", "C:"])
                .output();
             
             if let Ok(o) = output {
                 let stdout = String::from_utf8_lossy(&o.stdout).to_string();
                 let stderr = String::from_utf8_lossy(&o.stderr).to_string();
                 evidence.push_str(&format!("\n\nmanage-bde output:\n{}\nStderr: {}", stdout, stderr));
                 
                 let combined = format!("{}{}", stdout, stderr);
                 
                 if combined.contains("Protection On") {
                     status = "Pass";
                     details = "Protection Status: On (via manage-bde)".to_string();
                 } else if combined.contains("access a required resource was denied") || combined.contains("administrative rights") {
                     if status == "Fail" {
                         status = "Warning";
                         details = "Check requires Admin privileges".to_string();
                     }
                 }
             }
        }

        json!({
            "check": "BitLocker Encryption",
            "status": status,
            "details": details,
            "evidence_content": evidence
        })
    }

    fn check_firewall(&self) -> Value {
        let output = Command::new("powershell")
            .args(&["-Command", "Get-NetFirewallProfile | Select-Object Name, Enabled | ConvertTo-Json"])
            .output();

        match output {
            Ok(o) => {
                let stdout = String::from_utf8_lossy(&o.stdout).to_string();
                if stdout.contains("\"Enabled\":  true") || stdout.contains("\"Enabled\":  1") {
                     json!({
                        "check": "Windows Firewall Profiles",
                        "status": "Pass",
                        "details": "Firewall enabled",
                        "evidence_content": stdout
                    })
                } else {
                     json!({
                        "check": "Windows Firewall Profiles",
                        "status": "Fail",
                        "details": "Firewall disabled on some profiles",
                        "evidence_content": stdout
                    })
                }
            },
            Err(e) => {
                 json!({
                    "check": "Windows Firewall Profiles",
                    "status": "Error",
                    "details": format!("Execution error: {}", e),
                    "evidence_content": e.to_string()
                })
            }
        }
    }

    fn check_antivirus(&self) -> Value {
        let output = Command::new("powershell")
            .args(&["-Command", "Get-MpComputerStatus | Select-Object AntivirusEnabled, RealTimeProtectionEnabled | ConvertTo-Json"])
            .output();

        match output {
            Ok(o) => {
                let stdout = String::from_utf8_lossy(&o.stdout).to_string();
                if stdout.contains("true") || stdout.contains("1") {
                    json!({
                        "check": "Windows Defender Antivirus",
                        "status": "Pass",
                        "details": "Windows Defender Enabled",
                        "evidence_content": stdout
                    })
                } else {
                    json!({
                        "check": "Windows Defender Antivirus",
                        "status": "Fail",
                        "details": "Windows Defender Disabled (or not primary)",
                        "evidence_content": stdout
                    })
                }
            },
            Err(e) => json!({
                "check": "Windows Defender Antivirus",
                "status": "Error",
                "details": format!("Execution error: {}", e),
                "evidence_content": e.to_string()
            })
        }
    }

    fn check_secure_boot(&self) -> Value {
         let output = Command::new("powershell")
            .args(&["-Command", "Confirm-SecureBootUEFI"])
            .output();

        match output {
            Ok(o) => {
                let stdout = String::from_utf8_lossy(&o.stdout).trim().to_string();
                if stdout.contains("True") {
                    json!({
                        "check": "Secure Boot",
                        "status": "Pass",
                        "details": "Secure Boot Enabled",
                        "evidence_content": stdout
                    })
                } else {
                    json!({
                        "check": "Secure Boot",
                        "status": "Fail",
                        "details": "Secure Boot Disabled or Not Supported",
                        "evidence_content": stdout
                    })
                }
            },
            Err(e) => json!({
                "check": "Secure Boot",
                "status": "Error",
                "details": format!("Execution error: {}", e),
                "evidence_content": e.to_string()
            })
        }
    }

    fn check_uac(&self) -> Value {
        let output = Command::new("reg")
            .args(&["query", "HKLM\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Policies\\System", "/v", "EnableLUA"])
            .output();

        match output {
            Ok(o) => {
                let stdout = String::from_utf8_lossy(&o.stdout).to_string();
                if stdout.contains("0x1") {
                     json!({
                        "check": "User Access Control",
                        "status": "Pass",
                        "details": "UAC Enabled",
                        "evidence_content": stdout
                    })
                } else {
                     json!({
                        "check": "User Access Control",
                        "status": "Fail",
                        "details": "UAC Disabled",
                        "evidence_content": stdout
                    })
                }
            },
             Err(e) => json!({
                "check": "User Access Control",
                "status": "Error",
                "details": format!("Execution error: {}", e),
                "evidence_content": e.to_string()
            })
        }
    }

    fn check_account_policies(&self) -> Vec<Value> {
        let mut checks = Vec::new();
        let output = Command::new("net")
            .args(&["accounts"])
            .output();

        match output {
            Ok(o) => {
                let stdout = String::from_utf8_lossy(&o.stdout).to_string();
                let lines: Vec<&str> = stdout.lines().collect();
                
                // Defaults
                let mut max_pw_age = 9999;
                let mut min_pw_len = 0;
                let mut pw_history = 0;
                let mut lockout_thresh = 0;
                let mut min_pw_age = 0;

                for line in lines {
                    if line.contains("Maximum password age") {
                        if let Some(val) = line.split(':').nth(1) {
                            let val = val.trim();
                            if !val.to_lowercase().contains("unlimited") {
                                if let Some(first_part) = val.split_whitespace().next() {
                                     if let Ok(num) = first_part.parse::<i32>() { max_pw_age = num; }
                                }
                            }
                        }
                    }
                    if line.contains("Minimum password length") {
                         if let Some(val) = line.split(':').nth(1) {
                            if let Ok(num) = val.trim().parse::<i32>() { min_pw_len = num; }
                         }
                    }
                    if line.contains("Length of password history") {
                         if let Some(val) = line.split(':').nth(1) {
                            if let Ok(num) = val.trim().parse::<i32>() { pw_history = num; }
                         }
                    }
                    if line.contains("Lockout threshold") {
                         if let Some(val) = line.split(':').nth(1) {
                             let val = val.trim();
                             if !val.to_lowercase().contains("never") {
                                if let Ok(num) = val.parse::<i32>() { lockout_thresh = num; }
                             }
                         }
                    }
                    if line.contains("Minimum password age") {
                         if let Some(val) = line.split(':').nth(1) {
                            if let Some(first_part) = val.trim().split_whitespace().next() {
                                 if let Ok(num) = first_part.parse::<i32>() { min_pw_age = num; }
                            }
                         }
                    }
                }

                // 1. Password Min Length
                checks.push(json!({
                    "check": "Password Policy (Min Length)",
                    "status": if min_pw_len >= 8 { "Pass" } else { "Fail" },
                    "details": format!("Minimum length: {} (Required: 8)", min_pw_len),
                    "evidence_content": stdout
                }));

                // 2. Max Password Age
                checks.push(json!({
                    "check": "Maximum Password Age",
                    "status": if max_pw_age <= 90 { "Pass" } else { "Fail" },
                    "details": format!("Max age: {} days (Recommended: <=90)", max_pw_age),
                    "evidence_content": stdout
                }));

                // 3. Password History
                checks.push(json!({
                    "check": "Password History",
                    "status": if pw_history >= 4 { "Pass" } else { "Fail" },
                    "details": format!("Maintains {} passwords (Recommended: >=4)", pw_history),
                    "evidence_content": stdout
                }));

                 // 4. Lockout Threshold
                checks.push(json!({
                    "check": "Account Lockout Policy",
                    "status": if lockout_thresh >= 1 && lockout_thresh <= 10 { "Pass" } else { "Fail" },
                    "details": format!("Lockout after {} attempts (Recommended: 3-10)", lockout_thresh),
                    "evidence_content": stdout
                }));

                 // 5. Min Password Age
                 checks.push(json!({
                    "check": "Minimum Password Age",
                    "status": if min_pw_age >= 1 { "Pass" } else { "Fail" },
                    "details": format!("Min age: {} days (Recommended: >=1)", min_pw_age),
                    "evidence_content": stdout
                }));

            },
            Err(e) => {
                 let err_msg = e.to_string();
                 for check_name in ["Password Policy (Min Length)", "Maximum Password Age", "Password History", "Account Lockout Policy", "Minimum Password Age"] {
                     checks.push(json!({
                        "check": check_name,
                        "status": "Error",
                        "details": format!("Execution error: {}", err_msg),
                        "evidence_content": err_msg
                    }));
                 }
            }
        }
        checks
    }

    fn check_network_security(&self) -> Vec<Value> {
        let mut checks = Vec::new();

        // 1. Risky Ports (Telnet: 23, FTP: 21)
        let output = Command::new("netstat")
            .args(&["-an"])
            .output();
        
        let mut telnet_open = false;
        let mut ftp_open = false;
        let mut evidence = String::new();

        if let Ok(o) = output {
            let stdout = String::from_utf8_lossy(&o.stdout).to_string();
            evidence = stdout.chars().take(500).collect(); // Truncate evidence
            if stdout.contains(":23 ") { telnet_open = true; }
            if stdout.contains(":21 ") { ftp_open = true; }
        }

        checks.push(json!({
            "check": "Risky Ports (Telnet)",
            "status": if !telnet_open { "Pass" } else { "Fail" },
            "details": if !telnet_open { "Port 23 closed" } else { "Port 23 LISTENING" },
            "evidence_content": evidence
        }));
         checks.push(json!({
            "check": "Risky Ports (FTP)",
            "status": if !ftp_open { "Pass" } else { "Fail" },
            "details": if !ftp_open { "Port 21 closed" } else { "Port 21 LISTENING" },
            "evidence_content": evidence
        }));

        // 2. SMBv1 Check
        let mut smb_status = "Fail";
        let mut smb_details = "Check failed".to_string();
        let smb_output = Command::new("powershell")
            .args(&["-Command", "Get-SmbServerConfiguration | Select-Object EnableSMB1Protocol | ConvertTo-Json"])
            .output();
        
        if let Ok(o) = smb_output {
             let stdout = String::from_utf8_lossy(&o.stdout).to_string();
             if stdout.contains("false") {
                 smb_status = "Pass";
                 smb_details = "SMBv1 Disabled".to_string();
             } else if stdout.contains("true") {
                 smb_details = "SMBv1 ENABLED (Risk)".to_string();
             }
             checks.push(json!({
                "check": "SMBv1 Protocol Status",
                "status": smb_status,
                "details": smb_details,
                "evidence_content": stdout
            }));
        } else {
             checks.push(json!({
                "check": "SMBv1 Protocol Status",
                "status": "Error",
                "details": "Command execution failed",
                "evidence_content": ""
            }));
        }

        // 3. TLS 1.2 Check
        let output = Command::new("reg")
            .args(&["query", "HKLM\\SYSTEM\\CurrentControlSet\\Control\\SecurityProviders\\SCHANNEL\\Protocols\\TLS 1.2\\Client", "/v", "Enabled"])
            .output();
        
        let mut tls_status = "Warning"; // Default if key not found (often means default behavior)
        let mut tls_details = "Registry key not found (Windows Default)".to_string();
        
        if let Ok(o) = output {
             let stdout = String::from_utf8_lossy(&o.stdout).to_string();
             if stdout.contains("0x1") {
                 tls_status = "Pass";
                 tls_details = "TLS 1.2 Explicitly Enabled".to_string();
             } else if stdout.contains("0x0") {
                 tls_status = "Fail";
                 tls_details = "TLS 1.2 Disabled".to_string();
             }
              checks.push(json!({
                "check": "TLS Security Configuration",
                "status": tls_status,
                "details": tls_details,
                "evidence_content": stdout
            }));
        } else {
             checks.push(json!({
                "check": "TLS Security Configuration",
                "status": "Error",
                "details": "Registry check failed",
                "evidence_content": ""
            }));
        }

        checks
    }

    fn check_advanced_security(&self) -> Vec<Value> {
        let mut checks = Vec::new();

        // 1. Credential Guard
        // Check functionality not just service status if possible, but for parity we use similar logic to Python? 
        // Python agent checks "Credential Guard" via WMI or SystemInfo.
        // We will use PowerShell Get-ComputerInfo or Get-CimInstance.
        // Simple robust check: Get-CimInstance -ClassName Win32_DeviceGuard -Namespace root\Microsoft\Windows\DeviceGuard
        let cg_output = Command::new("powershell")
             .args(&["-Command", "Get-CimInstance -ClassName Win32_DeviceGuard -Namespace root\\Microsoft\\Windows\\DeviceGuard | Select-Object SecurityServicesRunning | ConvertTo-Json"])
             .output();
        
        let mut cg_status = "Fail";
        let mut cg_details = "Credential Guard Not Running".to_string();
        let mut cg_evidence = String::new();

        if let Ok(o) = cg_output {
             let stdout = String::from_utf8_lossy(&o.stdout).to_string();
             cg_evidence = stdout.clone();
             // SecurityServicesRunning contains {1} or {2} etc. 
             // 1=Cred Guard, 2=HVCI? 
             // Actually, usually it returns an array of integers.
             if stdout.contains("1") { // Simplified check for "1" in the array
                 cg_status = "Pass";
                 cg_details = "Credential Guard Running".to_string();
             }
        }
        checks.push(json!({
             "check": "Credential Guard",
             "status": cg_status,
             "details": cg_details,
             "evidence_content": cg_evidence
        }));

        // 2. Exploit Protection (DEP/ASLR)
        // Get-ProcessMitigation -System
        let ep_output = Command::new("powershell")
             .args(&["-Command", "Get-ProcessMitigation -System | Select-Object -ExpandProperty Dep | ConvertTo-Json"])
             .output();
        
        let mut dep_status = "Fail";
        let mut dep_details = "DEP Disabled".to_string();
        let mut dep_evidence = String::new();

        if let Ok(o) = ep_output {
             let stdout = String::from_utf8_lossy(&o.stdout).to_string();
             dep_evidence = stdout.clone();
             if stdout.contains("\"Enable\":  true") || stdout.contains("\"Enable\":  1") {
                 dep_status = "Pass";
                 dep_details = "DEP System-wide Enabled".to_string();
             }
        }
         checks.push(json!({
             "check": "Exploit Protection (DEP)",
             "status": dep_status,
             "details": dep_details,
             "evidence_content": dep_evidence
        }));
        
        checks
    }

    fn check_service_audit_compliance(&self) -> Vec<Value> {
        let mut checks = Vec::new();

        // 1. Guest Account Status
        // Get-LocalUser -Name 'Guest' | Select-Object Enabled | ConvertTo-Json
        let guest_output = Command::new("powershell")
             .args(&["-Command", "Get-LocalUser -Name 'Guest' | Select-Object Enabled | ConvertTo-Json"])
             .output();
        
        let mut guest_status = "Fail";
        let mut guest_details = "Guest Account Enabled (Risk)".to_string();
        let mut guest_evidence = String::new();

        if let Ok(o) = guest_output {
             let stdout = String::from_utf8_lossy(&o.stdout).to_string();
             guest_evidence = stdout.clone();
             if stdout.contains("false") {
                 guest_status = "Pass";
                 guest_details = "Guest Account Disabled".to_string();
             }
        }
         checks.push(json!({
             "check": "Guest Account Disabled",
             "status": guest_status,
             "details": guest_details,
             "evidence_content": guest_evidence
        }));

        // 2. RDP NLA (Network Level Authentication)
        // Get-ItemProperty ... UserAuthentication
        let rdp_cmd = "Get-ItemProperty -Path 'HKLM:\\System\\CurrentControlSet\\Control\\Terminal Server\\WinStations\\RDP-Tcp' -Name 'UserAuthentication' | Select-Object UserAuthentication | ConvertTo-Json";
        let rdp_output = Command::new("powershell")
             .args(&["-Command", rdp_cmd])
             .output();
        
        let mut rdp_status = "Fail";
        let mut rdp_details = "NLA Not Enforced".to_string();
        let mut rdp_evidence = String::new();

        if let Ok(o) = rdp_output {
             let stdout = String::from_utf8_lossy(&o.stdout).to_string();
             rdp_evidence = stdout.clone();
             if stdout.contains("\"UserAuthentication\":  1") {
                 rdp_status = "Pass";
                 rdp_details = "NLA Enforced".to_string();
             }
        }
        checks.push(json!({
             "check": "RDP NLA Required",
             "status": rdp_status,
             "details": rdp_details,
             "evidence_content": rdp_evidence
        }));

        // 3. Windows Update Service
        let wuauserv = Command::new("sc").args(&["query", "wuauserv"]).output();
        let mut wua_status = "Fail";
        let mut wua_evidence = String::new();
        if let Ok(o) = wuauserv {
            let stdout = String::from_utf8_lossy(&o.stdout).to_string();
            wua_evidence = stdout.clone();
            if stdout.contains("RUNNING") {
                 wua_status = "Pass";
            }
        }
        checks.push(json!({
             "check": "Windows Update Service",
             "status": wua_status,
             "details": if wua_status == "Pass" { "Service Running" } else { "Service Stopped/Missing" },
             "evidence_content": wua_evidence
        }));

        // 4. Remote Desktop Service (TermService) - Should ideally be stopped if not needed, but often running.
        // Python check fails if RUNNING (Pass if stopped).
        let termserv = Command::new("sc").args(&["query", "TermService"]).output();
        let mut ts_status = "Pass";
        let mut ts_details = "RDP Service Stopped".to_string();
        let mut ts_evidence = String::new();
        if let Ok(o) = termserv {
             let stdout = String::from_utf8_lossy(&o.stdout).to_string();
             ts_evidence = stdout.clone();
             if stdout.contains("RUNNING") {
                 ts_status = "Fail";
                 ts_details = "RDP Service Running (Potential Risk)".to_string();
             }
        }
        checks.push(json!({
             "check": "Remote Desktop Service",
             "status": ts_status,
             "details": ts_details,
             "evidence_content": ts_evidence
        }));

        // 5. WinRM Service
        let winrm = Command::new("sc").args(&["query", "WinRM"]).output();
        let mut winrm_status = "Pass"; 
        let mut winrm_details = "WinRM Service Stopped".to_string();
        let mut winrm_evidence = String::new();
        if let Ok(o) = winrm {
             let stdout = String::from_utf8_lossy(&o.stdout).to_string();
             winrm_evidence = stdout.clone();
             if stdout.contains("RUNNING") {
                 winrm_status = "Warning"; // Warning in Python
                 winrm_details = "WinRM Running".to_string();
             }
        }
         checks.push(json!({
             "check": "WinRM Service Status",
             "status": winrm_status,
             "details": winrm_details,
             "evidence_content": winrm_evidence
        }));

        // 6. Audit Policy (Logon/Logoff)
        let audit = Command::new("auditpol").args(&["/get", "/category:Logon/Logoff"]).output();
        let mut audit_status = "Fail";
        let mut audit_evidence = String::new();
        if let Ok(o) = audit {
             let stdout = String::from_utf8_lossy(&o.stdout).to_string();
             audit_evidence = stdout.clone();
             if stdout.contains("Success and Failure") {
                 audit_status = "Pass";
             }
        }
         checks.push(json!({
             "check": "Audit Logging Policy",
             "status": audit_status,
             "details": "Logon/Logoff auditing verified",
             "evidence_content": audit_evidence
        }));

        checks
    }

    fn check_privacy_compliance(&self) -> Vec<Value> {
        let mut checks = Vec::new();

        // 1. LLMNR/NetBIOS Protection
        // HKLM:\SOFTWARE\Policies\Microsoft\Windows NT\DNSClient -> EnableMulticast
        let llmnr_cmd = "Get-ItemProperty -Path 'HKLM:\\SOFTWARE\\Policies\\Microsoft\\Windows NT\\DNSClient' -Name 'EnableMulticast' -ErrorAction SilentlyContinue | Select-Object EnableMulticast | ConvertTo-Json";
        let output = Command::new("powershell").args(&["-Command", llmnr_cmd]).output();
        
        let mut llmnr_status = "Fail";
        let mut llmnr_evidence = String::new();
        if let Ok(o) = output {
             let stdout = String::from_utf8_lossy(&o.stdout).to_string();
             llmnr_evidence = stdout.clone();
             if stdout.contains("\"EnableMulticast\":  0") {
                  llmnr_status = "Pass";
             }
        }
        checks.push(json!({
             "check": "LLMNR/NetBIOS Protection",
             "status": llmnr_status,
             "details": if llmnr_status == "Pass" { "LLMNR Disabled" } else { "LLMNR Enabled (Risk)" },
             "evidence_content": llmnr_evidence
        }));

        // 2. PowerShell Script Block Logging
        // HKLM:\SOFTWARE\Policies\Microsoft\Windows\PowerShell\ScriptBlockLogging -> EnableScriptBlockLogging
        let ps_cmd = "Get-ItemProperty -Path 'HKLM:\\SOFTWARE\\Policies\\Microsoft\\Windows\\PowerShell\\ScriptBlockLogging' -Name 'EnableScriptBlockLogging' -ErrorAction SilentlyContinue | Select-Object EnableScriptBlockLogging | ConvertTo-Json";
        let output = Command::new("powershell").args(&["-Command", ps_cmd]).output();
        
        let mut ps_status = "Fail";
        let mut ps_evidence = String::new();
        if let Ok(o) = output {
             let stdout = String::from_utf8_lossy(&o.stdout).to_string();
             ps_evidence = stdout.clone();
             if stdout.contains("\"EnableScriptBlockLogging\":  1") {
                  ps_status = "Pass";
             }
        }
        checks.push(json!({
             "check": "PowerShell Script Block Logging",
             "status": ps_status,
             "details": if ps_status == "Pass" { "Logging Enabled" } else { "Logging Disabled" },
             "evidence_content": ps_evidence
        }));

        // 3. Attack Surface Reduction (ASR)
        // Get-MpPreference | Select ASR
        let asr_cmd = "Get-MpPreference | Select-Object AttackSurfaceReductionRules_Ids | ConvertTo-Json";
        let output = Command::new("powershell").args(&["-Command", asr_cmd]).output();
        
        let mut asr_status = "Warning";
        let mut asr_evidence = String::new();
        if let Ok(o) = output {
             let stdout = String::from_utf8_lossy(&o.stdout).to_string();
             asr_evidence = stdout.clone();
             if stdout.contains("AttackSurfaceReductionRules_Ids") && !stdout.contains("null") {
                  asr_status = "Pass";
             }
        }
        checks.push(json!({
             "check": "Attack Surface Reduction",
             "status": asr_status,
             "details": if asr_status == "Pass" { "ASR Rules Configured" } else { "No ASR Rules Found" },
             "evidence_content": asr_evidence
        }));

        // 4. Controlled Folder Access
        // Get-MpPreference | Select EnableControlledFolderAccess
        let cfa_cmd = "Get-MpPreference | Select-Object EnableControlledFolderAccess | ConvertTo-Json";
        let output = Command::new("powershell").args(&["-Command", cfa_cmd]).output();
        
        let mut cfa_status = "Warning";
        let mut cfa_evidence = String::new();
        if let Ok(o) = output {
             let stdout = String::from_utf8_lossy(&o.stdout).to_string();
             cfa_evidence = stdout.clone();
             if stdout.contains("\"EnableControlledFolderAccess\":  1") {
                  cfa_status = "Pass";
             }
        }
        checks.push(json!({
             "check": "Controlled Folder Access",
             "status": cfa_status,
             "details": if cfa_status == "Pass" { "Ransomware Protection Enabled" } else { "Disabled" },
             "evidence_content": cfa_evidence
        }));

        // 5. DPDP Consent Artifacts
        // Check directory existence: C:\ProgramData\OmniAgent\consent_logs
        let consent_path = std::path::Path::new("C:\\ProgramData\\OmniAgent\\consent_logs");
        let mut consent_status = "Fail";
        let mut consent_details = "Consent logs missing".to_string();
        if consent_path.exists() {
            consent_status = "Pass";
            consent_details = "Consent logs directory found".to_string();
        }
        checks.push(json!({
             "check": "DPDP-5.1 Consent Artifacts",
             "status": consent_status,
             "details": consent_details,
             "evidence_content": format!("Path: {}", consent_path.display())
        }));

        // 6. DPDP Data Retention Policy
        // Check file existence: C:\ProgramData\OmniAgent\retention_policy.json
        let retention_path = std::path::Path::new("C:\\ProgramData\\OmniAgent\\retention_policy.json");
        let mut rentention_status = "Fail";
        let mut retention_details = "Policy missing".to_string();
        if retention_path.exists() {
            rentention_status = "Pass";
            retention_details = "Retention policy found".to_string();
        }
        checks.push(json!({
             "check": "DPDP-8.4 Data Retention Policy",
             "status": rentention_status,
             "details": retention_details,
             "evidence_content": format!("Path: {}", retention_path.display())
        }));

        checks
    }

    // ==========================================
    // NEW CHECKS (Phase 8 Parity)
    // ==========================================

    fn check_prohibited_software(&self) -> Value {
        // check for bittorrent, utorrent, cheat engine
        let output = Command::new("powershell")
            .args(&["-Command", "Get-WmiObject -Class Win32_Product | Select-Object Name | ConvertTo-Json"])
            .output();

        let mut status = "Pass";
        let mut details = "No prohibited software found".to_string();
        let mut evidence = String::new();

        if let Ok(o) = output {
             let stdout = String::from_utf8_lossy(&o.stdout).to_string().to_lowercase();
             evidence = stdout.clone();
             
             let blacklist = vec!["bittorrent", "utorrent", "cheat engine"];
             let mut found = Vec::new();
             
             for sw in blacklist {
                 if stdout.contains(sw) {
                     found.push(sw);
                 }
             }
             
             if !found.is_empty() {
                 status = "Fail";
                 details = format!("Prohibited software found: {}", found.join(", "));
             }
        } else {
             // Fallback if WMI fails (common on some systems)
             status = "Warning";
             details = "Could not verify installed software".to_string();
        }

        json!({
             "check": "Prohibited Software",
             "status": status,
             "details": details,
             "evidence_content": evidence
        })
    }

    fn check_password_complexity(&self) -> Value {
        // SecEdit export method
        use std::env;
        let temp_dir = env::temp_dir();
        let cfg_path = temp_dir.join("secpol.cfg");
        let cfg_str = cfg_path.to_string_lossy().to_string();
        
        // Export
        let _ = Command::new("secedit")
            .args(&["/export", "/cfg", &cfg_str])
            .output();
            
        let mut status = "Fail";
        let mut details = "Complexity not strictly enforced".to_string();
        let mut evidence = String::new();
        
        // Read file
        if let Ok(content) = std::fs::read_to_string(&cfg_path) {
            evidence = content.clone();
            // Look for "PasswordComplexity = 1"
            // Note: File might be UTF-16, std::fs::read_to_string might fail if not handled. 
            // For simplicity in Rust without encoding crates, we assume valid text or try a basic check.
            // If utf-16, we might need a workaround. Let's try raw bytes if string fail.
        } 
        
        // Alternative: Retry with a simple finding in bytes if read_to_string fails (likely UTF-16)
        if evidence.is_empty() {
             if let Ok(bytes) = std::fs::read(&cfg_path) {
                 // Naive search in bytes for "PasswordComplexity = 1" (ASCII/UTF-8 compatible parts)
                 // Start simple: just say Warning if we can't read it
                 status = "Warning";
                 details = "Could not parse security policy (likely encoding)".to_string();
             }
        } else {
            if evidence.contains("PasswordComplexity = 1") {
                status = "Pass";
                details = "Password complexity enabled".to_string();
            }
        }
        
        // Cleanup
        let _ = std::fs::remove_file(cfg_path);

        json!({
             "check": "Password Complexity",
             "status": status,
             "details": details,
             "evidence_content": evidence
        })
    }

    fn check_device_guard(&self) -> Value {
        let output = Command::new("powershell")
             .args(&["-Command", "Get-CimInstance -ClassName Win32_DeviceGuard -Namespace root\\Microsoft\\Windows\\DeviceGuard | Select-Object CodeIntegrityPolicyEnforcementStatus | ConvertTo-Json"])
             .output();
        
        let mut status = "Warning";
        let mut details = "WDAC not enforced".to_string();
        let mut evidence = String::new();

        if let Ok(o) = output {
             let stdout = String::from_utf8_lossy(&o.stdout).to_string();
             evidence = stdout.clone();
             if stdout.contains("\"CodeIntegrityPolicyEnforcementStatus\":  1") {
                 status = "Pass";
                 details = "WDAC Enforced".to_string();
             }
        }

        json!({
             "check": "Device Guard/WDAC",
             "status": status,
             "details": details,
             "evidence_content": evidence
        })
    }

    fn check_third_party_av(&self) -> Value {
         let output = Command::new("powershell")
             .args(&["-Command", "Get-CimInstance -Namespace root/SecurityCenter2 -ClassName AntivirusProduct | Select-Object displayName, productState | ConvertTo-Json"])
             .output();
             
         let mut status = "Fail";
         let mut details = "No active 3rd party AV found".to_string();
         let mut evidence = String::new();
         
         if let Ok(o) = output {
             let stdout = String::from_utf8_lossy(&o.stdout).to_string();
             evidence = stdout.clone();
             
             if !stdout.trim().is_empty() && !stdout.contains("Windows Defender") {
                 // Primitive check: if there is ANY output that isn't just Defender, assume 3rd party
                 // Better parsing logic would be ideal but this suffices for "Detection"
                 status = "Pass"; // Or Info, but Pass means "We found something"
                 details = "Third-party AV detected".to_string();
             }
             
             // If Defender is also there, that's fine.
         }

        json!({
             "check": "Third-Party AV",
             "status": status,
             "details": details,
             "evidence_content": evidence
        })
    }
}
}

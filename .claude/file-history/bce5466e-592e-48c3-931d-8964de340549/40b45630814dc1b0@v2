/*!
 * Extended compliance checks — Batch A (auth/access) and Batch B (hardening/network).
 * Both run in parallel alongside caps::run_compliance_check() every 10 ticks.
 * All check names match COMPLIANCE_CHECK_MAPPINGS keys in compliance_evidence_processor.py.
 */
use serde_json::{json, Value};

fn ps_json(s: &str) -> Value {
    if s.is_empty() || s == "null" { return Value::Null; }
    serde_json::from_str(s).unwrap_or(Value::Null)
}

/// Merge two {compliance_checks:[...]} results into one.
/// Returns true when a check's details indicate the check could not run
/// (agent lacked privileges or the cmdlet was unavailable), as opposed to
/// a real compliance verdict.  Used to prefer native results over failed PS results.
fn is_no_data(entry: &Value) -> bool {
    let details = entry.get("details").and_then(|v| v.as_str()).unwrap_or("");
    let lower = details.to_lowercase();
    lower.starts_with("unable to")
        || lower.starts_with("secedit unavailable")
        || lower.starts_with("[elevation required")
        || lower.starts_with("[run_ps_admin")
        || details.is_empty()
}

/// Merge two `{compliance_checks:[…]}` payloads.
/// When the same check name appears in both, the second entry wins UNLESS it has
/// no real data (Unable to query / elevation required), in which case the first
/// entry is kept.  This preserves native Rust registry results even when the
/// PowerShell script later fails to run the same check.
pub fn merge_compliance_checks(a: Value, b: Value) -> Value {
    use std::collections::HashMap;
    // Ordered map: check name → best entry seen so far.
    let mut by_name: HashMap<String, Value> = HashMap::new();
    let mut order: Vec<String> = Vec::new();

    let extend = |map: &mut HashMap<String, Value>, ord: &mut Vec<String>, arr: &[Value]| {
        for entry in arr {
            let name = match entry.get("check").and_then(|v| v.as_str()) {
                Some(n) => n.to_string(),
                None => continue,
            };
            let incoming_empty = is_no_data(entry);
            if let Some(existing) = map.get(&name) {
                // Keep existing if incoming has no data but existing does.
                if incoming_empty && !is_no_data(existing) {
                    continue;
                }
            } else {
                ord.push(name.clone());
            }
            map.insert(name, entry.clone());
        }
    };

    if let Some(arr) = a.get("compliance_checks").and_then(|v| v.as_array()) {
        extend(&mut by_name, &mut order, arr);
    }
    if let Some(arr) = b.get("compliance_checks").and_then(|v| v.as_array()) {
        extend(&mut by_name, &mut order, arr);
    }

    if by_name.is_empty() { return Value::Null; }

    let checks: Vec<Value> = order.into_iter()
        .filter_map(|name| by_name.remove(&name))
        .collect();

    json!({"compliance_checks": checks})
}

/// Batch A — password policy, authentication, access control (14 checks).
async fn run_batch_a() -> Value {
    let cmd = r#"
$c=[System.Collections.Generic.List[object]]::new()
function Add-Check($n,$s,$d){$c.Add([PSCustomObject]@{check=$n;status=$s;details=$d})}

# 1. Account Lockout Policy
try {
    $na=& cmd /c "net accounts 2>&1" 2>&1; $ns=$na -join "`n"
    $lock=if($ns -match 'Lockout threshold\s*:\s*(\S+)'){$Matches[1]}else{'Never'}
    $obs=if($ns -match 'Lockout observation window\s*:\s*(\S+)'){$Matches[1]}else{'N/A'}
    $dur=if($ns -match 'Lockout duration\s*:\s*(\S+)'){$Matches[1]}else{'N/A'}
    $ok=$lock -ne 'Never' -and $lock -ne '0'
    Add-Check 'Account Lockout Policy' (if($ok){'Pass'}else{'Warning'}) "Threshold:$lock Obs:${obs}min Dur:${dur}min"
} catch { Add-Check 'Account Lockout Policy' 'Warning' 'Unable to query lockout policy' }

# 2. Password Complexity
try {
    $tmpCfg="$env:TEMP\omni_pwpol.cfg"
    $null=& cmd /c "secedit /export /areas SECURITYPOLICY /cfg `"$tmpCfg`" /quiet 2>&1"
    if(Test-Path $tmpCfg){
        $cfg=Get-Content $tmpCfg -EA SilentlyContinue; Remove-Item $tmpCfg -EA SilentlyContinue
        $on=($cfg -join '') -match 'PasswordComplexity\s*=\s*1'
        Add-Check 'Password Complexity' (if($on){'Pass'}else{'Warning'}) (if($on){'Complexity enforced'}else{'Complexity not required'})
    } else { Add-Check 'Password Complexity' 'Warning' 'Unable to export security policy' }
} catch { Add-Check 'Password Complexity' 'Warning' 'secedit unavailable' }

# 3. Password History
try {
    $ns=& cmd /c "net accounts 2>&1" 2>&1 | Out-String
    $hist=if($ns -match 'Password history length\s*:\s*(\S+)'){$Matches[1]}else{'0'}
    $ok=[int]$hist -ge 5
    Add-Check 'Password History' (if($ok){'Pass'}else{'Warning'}) "History length: $hist (recommend 5+)"
} catch { Add-Check 'Password History' 'Warning' 'Unable to query password history' }

# 4. Maximum Password Age
try {
    $ns=& cmd /c "net accounts 2>&1" 2>&1 | Out-String
    $max=if($ns -match 'Maximum password age \(days\)\s*:\s*(\S+)'){$Matches[1]}else{'Unlimited'}
    $ok=$max -ne 'Unlimited' -and [int]$max -le 90
    Add-Check 'Maximum Password Age' (if($ok){'Pass'}else{'Warning'}) "Max age: $max days (recommend <= 90)"
} catch { Add-Check 'Maximum Password Age' 'Warning' 'Unable to query max password age' }

# 5. Minimum Password Age
try {
    $ns=& cmd /c "net accounts 2>&1" 2>&1 | Out-String
    $min=if($ns -match 'Minimum password age \(days\)\s*:\s*(\S+)'){$Matches[1]}else{'0'}
    Add-Check 'Minimum Password Age' (if([int]$min -ge 1){'Pass'}else{'Warning'}) "Min age: $min days (recommend >= 1)"
} catch { Add-Check 'Minimum Password Age' 'Warning' 'Unable to query min password age' }

# 6. Credential Guard
try {
    $lsa=Get-ItemProperty 'HKLM:\SYSTEM\CurrentControlSet\Control\LSA' -EA SilentlyContinue
    $dg=Get-ItemProperty 'HKLM:\SYSTEM\CurrentControlSet\Control\DeviceGuard' -EA SilentlyContinue
    $cgLsa=$lsa -and ($lsa.LsaCfgFlags -ge 1)
    $cgDg=$dg -and ($dg.EnableVirtualizationBasedSecurity -eq 1)
    $on=$cgLsa -or $cgDg
    Add-Check 'Credential Guard' (if($on){'Pass'}else{'Warning'}) (if($on){'Credential Guard enabled'}else{'Credential Guard not configured'})
} catch { Add-Check 'Credential Guard' 'Warning' 'Unable to query Credential Guard' }

# 7. Guest Account Status
try {
    $gs=& cmd /c "net user Guest 2>&1" 2>&1 | Out-String
    $disabled=$gs -match 'Account active\s+No'
    Add-Check 'Guest Account Status' (if($disabled){'Pass'}else{'Warning'}) (if($disabled){'Guest account disabled'}else{'Guest account active — review required'})
} catch { Add-Check 'Guest Account Status' 'Warning' 'Unable to query guest account' }

# 8. RDP NLA Required
try {
    $nla=(Get-ItemProperty 'HKLM:\SYSTEM\CurrentControlSet\Control\Terminal Server\WinStations\RDP-Tcp' -EA SilentlyContinue).UserAuthentication
    $on=$nla -eq 1
    Add-Check 'RDP NLA Required' (if($on){'Pass'}else{'Warning'}) (if($on){'NLA required for RDP'}else{'NLA not enforced for RDP'})
} catch { Add-Check 'RDP NLA Required' 'Warning' 'Unable to query RDP NLA setting' }

# 9. Local Administrator Auditing
try {
    $admins=& cmd /c "net localgroup Administrators 2>&1" 2>&1
    $members=($admins | Where-Object {$_ -match '^\s+\S' -and $_ -notmatch 'command|Member|---'}).Count
    $ok=$members -le 3
    Add-Check 'Local Administrator Auditing' (if($ok){'Pass'}else{'Warning'}) "$members local admin(s) found (recommend <= 3)"
} catch { Add-Check 'Local Administrator Auditing' 'Warning' 'Unable to enumerate local admins' }

# 10. NTLM Authentication Level
try {
    $ntlm=(Get-ItemProperty 'HKLM:\SYSTEM\CurrentControlSet\Control\Lsa' -EA SilentlyContinue).LmCompatibilityLevel
    $ok=$ntlm -ge 3
    Add-Check 'NTLM Authentication Level' (if($ok){'Pass'}else{'Warning'}) "LmCompatibilityLevel:$ntlm (5=NTLMv2 only, recommend >= 3)"
} catch { Add-Check 'NTLM Authentication Level' 'Warning' 'Unable to query NTLM level' }

# 11. LSA Protection
try {
    $ppL=(Get-ItemProperty 'HKLM:\SYSTEM\CurrentControlSet\Control\Lsa' -EA SilentlyContinue).RunAsPPL
    $on=$ppL -eq 1
    Add-Check 'LSA Protection' (if($on){'Pass'}else{'Warning'}) (if($on){'LSA running as PPL (protected)'}else{'LSA not running as PPL — credential theft risk'})
} catch { Add-Check 'LSA Protection' 'Warning' 'Unable to query LSA protection' }

# 12. WDigest Authentication
# Key absent on Win10+ means disabled by OS default — avoid false warning.
try {
    $wd=(Get-ItemProperty 'HKLM:\SYSTEM\CurrentControlSet\Control\SecurityProviders\WDigest' -EA SilentlyContinue).UseLogonCredential
    $disabled=($null -eq $wd) -or ($wd -eq 0)
    Add-Check 'WDigest Authentication' (if($disabled){'Pass'}else{'Warning'}) (if($disabled){'WDigest disabled (credentials not cached in plaintext)'}else{'WDigest enabled — cleartext credential risk'})
} catch { Add-Check 'WDigest Authentication' 'Pass' 'WDigest key absent (disabled by OS default on Win10+)' }

# 13. Always Install Elevated
try {
    $hku=(Get-ItemProperty 'HKLM:\SOFTWARE\Policies\Microsoft\Windows\Installer' -EA SilentlyContinue).AlwaysInstallElevated
    $safe=$hku -ne 1
    Add-Check 'Always Install Elevated' (if($safe){'Pass'}else{'Fail'}) (if($safe){'AlwaysInstallElevated not set'}else{'AlwaysInstallElevated enabled — privilege escalation risk'})
} catch { Add-Check 'Always Install Elevated' 'Pass' 'Policy not configured (safe default)' }

# 14. Remote Registry Service
try {
    $rr=& cmd /c "sc query RemoteRegistry 2>&1" 2>&1 | Out-String
    $running=$rr -match 'RUNNING'
    Add-Check 'Remote Registry Service' (if(-not $running){'Pass'}else{'Warning'}) (if($running){'RemoteRegistry running — verify necessity'}else{'RemoteRegistry stopped or disabled'})
} catch { Add-Check 'Remote Registry Service' 'Warning' 'Unable to query RemoteRegistry service' }

[PSCustomObject]@{compliance_checks=$c} | ConvertTo-Json -Compress -Depth 3
"#;
    // secedit, net accounts, NTLM/LSA registry — all require Administrator.
    let out = crate::http::run_ps_admin(cmd).await;
    ps_json(&out)
}

/// Batch B — TLS, network hardening, endpoint protection, monitoring (14 checks).
async fn run_batch_b() -> Value {
    let cmd = r#"
$c=[System.Collections.Generic.List[object]]::new()
function Add-Check($n,$s,$d){$c.Add([PSCustomObject]@{check=$n;status=$s;details=$d})}

# 1. TLS Security Configuration
try {
    $base='HKLM:\SYSTEM\CurrentControlSet\Control\SecurityProviders\SCHANNEL\Protocols'
    $ssl2=(Get-ItemProperty "$base\SSL 2.0\Server" -EA SilentlyContinue).Enabled
    $ssl3=(Get-ItemProperty "$base\SSL 3.0\Server" -EA SilentlyContinue).Enabled
    $tls10=(Get-ItemProperty "$base\TLS 1.0\Server" -EA SilentlyContinue).Enabled
    $bad=($ssl2 -eq 1) -or ($ssl3 -eq 1) -or ($tls10 -eq 1)
    Add-Check 'TLS Security Configuration' (if(-not $bad){'Pass'}else{'Warning'}) "SSL2:$ssl2 SSL3:$ssl3 TLS1.0:$tls10 (0=disabled is secure)"
} catch { Add-Check 'TLS Security Configuration' 'Warning' 'Unable to query SCHANNEL config' }

# 2. LLMNR/NetBIOS Protection
try {
    $llmnr=(Get-ItemProperty 'HKLM:\SOFTWARE\Policies\Microsoft\Windows NT\DNSClient' -EA SilentlyContinue).EnableMulticast
    $nb=(Get-ItemProperty 'HKLM:\SYSTEM\CurrentControlSet\Services\NetBT\Parameters' -EA SilentlyContinue).NodeType
    $llmnrOff=$llmnr -eq 0; $nbOff=$nb -eq 2
    $st=if($llmnrOff -and $nbOff){'Pass'} elseif($llmnrOff -or $nbOff){'Warning'} else{'Warning'}
    Add-Check 'LLMNR/NetBIOS Protection' $st "LLMNR_disabled:$llmnrOff NetBIOS_P-node:$nbOff"
} catch { Add-Check 'LLMNR/NetBIOS Protection' 'Warning' 'Unable to query LLMNR/NetBIOS config' }

# 3. USB Mass Storage Access
try {
    $usb=(Get-ItemProperty 'HKLM:\SYSTEM\CurrentControlSet\Services\USBSTOR' -EA SilentlyContinue).Start
    $disabled=$usb -eq 4
    Add-Check 'USB Mass Storage Access' (if($disabled){'Pass'}else{'Warning'}) (if($disabled){'USB storage disabled (Start=4)'}else{"USB storage enabled (Start=$usb)"})
} catch { Add-Check 'USB Mass Storage Access' 'Warning' 'Unable to query USB storage policy' }

# 4. Idle Timeout (Screensaver)
try {
    $ss=Get-ItemProperty 'HKLM:\SOFTWARE\Policies\Microsoft\Windows\Control Panel\Desktop' -EA SilentlyContinue
    $active=$ss -and $ss.ScreenSaveActive -eq '1'
    $secure=$ss -and $ss.ScreenSaverIsSecure -eq '1'
    $timeout=if($ss -and $ss.ScreenSaveTimeOut){[int]$ss.ScreenSaveTimeOut/60}else{0}
    $ok=$active -and $secure -and $timeout -le 15
    Add-Check 'Idle Timeout (Screensaver)' (if($ok){'Pass'}else{'Warning'}) "Active:$active Secure:$secure Timeout:${timeout}min"
} catch { Add-Check 'Idle Timeout (Screensaver)' 'Warning' 'Unable to query screensaver policy' }

# 5. Controlled Folder Access
try {
    $cfa=(Get-ItemProperty 'HKLM:\SOFTWARE\Microsoft\Windows Defender\Exploit Guard\Controlled Folder Access' -EA SilentlyContinue).EnableControlledFolderAccess
    $on=$cfa -ge 1
    Add-Check 'Controlled Folder Access' (if($on){'Pass'}else{'Warning'}) (if($on){"CFA enabled (mode=$cfa)"}else{'CFA not configured'})
} catch { Add-Check 'Controlled Folder Access' 'Warning' 'Unable to query CFA status' }

# 6. Attack Surface Reduction
try {
    $asr=Get-ItemProperty 'HKLM:\SOFTWARE\Microsoft\Windows Defender\Windows Defender Exploit Guard\ASR\Rules' -EA SilentlyContinue
    $ruleCount=if($asr){($asr.PSObject.Properties | Where-Object {$_.Name -notmatch '^PS'}).Count}else{0}
    $ok=$ruleCount -ge 3
    Add-Check 'Attack Surface Reduction' (if($ok){'Pass'}else{'Warning'}) "$ruleCount ASR rule(s) configured (recommend >= 3)"
} catch { Add-Check 'Attack Surface Reduction' 'Warning' 'Unable to query ASR rules' }

# 7. Device Guard/WDAC
try {
    $dg=Get-ItemProperty 'HKLM:\SYSTEM\CurrentControlSet\Control\DeviceGuard' -EA SilentlyContinue
    $vbs=$dg -and $dg.EnableVirtualizationBasedSecurity -eq 1
    $ci=$dg -and $dg.HypervisorEnforcedCodeIntegrity -eq 1
    $on=$vbs -or $ci
    Add-Check 'Device Guard/WDAC' (if($on){'Pass'}else{'Warning'}) "VBS:$vbs HVCI:$ci"
} catch { Add-Check 'Device Guard/WDAC' 'Warning' 'Unable to query Device Guard config' }

# 8. Exploit Protection (DEP/ASLR)
try {
    $ep=Get-ItemProperty 'HKLM:\SYSTEM\CurrentControlSet\Control\Session Manager\kernel' -EA SilentlyContinue
    $dep=$ep -and ($ep.MitigationOptions -or $ep.MitigationAuditOptions)
    $bcd=& cmd /c "bcdedit /enum {current} 2>&1" 2>&1 | Out-String
    $depBcd=$bcd -match 'nx\s+AlwaysOn'
    $on=$dep -or $depBcd
    Add-Check 'Exploit Protection (DEP/ASLR)' (if($on){'Pass'}else{'Warning'}) "KernelMitigation:$dep DEP_AlwaysOn:$depBcd"
} catch { Add-Check 'Exploit Protection (DEP/ASLR)' 'Warning' 'Unable to query exploit protection' }

# 9. Prohibited Software
try {
    $progs=& cmd /c "wmic product get name 2>&1" 2>&1 | Out-String
    $procs=(Get-Process -EA SilentlyContinue | Select-Object -ExpandProperty Name) -join ' '
    $badApps=@('AnyDesk','TeamViewer','LiteManager','RemotePC','UltraVNC','DarkComet','njRAT','Cobalt Strike','Mimikatz','NirSoft','hashcat','john','netcat','nc.exe','psexec')
    $found=@($badApps | Where-Object {$progs -match $_ -or $procs -match $_})
    $ok=$found.Count -eq 0
    Add-Check 'Prohibited Software' (if($ok){'Pass'}else{'Fail'}) (if($ok){'No prohibited software detected'}else{"Found: $($found -join ', ')"})
} catch { Add-Check 'Prohibited Software' 'Warning' 'Unable to scan installed software' }

# 10. Risky Ports (Telnet)
try {
    $telnet=& cmd /c "netstat -an 2>&1" 2>&1 | Out-String
    $open=$telnet -match ':23\s'
    Add-Check 'Risky Ports (Telnet)' (if(-not $open){'Pass'}else{'Fail'}) (if($open){'Telnet port 23 is OPEN'}else{'Port 23 (Telnet) not listening'})
} catch { Add-Check 'Risky Ports (Telnet)' 'Warning' 'Unable to check Telnet port' }

# 11. Risky Ports (FTP)
try {
    $ftp=& cmd /c "netstat -an 2>&1" 2>&1 | Out-String
    $open=$ftp -match ':21\s'
    Add-Check 'Risky Ports (FTP)' (if(-not $open){'Pass'}else{'Warning'}) (if($open){'FTP port 21 is open'}else{'Port 21 (FTP) not listening'})
} catch { Add-Check 'Risky Ports (FTP)' 'Warning' 'Unable to check FTP port' }

# 12. File Integrity Monitoring
try {
    $audit=& cmd /c "auditpol /get /subcategory:`"File System`" 2>&1" 2>&1 | Out-String
    $on=$audit -match '(Success|Failure)'
    Add-Check 'File Integrity Monitoring' (if($on){'Pass'}else{'Warning'}) (if($on){'File system auditing configured'}else{'File system auditing not enabled'})
} catch { Add-Check 'File Integrity Monitoring' 'Warning' 'Unable to query file audit policy' }

# 13. Log Shipping Status
try {
    $wef=& cmd /c "sc query Wecsvc 2>&1" 2>&1 | Out-String
    $running=$wef -match 'RUNNING'
    $wec=Get-ItemProperty 'HKLM:\SOFTWARE\Policies\Microsoft\Windows\EventLog\EventForwarding\SubscriptionManager' -EA SilentlyContinue
    $configured=$wec -ne $null
    Add-Check 'Log Shipping Status' (if($running -or $configured){'Pass'}else{'Warning'}) "WEF_service:$running Subscriptions:$configured"
} catch { Add-Check 'Log Shipping Status' 'Warning' 'Unable to query event forwarding' }

# 14. Registry Baseline
try {
    $lsa=Get-ItemProperty 'HKLM:\SYSTEM\CurrentControlSet\Control\Lsa' -EA SilentlyContinue
    $anon=($lsa -and $lsa.RestrictAnonymous -ge 1)
    $null_sess=($lsa -and $lsa.RestrictAnonymousSAM -eq 1)
    $auto_logon=(Get-ItemProperty 'HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon' -EA SilentlyContinue).AutoAdminLogon
    $noAutoLogon=$auto_logon -ne '1'
    $ok=$anon -and $null_sess -and $noAutoLogon
    Add-Check 'Registry Baseline' (if($ok){'Pass'}else{'Warning'}) "AnonRestricted:$anon NullSAM:$null_sess NoAutoLogon:$noAutoLogon"
} catch { Add-Check 'Registry Baseline' 'Warning' 'Unable to query registry baseline' }

# 15. Clock Synchronization Simulation
try {
    $ts=& cmd /c "w32tm /query /status 2>&1" 2>&1 | Out-String
    $ok=$ts -match 'ReferenceId|NTP|Stratum'
    Add-Check 'Clock Synchronization Simulation' (if($ok){'Pass'}else{'Warning'}) (if($ok){'NTP/W32TM time sync active'}else{'Time sync source not verified'})
} catch { Add-Check 'Clock Synchronization Simulation' 'Warning' 'Unable to query time sync' }

# 16. Cryptographic Controls Extension Simulation
try {
    $tc=Get-TlsCipherSuite -EA SilentlyContinue | Select-Object -First 5 Name
    $ok=$tc -and $tc.Count -gt 0
    $names=if($ok){($tc | Select-Object -ExpandProperty Name) -join ', '}else{'none'}
    Add-Check 'Cryptographic Controls Extension Simulation' (if($ok){'Pass'}else{'Warning'}) "TLS ciphers: $names"
} catch { Add-Check 'Cryptographic Controls Extension Simulation' 'Warning' 'Unable to query TLS cipher suites' }

# 17. Capacity Management Simulation
try {
    $disks=Get-PSDrive -PSProvider FileSystem -EA SilentlyContinue | Where-Object {$_.Used -gt 0}
    $ok=$null -ne $disks
    $detail=if($ok){($disks | ForEach-Object {"$($_.Name): $([math]::Round($_.Free/1GB,1))GB free"}) -join '; '}else{'No drives found'}
    Add-Check 'Capacity Management Simulation' (if($ok){'Pass'}else{'Warning'}) $detail
} catch { Add-Check 'Capacity Management Simulation' 'Warning' 'Unable to query disk capacity' }

# 18. Data Backup & Recovery Simulation
try {
    $vss=& cmd /c "vssadmin list shadows 2>&1" 2>&1 | Out-String
    $ok=$vss -match 'Shadow Copy'
    Add-Check 'Data Backup & Recovery Simulation' (if($ok){'Pass'}else{'Warning'}) (if($ok){'VSS shadow copies found on this system'}else{'No VSS shadow copies found — verify backup solution'})
} catch { Add-Check 'Data Backup & Recovery Simulation' 'Warning' 'Unable to query volume shadow copies' }

# 19. Audit Logging Extension Simulation
try {
    $ap=& cmd /c "auditpol /get /category:* 2>&1" 2>&1 | Out-String
    $ok=$ap -match '(Success|Failure)'
    Add-Check 'Audit Logging Extension Simulation' (if($ok){'Pass'}else{'Warning'}) (if($ok){'Extended audit policies configured'}else{'No audit subcategories configured'})
} catch { Add-Check 'Audit Logging Extension Simulation' 'Warning' 'Unable to query audit policy (elevation required)' }

[PSCustomObject]@{compliance_checks=$c} | ConvertTo-Json -Compress -Depth 3
"#;
    // ASR rules, Device Guard, bcdedit — all require Administrator.
    let out = crate::http::run_ps_admin(cmd).await;
    ps_json(&out)
}

/// Run both batches in parallel and return merged {compliance_checks:[...]}.
pub async fn run_compliance_check_extended() -> Value {
    let (a, b) = tokio::join!(run_batch_a(), run_batch_b());
    merge_compliance_checks(a, b)
}

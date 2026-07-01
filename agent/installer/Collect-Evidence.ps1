#Requires -RunAsAdministrator
<#
.SYNOPSIS
    Collects Windows compliance evidence and submits to OmniAgent platform.
.DESCRIPTION
    Runs 28 CIS/NIST/PCI compliance checks using PowerShell and submits
    structured evidence to POST /api/powershell-evidence/submit.
    Reads api_base_url and registration_key from config.yaml in the same directory.
.EXAMPLE
    .\Collect-Evidence.ps1
    .\Collect-Evidence.ps1 -ApiUrl http://192.168.1.100:5000 -RegKey reg_abc123
    .\Collect-Evidence.ps1 -DryRun
#>
param(
    [string]$ApiUrl = "",
    [string]$RegKey = "",
    [switch]$DryRun
)
Set-StrictMode -Version Latest
$ErrorActionPreference = "SilentlyContinue"

# Load config.yaml if params not supplied
$ScriptDir  = Split-Path -Parent $MyInvocation.MyCommand.Definition
$ConfigFile = Join-Path $ScriptDir "config.yaml"
if ((-not $ApiUrl -or -not $RegKey) -and (Test-Path $ConfigFile)) {
    Get-Content $ConfigFile | ForEach-Object {
        if ($_ -match '^api_base_url:\s*(.+)$')     { if (-not $ApiUrl) { $ApiUrl = $Matches[1].Trim() } }
        if ($_ -match '^registration_key:\s*(.+)$') { if (-not $RegKey) { $RegKey = $Matches[1].Trim() } }
    }
}
if (-not $ApiUrl) { $ApiUrl = "http://localhost:5000" }
$ApiUrl   = $ApiUrl.TrimEnd("/")
$Hostname = $env:COMPUTERNAME

function Get-SHA256([string]$text) {
    $bytes = [System.Text.Encoding]::UTF8.GetBytes($text)
    $hash  = [System.Security.Cryptography.SHA256]::Create()
    [BitConverter]::ToString($hash.ComputeHash($bytes)).Replace("-","").ToLower()
}

function New-Check([string]$Name, [string]$Status, [string]$Details, [string]$Content) {
    @{
        check            = $Name
        status           = $Status
        details          = $Details
        evidence_content = $Content
        content_hash     = Get-SHA256 $Content
    }
}

# ── Check Functions ───────────────────────────────────────────────────────────

function Check-WindowsFirewall {
    $profiles = Get-NetFirewallProfile -ErrorAction SilentlyContinue
    $content  = $profiles | Select-Object Name, Enabled | Format-Table -AutoSize | Out-String
    $status   = if ($profiles | Where-Object { -not $_.Enabled }) { "Fail" } else { "Pass" }
    New-Check "Windows Firewall Profiles" $status "Profiles enabled: $($profiles.Enabled -join ',')" $content
}

function Check-WindowsDefender {
    $mp      = Get-MpComputerStatus -ErrorAction SilentlyContinue
    $content = $mp | Select-Object AntivirusEnabled, RealTimeProtectionEnabled, AntivirusSignatureAge | Format-Table -AutoSize | Out-String
    $status  = if ($mp -and $mp.AntivirusEnabled -and $mp.RealTimeProtectionEnabled) { "Pass" } else { "Fail" }
    New-Check "Windows Defender Antivirus" $status "AV: $($mp.AntivirusEnabled), RTP: $($mp.RealTimeProtectionEnabled)" $content
}

function Check-PasswordMinLength {
    $content = net accounts 2>&1 | Out-String
    $minLen  = if ($content -match 'Minimum password length\s+(\d+)') { [int]$Matches[1] } else { 0 }
    $status  = if ($minLen -ge 12) { "Pass" } elseif ($minLen -ge 8) { "Warning" } else { "Fail" }
    New-Check "Password Policy (Min Length)" $status "Minimum password length: $minLen" $content
}

function Check-GuestAccount {
    $guest   = Get-LocalUser -Name "Guest" -ErrorAction SilentlyContinue
    $content = $guest | Select-Object Name, Enabled | Format-Table | Out-String
    $status  = if (-not $guest -or -not $guest.Enabled) { "Pass" } else { "Fail" }
    New-Check "Guest Account Disabled" $status "Guest enabled: $($guest.Enabled)" $content
}

function Check-RDPNla {
    $val = $null
    try {
        $val    = (Get-ItemProperty "HKLM:\System\CurrentControlSet\Control\Terminal Server\WinStations\RDP-Tcp" -Name UserAuthentication -ErrorAction Stop).UserAuthentication
        $status = if ($val -eq 1) { "Pass" } else { "Fail" }
        $detail = "NLA enabled: $($val -eq 1)"
    } catch {
        $status = "Warning"; $detail = "Registry key not found"
    }
    $content = "UserAuthentication registry value: $val"
    New-Check "RDP NLA Required" $status $detail $content
}

function Check-BitLocker {
    $vols    = Get-BitLockerVolume -ErrorAction SilentlyContinue
    $content = $vols | Select-Object MountPoint, VolumeStatus, ProtectionStatus | Format-Table | Out-String
    $osVol   = $vols | Where-Object { $_.MountPoint -eq "C:" }
    $status  = if ($osVol -and $osVol.ProtectionStatus -eq "On") { "Pass" } else { "Fail" }
    New-Check "BitLocker Encryption" $status "C: Protection: $($osVol.ProtectionStatus)" $content
}

function Check-SecureBoot {
    $sb = $null
    try {
        $sb     = Confirm-SecureBootUEFI -ErrorAction Stop
        $status = if ($sb) { "Pass" } else { "Fail" }
        $detail = "SecureBoot: $sb"
    } catch {
        $status = "Warning"; $detail = "SecureBoot not supported on this platform"
    }
    New-Check "Secure Boot" $status $detail "SecureBootUEFI: $sb"
}

function Check-WindowsUpdate {
    $svc     = Get-Service -Name wuauserv -ErrorAction SilentlyContinue
    $content = $svc | Select-Object Name, Status, StartType | Format-Table | Out-String
    $status  = if ($svc -and $svc.Status -eq "Running") { "Pass" } elseif ($svc) { "Warning" } else { "Fail" }
    New-Check "Windows Update Service" $status "Status: $($svc.Status)" $content
}

function Check-UAC {
    $val     = (Get-ItemProperty "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\System" -Name EnableLUA -ErrorAction SilentlyContinue).EnableLUA
    $status  = if ($val -eq 1) { "Pass" } else { "Fail" }
    New-Check "User Access Control" $status "EnableLUA: $val" "EnableLUA registry value: $val"
}

function Check-AuditPolicy {
    $content    = (auditpol /get /category:* 2>&1) | Out-String
    $hasSuccess = $content -match 'Success'
    $status     = if ($hasSuccess) { "Pass" } else { "Warning" }
    New-Check "Audit Logging Policy" $status "Audit policy configured: $hasSuccess" $content
}

function Check-NetworkPorts {
    $risky    = @(23, 21, 69, 135, 137, 138, 139, 445, 1433, 3306, 5432)
    $listening = Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue | Where-Object { $_.LocalPort -in $risky }
    $content  = $listening | Select-Object LocalAddress, LocalPort, State | Format-Table | Out-String
    $status   = if (-not $listening) { "Pass" } else { "Fail" }
    New-Check "Risky Network Ports" $status "Risky ports open: $($listening.LocalPort -join ', ')" $content
}

function Check-TLS {
    $tls10   = (Get-ItemProperty "HKLM:\SYSTEM\CurrentControlSet\Control\SecurityProviders\SCHANNEL\Protocols\TLS 1.0\Server" -Name Enabled -ErrorAction SilentlyContinue).Enabled
    $tls12   = (Get-ItemProperty "HKLM:\SYSTEM\CurrentControlSet\Control\SecurityProviders\SCHANNEL\Protocols\TLS 1.2\Server" -Name Enabled -ErrorAction SilentlyContinue).Enabled
    $content = "TLS 1.0 Server Enabled: $tls10`nTLS 1.2 Server Enabled: $tls12"
    $status  = if ($tls10 -eq 0 -and $tls12 -ne 0) { "Pass" } elseif ($tls10 -eq 0) { "Warning" } else { "Fail" }
    New-Check "TLS Security Config" $status "TLS1.0 disabled: $($tls10 -eq 0), TLS1.2 enabled: $($tls12 -ne 0)" $content
}

function Check-ProhibitedSoftware {
    $prohibited = @("uTorrent","BitTorrent","LimeWire","Napster","Kazaa","eMule","Ares")
    $installed  = Get-ItemProperty @(
        "HKLM:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*",
        "HKLM:\Software\Wow6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*"
    ) -ErrorAction SilentlyContinue | Where-Object { $n = $_.DisplayName; $prohibited | Where-Object { $n -like "*$_*" } }
    $content = if ($installed) { $installed | Select-Object DisplayName | Format-Table | Out-String } else { "No prohibited software found." }
    $status  = if (-not $installed) { "Pass" } else { "Fail" }
    New-Check "Prohibited Software" $status "Prohibited apps: $($installed.Count)" $content
}

function Check-MaxPasswordAge {
    $content = net accounts 2>&1 | Out-String
    $age     = if ($content -match 'Maximum password age \(days\)\s+(\d+|Never)') { $Matches[1] } else { "Unknown" }
    $status  = if ($age -ne "Never" -and $age -ne "Unknown" -and [int]$age -le 90) { "Pass" } else { "Fail" }
    New-Check "Maximum Password Age" $status "Maximum password age: $age days" $content
}

function Check-AccountLockout {
    $content   = net accounts 2>&1 | Out-String
    $threshold = if ($content -match 'Lockout threshold\s+(\d+|Never)') { $Matches[1] } else { "Unknown" }
    $status    = if ($threshold -ne "Never" -and $threshold -ne "Unknown" -and [int]$threshold -le 10) { "Pass" } else { "Fail" }
    New-Check "Account Lockout Policy" $status "Lockout threshold: $threshold" $content
}

function Check-PasswordComplexity {
    $tmp     = "$env:TEMP\secpol_$(Get-Random).cfg"
    secedit /export /cfg $tmp /quiet 2>$null
    $content = if (Test-Path $tmp) { Get-Content $tmp | Out-String; Remove-Item $tmp -ErrorAction SilentlyContinue } else { "secedit export failed" }
    $complex = $content -match 'PasswordComplexity = 1'
    $status  = if ($complex) { "Pass" } else { "Fail" }
    New-Check "Password Complexity" $status "PasswordComplexity enabled: $complex" $content
}

function Check-PasswordHistory {
    $content = net accounts 2>&1 | Out-String
    $hist    = if ($content -match 'Length of password history maintained\s+(\d+|None)') { $Matches[1] } else { "Unknown" }
    $status  = if ($hist -ne "None" -and $hist -ne "Unknown" -and [int]$hist -ge 10) { "Pass" } else { "Warning" }
    New-Check "Password History" $status "Password history: $hist" $content
}

function Check-MinPasswordAge {
    $content = net accounts 2>&1 | Out-String
    $age     = if ($content -match 'Minimum password age \(days\)\s+(\d+)') { $Matches[1] } else { "0" }
    $status  = if ([int]$age -ge 1) { "Pass" } else { "Warning" }
    New-Check "Minimum Password Age" $status "Minimum password age: $age days" $content
}

function Check-RemoteDesktopService {
    $svc        = Get-Service -Name TermService -ErrorAction SilentlyContinue
    $rdpEnabled = (Get-ItemProperty "HKLM:\System\CurrentControlSet\Control\Terminal Server" -Name fDenyTSConnections -ErrorAction SilentlyContinue).fDenyTSConnections
    $content    = "Service: $($svc.Status), fDenyTSConnections: $rdpEnabled"
    $status     = if ($rdpEnabled -eq 1) { "Pass" } else { "Warning" }
    New-Check "Remote Desktop Service" $status "RDP connections denied: $($rdpEnabled -eq 1)" $content
}

function Check-SMBv1 {
    $feature = Get-WindowsOptionalFeature -Online -FeatureName SMB1Protocol -ErrorAction SilentlyContinue
    $content = "SMB1Protocol State: $($feature.State)"
    $status  = if ($feature.State -eq "Disabled") { "Pass" } else { "Fail" }
    New-Check "SMBv1 Protocol Disabled" $status "SMBv1 disabled: $($feature.State -eq 'Disabled')" $content
}

function Check-LLMNR {
    $llmnr   = (Get-ItemProperty "HKLM:\SOFTWARE\Policies\Microsoft\Windows NT\DNSClient" -Name EnableMulticast -ErrorAction SilentlyContinue).EnableMulticast
    $nb      = (Get-ItemProperty "HKLM:\SYSTEM\CurrentControlSet\Services\NetBT\Parameters\Interfaces" -ErrorAction SilentlyContinue)
    $content = "LLMNR EnableMulticast: $llmnr"
    $status  = if ($llmnr -eq 0) { "Pass" } else { "Warning" }
    New-Check "LLMNR/NetBIOS Protection" $status "LLMNR disabled: $($llmnr -eq 0)" $content
}

function Check-PSScriptBlockLogging {
    $val     = (Get-ItemProperty "HKLM:\SOFTWARE\Policies\Microsoft\Windows\PowerShell\ScriptBlockLogging" -Name EnableScriptBlockLogging -ErrorAction SilentlyContinue).EnableScriptBlockLogging
    $content = "EnableScriptBlockLogging: $val"
    $status  = if ($val -eq 1) { "Pass" } else { "Fail" }
    New-Check "PowerShell Script Block Logging" $status "Script Block Logging: $($val -eq 1)" $content
}

function Check-WinRM {
    $svc     = Get-Service -Name WinRM -ErrorAction SilentlyContinue
    $content = $svc | Select-Object Name, Status, StartType | Format-Table | Out-String
    $status  = if ($svc -and $svc.Status -eq "Stopped") { "Pass" } elseif ($svc) { "Warning" } else { "Pass" }
    New-Check "WinRM Service Status" $status "WinRM Status: $($svc.Status)" $content
}

function Check-CredentialGuard {
    $dg      = Get-CimInstance -ClassName Win32_DeviceGuard -Namespace root\Microsoft\Windows\DeviceGuard -ErrorAction SilentlyContinue
    $content = $dg | Format-List | Out-String
    $enabled = $dg.SecurityServicesRunning -contains 1
    $status  = if ($enabled) { "Pass" } else { "Warning" }
    New-Check "Credential Guard" $status "Credential Guard running: $enabled" $content
}

function Check-DeviceGuard {
    $dg      = Get-CimInstance -ClassName Win32_DeviceGuard -Namespace root\Microsoft\Windows\DeviceGuard -ErrorAction SilentlyContinue
    $content = $dg | Format-List | Out-String
    $enabled = $dg.CodeIntegrityPolicyEnforcementStatus -ge 1
    $status  = if ($enabled) { "Pass" } else { "Warning" }
    New-Check "Device Guard/WDAC" $status "WDAC enforced: $enabled" $content
}

function Check-ExploitProtection {
    $mit     = Get-ProcessMitigation -System -ErrorAction SilentlyContinue
    $dep     = $mit.DEP.Enable -eq "ON"
    $aslr    = $mit.ASLR.ForceRelocateImages -eq "ON"
    $content = $mit | Format-List | Out-String
    $status  = if ($dep -and $aslr) { "Pass" } elseif ($dep -or $aslr) { "Warning" } else { "Fail" }
    New-Check "Exploit Protection (DEP/ASLR)" $status "DEP: $dep, ASLR: $aslr" $content
}

function Check-ASR {
    $prefs   = Get-MpPreference -ErrorAction SilentlyContinue
    $rules   = $prefs.AttackSurfaceReductionRules_Ids
    $content = "ASR Rules: $($rules -join ', ')"
    $status  = if ($rules -and $rules.Count -gt 0) { "Pass" } else { "Warning" }
    New-Check "Attack Surface Reduction" $status "ASR rules count: $($rules.Count)" $content
}

function Check-ControlledFolderAccess {
    $prefs   = Get-MpPreference -ErrorAction SilentlyContinue
    $cfa     = $prefs.EnableControlledFolderAccess
    $content = "EnableControlledFolderAccess: $cfa"
    $status  = if ($cfa -eq 1) { "Pass" } elseif ($cfa -eq 2) { "Warning" } else { "Fail" }
    New-Check "Controlled Folder Access" $status "CFA mode: $cfa" $content
}

# ── Main Execution ────────────────────────────────────────────────────────────

Write-Host "`n[OmniAgent] Collecting Windows compliance evidence for $Hostname..." -ForegroundColor Cyan

$checks = @(
    Check-WindowsFirewall
    Check-WindowsDefender
    Check-PasswordMinLength
    Check-GuestAccount
    Check-RDPNla
    Check-BitLocker
    Check-SecureBoot
    Check-WindowsUpdate
    Check-UAC
    Check-AuditPolicy
    Check-NetworkPorts
    Check-TLS
    Check-ProhibitedSoftware
    Check-MaxPasswordAge
    Check-AccountLockout
    Check-PasswordComplexity
    Check-PasswordHistory
    Check-MinPasswordAge
    Check-RemoteDesktopService
    Check-SMBv1
    Check-LLMNR
    Check-PSScriptBlockLogging
    Check-WinRM
    Check-CredentialGuard
    Check-DeviceGuard
    Check-ExploitProtection
    Check-ASR
    Check-ControlledFolderAccess
)

foreach ($c in $checks) {
    $color = switch ($c.status) { "Pass" { "Green" } "Warning" { "Yellow" } default { "Red" } }
    Write-Host ("  [{0,-7}] {1}" -f $c.status, $c.check) -ForegroundColor $color
}

$pass    = ($checks | Where-Object { $_.status -eq "Pass" }).Count
$fail    = ($checks | Where-Object { $_.status -eq "Fail" }).Count
$warning = ($checks | Where-Object { $_.status -eq "Warning" }).Count
Write-Host "`n  Results: $pass pass  $warning warning  $fail fail  (total: $($checks.Count))`n" -ForegroundColor Cyan

if ($DryRun) {
    Write-Host "[DryRun] Skipping submission." -ForegroundColor Yellow
    exit 0
}

$payload = @{ hostname = $Hostname; checks = $checks } | ConvertTo-Json -Depth 5
$headers = @{ "Content-Type" = "application/json"; "X-Registration-Key" = $RegKey }

try {
    $resp = Invoke-RestMethod -Uri "$ApiUrl/api/powershell-evidence/submit" `
        -Method POST -Headers $headers -Body $payload -TimeoutSec 30
    Write-Host "[OK] $($resp.accepted) checks accepted by $ApiUrl" -ForegroundColor Green
} catch {
    Write-Host "[ERROR] Submission failed: $_" -ForegroundColor Red
    exit 1
}

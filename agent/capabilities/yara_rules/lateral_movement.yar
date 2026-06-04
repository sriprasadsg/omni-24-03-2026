"""
YARA Rule: Lateral Movement Techniques
Detects PsExec, WMI remote execution, Pass-the-Hash, remote service creation,
DCOM abuse, and other lateral movement indicators.
"""

rule PsExecLateralMovement {
    meta:
        description = "PsExec and variants used for lateral movement"
        severity = "high"
        mitre = "T1021.002 - Remote Services: SMB/Windows Admin Shares"
        author = "Open Threat Research"
    strings:
        $psexec1 = "psexec" nocase
        $psexec2 = "PsExec Service" nocase
        $psexec3 = "PSEXESVC" nocase
        $psexec4 = "psexesvc.exe" nocase
        $sysinternals = "Sysinternals" nocase
        $remote_svc = "\\\\" nocase
        $ipc_share = "IPC$" nocase
        $admin_share1 = "ADMIN$" nocase
        $admin_share2 = "C$" nocase
    condition:
        any of ($psexec*) or ($sysinternals and ($remote_svc or $admin_share1 or $admin_share2))
}

rule WMIRemoteExecution {
    meta:
        description = "WMI-based remote execution for lateral movement"
        severity = "high"
        mitre = "T1021.006 - Remote Services: Windows Remote Management"
    strings:
        $wmi1 = "wmic /node:" nocase
        $wmi2 = "Win32_Process.Create" nocase
        $wmi3 = "wmic process call create" nocase
        $wmi4 = "Invoke-WmiMethod" nocase
        $wmi5 = "Get-WmiObject" nocase
        $wmi6 = "New-Object System.Management.ManagementObject" nocase
        $wmiprvse = "wmiprvse.exe" nocase
        $wmi_remote = "winmgmt" nocase
    condition:
        2 of them
}

rule PassTheHashPatterns {
    meta:
        description = "Pass-the-Hash attack patterns and tools"
        severity = "critical"
        mitre = "T1550.002 - Use Alternate Authentication Material: Pass the Hash"
    strings:
        $pth1 = "Pass-the-Hash" nocase
        $pth2 = "pth-winexe" nocase
        $pth3 = "pth-smbclient" nocase
        $pth4 = "sekurlsa::pth" nocase
        $pth5 = "/pth" nocase
        $ntlm_hash = /[0-9a-fA-F]{32}:[0-9a-fA-F]{32}/  // LM:NTLM hash format
        $overpass = "Overpass-the-Hash" nocase
        $pass_ticket = "Pass-the-Ticket" nocase
    condition:
        any of ($pth*) or $ntlm_hash or $overpass or $pass_ticket
}

rule RemoteServiceCreation {
    meta:
        description = "Remote service creation for lateral movement"
        severity = "high"
        mitre = "T1021.002 - Remote Services"
    strings:
        $svc1 = "sc \\\\.*create" nocase
        $svc2 = "sc.exe \\\\.*create" nocase
        $svc3 = "CreateService" nocase
        $svc4 = "OpenSCManager" nocase
        $svc5 = "StartService" nocase
        $svc6 = "SERVICE_DEMAND_START" nocase
        $impacket = "impacket" nocase
        $atexec = "atexec.py" nocase
        $smbexec = "smbexec.py" nocase
    condition:
        any of ($impacket, $atexec, $smbexec) or (2 of ($svc*))
}

rule DCOMAbuse {
    meta:
        description = "DCOM (Distributed COM) abuse for lateral movement"
        severity = "high"
        mitre = "T1021.003 - Remote Services: Distributed Component Object Model"
    strings:
        $dcom1 = "MMC20.Application" nocase
        $dcom2 = "ShellWindows" nocase
        $dcom3 = "ShellBrowserWindow" nocase
        $dcom4 = "Excel.Application" nocase
        $dcom5 = "Invoke-DCOM" nocase
        $dcom6 = "Activator.CreateInstance" nocase
        $dcom7 = "[activator]::CreateInstance" nocase
    condition:
        any of them
}

rule KerberostingAndASREP {
    meta:
        description = "Kerberoasting and AS-REP roasting attack patterns"
        severity = "critical"
        mitre = "T1558.003 - Steal or Forge Kerberos Tickets: Kerberoasting"
    strings:
        $kerb1 = "Invoke-Kerberoast" nocase
        $kerb2 = "Get-DomainSPNTicket" nocase
        $kerb3 = "Request-SPNTicket" nocase
        $kerb4 = "kerberoast" nocase
        $asrep1 = "ASREPRoasting" nocase
        $asrep2 = "Get-ASREPHash" nocase
        $asrep3 = "Rubeus asreproast" nocase
        $rubeus = "Rubeus" nocase
        $impacket_kerb = "GetUserSPNs.py" nocase
    condition:
        any of them
}

rule BloodhoundADRecon {
    meta:
        description = "BloodHound/SharpHound Active Directory reconnaissance"
        severity = "high"
        mitre = "T1069.002 - Permission Groups Discovery: Domain Groups"
    strings:
        $bh1 = "bloodhound" nocase
        $bh2 = "sharphound" nocase
        $bh3 = "BloodHound.ps1" nocase
        $bh4 = "Invoke-BloodHound" nocase
        $bh5 = "CollectionMethod All" nocase
        $bh6 = "Get-BloodHoundData" nocase
        $ad_enum1 = "Get-DomainController" nocase
        $ad_enum2 = "Get-DomainUser" nocase
        $ad_enum3 = "Get-DomainGroup" nocase
    condition:
        any of ($bh*) or (2 of ($ad_enum*))
}

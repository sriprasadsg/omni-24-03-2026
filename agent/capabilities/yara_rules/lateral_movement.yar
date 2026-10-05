/*
YARA Rule: Lateral Movement Techniques
Detects PsExec, WMI remote execution, Pass-the-Hash, remote service creation,
DCOM abuse, and other lateral movement indicators.
*/

rule PsExecLateralMovement {
    meta:
        description = "PsExec and variants used for lateral movement"
        severity = "high"
        mitre = "T1021.002 - Remote Services: SMB/Windows Admin Shares"
        author = "Open Threat Research"
    strings:
        // A bare "psexec" substring hits identifiers like "mapsExec"/"PSExecution", and
        // "\\" and "C$" occur in nearly every binary — require PsExec-specific artifacts.
        $psexec1 = "psexec.exe" nocase
        $psexec2 = "PsExec Service" nocase
        $psexec3 = "PSEXESVC" nocase
        $psexec4 = "psexesvc.exe" nocase
        $psexec_word = "psexec" nocase fullword
        $sysinternals = "Sysinternals" nocase
        $ipc_share = "IPC$" nocase
        $admin_share1 = "ADMIN$" nocase
    condition:
        any of ($psexec1, $psexec2, $psexec3, $psexec4) or ($psexec_word and $sysinternals and ($ipc_share or $admin_share1))
}

rule WMIRemoteExecution {
    meta:
        description = "WMI-based remote execution for lateral movement"
        severity = "high"
        mitre = "T1021.006 - Remote Services: Windows Remote Management"
    strings:
        // Admin tooling and bundled PowerShell docs mention these cmdlets/classes, so a
        // cmdlet + class pair must also target a remote host to count as lateral movement.
        $wmic_node = "wmic /node:" nocase
        $wmic_create = "wmic process call create" nocase
        $wmi_create = "Win32_Process.Create" nocase
        $ps_invoke = "Invoke-WmiMethod" nocase
        $ps_object = "New-Object System.Management.ManagementObject" nocase
        $remote = "-ComputerName" nocase
    condition:
        // Size cap: the only benign hits were 200+ MB runtimes bundling PowerShell docs
        // (e.g. Claude Code); WMI lateral-movement scripts and tools are small.
        filesize < 20MB and (any of ($wmic_*) or ($wmi_create and any of ($ps_*) and $remote))
}

rule PassTheHashPatterns {
    meta:
        description = "Pass-the-Hash attack patterns and tools"
        severity = "critical"
        mitre = "T1550.002 - Use Alternate Authentication Material: Pass the Hash"
    strings:
        // "/pth" is a common path fragment and any "32hex:32hex" pair (checksums) matched
        // the old hash regex; require PtH tooling or a full pwdump/secretsdump line.
        $pth_tool1 = "pth-winexe" nocase
        $pth_tool2 = "pth-smbclient" nocase
        $pth_tool3 = "sekurlsa::pth" nocase
        $pwdump_line = /:[0-9a-fA-F]{32}:[0-9a-fA-F]{32}:::/  // user:rid:LM:NT::: dump format
        $term1 = "Pass-the-Hash" nocase
        $term2 = "Overpass-the-Hash" nocase
        $term3 = "Pass-the-Ticket" nocase
    condition:
        any of ($pth_tool*) or $pwdump_line or 2 of ($term*)
}

rule RemoteServiceCreation {
    meta:
        description = "Remote service creation for lateral movement"
        severity = "high"
        mitre = "T1021.002 - Remote Services"
    strings:
        // The old "sc \\\\.*create" text strings were literal (".*" never matched); the
        // service-control APIs alone are used by every Windows service/updater (e.g. Chrome).
        $sc_remote = /sc(\.exe)?\s+\\\\[^\s\\]+\s+create/ nocase  // sc \\HOST create
        $impacket = "impacket" nocase fullword  // not "MbimPacketService" (libmbim)
        $atexec = "atexec.py" nocase
        $smbexec = "smbexec.py" nocase
    condition:
        any of them
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
        // Activator.CreateInstance is in nearly every .NET assembly and ShellWindows/Excel
        // automation is common in Office tooling — require a DCOM target plus instantiation.
        any of ($dcom1, $dcom5) or (any of ($dcom2, $dcom3, $dcom4) and any of ($dcom6, $dcom7))
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
        $rubeus = "Rubeus.exe" nocase  // bare "Rubeus" also appears in word/name lists (e.g. Node ICU data)
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

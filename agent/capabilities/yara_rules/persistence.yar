/*
YARA Rule: Persistence Mechanisms
Detects registry run keys, scheduled task manipulation, startup folder abuse,
WMI event subscriptions, DLL hijacking, and bootkit indicators.
*/

rule RegistryRunKeyPersistence {
    meta:
        description = "Registry Run/RunOnce key modifications for persistence"
        severity = "high"
        mitre = "T1547.001 - Registry Run Keys / Startup Folder"
        author = "Open Threat Research"
    strings:
        $run1 = "SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Run" nocase
        $run2 = "SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\RunOnce" nocase
        $run3 = "HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run" nocase
        $run4 = "HKLM\\Software\\Microsoft\\Windows\\CurrentVersion\\Run" nocase
        $run5 = "CurrentVersion\\Run\\" nocase
        // Were literal text strings (".*" never matched); now real regexes.
        $runkey_ps = /Set-ItemProperty\s+-Path\s+\S*\\Run/ nocase
        $runkey_reg = /reg(\.exe)?\s+add\s+\S*\\Run/ nocase
    condition:
        any of them
}

rule ScheduledTaskPersistence {
    meta:
        description = "Malicious scheduled task creation for persistence"
        severity = "high"
        mitre = "T1053.005 - Scheduled Task/Job: Scheduled Task"
    strings:
        // "TaskScheduler"/"ITaskService" are ordinary class/COM names (Chrome, Node) and a
        // single cmdlet name appears in bundled PowerShell docs — require task creation.
        $create1 = "schtasks /create" nocase
        $create2 = "schtasks.exe /create" nocase
        $ps_register = "Register-ScheduledTask" nocase
        $ps_action = "New-ScheduledTaskAction" nocase
        $ps_trigger = "New-ScheduledTaskTrigger" nocase
        $xml_task = "<Task version=\"1.2\"" nocase
        $xml_exec = /<Exec>\s*<Command>/ nocase
        $trigger_logon = "<LogonTrigger>" nocase
        $trigger_boot = "<BootTrigger>" nocase
    condition:
        any of ($create*) or ($ps_register and $ps_action and $ps_trigger) or ($xml_task and ($xml_exec or $trigger_logon or $trigger_boot))
}

rule StartupFolderAbuse {
    meta:
        description = "Files dropped in Windows startup folders"
        severity = "medium"
        mitre = "T1547.001 - Boot or Logon Autostart Execution"
    strings:
        $startup1 = "\\AppData\\Roaming\\Microsoft\\Windows\\Start Menu\\Programs\\Startup\\" nocase
        $startup2 = "\\ProgramData\\Microsoft\\Windows\\Start Menu\\Programs\\StartUp\\" nocase
        $startup3 = "shell:startup" nocase
        $startup4 = "shell:common startup" nocase
        $lnk_header = { 4C 00 00 00 01 14 02 00 }  // .lnk file magic
    condition:
        any of ($startup*) or $lnk_header at 0  // a shortcut file itself, not LNK bytes embedded anywhere
}

rule WMIEventSubscriptionPersistence {
    meta:
        description = "WMI event subscription-based persistence mechanism"
        severity = "critical"
        mitre = "T1546.003 - Event Triggered Execution: Windows Management Instrumentation Event Subscription"
    strings:
        $wmi_sub1 = "__EventFilter" nocase
        $wmi_sub2 = "__EventConsumer" nocase
        $wmi_sub3 = "__FilterToConsumerBinding" nocase
        $wmi_sub4 = "CommandLineEventConsumer" nocase
        $wmi_sub5 = "ActiveScriptEventConsumer" nocase
        $wmi_sub6 = "New-Object -ComObject \"WbemScripting" nocase
        $wmi_sub7 = "Set-WMIInstance" nocase
        $invoke_wmi = "Invoke-WMIEvent" nocase
        $wmi_ps = "Subscribe-WmiEvent" nocase
    condition:
        2 of them
}

rule DLLSearchOrderHijacking {
    meta:
        description = "DLL search order hijacking / phantom DLL loading"
        severity = "high"
        mitre = "T1574.001 - Hijack Execution Flow: DLL Search Order Hijacking"
    strings:
        $dll_hijack1 = "DLL Hijacking" nocase
        $dll_hijack2 = "DLL planting" nocase
        $phantom1 = "wlbsctrl.dll" nocase
        $phantom2 = "ualapi.dll" nocase
        $phantom3 = "TSMSISrv.dll" nocase
        $phantom4 = "RpcEptMapper.dll" nocase
        // CRYPTBASE.dll (a normal import) and DllMain + GetProcAddress (present in every
        // Windows DLL) were dropped — they matched essentially all PE files.
    condition:
        any of ($dll_hijack*) or (2 of ($phantom*))
}

rule BootkitAndMBRInfection {
    meta:
        description = "Bootkit, MBR/VBR infection and UEFI persistence indicators"
        severity = "critical"
        mitre = "T1542.003 - Pre-OS Boot: Bootkit"
    strings:
        // "55 AA" anywhere + EFI_SYSTEM_TABLE matched every EFI tool, BOOTMGR is the
        // legitimate Windows boot manager, and "TDL4" is an Intel GPU counter name in
        // Mesa's Vulkan driver — keep only distinctive family names, as whole words.
        $bootkit1 = "ZeroAccess" fullword
        $bootkit3 = "Mebroot" fullword
        $bootkit4 = "Petya" fullword
        $grub_evil = "Evil GRUB" nocase
    condition:
        any of ($bootkit*) or $grub_evil
}

rule ServicePersistence {
    meta:
        description = "Malicious Windows service installation for persistence"
        severity = "high"
        mitre = "T1543.003 - Create or Modify System Process: Windows Service"
    strings:
        $svc1 = "OpenSCManager" nocase
        $svc2 = "CreateService" nocase
        $svc3 = "ChangeServiceConfig" nocase
        $svc_key = "SYSTEM\\CurrentControlSet\\Services\\" nocase
        $service_dll = "ServiceDll" nocase
        $malicious_svc1 = "VSSMini" fullword
        // "NetMan" is the legitimate Network Connections service (and matched "NETMAN" in
        // libLLVM); service APIs / ImagePath alone are used by every service installer.
    condition:
        ((2 of ($svc1, $svc2, $svc3)) and $service_dll) or ($svc_key and $service_dll) or $malicious_svc1
}

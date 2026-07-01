"""
YARA Rule: Persistence Mechanisms
Detects registry run keys, scheduled task manipulation, startup folder abuse,
WMI event subscriptions, DLL hijacking, and bootkit indicators.
"""

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
        $runkey_ps = "Set-ItemProperty -Path.*Run" nocase
        $runkey_reg = "reg add.*\\\\Run\\" nocase
    condition:
        any of them
}

rule ScheduledTaskPersistence {
    meta:
        description = "Malicious scheduled task creation for persistence"
        severity = "high"
        mitre = "T1053.005 - Scheduled Task/Job: Scheduled Task"
    strings:
        $schtask1 = "schtasks /create" nocase
        $schtask2 = "SchTasks.exe" nocase
        $schtask3 = "New-ScheduledTask" nocase
        $schtask4 = "Register-ScheduledTask" nocase
        $schtask5 = "ITaskService" nocase
        $schtask6 = "TaskScheduler" nocase
        $xml_task = "<Task version=\"1.2\"" nocase
        $xml_exec = "<Exec><Command>" nocase
        $trigger_logon = "<LogonTrigger>" nocase
        $trigger_boot = "<BootTrigger>" nocase
    condition:
        any of ($schtask*) or ($xml_task and ($xml_exec or $trigger_logon or $trigger_boot))
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
        any of ($startup*) or $lnk_header
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
        $phantom5 = "CRYPTBASE.dll" nocase
        $side_load = "DllMain" nocase
        $dll_export = "GetProcAddress" nocase
    condition:
        any of ($dll_hijack*) or (2 of ($phantom*)) or ($side_load and $dll_export)
}

rule BootkitAndMBRInfection {
    meta:
        description = "Bootkit, MBR/VBR infection and UEFI persistence indicators"
        severity = "critical"
        mitre = "T1542.003 - Pre-OS Boot: Bootkit"
    strings:
        $mbr1 = { 55 AA }  // MBR signature at offset 510
        $uefi1 = "EFI_SYSTEM_TABLE" nocase
        $bootkit1 = "ZeroAccess" nocase
        $bootkit2 = "TDL4" nocase
        $bootkit3 = "Mebroot" nocase
        $bootkit4 = "Petya" nocase
        $vbr = "BOOTMGR" nocase
        $grub_evil = "Evil GRUB" nocase
    condition:
        any of ($bootkit*) or $grub_evil or ($mbr1 and $uefi1)
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
        $image_path = "ImagePath" nocase
        $service_dll = "ServiceDll" nocase
        $malicious_svc1 = "VSSMini" nocase
        $malicious_svc2 = "NetMan" nocase
    condition:
        ($svc1 and $svc2) or ($svc_key and ($image_path or $service_dll))
}

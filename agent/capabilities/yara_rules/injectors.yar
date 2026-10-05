/*
YARA Rule: Process Injection Techniques
Detects shellcode injection patterns and memory manipulation APIs
used by malware and dual-use tools.
*/

rule ProcessInjectionAPIs {
    meta:
        description = "Import of known process injection Windows APIs"
        severity = "high"
        technique = "T1055 - Process Injection"
    strings:
        $api1 = "VirtualAllocEx" nocase
        $api2 = "WriteProcessMemory" nocase
        $api3 = "CreateRemoteThread" nocase
        $api4 = "NtCreateThreadEx" nocase
        $api5 = "RtlCreateUserThread" nocase
        $api6 = "QueueUserAPC" nocase
        $api7 = "SetWindowsHookEx" nocase
        $api8 = "NtMapViewOfSection" nocase
        $api9 = "ZwUnmapViewOfSection" nocase
    condition:
        3 of them
}

rule ReflectiveDLLInjection {
    meta:
        description = "Reflective DLL injection bootstrap pattern"
        severity = "critical"
        technique = "T1055.001 - Reflective DLL Injection"
    strings:
        $reflective = "ReflectiveLoader" nocase
        $reflective2 = { 52 65 66 6C 65 63 74 69 76 65 4C 6F 61 64 65 72 }
        $pe_header = { 4D 5A }   // MZ
        // A bare 0x90 run is ordinary GCC/MinGW alignment padding in PE files, so it
        // is no longer a standalone trigger.
    condition:
        ($pe_header at 0) and any of ($reflective*)
}

rule ShellcodePatterns {
    meta:
        description = "Generic shellcode / raw execution patterns"
        severity = "high"
        technique = "T1059 - Command and Scripting Interpreter"
    strings:
        // 2-byte opcodes (FC E8, 31 C9, ...) occur thousands of times in any compiled
        // binary, so match full well-known stager prologues and API-hashing loops instead.
        $msf_x86 = { FC E8 82 00 00 00 60 89 E5 31 C0 64 8B 50 30 }  // msfvenom x86 block_api prologue
        $msf_x64 = { FC 48 83 E4 F0 E8 C0 00 00 00 41 51 41 50 52 }  // msfvenom x64 block_api prologue
        $ror13_x86 = { C1 CF 0D 01 C7 }                              // ror edi,0Dh / add edi,eax (API hashing)
        $ror13_x64 = { 41 C1 C9 0D 41 01 C1 }                        // ror r9d,0Dh / add r9d,eax
        $peb_x86 = { 64 A1 30 00 00 00 }                             // mov eax, fs:[30h] (PEB walk)
        $peb_x64 = { 65 48 8B 04 25 60 00 00 00 }                    // mov rax, gs:[60h] (PEB walk)
    condition:
        any of ($msf_*) or (any of ($ror13_*) and any of ($peb_*))
}

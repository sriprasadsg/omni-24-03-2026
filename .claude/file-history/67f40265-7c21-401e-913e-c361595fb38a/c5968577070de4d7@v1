"""
YARA Rule: Process Injection Techniques
Detects shellcode injection patterns and memory manipulation APIs
used by malware and dual-use tools.
"""

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
        $shellcode_nop = { 90 90 90 90 90 90 90 90 }  // NOP sled
    condition:
        ($pe_header at 0) and (any of ($reflective*) or $shellcode_nop)
}

rule ShellcodePatterns {
    meta:
        description = "Generic shellcode / raw execution patterns"
        severity = "high"
        technique = "T1059 - Command and Scripting Interpreter"
    strings:
        // Common shellcode stub patterns
        $fc_e8 = { FC E8 }
        $eb_fe = { EB FE }        // infinite loop / landing NOP
        $jmp_esp = { FF E4 }     // JMP ESP
        $call_pop = { E8 00 00 00 00 }  // CALL + POP for PIC shellcode
        $xor_ecx = { 31 C9 }    // XOR ECX,ECX
    condition:
        2 of them
}

"""
YARA Rule: Credential Dumper Signatures
Detects Mimikatz, LaZagne, and similar dual-use credential-extraction tools.
"""

rule MimikatzSignatures {
    meta:
        description = "Mimikatz credential dumper detection"
        severity = "critical"
        tool = "Mimikatz"
        author = "Open Threat Research"
        mitre = "T1003.001 - LSASS Memory"
    strings:
        $mimikatz1 = "mimikatz" nocase
        $mimikatz2 = "mimilib" nocase
        $mimikatz3 = "sekurlsa::" nocase
        $mimikatz4 = "privilege::debug" nocase
        $mimikatz5 = "lsadump::" nocase
        $mimikatz6 = "kerberos::ptt" nocase
        $mimikatz7 = "token::elevate" nocase
        $mimikatz8 = "Benjamin DELPY" nocase
        $mimikatz9 = "gentilkiwi" nocase
        // SHA-256 hash of common mimikatz binary (truncated for YARA)
        $hash_pattern = { 4D 49 4D 49 4B 41 54 5A }  // "MIMIKATZ" bytes
    condition:
        any of them
}

rule LaZagneCredentialDumper {
    meta:
        description = "LaZagne password recovery tool"
        severity = "critical"
        tool = "LaZagne"
        mitre = "T1555 - Credentials from Password Stores"
    strings:
        $lazagne1 = "lazagne" nocase
        $lazagne2 = "AESModeOfOperationCBC" nocase
        $lazagne3 = "credentialmanager" nocase
        $lazagne4 = "passwordmgr" nocase
    condition:
        any of them
}

rule LSASSMemoryAccess {
    meta:
        description = "Direct LSASS memory access pattern — credential dump indicator"
        severity = "critical"
        mitre = "T1003.001"
    strings:
        $lsass1 = "lsass.exe" nocase
        $lsass2 = "OpenProcess" nocase
        $lsass3 = "MiniDumpWriteDump" nocase
        $lsass4 = "NtReadVirtualMemory" nocase
        $lsass5 = "SeDebugPrivilege" nocase
        $lsass6 = "SamQueryInformationUser" nocase
    condition:
        $lsass1 and (2 of ($lsass2, $lsass3, $lsass4, $lsass5, $lsass6))
}

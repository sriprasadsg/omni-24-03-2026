"""
YARA Rule: Ransomware Families
Detects file-header patterns and behavioral signatures of common ransomware.
"""

rule RansomwareGeneric {
    meta:
        description = "Generic ransomware file extension mutation pattern"
        severity = "critical"
        family = "ransomware"
    strings:
        $ext1 = ".locked" nocase
        $ext2 = ".crypted" nocase
        $ext3 = ".encrypted" nocase
        $ext4 = ".crypt" nocase
        $ext5 = ".enc" nocase
        $ransom1 = "bitcoin" nocase
        $ransom2 = "decrypt" nocase
        $ransom3 = "readme_decrypt" nocase
        $ransom4 = "how_to_decrypt" nocase
        $ransom5 = "your files have been encrypted" nocase
        $ransom6 = "send bitcoin" nocase
    condition:
        (any of ($ext*)) or (2 of ($ransom*))
}

rule WannaCryIndicators {
    meta:
        description = "WannaCry ransomware indicators"
        severity = "critical"
        family = "WannaCry"
        cve = "CVE-2017-0144"
    strings:
        $wannacry1 = "WannaCry" nocase
        $wannacry2 = "WANACRY" nocase
        $wannacry3 = "WanaCrypt0r" nocase
        $wannacry4 = { 57 61 6E 61 43 72 79 70 74 30 72 }   // WanaCrypt0r bytes
        $mutex1 = "MsWinZonesCacheCounterMutexA" nocase
        $wcry_ext = ".WCRY" nocase
        $wncry_ext = ".WNCRY" nocase
    condition:
        any of them
}

rule LockerRansomware {
    meta:
        description = "File locker / screen locker indicator patterns"
        severity = "critical"
        family = "Locker"
    strings:
        $locker1 = "CryptEncrypt" nocase
        $locker2 = "CryptoAPI" nocase
        $locker3 = "AES_set_encrypt_key" nocase
        $locker4 = "EVP_aes_256_cbc" nocase
        $bitcoin_addr = /[13][a-km-zA-HJ-NP-Z1-9]{25,34}/
    condition:
        (2 of ($locker*)) or $bitcoin_addr
}

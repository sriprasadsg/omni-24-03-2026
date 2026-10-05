/*
YARA Rule: Ransomware Families
Detects file-header patterns and behavioral signatures of common ransomware.
*/

rule RansomwareGeneric {
    meta:
        description = "Generic ransomware file extension mutation pattern"
        severity = "critical"
        family = "ransomware"
    strings:
        // Extensions and "bitcoin" occur in almost every crypto/network binary, so
        // they only corroborate a ransom-note phrase — they never match alone.
        $ext1 = ".locked" nocase
        $ext2 = ".crypted" nocase
        $ext3 = ".encrypted" nocase
        $ext4 = ".crypt" nocase
        $ext5 = ".enc" nocase
        $btc = "bitcoin" nocase
        $note1 = "readme_decrypt" nocase
        $note2 = "how_to_decrypt" nocase
        $note3 = "your files have been encrypted" nocase
        $note4 = "send bitcoin" nocase
    condition:
        2 of ($note*) or (1 of ($note*) and (any of ($ext*) or $btc))
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
        // Crypto APIs are in every TLS library and a bare base58 regex matches C++
        // mangled symbols, so require crypto use plus a lock note or a payment address.
        $locker1 = "CryptEncrypt" nocase
        $locker2 = "CryptoAPI" nocase
        $locker3 = "AES_set_encrypt_key" nocase
        $locker4 = "EVP_aes_256_cbc" nocase
        $lock_note1 = "your computer has been locked" nocase
        $lock_note2 = "your files are locked" nocase
        $lock_note3 = "pay the ransom" nocase
        $btc_payment = /([Bb]itcoin|BTC)[^\x00]{0,64}[13][a-km-zA-HJ-NP-Z1-9]{25,34}/
    condition:
        any of ($locker*) and (any of ($lock_note*) or $btc_payment)
}

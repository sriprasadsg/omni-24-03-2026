/*
YARA Rule: Network IOC & C2 Beacon Detection
Detects C2 callback patterns, DNS tunnelling, suspicious HTTP user-agents,
and common RAT/beacon network artifacts.
*/

rule C2BeaconCobaltStrike {
    meta:
        description = "Cobalt Strike beacon network pattern (sleep jitter + malleable C2)"
        severity = "critical"
        mitre = "T1071.001 - Application Layer Protocol: Web Protocols"
        family = "CobaltStrike"
        author = "Open Threat Research"
    strings:
        $cs1 = "cobaltstrike" nocase
        $cs2 = "beacon.dll" nocase
        $cs3 = "beacon.x64.dll" nocase
        // A standard MZ/PE header (in every EFI tool and PE) and Chrome's "\\.\pipe\mojo"
        // IPC pipe were removed; these are Cobalt Strike's default named pipes.
        $ua1 = "Mozilla/5.0 (compatible; MSIE 9.0; Windows NT 6.1; Trident/5.0)" nocase
        $ua2 = "Mozilla/4.0 (compatible; MSIE 7.0; Windows NT 5.1; .NET CLR)" nocase
        $sleep = "sleep_mask"
        $jitter = "jitter"
        $pipe1 = "\\\\.\\pipe\\MSSE-" nocase
        $pipe2 = "\\\\.\\pipe\\msagent_" nocase
        $pipe3 = "\\\\.\\pipe\\postex_" nocase
    condition:
        any of ($cs*) or (any of ($ua*) and ($sleep or $jitter)) or any of ($pipe*)
}

rule C2BeaconMetasploit {
    meta:
        description = "Metasploit meterpreter/reverse shell network patterns"
        severity = "critical"
        mitre = "T1059.005 - Command and Scripting Interpreter"
        family = "Metasploit"
    strings:
        $msf1 = "meterpreter" nocase
        $msf2 = "Meterpreter session" nocase
        $msf3 = "metasploit" nocase
        $shell1 = { 6A 00 68 63 6D 64 00 }  // push cmd shellcode
        $stager = "EXITFUNC=thread" nocase
        // "rc4_key" (an OpenSSL struct/field name) was removed as a standalone trigger.
    condition:
        any of them
}

rule DNSTunnelingPatterns {
    meta:
        description = "DNS tunnelling tool signatures (iodine, dnscat2, DNSExfiltrator)"
        severity = "high"
        mitre = "T1071.004 - Application Layer Protocol: DNS"
    strings:
        // "AAAAAAAA" (8 x 0x41) and 50+ char "word.tld" runs occur in any large binary,
        // and a bare "iodine" matches NetworkManager's iodine VPN plugin name — match the
        // tunnel tools' own artifacts instead.
        $iodine1 = "iodined" fullword
        $iodine2 = "iodine IP over DNS" nocase
        $dnscat = "dnscat" nocase
        $dnsexfil = "DNSExfiltrator" nocase
        $tunnel1 = "tunnel.domain" nocase
    condition:
        any of them
}

rule SuspiciousUserAgents {
    meta:
        description = "Known malicious or uncommon HTTP user agents used by RATs/tools"
        severity = "medium"
        mitre = "T1071.001 - Web Protocols"
    strings:
        // The default UAs of curl, Go, Java, wget and python-requests are compiled into
        // every program that uses those HTTP clients, and "Empire" is an ordinary word —
        // keep only offensive-tool markers.
        $ua_evil1 = "EvilGrade" nocase
        $ua_evil2 = "Invoke-Empire" nocase
        $ua_evil3 = "PoshC2" nocase
        $ua_evil4 = "Koadic" nocase
        $ua_empty = "User-Agent: \r\n"
        $ua_empty2 = "User-Agent:  \r\n"
    condition:
        any of them
}

rule ICMPTunneling {
    meta:
        description = "ICMP-based data exfiltration or tunnelling (ptunnel, icmpsh)"
        severity = "high"
        mitre = "T1095 - Non-Application Layer Protocol"
    strings:
        // "08 00" + a 16-byte zero run is present in essentially every file (it matched
        // 75% of binaries on a stock VM); "ptunnel" also hit "httpTunnel" without fullword.
        $ptunnel = "ptunnel" nocase fullword
        $icmpsh = "icmpsh" nocase fullword
        $data_in_icmp = "ICMP_EXFIL" nocase
    condition:
        any of them
}

rule ReverseShellNetcat {
    meta:
        description = "Netcat reverse shell invocation patterns"
        severity = "high"
        mitre = "T1059 - Command and Scripting Interpreter"
    strings:
        $nc1 = "nc -e /bin/sh" nocase
        $nc2 = "nc -e /bin/bash" nocase
        $nc3 = "nc -e cmd.exe" nocase
        $nc4 = "ncat --exec" nocase
        $nc5 = "nc.exe -lvp" nocase
        $nc6 = "bash -i >& /dev/tcp" nocase
        // "0>&1" and "mkfifo /tmp/" are everyday shell idioms; together they form the
        // classic named-pipe reverse shell, so they only count in combination.
        $redir = "0>&1" nocase
        $mkfifo = "mkfifo /tmp/" nocase
    condition:
        any of ($nc*) or ($mkfifo and $redir)
}

rule TorC2Communication {
    meta:
        description = "Tor proxy or .onion C2 communication patterns"
        severity = "high"
        mitre = "T1090.003 - Proxy: Multi-hop Proxy"
    strings:
        // ".onion" alone is a special-use TLD known to every HTTP/DNS library (Go, Node,
        // curl) and "torsocks"/"torproject.org" appear in docs — match concrete onion
        // service addresses (v2/v3) and Tor proxy wiring instead.
        $onion_v3 = /[a-z2-7]{56}\.onion/
        $onion_v2 = /[^a-z2-7][a-z2-7]{16}\.onion/
        $tor1 = "tor2web" nocase
        $socks_tor = "SOCKS5 127.0.0.1:9050" nocase
    condition:
        any of them
}

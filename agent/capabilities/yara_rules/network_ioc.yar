"""
YARA Rule: Network IOC & C2 Beacon Detection
Detects C2 callback patterns, DNS tunnelling, suspicious HTTP user-agents,
and common RAT/beacon network artifacts.
"""

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
        $cs4 = { 4D 5A 90 00 03 00 00 00 04 00 00 00 FF FF }  // MZ header in shellcode
        $ua1 = "Mozilla/5.0 (compatible; MSIE 9.0; Windows NT 6.1; Trident/5.0)" nocase
        $ua2 = "Mozilla/4.0 (compatible; MSIE 7.0; Windows NT 5.1; .NET CLR)" nocase
        $sleep = "sleep_mask"
        $jitter = "jitter"
        $pipe1 = "\\\\.\\pipe\\mojo" nocase
        $pipe2 = "\\\\.\\pipe\\msagent_" nocase
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
        $rc4key = "rc4_key"
    condition:
        any of them
}

rule DNSTunnelingPatterns {
    meta:
        description = "DNS tunnelling tool signatures (iodine, dnscat2, DNSExfiltrator)"
        severity = "high"
        mitre = "T1071.004 - Application Layer Protocol: DNS"
    strings:
        $iodine = "iodine" nocase
        $dnscat = "dnscat" nocase
        $dnsexfil = "DNSExfiltrator" nocase
        $dns_b32 = { 41 41 41 41 41 41 41 41 }  // base32 padding pattern
        $tunnel1 = "tunnel.domain" nocase
        $subdomain_len = /[a-z0-9]{50,}\.[a-z]{2,6}/  // abnormally long subdomain
    condition:
        any of ($iodine, $dnscat, $dnsexfil) or $subdomain_len
}

rule SuspiciousUserAgents {
    meta:
        description = "Known malicious or uncommon HTTP user agents used by RATs/tools"
        severity = "medium"
        mitre = "T1071.001 - Web Protocols"
    strings:
        $ua_python = "python-requests" nocase
        $ua_curl = "curl/" nocase
        $ua_wget = "Wget/" nocase
        $ua_go = "Go-http-client" nocase
        $ua_java = "Java/" nocase
        $ua_evil1 = "EvilGrade" nocase
        $ua_evil2 = "Empire" nocase
        $ua_evil3 = "PoshC2" nocase
        $ua_evil4 = "Koadic" nocase
        $ua_empty = "User-Agent: \r\n"
        $ua_empty2 = "User-Agent:  \r\n"
    condition:
        any of ($ua_evil*) or $ua_empty or $ua_empty2
}

rule ICMPTunneling {
    meta:
        description = "ICMP-based data exfiltration or tunnelling (ptunnel, icmpsh)"
        severity = "high"
        mitre = "T1095 - Non-Application Layer Protocol"
    strings:
        $ptunnel = "ptunnel" nocase
        $icmpsh = "icmpsh" nocase
        $icmp_magic = { 08 00 }  // ICMP echo type
        $data_in_icmp = "ICMP_EXFIL" nocase
        $large_payload = { 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 }  // 16-byte zero padding typical of tunnel tools
    condition:
        any of ($ptunnel, $icmpsh, $data_in_icmp)
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
        $nc7 = "0>&1" nocase
        $mkfifo = "mkfifo /tmp/" nocase
    condition:
        any of them
}

rule TorC2Communication {
    meta:
        description = "Tor proxy or .onion C2 communication patterns"
        severity = "high"
        mitre = "T1090.003 - Proxy: Multi-hop Proxy"
    strings:
        $onion = ".onion" nocase
        $tor1 = "tor2web" nocase
        $tor2 = "torproject.org" nocase
        $socks_tor = "SOCKS5 127.0.0.1:9050" nocase
        $torsocks = "torsocks" nocase
    condition:
        any of them
}

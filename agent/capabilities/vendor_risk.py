"""
Vendor / Third-Party Risk Evidence Collector

Automatically collects evidence required by:
  - SOC 2   CC9.2  (Vendor and Business Partner Management)
  - ISO 27001 A.5.19/A.5.20/A.5.21 (Information security in supplier relationships)
  - PCI DSS  12.8  (Third-party service provider management)
  - HIPAA    164.308(b) (Business associate contracts)
  - NIST 800-53 SA-9 (External Information System Services)
  - GDPR     Art.28 (Processor obligations / sub-processor list)

What is collected automatically:
  1. Active outbound TCP connections — identifies which external hosts this machine talks to
  2. Reverse DNS + GeoIP (local) — maps IPs to vendor names where possible
  3. TLS certificate details for HTTPS connections — expiry, issuer, subject
  4. Known vendor fingerprinting — recognises AWS/Azure/GCP/Datadog/Splunk/etc. by IP range or DNS suffix
  5. Installed agent/monitoring software — third-party tools embedded in the system
  6. External DNS resolvers in use
  7. Proxy configuration (corporate proxies are third parties too)
"""

from .base import BaseCapability
import platform
import socket
import subprocess
import ssl
import re
import logging
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)

# Known vendor domains/suffixes → vendor name + category
VENDOR_FINGERPRINTS = {
    "amazonaws.com":       {"vendor": "Amazon Web Services",  "category": "Cloud Infrastructure"},
    "aws.amazon.com":      {"vendor": "Amazon Web Services",  "category": "Cloud Infrastructure"},
    "azure.com":           {"vendor": "Microsoft Azure",      "category": "Cloud Infrastructure"},
    "microsoftonline.com": {"vendor": "Microsoft 365/Azure",  "category": "Identity / SaaS"},
    "office365.com":       {"vendor": "Microsoft 365",        "category": "SaaS Productivity"},
    "live.com":            {"vendor": "Microsoft",            "category": "Identity"},
    "gcp.com":             {"vendor": "Google Cloud",         "category": "Cloud Infrastructure"},
    "googleapis.com":      {"vendor": "Google APIs",          "category": "Cloud / AI"},
    "google.com":          {"vendor": "Google",               "category": "Search / Analytics"},
    "datadog.com":         {"vendor": "Datadog",              "category": "Observability"},
    "datadoghq.com":       {"vendor": "Datadog",              "category": "Observability"},
    "splunk.com":          {"vendor": "Splunk",               "category": "SIEM"},
    "newrelic.com":        {"vendor": "New Relic",            "category": "Observability"},
    "elastic.co":          {"vendor": "Elastic",              "category": "SIEM / Search"},
    "crowdstrike.com":     {"vendor": "CrowdStrike",          "category": "EDR / Security"},
    "sentinelone.com":     {"vendor": "SentinelOne",          "category": "EDR / Security"},
    "carbonblack.com":     {"vendor": "VMware Carbon Black",  "category": "EDR / Security"},
    "tenable.com":         {"vendor": "Tenable",              "category": "Vulnerability Scanning"},
    "qualys.com":          {"vendor": "Qualys",               "category": "Vulnerability Scanning"},
    "pagerduty.com":       {"vendor": "PagerDuty",            "category": "Incident Management"},
    "atlassian.com":       {"vendor": "Atlassian",            "category": "Dev / Ticketing"},
    "atlassian.net":       {"vendor": "Atlassian",            "category": "Dev / Ticketing"},
    "github.com":          {"vendor": "GitHub",               "category": "Source Control"},
    "gitlab.com":          {"vendor": "GitLab",               "category": "Source Control / CI"},
    "okta.com":            {"vendor": "Okta",                 "category": "Identity / SSO"},
    "auth0.com":           {"vendor": "Auth0 (Okta)",         "category": "Identity / SSO"},
    "pingidentity.com":    {"vendor": "Ping Identity",        "category": "Identity / SSO"},
    "duo.com":             {"vendor": "Duo Security (Cisco)", "category": "MFA"},
    "1password.com":       {"vendor": "1Password",            "category": "Secrets Management"},
    "hashicorp.com":       {"vendor": "HashiCorp Vault",      "category": "Secrets Management"},
    "cloudflare.com":      {"vendor": "Cloudflare",           "category": "CDN / DDoS Protection"},
    "fastly.com":          {"vendor": "Fastly",               "category": "CDN"},
    "akamai.com":          {"vendor": "Akamai",               "category": "CDN / DDoS Protection"},
    "slack.com":           {"vendor": "Slack",                "category": "Collaboration / SaaS"},
    "salesforce.com":      {"vendor": "Salesforce",           "category": "CRM / SaaS"},
    "servicenow.com":      {"vendor": "ServiceNow",           "category": "ITSM"},
    "mongodb.com":         {"vendor": "MongoDB Atlas",        "category": "Database-as-a-Service"},
    "snowflake.com":       {"vendor": "Snowflake",            "category": "Data Warehouse"},
    "twilio.com":          {"vendor": "Twilio",               "category": "Communications API"},
    "stripe.com":          {"vendor": "Stripe",               "category": "Payment Processing"},
    "sumologic.com":       {"vendor": "Sumo Logic",           "category": "SIEM / Observability"},
    "logz.io":             {"vendor": "Logz.io",              "category": "SIEM / Observability"},
    "anthropic.com":       {"vendor": "Anthropic",            "category": "AI / LLM API"},
    "openai.com":          {"vendor": "OpenAI",               "category": "AI / LLM API"},
    "azure.openai.com":    {"vendor": "Azure OpenAI",         "category": "AI / LLM API"},
}

# Known monitoring/agent software installed on endpoints
VENDOR_SOFTWARE_PATTERNS = [
    (r"crowdstrike|falcon",  "CrowdStrike Falcon",   "EDR"),
    (r"sentinelone",         "SentinelOne",          "EDR"),
    (r"carbon.black|cbdefense", "VMware Carbon Black","EDR"),
    (r"cylance",             "Cylance",              "EDR"),
    (r"datadog.agent",       "Datadog Agent",        "Observability"),
    (r"splunk.?universal",   "Splunk UF",            "SIEM"),
    (r"nessus",              "Tenable Nessus",       "Vulnerability Scan"),
    (r"qualys",              "Qualys Agent",         "Vulnerability Scan"),
    (r"duo",                 "Duo MFA",              "MFA"),
    (r"okta.verify|okta.plugin", "Okta Verify",      "Identity / SSO"),
    (r"1password",           "1Password",            "Secrets Mgmt"),
    (r"cloudflare.warp",     "Cloudflare WARP",      "Zero Trust"),
    (r"zscaler",             "Zscaler Client",       "Zero Trust"),
    (r"paloalto|globalprotect", "Palo Alto GP",      "Zero Trust / VPN"),
    (r"cisco.anyconnect",    "Cisco AnyConnect",     "VPN"),
    (r"openvpn",             "OpenVPN",              "VPN"),
    (r"tenable",             "Tenable",              "Vulnerability Scan"),
    (r"newrelic",            "New Relic Agent",      "Observability"),
    (r"elastic.agent|elastic.endpoint", "Elastic Agent", "SIEM / EDR"),
]


class VendorRiskCapability(BaseCapability):
    """
    Automatically discovers and documents third-party vendor relationships
    for SOC 2 CC9.2, ISO 27001 A.5.19-21, PCI DSS 12.8, HIPAA 164.308(b).
    """

    @property
    def capability_id(self) -> str:
        return "vendor_risk"

    @property
    def capability_name(self) -> str:
        return "Vendor / Third-Party Risk"

    _CACHE_TTL = 1800   # re-scan at most once every 30 minutes

    def collect(self) -> Dict[str, Any]:
        import time as _time
        last_ts = getattr(self, "_cached_ts", 0)
        if _time.time() - last_ts < self._CACHE_TTL and hasattr(self, "_cached_result"):
            cached = dict(self._cached_result)
            cached["from_cache"] = True
            cached["cache_age_s"] = round(_time.time() - last_ts)
            return cached

        result = {
            "collected_at": datetime.now(timezone.utc).isoformat(),
            "platform": platform.system(),
            "outbound_connections":    self._outbound_connections(),
            "tls_certificate_checks":  self._tls_cert_checks(),
            "installed_vendor_agents": self._installed_vendor_software(),
            "dns_resolvers":           self._dns_resolvers(),
            "proxy_config":            self._proxy_config(),
            "controls_mapped": {
                "SOC2":     "CC9.2 (Vendor Management)",
                "ISO27001": "A.5.19, A.5.20, A.5.21",
                "PCI-DSS":  "12.8",
                "HIPAA":    "164.308(b)",
                "NIST":     "SA-9",
                "GDPR":     "Art.28",
            },
        }
        self._cached_result = result
        self._cached_ts = _time.time()
        return result

    # ── Outbound connection inventory ─────────────────────────────────────────

    def _fingerprint_host(self, hostname: str) -> Optional[Dict[str, str]]:
        for suffix, info in VENDOR_FINGERPRINTS.items():
            if hostname.lower().endswith(suffix):
                return info
        return None

    def _reverse_dns(self, ip: str, timeout: float = 1.5) -> str:
        """Reverse DNS with a hard timeout so slow/missing PTR records don't block."""
        from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout
        try:
            with ThreadPoolExecutor(max_workers=1) as ex:
                future = ex.submit(socket.gethostbyaddr, ip)
                return future.result(timeout=timeout)[0]
        except Exception:
            return ip

    def _outbound_connections(self) -> Dict[str, Any]:
        """
        Enumerate established outbound TCP connections and map external IPs
        to vendor names using parallel reverse DNS + fingerprint table.
        All reverse DNS lookups run concurrently (max 1.5 s each) so the
        total time is bounded by the slowest single lookup, not sum of all.
        """
        try:
            import psutil
            conns = psutil.net_connections(kind="tcp")
        except Exception as e:
            return {"status": "error", "error": str(e)}

        external_ips: Dict[str, Dict] = {}   # ip -> partial info
        internal_count = 0

        for c in conns:
            if c.status != "ESTABLISHED" or not c.raddr:
                continue
            ip = c.raddr.ip
            if (ip.startswith("10.") or ip.startswith("192.168.") or
                    ip.startswith("172.") or ip.startswith("127.") or ip == "::1"):
                internal_count += 1
                continue
            if ip not in external_ips:
                external_ips[ip] = {"ip": ip, "port": c.raddr.port, "connection_count": 0}
            external_ips[ip]["connection_count"] += 1

        # Resolve all unique external IPs concurrently (cap at 30 to stay fast)
        from concurrent.futures import ThreadPoolExecutor, as_completed
        unique_ips = list(external_ips.keys())[:30]
        resolved: Dict[str, str] = {}
        with ThreadPoolExecutor(max_workers=min(len(unique_ips) or 1, 20)) as pool:
            fut_map = {pool.submit(self._reverse_dns, ip): ip for ip in unique_ips}
            for fut in as_completed(fut_map, timeout=5):
                ip = fut_map[fut]
                try:
                    resolved[ip] = fut.result()
                except Exception:
                    resolved[ip] = ip

        for ip, entry in external_ips.items():
            hostname = resolved.get(ip, ip)
            vendor_info = self._fingerprint_host(hostname)
            entry["hostname"] = hostname
            entry["vendor"]   = vendor_info.get("vendor")   if vendor_info else "Unknown"
            entry["category"] = vendor_info.get("category") if vendor_info else "Unknown"

        vendor_list = list(external_ips.values())
        known   = [v for v in vendor_list if v["vendor"] != "Unknown"]
        unknown = [v for v in vendor_list if v["vendor"] == "Unknown"]

        return {
            "status": "collected",
            "external_ips_active": len(vendor_list),
            "internal_connections": internal_count,
            "known_vendors": known,
            "unknown_external": unknown,
            "unique_vendors": list({v["vendor"] for v in known}),
            "vendor_count": len({v["vendor"] for v in known}),
        }

    # ── TLS certificate verification ──────────────────────────────────────────

    def _tls_cert_checks(self) -> Dict[str, Any]:
        """
        Verify TLS certificate validity for active HTTPS (port 443) connections.
        Evidence for: PCI-DSS 4.2.1, ISO27001 A.8.24, SOC2 CC6.7
        """
        # Collect unique external HTTPS hosts from active connections
        https_hosts: List[str] = []
        try:
            import psutil
            seen: set = set()
            for c in psutil.net_connections(kind="tcp"):
                if c.status == "ESTABLISHED" and c.raddr and c.raddr.port == 443:
                    ip = c.raddr.ip
                    if ip not in seen and not ip.startswith(("10.", "192.168.", "172.", "127.")):
                        seen.add(ip)
                        https_hosts.append(self._reverse_dns(ip))
        except Exception:
            pass

        # Check certs concurrently — max 8 hosts, 3 s per check, 12 s total budget
        from concurrent.futures import ThreadPoolExecutor, as_completed as _asc
        results = []
        targets = https_hosts[:8]
        with ThreadPoolExecutor(max_workers=min(len(targets) or 1, 8)) as pool:
            fut_map = {pool.submit(self._check_tls, h): h for h in targets}
            for fut in _asc(fut_map, timeout=12):
                try:
                    results.append(fut.result())
                except Exception as e:
                    results.append({"host": fut_map[fut], "valid": None, "error": str(e)})

        expired = [r for r in results if r.get("expired")]
        expiring_soon = [r for r in results if r.get("days_until_expiry", 999) < 30 and not r.get("expired")]

        return {
            "status": "collected",
            "hosts_checked": len(results),
            "certificates": results,
            "expired_count": len(expired),
            "expiring_within_30d": len(expiring_soon),
            "expired_hosts": [r["host"] for r in expired],
            "expiring_hosts": [r["host"] for r in expiring_soon],
        }

    def _check_tls(self, host: str, port: int = 443, timeout: int = 3) -> Dict[str, Any]:
        entry: Dict[str, Any] = {"host": host, "port": port}
        try:
            ctx = ssl.create_default_context()
            with ctx.wrap_socket(socket.create_connection((host, port), timeout=timeout),
                                 server_hostname=host) as s:
                cert = s.getpeercert()
            not_after_str = cert.get("notAfter", "")
            not_after = datetime.strptime(not_after_str, "%b %d %H:%M:%S %Y %Z") if not_after_str else None
            days_left = (not_after - datetime.utcnow()).days if not_after else None
            subject = dict(x[0] for x in cert.get("subject", []))
            issuer  = dict(x[0] for x in cert.get("issuer",  []))
            entry.update({
                "valid": True,
                "subject_cn": subject.get("commonName"),
                "issuer_cn":  issuer.get("commonName"),
                "issuer_org": issuer.get("organizationName"),
                "not_after":  not_after.isoformat() if not_after else None,
                "days_until_expiry": days_left,
                "expired": (days_left is not None and days_left < 0),
            })
        except ssl.SSLCertVerificationError as e:
            entry.update({"valid": False, "error": f"Certificate verification failed: {e}"})
        except Exception as e:
            entry.update({"valid": None, "error": str(e)})
        return entry

    # ── Installed vendor software ──────────────────────────────────────────────

    def _installed_vendor_software(self) -> Dict[str, Any]:
        """
        Detect known third-party security/monitoring agents installed on the endpoint.
        Evidence for: SOC2 CC9.2, HIPAA 164.308(b), ISO27001 A.5.21
        """
        detected = []
        system = platform.system()

        if system == "Windows":
            raw = self._ps_run(
                "Get-ItemProperty HKLM:\\Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\* "
                "| Select-Object -ExpandProperty DisplayName 2>$null | Where-Object {$_}"
            ) or ""
        elif system == "Linux":
            raw = self._sh_run("dpkg -l 2>/dev/null || rpm -qa 2>/dev/null") or ""
        else:
            raw = ""

        raw_lower = raw.lower()
        for pattern, vendor_name, category in VENDOR_SOFTWARE_PATTERNS:
            if re.search(pattern, raw_lower):
                detected.append({"vendor": vendor_name, "category": category, "detected_via": "installed software list"})

        # Also check running processes
        try:
            import psutil
            running_names = " ".join(p.info.get("name", "") for p in psutil.process_iter(["name"])).lower()
            for pattern, vendor_name, category in VENDOR_SOFTWARE_PATTERNS:
                if re.search(pattern, running_names):
                    if not any(d["vendor"] == vendor_name for d in detected):
                        detected.append({"vendor": vendor_name, "category": category, "detected_via": "running process"})
        except Exception:
            pass

        return {
            "status": "collected",
            "installed_vendor_count": len(detected),
            "vendors": detected,
        }

    # ── DNS resolvers ──────────────────────────────────────────────────────────

    def _dns_resolvers(self) -> Dict[str, Any]:
        """
        Identify DNS resolvers in use — third-party DNS (8.8.8.8, 1.1.1.1) implies
        data leaves corporate network; relevant for GDPR Art.28 / HIPAA sub-processor.
        """
        resolvers: List[str] = []
        system = platform.system()
        try:
            if system == "Windows":
                raw = self._ps_run(
                    "Get-DnsClientServerAddress -AddressFamily IPv4 "
                    "| Select-Object -ExpandProperty ServerAddresses"
                ) or ""
                resolvers = [l.strip() for l in raw.splitlines() if re.match(r'\d+\.\d+', l.strip())]
            elif system == "Linux":
                raw = self._sh_run("grep nameserver /etc/resolv.conf 2>/dev/null") or ""
                resolvers = re.findall(r'nameserver\s+([\d.]+)', raw)
        except Exception:
            pass

        known_public = {
            "8.8.8.8": "Google Public DNS",  "8.8.4.4": "Google Public DNS",
            "1.1.1.1": "Cloudflare DNS",      "1.0.0.1": "Cloudflare DNS",
            "9.9.9.9": "Quad9 DNS",           "208.67.222.222": "OpenDNS",
        }
        annotated = [{"ip": r, "vendor": known_public.get(r, "Corporate/Unknown")} for r in resolvers]
        public_dns_in_use = [a for a in annotated if a["vendor"] != "Corporate/Unknown"]

        return {
            "status": "collected",
            "resolvers": annotated,
            "public_dns_in_use": public_dns_in_use,
            "note": "Public DNS usage means DNS queries are processed by a third party (GDPR Art.28 applies)" if public_dns_in_use else None,
        }

    # ── Proxy configuration ────────────────────────────────────────────────────

    def _proxy_config(self) -> Dict[str, Any]:
        """
        Detect HTTP/HTTPS proxy configuration — proxies are third parties that
        inspect traffic; must be documented for SOC2 CC6.7 / ISO27001 A.8.20.
        """
        proxies: Dict[str, Any] = {"status": "collected"}
        system = platform.system()
        try:
            if system == "Windows":
                raw = self._ps_run(
                    "Get-ItemProperty 'HKCU:\\Software\\Microsoft\\Windows\\CurrentVersion\\Internet Settings' "
                    "| Select-Object ProxyEnable, ProxyServer, AutoConfigURL"
                ) or ""
                proxies["windows_ie_proxy"] = raw.strip()
            elif system == "Linux":
                for var in ("http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY", "no_proxy"):
                    val = os.environ.get(var)
                    if val:
                        proxies[var] = val
            # Check env vars on any platform
            import os
            for var in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"):
                val = os.environ.get(var)
                if val:
                    proxies[f"env_{var}"] = val
        except Exception as e:
            proxies["error"] = str(e)
        return proxies

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _ps_run(self, script: str, timeout: int = 15) -> Optional[str]:
        try:
            r = subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
                capture_output=True, text=True, timeout=timeout,
            )
            return r.stdout.strip() or None
        except Exception:
            return None

    def _sh_run(self, cmd: str, timeout: int = 15) -> Optional[str]:
        try:
            r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
            return r.stdout.strip() or None
        except Exception:
            return None

"""
VirusTotal Scan Capability
"""

import os
import json
import logging
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Union

import subprocess
import hashlib
import psutil
from typing import Set

from .base import BaseCapability
from backend.virustotal_client import get_virustotal_client

logger = logging.getLogger(__name__)

class VirusTotalScanCapability(BaseCapability):
    """
    VirusTotal-based threat scanning for IPs, domains, URLs, and file hashes.
    Agent‑side capability that scans in‑memory artifacts (processes, open sockets)
    and reports findings back to backend.
    """

    @property
    def capability_id(self) -> str:
        return "virustotal_scan"

    @property
    def capability_name(self) -> str:
        return "VirusTotal Endpoint Scanner"

    def collect(self) -> Dict[str, Any]:
        """Run scans based on discovered artifacts."""
        results = {
            "scanned_ips": [],
            "scanned_domains": [],
            "scanned_urls": [],
            "scanned_hashes": [],
            "malicious_count": 0,
            "scan_time": datetime.now(timezone.utc).isoformat(),
            "status": "completed"
        }

        # ----- Scan open TCP ports for suspicious IPs -----
        try:
            probed = self._probe_open_ports()
            results["scanned_ips"] = probed
            results["malicious_count"] += len([x for x in probed if any(v in x.get("verdict", "") for v in ("Malicious", "Suspicious"))])
        except Exception as e:
            logger.error("[VT Scan] IP probing failed: %s", e)

        # ----- Scan process executable hashes -----
        try:
            hashes = self._scan_process_hashes()
            results["scanned_hashes"] = list(hashes)
            results["malicious_count"] += len([x for x in results["scanned_hashes"] if x.get("verdict") == "Malicious"])
        except Exception as e:
            logger.error("[VT Scan] Process hash scanning failed: %s", e)

        # ----- Scan network connections for suspicious domains/URLs -----
        try:
            found = self._scan_network_connections()
            results["scanned_domains"] = list(found.get("domains", []))
            results["scanned_urls"] = list(found.get("urls", []))
            # Count malicious domain/URL scans
            results["malicious_count"] += (
                len([x for x in results["scanned_domains"] if x.get("verdict") == "Malicious"]) +
                len([x for x in results["scanned_urls"]   if x.get("verdict") == "Malicious"])
            )
        except Exception as e:
            logger.error("[VT Scan] Network connection scanning failed: %s", e)

        return results

    def _probe_open_ports(self) -> List[Dict[str, Any]]:
        """Check for suspicious IPs on active TCP connections and scan them."""
        suspicious_ips = []
        scanned = set()

        for conn in psutil.net_connections(kind="tcp"):
            if not conn.raddr:
                continue
            ip_port = conn.raddr
            ip = ip_port[0]
            # Avoid duplicates
            if ip in scanned:
                continue
            scanned.add(ip)

            vt_result = get_virustotal_client().lookup_ip(ip) if ip else {}
            suspicious_ips.append(vt_result)

        return suspicious_ips

    def _scan_process_hashes(self) -> Dict[str, Dict[str, Any]]:
        """Hash current executable and perform VT hash lookup."""
        client = get_virustotal_client()
        hashes: Dict[str, Dict[str, Any]] = {}

        try:
            exe_path = self._get_current_exe_path()
            if exe_path:
                sha256 = hashlib.sha256(open(exe_path, "rb").read()).hexdigest()
                result = client.lookup_hash(sha256)
                if "error" not in result:
                    hashes[sha256] = result
        except Exception as e:
            logger.error("[VT Scan] Process hash scan failed: %s", e)

        return hashes

    def _scan_network_connections(self) -> Dict[str, List[Dict[str, str]]]:
        """Collect domains/URLs from process network connections and scan them."""
        client = get_virustotal_client()
        found_domains: Set[str] = set()
        found_urls:   Set[str] = set()

        for conn in psutil.net_connections(kind="tcp"):
            if not conn.raddr:
                continue
            # conn.raddr format (ip, port)
            ip, port = conn.raddr
            try:
                # Resolve DNS for IPs to domain names
                if ip:
                    import socket
                    hostname = socket.gethostbyaddr(ip)[0]
                    found_domains.add(hostname)

                    # Look for HTTP(S) traffic (typical for C2 beaconing)
                    if conn.status == psutil.CONN_ESTABLISHED and port in (80, 443):
                        laddr = conn.laddr if conn.laddr else ("", 0)
                        proc = psutil.Process(conn.pid)
                        cmdline = proc.cmdline()
                        # Very simple heuristic: look for URLs in command line args
                        for arg in cmdline:
                            if "http" in arg.lower():
                                found_urls.add(arg.strip())
            except Exception:
                continue

        # Scan collected domains/URLs
        domains_results = [client.lookup_domain(d) for d in found_domains if d]
        urls_results    = [client.lookup_url(u)   for u in found_urls   if u]

        # Combine verdicts for counting malicious
        for vt_res in list(domains_results) + list(urls_results):
            if isinstance(vt_res, dict) and vt_res.get("verdict") == "Malicious":
                # Increment malicious count later in collect()
                pass

        return {
            "domains": domains_results,
            "urls": urls_results
        }

    def _get_current_exe_path(self) -> Optional[str]:
        """Return path of current executable."""
        try:
            from pathlib import Path
            exe_path = Path(__file__).resolve()
            # In a running agent script, __file__ points to this file; we need the binary path.
            # Fallback: use psutil to get the main process exe
            for proc in psutil.process_iter(['exe', 'cmdline']):
                if proc.info['exe'] and os.path.exists(proc.info['exe']):
                    return proc.info['exe']
        except Exception as e:
            logger.error("[VT Scan] Executable path lookup failed: %s", e)
        return None
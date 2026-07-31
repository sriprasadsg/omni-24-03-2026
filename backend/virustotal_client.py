import os
import json
import logging
from typing import Dict, Any
from datetime import datetime, timezone

class VirusTotalScanCapability(BaseCapability):
    """
    VirusTotal integration for endpoint scanning.
    Provides scan capability for agent assets using VT API v3.
    """

    @property
    def capability_id(self) -> str:
        return "virustotal_scan"

    @property
    def capability_name(self) -> str:
        return "VirusTotal Endpoint Scanner"

    def collect(self) -> Dict[str, Any]:
        """
        Execute scans against collected artifacts.
        Returns structured result dictionary.
        """
        base_url = "https://www.virustotal.com/api/v3"
        api_key = os.getenv("VIRUSTOTAL_API_KEY", "")
        headers = {"x-apikey": api_key, "Accept": "application/json"}
        client = requests.Session()
        client.headers.update(headers)

        results = {
            "scanned_ips": [],
            "scanned_domains": [],
            "scanned_urls": [],
            "scanned_hashes": [],
            "malicious_count": 0,
            "scan_time": datetime.now(timezone.utc).isoformat(),
            "status": "completed"
        }

        # Scan open ports for malicious IPs
        try:
            for conn in psutil.net_connections(kind="tcp"):
                if not conn.raddr:
                    continue
                ip, _ = conn.raddr
                ip_hash = hashlib.md5(ip.encode()).hexdigest()
                # Use VT hash endpoint
                resp = client.get(f"{base_url}/ip_addresses/{ip_hash}", timeout=10)
                if resp.status_code == 200:
                    results["scanned_ips"].append({
                        **resp.json().get("data", {}).get("attributes", {}),
                        "verdict": "Malicious" if
                        resp.json().get("data", {}).get("attributes", {}).get("last_analysis_stats", {}).get("malicious", 0) > 0 else "Clean",
                        "ratio": "0/0"
                    })
        except Exception as e:
            logger.error(f"[VT scan] IP scan failed: {e}")

        # Scan process hashes
        try:
            exe_path = next(
                (proc.exe() for proc in psutil.process_iter(['exe']) if proc.exe()),
                None
            )
            if exe_path:
                sha256 = hashlib.sha256(open(exe_path, "rb").read()).hexdigest()
                resp = client.get(f"{base_url}/files/{sha256}", timeout=10)
                if resp.status_code == 200:
                    data = resp.json().get("data", {}).get("attributes", {})
                    stats = data.get("last_analysis_stats", {})
                    results["scanned_hashes"].append({
                        "verdict": "Malicious" if stats.get("malicious", 0) > 0 else "Clean",
                        "ratio": f"{stats.get('malicious', 0)+stats.get('suspicious', 0)}/{stats.get('total', 0)}",
                        "hash": sha256
                    })
        except Exception as e:
            logger.error(f"[VT scan] Hash scan failed: {e}")

        # Scan live network addresses
        try:
            for conn in psutil.net_connections(kind="tcp"):
                if not conn.raddr:
                    continue
                domain = socket.gethostbyaddr(conn.raddr[0])[0]
                resp = client.get(f"{base_url}/domains/{domain}", timeout=10)
                if resp.status_code == 200:
                    results["scanned_domains"].append({
                        **resp.json().get("data", {}).get("attributes", {}),
                        "verdict": "Malicious" if resp.json().get("data", {}).get("attributes", {}).get("last_analysis_stats", {}).get("malicious", 0) > 0 else "Clean",
                        "ratio": "0/0"
                    })
        except Exception as e:
            logger.error(f"[VT scan] Domain scan failed: {e}")

        # Scan URLs from connections
        try:
            for conn in psutil.net_connections(kind="tcp"):
                if not conn.raddr:
                    continue
                if conn.status == psutil.CONN_ESTABLISHED and conn.laddr:
                    cmdline = subprocess.Popen(
                        ["ps", "-p", str(conn.pid), "-o", "args="],
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        text=True
                    ).communicate()
                    if "http" in cmdline[0]:
                        url = re.search(r"https?://\S+", cmdline[0])
                        if url:
                            resp = client.get(f"{base_url}/urls/{url.group()}", timeout=10)
                            if resp.status_code == 200:
                                results["scanned_urls"].append({
                                    **resp.json().get("data", {}).get("attributes", {}),
                                    "verdict": "Malicious" if resp.json().get("data", {}).get("attributes", {}).get("last_analysis_stats", {}).get("malicious", 0) > 0 else "Clean",
                                    "ratio": "0/0"
                                })
        except Exception as e:
            logger.error(f"[VT scan] URL scan failed: {e}")

        return results
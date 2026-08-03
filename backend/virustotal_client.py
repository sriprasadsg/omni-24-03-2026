"""VirusTotal API v3 client.

Real, synchronous outbound calls to https://www.virustotal.com/api/v3/*
using httpx (already a project dependency — no new packages). Every
scan_* method is SYNCHRONOUS by design: the four real callers
(threat_intel_endpoints.py, threat_endpoints.py, soar_engine.py,
agent_security_endpoints.py) invoke these via asyncio.to_thread /
run_in_executor so a slow/rate-limited VirusTotal call never blocks the
event loop (T-55-05).

API-key-absent = graceful degrade: construction never fails, and every
lookup returns {"error": ...} with NO fabricated verdict (T-55-04). The
dead VirusTotalScanCapability(BaseCapability) class that made this module
unimportable (NameError at import time, silently swallowing the whole
/api/threat-intel router — INT-04, 55-VERIFICATION.md gap #1) has been
removed as part of this rewrite (55-05).
"""
import base64
import os
from typing import Any, Dict, List, Optional
from urllib.parse import quote

import httpx

_BASE_URL = "https://www.virustotal.com/api/v3"
_TIMEOUT = 10.0


class VirusTotalClient:
    """Synchronous VirusTotal API v3 client."""

    def __init__(self, api_key: Optional[str] = None):
        self._api_key = api_key if api_key is not None else os.getenv("VIRUSTOTAL_API_KEY", "")

    def _lookup(self, path: str) -> Dict[str, Any]:
        """GET a fixed VirusTotal v3 path and map the response into the
        shared caller contract.

        Never raises. `path` is always built by the caller from the FIXED
        `_BASE_URL` host constant plus a URL-encoded artifact segment —
        the artifact itself never becomes the host/scheme (T-55-02).
        Key-absent and error paths return {"error": ...} with NO "verdict"
        key — callers must never mistake a degraded/failed lookup for a
        real Harmless/Clean result (T-55-04).
        """
        if not self._api_key:
            return {"error": "VirusTotal API key not configured"}

        headers = {"x-apikey": self._api_key, "Accept": "application/json"}
        url = f"{_BASE_URL}/{path}"
        try:
            with httpx.Client(timeout=_TIMEOUT) as client:
                resp = client.get(url, headers=headers)
            if resp.status_code != 200:
                return {"error": f"VirusTotal API returned status {resp.status_code}"}
            attributes = resp.json().get("data", {}).get("attributes", {}) or {}
        except Exception as exc:
            return {"error": f"VirusTotal request failed: {exc}"}

        stats = attributes.get("last_analysis_stats", {}) or {}
        malicious = int(stats.get("malicious", 0) or 0)
        suspicious = int(stats.get("suspicious", 0) or 0)
        harmless = int(stats.get("harmless", 0) or 0)
        undetected = int(stats.get("undetected", 0) or 0)
        timeout_n = int(stats.get("timeout", 0) or 0)

        if malicious > 0:
            verdict = "Malicious"
        elif suspicious > 0:
            verdict = "Suspicious"
        elif harmless > 0:
            verdict = "Harmless"
        else:
            verdict = "Unknown"

        total = malicious + suspicious + harmless + undetected + timeout_n
        detection_ratio = f"{malicious + suspicious}/{total}" if total else "0/0"

        return {
            "verdict": verdict,
            "detectionRatio": detection_ratio,
            "malicious": malicious,
            "suspicious": suspicious,
            "harmless": harmless,
            "undetected": undetected,
            "scanDate": attributes.get("last_analysis_date"),
            "reputation": attributes.get("reputation", 0),
            "details": attributes,
        }

    def scan_ip(self, ip: str) -> Dict[str, Any]:
        """Look up an IP address's VirusTotal reputation."""
        return self._lookup(f"ip_addresses/{quote(ip, safe='')}")

    def scan_domain(self, domain: str) -> Dict[str, Any]:
        """Look up a domain's VirusTotal reputation."""
        return self._lookup(f"domains/{quote(domain, safe='')}")

    def scan_url(self, url: str) -> Dict[str, Any]:
        """Look up a URL's VirusTotal reputation.

        VT v3 identifies URLs by the urlsafe-base64 encoding of the URL
        string with '=' padding stripped.
        """
        url_id = base64.urlsafe_b64encode(url.encode()).decode().rstrip("=")
        return self._lookup(f"urls/{url_id}")

    def scan_file_hash(self, file_hash: str) -> Dict[str, Any]:
        """Look up a file hash's (md5/sha1/sha256) VirusTotal reputation."""
        return self._lookup(f"files/{quote(file_hash, safe='')}")


def get_virustotal_client() -> VirusTotalClient:
    """Module-level factory. Never requires a key to construct — the
    key-absent graceful-degrade path lives inside VirusTotalClient itself."""
    return VirusTotalClient()


def enrich_file_hashes(hashes: List[str]) -> Dict[str, Any]:
    """Bulk hash-lookup helper.

    Consumed by agent_security_endpoints.py (FIM/YARA ingestion) via
    asyncio.to_thread. Returns {lowercased-hash: result} for every hash
    whose lookup succeeded (no "error" key) — hashes that are empty or
    whose lookup errored are omitted entirely so callers' `if verdict:`
    checks degrade cleanly rather than treating an error dict as a verdict.
    An empty/falsy input returns {}.
    """
    if not hashes:
        return {}
    client = get_virustotal_client()
    results: Dict[str, Any] = {}
    for raw_hash in hashes:
        if not raw_hash:
            continue
        key = raw_hash.strip().lower()
        if not key:
            continue
        result = client.scan_file_hash(raw_hash)
        if result and "error" not in result:
            results[key] = result
    return results

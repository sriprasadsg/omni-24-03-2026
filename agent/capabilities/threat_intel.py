"""
Threat Intelligence Capability
Enriches IOCs (IPs, domains, URLs, file hashes) via VirusTotal API v3.
"""
import os
import json
import logging
import requests
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from .base import BaseCapability

logger = logging.getLogger(__name__)

_CACHE_TTL = 300  # seconds — don't re-query the same IOC within 5 minutes


def _vt_key(config: Dict = None) -> str:
    """Return VT API key — prefers server-pushed config over local env var."""
    if config:
        key = config.get("virustotal_api_key", "")
        if key:
            return key
    return os.getenv("VIRUSTOTAL_API_KEY", "")


def _vt_headers(config: Dict = None) -> Dict[str, str]:
    return {"x-apikey": _vt_key(config), "Accept": "application/json"}


def _is_vt_configured(config: Dict = None) -> bool:
    return bool(_vt_key(config))


def _parse_vt_response(data: Dict, artifact: str, artifact_type: str) -> Dict[str, Any]:
    attrs = data.get("data", {}).get("attributes", {})
    stats = attrs.get("last_analysis_stats", {})
    malicious  = stats.get("malicious", 0)
    suspicious = stats.get("suspicious", 0)
    harmless   = stats.get("harmless", 0)
    undetected = stats.get("undetected", 0)
    total      = malicious + suspicious + harmless + undetected
    detections = malicious + suspicious

    if malicious > 0:
        verdict = "Malicious"
    elif suspicious > 0:
        verdict = "Suspicious"
    else:
        verdict = "Harmless"

    return {
        "artifact":        artifact,
        "type":            artifact_type,
        "verdict":         verdict,
        "detectionRatio":  f"{detections}/{total}",
        "malicious":       malicious,
        "suspicious":      suspicious,
        "harmless":        harmless,
        "undetected":      undetected,
        "scanDate":        attrs.get("last_analysis_date", ""),
        "reputation":      attrs.get("reputation", 0),
    }


def lookup_ip(ip_address: str, config: Dict = None) -> Dict[str, Any]:
    """Query VirusTotal for an IP address reputation."""
    if not _is_vt_configured(config):
        return {"artifact": ip_address, "type": "ip", "verdict": "Unconfigured",
                "error": "VIRUSTOTAL_API_KEY not set on agent or server"}
    try:
        resp = requests.get(
            f"https://www.virustotal.com/api/v3/ip_addresses/{ip_address}",
            headers=_vt_headers(config), timeout=10
        )
        if resp.status_code == 200:
            return _parse_vt_response(resp.json(), ip_address, "ip")
        if resp.status_code == 404:
            return {"artifact": ip_address, "type": "ip", "verdict": "Unknown",
                    "message": "Not found in VirusTotal"}
        return {"artifact": ip_address, "type": "ip", "verdict": "Error",
                "error": f"HTTP {resp.status_code}"}
    except Exception as e:
        return {"artifact": ip_address, "type": "ip", "verdict": "Error", "error": str(e)}


def lookup_domain(domain: str, config: Dict = None) -> Dict[str, Any]:
    """Query VirusTotal for a domain reputation."""
    if not _is_vt_configured(config):
        return {"artifact": domain, "type": "domain", "verdict": "Unconfigured",
                "error": "VIRUSTOTAL_API_KEY not set on agent or server"}
    try:
        resp = requests.get(
            f"https://www.virustotal.com/api/v3/domains/{domain}",
            headers=_vt_headers(config), timeout=10
        )
        if resp.status_code == 200:
            return _parse_vt_response(resp.json(), domain, "domain")
        if resp.status_code == 404:
            return {"artifact": domain, "type": "domain", "verdict": "Unknown",
                    "message": "Not found in VirusTotal"}
        return {"artifact": domain, "type": "domain", "verdict": "Error",
                "error": f"HTTP {resp.status_code}"}
    except Exception as e:
        return {"artifact": domain, "type": "domain", "verdict": "Error", "error": str(e)}


def lookup_url(url: str, config: Dict = None) -> Dict[str, Any]:
    """Query VirusTotal for a URL reputation."""
    if not _is_vt_configured(config):
        return {"artifact": url, "type": "url", "verdict": "Unconfigured",
                "error": "VIRUSTOTAL_API_KEY not set on agent or server"}
    try:
        import base64
        url_id = base64.urlsafe_b64encode(url.encode()).decode().rstrip("=")
        resp = requests.get(
            f"https://www.virustotal.com/api/v3/urls/{url_id}",
            headers=_vt_headers(config), timeout=10
        )
        if resp.status_code == 200:
            return _parse_vt_response(resp.json(), url, "url")
        if resp.status_code == 404:
            return {"artifact": url, "type": "url", "verdict": "Unknown",
                    "message": "Not found in VirusTotal — submit for scanning"}
        return {"artifact": url, "type": "url", "verdict": "Error",
                "error": f"HTTP {resp.status_code}"}
    except Exception as e:
        return {"artifact": url, "type": "url", "verdict": "Error", "error": str(e)}


def lookup_hash(file_hash: str, config: Dict = None) -> Dict[str, Any]:
    """Query VirusTotal for a file hash (MD5/SHA1/SHA256) reputation."""
    if not _is_vt_configured(config):
        return {"artifact": file_hash, "type": "hash", "verdict": "Unconfigured",
                "error": "VIRUSTOTAL_API_KEY not set on agent or server"}
    try:
        resp = requests.get(
            f"https://www.virustotal.com/api/v3/files/{file_hash}",
            headers=_vt_headers(config), timeout=10
        )
        if resp.status_code == 200:
            return _parse_vt_response(resp.json(), file_hash, "hash")
        if resp.status_code == 404:
            return {"artifact": file_hash, "type": "hash", "verdict": "Unknown",
                    "message": "Hash not found in VirusTotal"}
        return {"artifact": file_hash, "type": "hash", "verdict": "Error",
                "error": f"HTTP {resp.status_code}"}
    except Exception as e:
        return {"artifact": file_hash, "type": "hash", "verdict": "Error", "error": str(e)}


class ThreatIntelCapability(BaseCapability):
    """
    Threat Intelligence capability — enriches a watchlist of IOCs via VirusTotal.
    IOCs are read from config["iocs"] (list of {"type": "ip"|"domain"|"url"|"hash", "value": "..."}).
    If no IOCs are configured, returns status/configuration info only.
    """

    _lookup_map = {
        "ip":     lookup_ip,
        "domain": lookup_domain,
        "url":    lookup_url,
        "hash":   lookup_hash,
    }

    @property
    def capability_id(self) -> str:
        return "threat_intel"

    @property
    def capability_name(self) -> str:
        return "Threat Intelligence (VirusTotal)"

    def collect(self) -> Dict[str, Any]:
        configured = _is_vt_configured(self.config)
        if not configured:
            logger.warning(
                "[ThreatIntel] VirusTotal API key not set (checked config + env). "
                "Push the key from the Security Intelligence Connectors dashboard to enable IOC enrichment."
            )
        iocs: List[Dict[str, str]] = self.config.get("iocs", [])

        results = []
        malicious_count = 0

        for ioc in iocs[:20]:  # cap at 20 per cycle to respect API limits
            ioc_type  = ioc.get("type", "").lower()
            ioc_value = ioc.get("value", "").strip()
            if not ioc_value or ioc_type not in self._lookup_map:
                continue
            result = self._lookup_map[ioc_type](ioc_value, self.config)
            results.append(result)
            if result.get("verdict") == "Malicious":
                malicious_count += 1
                logger.warning(
                    "[ThreatIntel] Malicious IOC detected: %s (%s) — %s",
                    ioc_value, ioc_type, result.get("detectionRatio", ""),
                )

        return {
            "configured":      configured,
            "iocs_checked":    len(results),
            "malicious_count": malicious_count,
            "results":         results,
            "scan_time":       datetime.now(timezone.utc).isoformat(),
        }

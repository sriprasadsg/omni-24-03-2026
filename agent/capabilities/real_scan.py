"""
Real Vulnerability Scanning Capability
Delegates to the VulnerabilityScanner which queries the OSV API for real CVE data.
Falls back to outdated-package detection if OSV is unreachable.
"""
from .base import BaseCapability
from typing import Dict, Any
import logging

logger = logging.getLogger(__name__)


class RealVulnerabilityScanningCapability(BaseCapability):

    @property
    def capability_id(self) -> str:
        return "vulnerability_scanning"

    @property
    def capability_name(self) -> str:
        return "Real Vulnerability Scanning"

    def collect(self) -> Dict[str, Any]:
        """Run a full vulnerability scan using OSV API, falling back to pip outdated check."""
        try:
            from .vulnerability_scanner import VulnerabilityScanner
            scanner = VulnerabilityScanner()
            report = scanner.generate_scan_report()

            # Flatten into the shape agent.py and the backend expect
            vulnerabilities = []
            for pkg in report.get("software", []):
                for cve in pkg.get("cves", []):
                    vulnerabilities.append({
                        "package": pkg["name"],
                        "version": pkg["version"],
                        "ecosystem": pkg.get("ecosystem", "PyPI"),
                        "cve_id": cve.get("cve") or cve.get("id", "UNKNOWN"),
                        "severity": cve.get("severity", "Medium"),
                        "description": cve.get("summary", ""),
                    })

            return {
                "installed_software_count": report.get("total_packages", 0),
                "vulnerabilities_found": report.get("total_cves", 0),
                "vulnerable_packages": report.get("vulnerable_packages", 0),
                "vulnerabilities": vulnerabilities[:50],
                "os_patches": report.get("os_patches", {}),
                "scan_timestamp": report.get("scan_timestamp", self._get_timestamp()),
            }
        except Exception as e:
            logger.warning("OSV scan failed, falling back to pip outdated check: %s", e)
            logger.debug("Full exception for OSV scan failure: ", exc_info=True)
            return self._fallback_scan()

    def _fallback_scan(self) -> Dict[str, Any]:
        """Fallback: detect outdated pip packages without CVE lookup."""
        import subprocess
        import sys
        import json

        outdated = []
        try:
            result = subprocess.run(
                [sys.executable, "-m", "pip", "list", "--outdated", "--format=json"],
                capture_output=True, text=True, timeout=30,
            )
            if result.returncode == 0:
                for item in json.loads(result.stdout):
                    outdated.append({
                        "package": item.get("name"),
                        "version": item.get("version"),
                        "ecosystem": "PyPI",
                        "cve_id": "OUTDATED-LIB",
                        "severity": "Medium",
                        "description": (
                            f"{item.get('name')} is outdated: "
                            f"{item.get('version')} → {item.get('latest_version')}"
                        ),
                    })
        except Exception as ex:
            logger.debug("pip outdated fallback also failed: %s", ex)

        return {
            "installed_software_count": len(outdated),
            "vulnerabilities_found": len(outdated),
            "vulnerable_packages": len(outdated),
            "vulnerabilities": outdated[:50],
            "os_patches": {},
            "scan_timestamp": self._get_timestamp(),
            "fallback": True,
        }

    def _get_timestamp(self) -> str:
        from datetime import datetime, timezone
        return datetime.now(timezone.utc).isoformat()

"""
Vulnerability Scanning Capability
Scans installed packages for known CVEs
"""
from .base import BaseCapability
import platform
import subprocess
from typing import Dict, Any, List
import re

class VulnerabilityScanningCapability(BaseCapability):
    
    @property
    def capability_id(self) -> str:
        return "vulnerability_scanning"
    
    @property
    def capability_name(self) -> str:
        return "Vulnerability Scanning"
    
    def collect(self) -> Dict[str, Any]:
        """Scan for vulnerabilities in installed software"""
        system = platform.system()
        software = []
        vulnerabilities = []
        
        if system == "Windows":
            software = self._get_windows_software()
        elif system == "Linux":
            software = self._get_linux_software()
        
        vulnerabilities = self._check_vulnerabilities(software)

        return {
            "installed_software_count": len(software),
            "vulnerabilities_found": len(vulnerabilities),
            "vulnerabilities": vulnerabilities[:10],
            "scan_timestamp": self._get_timestamp()
        }
    
    def _get_windows_software(self) -> List[Dict[str, str]]:
        """Get installed software on Windows"""
        try:
            result = subprocess.run(
                ['powershell', '-Command', 
                 'Get-ItemProperty HKLM:\\Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\* | Select-Object DisplayName, DisplayVersion | ConvertTo-Json'],
                capture_output=True, text=True, timeout=10
            )
            if result.returncode == 0 and result.stdout:
                import json
                data = json.loads(result.stdout)
                if not isinstance(data, list):
                    data = [data]
                return [
                    {"name": item.get("DisplayName", ""), "version": item.get("DisplayVersion", "")}
                    for item in data if item.get("DisplayName")
                ]
        except:
            pass
        return []
    
    def _get_linux_software(self) -> List[Dict[str, str]]:
        """Get installed packages on Linux"""
        try:
            # Try dpkg first (Debian/Ubuntu)
            result = subprocess.run(['dpkg', '-l'], capture_output=True, text=True, timeout=10)
            if result.returncode == 0:
                packages = []
                for line in result.stdout.split('\n'):
                    if line.startswith('ii '):
                        parts = line.split()
                        if len(parts) >= 3:
                            packages.append({"name": parts[1], "version": parts[2]})
                return packages[:100]  # Limit to 100
        except:
            pass
        
        try:
            # Try rpm (RedHat/CentOS)
            result = subprocess.run(['rpm', '-qa', '--queryformat', '%{NAME} %{VERSION}\n'], 
                                  capture_output=True, text=True, timeout=10)
            if result.returncode == 0:
                packages = []
                for line in result.stdout.split('\n'):
                    if line:
                        parts = line.split()
                        if len(parts) >= 2:
                            packages.append({"name": parts[0], "version": parts[1]})
                return packages[:100]
        except:
            pass
        
        return []
    
    def _check_vulnerabilities(self, software: List[Dict[str, str]]) -> List[Dict[str, Any]]:
        """Query OSV API for real CVEs; fall back to outdated-package detection."""
        try:
            from .vulnerability_scanner import VulnerabilityScanner
            scanner = VulnerabilityScanner()
            report = scanner.generate_scan_report()
            vulnerabilities = []
            for pkg in report.get("software", []):
                for cve in pkg.get("cves", []):
                    vulnerabilities.append({
                        "package": pkg["name"],
                        "version": pkg["version"],
                        "cve_id": cve.get("cve") or cve.get("id", "UNKNOWN"),
                        "severity": cve.get("severity", "Medium"),
                        "description": cve.get("summary", ""),
                    })
            return vulnerabilities
        except Exception:
            pass

        # Fallback: flag any software packages without a known-good version string
        vulnerabilities = []
        for pkg in software[:50]:
            version = pkg.get("version", "")
            if not version or version in ("", "N/A", "Unknown"):
                vulnerabilities.append({
                    "package": pkg.get("name"),
                    "version": version,
                    "cve_id": "UNKNOWN-VERSION",
                    "severity": "Low",
                    "description": f"Package {pkg.get('name')} has no version metadata — cannot assess CVE exposure.",
                })
        return vulnerabilities
    
    def _get_timestamp(self) -> str:
        from datetime import datetime
        return datetime.now().isoformat()

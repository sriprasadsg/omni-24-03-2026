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
        
        # Simulate vulnerability detection (in production, query CVE database)
        vulnerabilities = self._simulate_vulnerability_check(software)
        
        return {
            "installed_software_count": len(software),
            "vulnerabilities_found": len(vulnerabilities),
            "vulnerabilities": vulnerabilities[:10],  # Limit to 10 for heartbeat
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
    
    def _simulate_vulnerability_check(self, software: List[Dict[str, str]]) -> List[Dict[str, Any]]:
        """Simulate vulnerability checking (mock data for demo)"""
        # In production, this would query NVD API or local CVE database
        vulnerabilities = []
        
        # Simulate finding vulnerabilities in older software
        risky_keywords = ['openssl', 'apache', 'nginx', 'kernel', 'python', 'node']
        
        for pkg in software[:20]:  # Check first 20 packages
            name = pkg.get('name', '').lower()
            if any(keyword in name for keyword in risky_keywords):
                # Simulate vulnerability
                vulnerabilities.append({
                    "package": pkg.get('name'),
                    "version": pkg.get('version'),
                    "cve_id": f"CVE-2024-{hash(name) % 10000:04d}",
                    "severity": self._random_severity(name),
                    "description": f"Potential vulnerability in {pkg.get('name')}"
                })
        
        return vulnerabilities
    
    def _random_severity(self, seed: str) -> str:
        """Generate consistent severity based on package name"""
        hash_val = hash(seed) % 4
        return ["Critical", "High", "Medium", "Low"][hash_val]
    
    def _get_timestamp(self) -> str:
        from datetime import datetime
        return datetime.now().isoformat()

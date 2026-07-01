"""
Real Vulnerability Scanning Capability
Scans installed pip packages for outdated versions
"""
from .base import BaseCapability
import subprocess
import json
from typing import Dict, Any, List
import sys

class RealVulnerabilityScanningCapability(BaseCapability):
    
    @property
    def capability_id(self) -> str:
        return "vulnerability_scanning"
    
    @property
    def capability_name(self) -> str:
        return "Real Vulnerability Scanning"
    
    def collect(self) -> Dict[str, Any]:
        """Scan for outdated pip packages"""
        outdated_packages = self._get_outdated_packages()
        
        return {
            "installed_software_count": len(outdated_packages), # Just counting outdated for now as a proxy
            "vulnerabilities_found": len(outdated_packages),
            "vulnerabilities": outdated_packages[:10],
            "scan_timestamp": self._get_timestamp()
        }
    
    def _get_outdated_packages(self) -> List[Dict[str, Any]]:
        """Get outdated pip packages"""
        try:
            # Run pip list --outdated --format=json
            result = subprocess.run(
                [sys.executable, '-m', 'pip', 'list', '--outdated', '--format=json'],
                capture_output=True, text=True, timeout=30
            )
            
            if result.returncode == 0:
                data = json.loads(result.stdout)
                vulnerabilities = []
                
                for item in data:
                    vulnerabilities.append({
                        "package": item.get("name"),
                        "version": item.get("version"),
                        "latest_version": item.get("latest_version"),
                        "cve_id": "OUTDATED-LIB", # Placeholder for real CVE lookup
                        "severity": "Medium", # Assume medium for outdated
                        "description": f"Package {item.get('name')} is outdated. Installed: {item.get('version')}, Latest: {item.get('latest_version')}"
                    })
                return vulnerabilities
        except Exception as e:
            print(f"Error scanning packages: {e}")
            pass
        
        return []
    
    def _get_timestamp(self) -> str:
        from datetime import datetime
        return datetime.now().isoformat()

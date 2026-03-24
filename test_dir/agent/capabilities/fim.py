"""
File Integrity Monitoring Capability
Monitors critical system files for unauthorized changes
"""
from .base import BaseCapability
import os
import hashlib
import platform
from typing import Dict, Any, List

class FIMCapability(BaseCapability):
    
    @property
    def capability_id(self) -> str:
        return "fim"
    
    @property
    def capability_name(self) -> str:
        return "File Integrity Monitoring"
    
    def collect(self) -> Dict[str, Any]:
        """Monitor critical files for changes"""
        system = platform.system()
        critical_files = self._get_critical_files(system)
        monitored_files = []
        
        for filepath in critical_files:
            if os.path.exists(filepath):
                try:
                    checksum = self._calculate_checksum(filepath)
                    stat = os.stat(filepath)
                    monitored_files.append({
                        "path": filepath,
                        "checksum": checksum,
                        "size": stat.st_size,
                        "modified": stat.st_mtime,
                        "status": "Monitored"
                    })
                except Exception as e:
                    monitored_files.append({
                        "path": filepath,
                        "status": f"Error: {e}"
                    })
        
        return {
            "monitored_files": monitored_files,
            "count": len(monitored_files)
        }
    
    def _get_critical_files(self, system: str) -> List[str]:
        """Get list of critical files to monitor based on OS"""
        if system == "Windows":
            return [
                r"C:\Windows\System32\drivers\etc\hosts",
                r"C:\Windows\System32\config\SAM",
                r"C:\Windows\System32\config\SYSTEM"
            ]
        elif system == "Linux":
            return [
                "/etc/passwd",
                "/etc/shadow",
                "/etc/sudoers",
                "/etc/hosts",
                "/etc/ssh/sshd_config"
            ]
        return []
    
    def _calculate_checksum(self, filepath: str) -> str:
        """Calculate SHA256 checksum of a file"""
        sha256 = hashlib.sha256()
        try:
            with open(filepath, 'rb') as f:
                while chunk := f.read(8192):
                    sha256.update(chunk)
            return sha256.hexdigest()
        except:
            return "N/A"

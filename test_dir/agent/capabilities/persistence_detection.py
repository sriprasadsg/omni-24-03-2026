"""
Persistence Detection Capability
Scans for common persistence mechanisms on Windows and Linux.
"""
import os
import sys
import logging
import subprocess
from typing import Dict, Any, List
from .base import BaseCapability

logger = logging.getLogger(__name__)

class PersistenceDetectionCapability(BaseCapability):
    
    @property
    def capability_id(self) -> str:
        return "persistence_detection"
    
    @property
    def capability_name(self) -> str:
        return "Persistence Detection"
    
    def collect(self) -> Dict[str, Any]:
        """
        Perform a persistence scan and return findings.
        """
        findings = []
        try:
            if os.name == "nt":
                findings = self._scan_windows()
            else:
                findings = self._scan_linux()
        except Exception as e:
            logger.error(f"Persistence scan failed: {e}")
            return {"error": str(e), "findings": []}
            
        return {
            "findings": findings,
            "count": len(findings),
            "platform": os.name
        }

    def _scan_windows(self) -> List[Dict[str, Any]]:
        findings = []
        try:
            import winreg
        except ImportError:
            return findings

        # Common Run keys
        locations = [
            (winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run"),
            (winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\RunOnce"),
            (winreg.HKEY_LOCAL_MACHINE, r"Software\Microsoft\Windows\CurrentVersion\Run"),
            (winreg.HKEY_LOCAL_MACHINE, r"Software\Microsoft\Windows\CurrentVersion\RunOnce"),
        ]

        for hkey, path in locations:
            try:
                with winreg.OpenKey(hkey, path) as key:
                    i = 0
                    while True:
                        try:
                            name, value, _ = winreg.EnumValue(key, i)
                            findings.append({
                                "type": "Registry Run Key",
                                "location": f"{'HKCU' if hkey == winreg.HKEY_CURRENT_USER else 'HKLM'}\\{path}",
                                "name": name,
                                "command": value,
                                "severity": "Medium" if "temp" in value.lower() or "appdata" in value.lower() else "Low"
                            })
                            i += 1
                        except OSError:
                            break
            except Exception:
                continue

        # Startup folders
        startup_paths = [
            os.path.join(os.environ.get('APPDATA', ''), r"Microsoft\Windows\Start Menu\Programs\Startup"),
            r"C:\ProgramData\Microsoft\Windows\Start Menu\Programs\Startup"
        ]
        for path in startup_paths:
            if os.path.exists(path):
                for item in os.listdir(path):
                    findings.append({
                        "type": "Startup Folder",
                        "location": path,
                        "name": item,
                        "command": os.path.join(path, item),
                        "severity": "Low"
                    })

        return findings

    def _scan_linux(self) -> List[Dict[str, Any]]:
        findings = []
        
        # systemd services
        systemd_path = "/etc/systemd/system"
        if os.path.exists(systemd_path):
            for item in os.listdir(systemd_path):
                if item.endswith(".service"):
                    findings.append({
                        "type": "systemd Service",
                        "location": os.path.join(systemd_path, item),
                        "name": item,
                        "command": "N/A (Check unit file)",
                        "severity": "Low"
                    })

        # crontab
        try:
            output = subprocess.check_output(["crontab", "-l"], stderr=subprocess.STDOUT).decode()
            for line in output.splitlines():
                if line.strip() and not line.startswith("#"):
                    findings.append({
                        "type": "Crontab Entry",
                        "location": "User Crontab",
                        "name": "Cron Job",
                        "command": line.strip(),
                        "severity": "Low"
                    })
        except Exception:
            pass

        return findings

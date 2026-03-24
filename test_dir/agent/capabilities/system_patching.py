"""
System Patching & Health Capability
Collects pending OS updates, BIOS version, and system uptime.
"""
from .base import BaseCapability
import platform
import subprocess
import datetime
from typing import Dict, Any, List

class SystemPatchingCapability(BaseCapability):
    
    @property
    def capability_id(self) -> str:
        return "system_patching"
    
    @property
    def capability_name(self) -> str:
        return "System Patching & Health"
    
    def collect(self) -> Dict[str, Any]:
        """Collect patching and health metrics"""
        data = {
            "pending_updates": [],
            "bios_info": {},
            "uptime": {},
            "last_scan": datetime.datetime.now().isoformat()
        }
        
        system = platform.system()
        if system == "Windows":
            data["pending_updates"] = self._get_windows_updates()
            data["bios_info"] = self._get_windows_bios()
            data["uptime"] = self._get_windows_uptime()
        elif system == "Linux":
            data["pending_updates"] = self._get_linux_updates()
            # Linux BIOS/Uptime placeholder
            
        return data

    def _get_windows_updates(self) -> List[Dict[str, str]]:
        """Check for pending Windows Updates using PowerShell"""
        updates = []
        try:
            # PowerShell script to search for updates (IsInstalled=0)
            ps_script = """
            $Session = New-Object -ComObject Microsoft.Update.Session
            $Searcher = $Session.CreateUpdateSearcher()
            $Criteria = "IsInstalled=0 and Type='Software'"
            $Result = $Searcher.Search($Criteria)
            $Result.Updates | Select-Object Title, Severity, IsMandatory | ConvertTo-Json
            """
            
            cmd = ["powershell", "-Command", ps_script]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            
            if result.returncode == 0 and result.stdout.strip():
                import json
                try:
                    raw_data = json.loads(result.stdout)
                    if not isinstance(raw_data, list):
                        raw_data = [raw_data]
                    
                        # Map Windows Update severity codes to standard strings
                        # 0=N/A, 1=Low, 2=Moderate, 3=Important, 4=Critical
                        # Note: Different versions of WUA might return different codes, so we handle common ones.
                        raw_severity = item.get("Severity", "Unknown")
                        severity_map = {
                            "0": "Low",
                            "1": "Low",
                            "2": "Medium",
                            "3": "High",
                            "4": "Critical",
                            "5": "Critical"
                        }
                        severity = severity_map.get(str(raw_severity), "Medium")
                        
                        updates.append({
                            "title": item.get("Title", "Unknown Update"),
                            "severity": severity,
                            "mandatory": item.get("IsMandatory", False)
                        })
                except json.JSONDecodeError:
                    pass # Result might be empty/null if no updates found
        except Exception as e:
            print(f"Error checking Windows Updates: {e}")
            
        return updates

    def _get_windows_bios(self) -> Dict[str, str]:
        """Get BIOS Version and Manufacturer via PowerShell"""
        info = {"version": "Unknown", "manufacturer": "Unknown", "release_date": "Unknown"}
        try:
            ps_script = """
            Get-CimInstance Win32_BIOS | Select-Object Manufacturer, SMBIOSBIOSVersion, @{N='ReleaseDate';E={$_.ReleaseDate.ToString('yyyy-MM-dd')}} | ConvertTo-Json
            """
            cmd = ["powershell", "-Command", ps_script]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            
            if result.returncode == 0 and result.stdout.strip():
                import json
                try:
                    data = json.loads(result.stdout)
                    # Handle single object vs list (though BIOS is usually single)
                    if isinstance(data, list):
                        data = data[0]
                        
                    info["manufacturer"] = data.get("Manufacturer", "Unknown")
                    info["version"] = data.get("SMBIOSBIOSVersion", "Unknown")
                    info["release_date"] = data.get("ReleaseDate", "Unknown")
                except json.JSONDecodeError:
                    pass
        except Exception as e:
            print(f"Error checking BIOS: {e}")
        return info

    def _get_windows_uptime(self) -> Dict[str, str]:
        """Get Last Boot Time via PowerShell"""
        info = {"boot_time": "Unknown", "uptime_seconds": 0}
        try:
            ps_script = """
            Get-CimInstance Win32_OperatingSystem | Select-Object @{N='LastBootUpTime';E={$_.LastBootUpTime.ToString('yyyy-MM-dd HH:mm:ss')}} | ConvertTo-Json
            """
            cmd = ["powershell", "-Command", ps_script]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            
            if result.returncode == 0 and result.stdout.strip():
                import json
                try:
                    data = json.loads(result.stdout)
                    if isinstance(data, list):
                        data = data[0]
                        
                    info["boot_time"] = data.get("LastBootUpTime", "Unknown")
                    
                    # Calculate uptime if possible (simplified for now)
                    # In a real scenario, we'd parse the date string to a datetime obj
                except json.JSONDecodeError:
                    pass
        except Exception as e:
            print(f"Error checking Uptime: {e}")
        return info

    def _get_linux_updates(self) -> List[Dict[str, str]]:
        # Placeholder for Linux update check (apt/yum)
        return []

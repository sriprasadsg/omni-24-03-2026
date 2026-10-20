"""
System Patching & Health Capability
Collects pending OS updates, BIOS version, and system uptime.
"""
from .base import BaseCapability
import platform
import subprocess
import datetime
import json
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
        self._scan_error = None

        system = platform.system()
        if system == "Windows":
            data["pending_updates"] = self._get_windows_updates()
            data["bios_info"] = self._get_windows_bios()
            data["uptime"] = self._get_windows_uptime()
        elif system == "Linux":
            data["pending_updates"] = self._get_linux_updates()
            data["bios_info"] = self._get_linux_bios()
            data["uptime"] = self._get_linux_uptime()
        data["pending_update_count"] = len(data["pending_updates"])
        if self._scan_error:
            # Lets the dashboard tell "0 pending" apart from "the scan failed".
            data["scan_error"] = self._scan_error

        return data

    def _get_windows_updates(self) -> List[Dict[str, Any]]:
        """Pending Windows Updates from the Windows Update Agent, keyed by KB number."""
        updates = []
        ps_script = """
        $ErrorActionPreference = 'Stop'
        $Session = New-Object -ComObject Microsoft.Update.Session
        $Searcher = $Session.CreateUpdateSearcher()
        $Result = $Searcher.Search("IsInstalled=0 and Type='Software' and IsHidden=0")
        @($Result.Updates | ForEach-Object {
            [PSCustomObject]@{
                Title = $_.Title
                MsrcSeverity = $_.MsrcSeverity
                IsMandatory = $_.IsMandatory
                KB = ($_.KBArticleIDs | Select-Object -First 1)
            }
        }) | ConvertTo-Json -Compress
        """
        try:
            # A Windows Update search routinely takes minutes on a cold cache.
            result = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_script],
                                    capture_output=True, text=True, timeout=600)
        except Exception as e:
            self._scan_error = f"Windows Update search failed: {e}"
            return updates
        if result.returncode != 0:
            self._scan_error = f"Windows Update search failed: {(result.stderr or result.stdout).strip()[:300]}"
            return updates
        text = result.stdout.strip()
        if not text:
            return updates
        try:
            raw_data = json.loads(text)
        except json.JSONDecodeError:
            self._scan_error = "Windows Update search returned unreadable output"
            return updates
        if not isinstance(raw_data, list):
            raw_data = [raw_data]
        severity_map = {"critical": "Critical", "important": "High", "moderate": "Medium", "low": "Low"}
        for item in raw_data:
            if not isinstance(item, dict):
                continue
            kb = str(item.get("KB") or "").strip()
            entry = {
                "title": item.get("Title", "Unknown Update"),
                "severity": severity_map.get(str(item.get("MsrcSeverity") or "").lower(), "Unknown"),
                "mandatory": bool(item.get("IsMandatory", False)),
            }
            if kb.isdigit():
                entry["kb"] = kb
                entry["id"] = f"KB{kb}"
            updates.append(entry)
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

    def _get_linux_bios(self) -> Dict[str, str]:
        """Get BIOS Version and Manufacturer from sysfs, then dmidecode"""
        info = {"version": "Unknown", "manufacturer": "Unknown", "release_date": "Unknown"}
        # sysfs is world-readable; dmidecode needs root, which the agent often lacks.
        for field, name in (("version", "bios_version"), ("manufacturer", "bios_vendor"),
                            ("release_date", "bios_date")):
            try:
                with open(f"/sys/class/dmi/id/{name}") as f:
                    value = f.read().strip()
                if value and value != "Not Specified":
                    info[field] = value
            except OSError:
                pass
        if "Unknown" not in info.values():
            return info
        try:
            # dmidecode -t bios prints "Vendor:", "Version:", "Release Date:"
            result = subprocess.run(
                ["dmidecode", "-t", "bios"],
                capture_output=True,
                text=True,
                timeout=10
            )
            if result.returncode == 0:
                for line in result.stdout.split('\n'):
                    line = line.strip()
                    if ':' in line:
                        key, value = line.split(':', 1)
                        key = key.strip().lower()
                        value = value.strip()
                        field = {"version": "version", "vendor": "manufacturer",
                                 "release date": "release_date"}.get(key)
                        if field and value and info[field] == "Unknown":
                            info[field] = value
        except (FileNotFoundError, subprocess.TimeoutExpired, PermissionError, Exception):
            pass
        return info

    def _get_linux_uptime(self) -> Dict[str, str]:
        """Get Last Boot Time and uptime from /proc/uptime"""
        info = {"boot_time": "Unknown", "uptime_seconds": 0}
        try:
            with open("/proc/uptime", "r") as f:
                uptime_seconds = float(f.read().split()[0])
            info["uptime_seconds"] = uptime_seconds

            # Boot time as ISO-8601 UTC so the dashboard can show it in local time
            boot_time = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(seconds=uptime_seconds)
            info["boot_time"] = boot_time.replace(microsecond=0).isoformat()
        except (FileNotFoundError, PermissionError, Exception):
            pass
        return info

    def _get_linux_updates(self) -> List[Dict[str, str]]:
        """Check for pending Linux updates (apt/dnf/yum)"""
        updates = []
        try:
            # Try apt (Debian/Ubuntu)
            result = subprocess.run(
                ["apt", "list", "--upgradable"],
                capture_output=True,
                text=True,
                timeout=30
            )
            if result.returncode == 0:
                for line in result.stdout.strip().split('\n')[1:]:  # Skip header line
                    if '/' in line:
                        parts = line.split('/')
                        pkg_name = parts[0].strip()
                        # Parse version info from the rest
                        # "pkg/suite 1.2-3 amd64 [upgradable from: 1.2-2]": the version is the 2nd token
                        rest = '/'.join(parts[1:]).split()
                        version_part = rest[1] if len(rest) > 1 else ''
                        updates.append({
                            "title": f"{pkg_name} ({version_part})",
                            "severity": "Medium",
                            "mandatory": False,
                            "package": pkg_name,
                            "id": pkg_name,
                        })
                return updates[:50]  # Limit to 50
        except (FileNotFoundError, subprocess.TimeoutExpired, Exception):
            pass

        try:
            # Try dnf (Fedora/RHEL 8+)
            result = subprocess.run(
                ["dnf", "check-update", "-q"],
                capture_output=True,
                text=True,
                timeout=30
            )
            if result.returncode == 100:  # 100 means updates available
                for line in result.stdout.strip().split('\n'):
                    parts = line.split()
                    if len(parts) >= 3:  # "name.arch  version  repo"; skips headers and blank lines
                        updates.append({
                            "title": parts[0],
                            "severity": "Medium",
                            "mandatory": False,
                            "package": parts[0],
                            "id": parts[0],
                        })
                return updates[:50]
        except (FileNotFoundError, subprocess.TimeoutExpired, Exception):
            pass

        try:
            # Try yum (RHEL/CentOS 7)
            result = subprocess.run(
                ["yum", "check-update", "-q"],
                capture_output=True,
                text=True,
                timeout=30
            )
            if result.returncode == 100:
                for line in result.stdout.strip().split('\n'):
                    parts = line.split()
                    if len(parts) >= 3:  # "name.arch  version  repo"; skips headers and blank lines
                        updates.append({
                            "title": parts[0],
                            "severity": "Medium",
                            "mandatory": False,
                            "package": parts[0],
                            "id": parts[0],
                        })
                return updates[:50]
        except (FileNotFoundError, subprocess.TimeoutExpired, Exception):
            pass

        return updates

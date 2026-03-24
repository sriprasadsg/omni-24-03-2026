"""
Metrics Collection Capability
Collects CPU, memory, disk, network metrics, and installed software inventory
"""
from .base import BaseCapability
import psutil
import cpuinfo
from typing import Dict, Any, List
import platform
import subprocess
from datetime import datetime

class MetricsCapability(BaseCapability):
    
    @property
    def capability_id(self) -> str:
        return "metrics_collection"
    
    @property
    def capability_name(self) -> str:
        return "Metric Collection"
    
    def _collect_installed_software_windows(self) -> List[Dict[str, Any]]:
        """Collect installed software on Windows using PowerShell with improved date parsing"""
        try:
            # First, check for updates if winget is available
            upgradable_packages = set()
            try:
                winget_check = subprocess.run(
                    ["winget", "upgrade", "--include-unknown"],
                    capture_output=True,
                    text=True,
                    timeout=60
                )
                if winget_check.returncode == 0:
                    for line in winget_check.stdout.split('\n'):
                        # Very basic parsing, assumes name is at start
                        # A better approach would be JSON output if supported or specific column parsing
                        parts = line.split()
                        if len(parts) > 2:
                            upgradable_packages.add(parts[0].lower())
            except Exception:
                pass # Winget might not be available
            
            # Use PowerShell to get installed software from registry
            ps_command = """
            Get-ItemProperty HKLM:\\Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\* |
            Select-Object DisplayName, DisplayVersion, InstallDate |
            Where-Object {$_.DisplayName -ne $null} |
            ConvertTo-Json
            """
            
            result = subprocess.run(
                ["powershell", "-Command", ps_command],
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.returncode == 0 and result.stdout.strip():
                import json
                try:
                    software_list = json.loads(result.stdout)
                except json.JSONDecodeError:
                    return []
                
                # Handle single item (not a list)
                if isinstance(software_list, dict):
                    software_list = [software_list]
                
                installed_software = []
                for item in software_list:
                    if item.get('DisplayName'):
                        # Parse install date if available
                        install_date_str = item.get('InstallDate', '')
                        install_date = 'Unknown'
                        
                        if install_date_str:
                            install_date_str = str(install_date_str).strip()
                            if len(install_date_str) == 8 and install_date_str.isdigit():
                                # Format: YYYYMMDD
                                install_date = f"{install_date_str[0:4]}-{install_date_str[4:6]}-{install_date_str[6:8]}"
                            
                        name = item.get('DisplayName', 'Unknown')
                        version = item.get('DisplayVersion', 'Unknown')
                        
                        installed_software.append({
                            'name': name,
                            'version': version,
                            'installDate': install_date,
                            'updateAvailable': name.lower() in upgradable_packages
                        })
                
                return installed_software[:100]  # Limit to 100 packages
        except Exception as e:
            print(f"Error collecting Windows software: {e}")
        
        return []
    
    def _collect_installed_software_linux(self) -> List[Dict[str, Any]]:
        """Collect installed software on Linux using package managers"""
        try:
            installed_software = []
            upgradable_packages = set()
            
            # Check for updates (apt)
            try:
                apt_check = subprocess.run(
                    ["apt", "list", "--upgradable"],
                    capture_output=True,
                    text=True,
                    timeout=30
                )
                if apt_check.returncode == 0:
                    for line in apt_check.stdout.split('\n'):
                        if '/' in line:
                            upgradable_packages.add(line.split('/')[0])
            except FileNotFoundError:
                pass

            
            # Try dpkg (Debian/Ubuntu)
            try:
                result = subprocess.run(
                    ["dpkg-query", "-W", "-f=${Package}\t${Version}\t${Status}\n"],
                    capture_output=True,
                    text=True,
                    timeout=30
                )
                
                if result.returncode == 0:
                    for line in result.stdout.strip().split('\n'):
                        parts = line.split('\t')
                        if len(parts) >= 3 and 'installed' in parts[2]:
                            name = parts[0]
                            installed_software.append({
                                'name': name,
                                'version': parts[1],
                                'installDate': 'Unknown',  # dpkg doesn't track install date easily
                                'updateAvailable': name in upgradable_packages
                            })
            except FileNotFoundError:
                pass  # dpkg not available
            
            # Try rpm (RedHat/CentOS/Fedora) if dpkg didn't work or to supplement
            if not installed_software:
                try:
                    # check updates dnf
                    try:
                        dnf_check = subprocess.run(["dnf", "check-update", "-q"], capture_output=True, text=True, timeout=30)
                        if dnf_check.returncode == 100: # 100 means updates available
                             for line in dnf_check.stdout.split('\n'):
                                 parts = line.split()
                                 if parts:
                                     upgradable_packages.add(parts[0])
                    except FileNotFoundError:
                        pass
                        
                    result = subprocess.run(
                        ["rpm", "-qa", "--queryformat", "%{NAME}\t%{VERSION}-%{RELEASE}\t%{INSTALLTIME:date}\n"],
                        capture_output=True,
                        text=True,
                        timeout=30
                    )
                    
                    if result.returncode == 0:
                        for line in result.stdout.strip().split('\n'):
                            parts = line.split('\t')
                            if len(parts) >= 2:
                                name = parts[0]
                                install_date = parts[2] if len(parts) > 2 else 'Unknown'
                                # Parse rpm date format if needed, usually it's "Mon 01 Jan 2023..."
                                # Let's try to standardize to YYYY-MM-DD if possible using dateutil or datetime
                                # For now, keep as string or try basic parse
                                try:
                                     dt = datetime.strptime(install_date, "%a %d %b %Y %I:%M:%S %p %Z")
                                     install_date = dt.strftime("%Y-%m-%d")
                                except:
                                     pass # Keep original format if parse fails
                                
                                installed_software.append({
                                    'name': name,
                                    'version': parts[1],
                                    'installDate': install_date,
                                    'updateAvailable': name in upgradable_packages
                                })
                except FileNotFoundError:
                    pass  # rpm not available
            
            return installed_software[:100]  # Limit to 100 packages
        except Exception as e:
            print(f"Error collecting Linux software: {e}")
        
        return []
    
    def _collect_installed_software(self) -> List[Dict[str, Any]]:
        """Collect installed software based on OS"""
        system = platform.system()
        
        if system == "Windows":
            return self._collect_installed_software_windows()
        elif system == "Linux":
            return self._collect_installed_software_linux()
        else:
            return []  # macOS or other systems not implemented yet
    
    def collect(self) -> Dict[str, Any]:
        """Collect system metrics and installed software"""
        cpu_info = cpuinfo.get_cpu_info()
        
        # Collect MAC addresses
        mac_addresses = []
        try:
            for interface_name, interface_addresses in psutil.net_if_addrs().items():
                for address in interface_addresses:
                    if address.family == psutil.AF_LINK:
                        mac_addresses.append({
                            "interface": interface_name,
                            "mac": address.address
                        })
        except Exception as e:
             # Fallback or specific platform handling if needed
             pass

        return {
            "cpu": {
                "percent": psutil.cpu_percent(interval=1),
                "count": psutil.cpu_count(),
                "model": cpu_info.get('brand_raw', 'Unknown')
            },
            "memory": {
                "total": psutil.virtual_memory().total,
                "available": psutil.virtual_memory().available,
                "percent": psutil.virtual_memory().percent
            },
            "disk": [
                {
                    "device": partition.device,
                    "mountpoint": partition.mountpoint,
                    "type": partition.fstype,
                    "total": psutil.disk_usage(partition.mountpoint).total,
                    "used": psutil.disk_usage(partition.mountpoint).used,
                    "free": psutil.disk_usage(partition.mountpoint).free,
                    "percent": psutil.disk_usage(partition.mountpoint).percent
                }
                for partition in psutil.disk_partitions() if 'cdrom' not in partition.opts
            ],
            "network": {
                "bytes_sent": psutil.net_io_counters().bytes_sent,
                "bytes_recv": psutil.net_io_counters().bytes_recv,
                "interfaces": mac_addresses
            },
            "installedSoftware": self._collect_installed_software()
        }

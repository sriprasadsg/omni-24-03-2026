
import platform
import socket
import logging
import subprocess
import psutil
import uuid

logger = logging.getLogger(__name__)

class PlatformUtils:
    """
    Abstracts platform-specific system calls for Windows, Linux, and MacOS.
    """
    
    @staticmethod
    def get_os_type():
        return platform.system()

    @staticmethod
    def get_system_info():
        """
        Return a standardized dictionary of system information:
        {
            "os": "Windows|Linux|Darwin",
            "os_full_name": "Windows 10 Pro ...",
            "os_release": "10",
            "os_version_detail": "10.0.19041",
            "service_pack": "",
            "python_version": "3.9.5"
        }
        """
        system = platform.system()
        info = {
            "os": system,
            "os_release": platform.release(),
            "os_version_detail": platform.version(),
            "os_version": platform.version(),
            "service_pack": "",
            "python_version": platform.python_version(),
            "os_full_name": f"{system} {platform.release()}"
        }

        try:
            if system == "Windows":
                win_rel, win_ver, win_csd, win_ptype = platform.win32_ver()
                info["os_release"] = win_rel
                info["os_version_detail"] = win_ver
                info["service_pack"] = win_csd
                info["os_full_name"] = f"Windows {win_rel} {win_ptype} {win_csd}".strip()
                
            elif system == "Linux":
                # Try reading /etc/os-release
                try:
                    with open("/etc/os-release") as f:
                        for line in f:
                            if line.startswith("PRETTY_NAME="):
                                info["os_full_name"] = line.split("=", 1)[1].strip().strip('"')
                                break
                except:
                    pass
                    
            elif system == "Darwin": # MacOS
                mac_ver, match_stage, arch = platform.mac_ver()
                info["os_release"] = mac_ver
                info["os_full_name"] = f"macOS {mac_ver} {arch}"

        except Exception as e:
            logger.error(f"Error getting system info: {e}")

        return info

    @staticmethod
    def get_ip_address():
        """Get primary non-loopback IP address"""
        try:
            # Method 1: Get all IPs associated with hostname
            hostname = socket.gethostname()
            _, _, ip_list = socket.gethostbyname_ex(hostname)
            
            # Filter out 127. loops
            non_local_ips = [ip for ip in ip_list if not ip.startswith("127.")]
            
            if not non_local_ips:
                # Method 2: Connect to a public DNS (doesn't send data)
                s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                s.connect(("8.8.8.8", 80))
                ip = s.getsockname()[0]
                s.close()
                return ip
            
            # Heuristic for best IP
            for ip in non_local_ips:
                if ip.startswith("192.168."): return ip
            for ip in non_local_ips:
                if ip.startswith("10."): return ip
            for ip in non_local_ips:
                if ip.startswith("172."): return ip
                
            return non_local_ips[0]
            
        except Exception:
            return "127.0.0.1"

    @staticmethod
    def reboot_system():
        """Reboot the machine"""
        system = platform.system()
        try:
            if system == "Windows":
                subprocess.run(["shutdown", "/r", "/t", "0"])
            elif system == "Linux" or system == "Darwin":
                subprocess.run(["sudo", "shutdown", "-r", "now"])
        except Exception as e:
            logger.error(f"Failed to reboot: {e}")

    @staticmethod
    def get_storage_info():
        """Get disk usage info"""
        try:
            disks = []
            partitions = psutil.disk_partitions()
            
            for partition in partitions:
                try:
                    usage = psutil.disk_usage(partition.mountpoint)
                    
                    # Accurate removable detection
                    is_removable = False
                    try:
                        if platform.system() == "Windows":
                            import ctypes
                            # GetDriveType returns: 2=Removable, 3=Fixed, 4=Network, 5=CDROM, 6=RAMDisk
                            drive_type = ctypes.windll.kernel32.GetDriveTypeW(partition.device)
                            is_removable = (drive_type == 2)
                        else:
                            opts_lower = partition.opts.lower()
                            is_removable = any(k in opts_lower for k in ('removable', 'external', 'usb'))
                    except Exception:
                        is_removable = False
                    
                    disks.append({
                        "device": partition.device,
                        "mountpoint": partition.mountpoint,
                        "type": partition.fstype,
                        "total": f"{usage.total / (1024**3):.1f} GB",
                        "used": f"{usage.used / (1024**3):.1f} GB",
                        "free": f"{usage.free / (1024**3):.1f} GB",
                        "usedPercent": round(usage.percent, 1),
                        "isRemovable": is_removable
                    })
                except PermissionError:
                    continue
                    
            return disks
        except Exception as e:
            logger.error(f"Error getting storage info: {e}")
            return []

    
    @staticmethod
    def get_cpu_info():
        """Get CPU information"""
        try:
            cpu_info = platform.processor() or "Unknown CPU"
            cpu_count = psutil.cpu_count(logical=False) or 1
            cpu_threads = psutil.cpu_count(logical=True) or 1
            return f"{cpu_info} ({cpu_count} cores, {cpu_threads} threads)"
        except Exception as e:
            logger.error(f"Error getting CPU info: {e}")
            return "Unknown CPU"
    
    @staticmethod
    def get_memory_info():
        """Get RAM information"""
        try:
            mem = psutil.virtual_memory()
            return f"{mem.total / (1024**3):.1f} GB"
        except Exception as e:
            logger.error(f"Error getting memory info: {e}")
            return "Unknown"
    
    @staticmethod
    def get_mac_address():
        """Get primary MAC address"""
        try:
            mac = ':'.join(['{:02x}'.format((uuid.getnode() >> elements) & 0xff)
                           for elements in range(0, 2*6, 2)][::-1])
            return mac.upper()
        except Exception as e:
            logger.error(f"Error getting MAC address: {e}")
            return "00:00:00:00:00:00"
    
    @staticmethod
    def get_serial_number():
        """Get system serial number"""
        system = platform.system()
        try:
            if system == "Windows":
                result = subprocess.run(
                    ["wmic", "bios", "get", "serialnumber"],
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                if result.returncode == 0:
                    lines = result.stdout.strip().split('\n')
                    if len(lines) > 1:
                        serial = lines[1].strip()
                        if serial and serial != "To Be Filled By O.E.M.":
                            return serial
                            
            elif system == "Linux":
                try:
                    with open("/sys/class/dmi/id/product_serial") as f:
                        serial = f.read().strip()
                        if serial:
                            return serial
                except:
                    pass
                    
            elif system == "Darwin":
                result = subprocess.run(
                    ["system_profiler", "SPHardwareDataType"],
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                if result.returncode == 0:
                    for line in result.stdout.split('\n'):
                        if 'Serial Number' in line:
                            return line.split(':')[1].strip()
                            
        except Exception as e:
            logger.error(f"Error getting serial number: {e}")
        
        # Fallback to hostname-based ID
        return f"SN-{socket.gethostname()[:12]}"
    
    @staticmethod
    def get_installed_software():
        """
        Get list of installed software packages.
        Returns list of dicts with: name, version, installDate
        """
        import logging
        logger = logging.getLogger(__name__)
        
        os_type = platform.system()
        software_list = []
        
        try:
            if os_type == "Windows":
                software_list = PlatformUtils._get_windows_software()
            elif os_type == "Linux":
                software_list = PlatformUtils._get_linux_software()
            elif os_type == "Darwin":  # MacOS
                software_list = PlatformUtils._get_macos_software()
            else:
                logger.warning(f"Software enumeration not supported on {os_type}")
        except Exception as e:
            logger.error(f"Failed to enumerate software: {e}")
        
        return software_list
    
    @staticmethod
    def _get_windows_software():
        """Enumerate installed software on Windows using Registry and winget"""
        import winreg
        import subprocess
        import logging
        logger = logging.getLogger(__name__)
        
        software_list = []
        seen_names = set()
        
        # Method 1: Windows Registry (most comprehensive)
        # OPTIMIZATION: Only check the main registry paths, limit iterations
        registry_paths = [
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
            (winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Uninstall"),
        ]
        
        MAX_APPS_PER_PATH = 1000  # Increased limit
        
        for hive, path in registry_paths:
            try:
                key = winreg.OpenKey(hive, path)
                i = 0
                apps_from_this_path = 0
                
                while apps_from_this_path < MAX_APPS_PER_PATH:
                    try:
                        subkey_name = winreg.EnumKey(key, i)
                        subkey = winreg.OpenKey(key, subkey_name)
                        
                        try:
                            name = winreg.QueryValueEx(subkey, "DisplayName")[0]
                            
                            # Skip if already added or if name is empty
                            if not name or name in seen_names:
                                i += 1
                                continue
                            
                            # Get version and install date
                            try:
                                version = winreg.QueryValueEx(subkey, "DisplayVersion")[0]
                            except:
                                version = "Unknown"
                            
                            try:
                                install_date = winreg.QueryValueEx(subkey, "InstallDate")[0]
                                # Format: YYYYMMDD -> YYYY-MM-DD
                                if len(install_date) == 8:
                                    install_date = f"{install_date[:4]}-{install_date[4:6]}-{install_date[6:]}"
                            except:
                                install_date = None
                            
                            software_list.append({
                                "name": name,
                                "version": version,
                                "installDate": install_date
                            })
                            seen_names.add(name)
                            apps_from_this_path += 1
                            
                        except:
                            pass
                        finally:
                            winreg.CloseKey(subkey)
                        
                        i += 1
                    except OSError:
                        break
                
                winreg.CloseKey(key)
            except Exception as e:
                logger.debug(f"Could not access registry path {path}: {e}")
        
        logger.info(f"Found {len(software_list)} installed applications on Windows")
        return software_list
    
    @staticmethod
    def _get_linux_software():
        """Enumerate installed software on Linux using dpkg or rpm"""
        import subprocess
        import logging
        logger = logging.getLogger(__name__)
        
        software_list = []
        
        # Try dpkg (Debian/Ubuntu)
        try:
            result = subprocess.run(
                ["dpkg", "-l"],
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.returncode == 0:
                lines = result.stdout.split('\n')
                for line in lines:
                    if line.startswith('ii'):  # Only installed packages
                        parts = line.split()
                        if len(parts) >= 3:
                            software_list.append({
                                "name": parts[1],
                                "version": parts[2],
                                "installDate": None
                            })
                logger.info(f"Found {len(software_list)} packages via dpkg")
                return software_list
        except FileNotFoundError:
            pass
        except Exception as e:
            logger.debug(f"dpkg enumeration failed: {e}")
        
        # Try rpm (RHEL/CentOS/Fedora)
        try:
            result = subprocess.run(
                ["rpm", "-qa", "--queryformat", "%{NAME}|%{VERSION}-%{RELEASE}|%{INSTALLTIME:date}\n"],
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.returncode == 0:
                lines = result.stdout.split('\n')
                for line in lines:
                    if '|' in line:
                        parts = line.split('|')
                        if len(parts) >= 2:
                            software_list.append({
                                "name": parts[0],
                                "version": parts[1],
                                "installDate": parts[2] if len(parts) > 2 else None
                            })
                logger.info(f"Found {len(software_list)} packages via rpm")
                return software_list
        except FileNotFoundError:
            pass
        except Exception as e:
            logger.debug(f"rpm enumeration failed: {e}")
        
        logger.warning("No supported package manager found (dpkg/rpm)")
        return software_list
    
    @staticmethod
    def _get_macos_software():
        """Enumerate installed software on MacOS using system_profiler"""
        import subprocess
        import json
        import logging
        logger = logging.getLogger(__name__)
        
        software_list = []
        
        try:
            result = subprocess.run(
                ["system_profiler", "-json", "SPApplicationsDataType"],
                capture_output=True,
                text=True,
                timeout=60
            )
            
            if result.returncode == 0:
                data = json.loads(result.stdout)
                applications = data.get("SPApplicationsDataType", [])
                
                for app in applications:
                    name = app.get("_name", "Unknown")
                    version = app.get("version", "Unknown")
                    
                    software_list.append({
                        "name": name,
                        "version": version,
                        "installDate": None
                    })
                
                logger.info(f"Found {len(software_list)} applications on MacOS")
        except Exception as e:
            logger.error(f"MacOS software enumeration failed: {e}")
        
        return software_list


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
        Return a standardized dictionary of system information.
        On Windows uses winreg for accurate product name, display version, and build number.
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
                # Use winreg for accurate product name, edition, build + UBR (patch level)
                try:
                    import winreg

                    # Edition display names (EditionID → friendly label)
                    _EDITION_MAP = {
                        "Professional":            "Pro",
                        "ProfessionalWorkstation": "Pro for Workstations",
                        "ProfessionalEducation":   "Pro Education",
                        "Home":                    "Home",
                        "HomeN":                   "Home N",
                        "ProfessionalN":           "Pro N",
                        "Enterprise":              "Enterprise",
                        "EnterpriseN":             "Enterprise N",
                        "EnterpriseS":             "Enterprise LTSC",
                        "EnterpriseSN":            "Enterprise LTSC N",
                        "Education":               "Education",
                        "EducationN":              "Education N",
                        "IoT":                     "IoT",
                        "ServerStandard":          "Server Standard",
                        "ServerDatacenter":        "Server Datacenter",
                    }

                    key = winreg.OpenKey(
                        winreg.HKEY_LOCAL_MACHINE,
                        r"SOFTWARE\Microsoft\Windows NT\CurrentVersion"
                    )

                    current_build = winreg.QueryValueEx(key, "CurrentBuildNumber")[0]  # "26200"

                    # UBR = Update Build Revision (monthly patch level), e.g. 2803
                    try:
                        ubr = winreg.QueryValueEx(key, "UBR")[0]  # DWORD
                        full_build = f"10.0.{current_build}.{ubr}"
                    except Exception:
                        ubr = 0
                        full_build = f"10.0.{current_build}"

                    # DisplayVersion = "23H2"; fall back to ReleaseId = "2009"
                    try:
                        display_ver = winreg.QueryValueEx(key, "DisplayVersion")[0]
                    except Exception:
                        try:
                            display_ver = winreg.QueryValueEx(key, "ReleaseId")[0]
                        except Exception:
                            display_ver = current_build

                    # ProductName may say "Windows 10 Pro" even on Win11
                    product_name = winreg.QueryValueEx(key, "ProductName")[0]

                    # EditionID gives a machine-readable edition we can map to a friendly name
                    try:
                        edition_id = winreg.QueryValueEx(key, "EditionID")[0]
                        friendly_edition = _EDITION_MAP.get(edition_id, edition_id)
                    except Exception:
                        friendly_edition = None

                    winreg.CloseKey(key)

                    # Determine major version: Win11 starts at build 22000
                    major = "11" if int(current_build) >= 22000 else "10"

                    if friendly_edition:
                        os_full = f"Windows {major} {friendly_edition}"
                    else:
                        # Fix ProductName: may say Win10 even on Win11
                        if major == "11" and "Windows 10" in product_name:
                            os_full = product_name.replace("Windows 10", "Windows 11")
                        else:
                            os_full = product_name

                    info["os_full_name"]      = os_full        # "Windows 11 Pro"
                    info["os_release"]        = display_ver    # "23H2"
                    info["os_version_detail"] = full_build     # "10.0.26200.2803"
                    info["os_version"]        = full_build
                    info["os_build_number"]   = current_build  # "26200" (bare, for filtering)
                    info["os_ubr"]            = str(ubr)       # "2803"

                except Exception:
                    # Fallback: platform.win32_ver()
                    win_rel, win_ver, win_csd, win_ptype = platform.win32_ver()
                    info["os_release"]        = win_rel
                    info["os_version_detail"] = win_ver
                    info["service_pack"]      = win_csd
                    info["os_full_name"]      = f"Windows {win_rel} {win_ptype}".strip()

            elif system == "Linux":
                # Parse /etc/os-release for full name and release label
                try:
                    os_release_data = {}
                    with open("/etc/os-release") as f:
                        for line in f:
                            line = line.strip()
                            if "=" in line:
                                k, _, v = line.partition("=")
                                os_release_data[k] = v.strip().strip('"')
                    if "PRETTY_NAME" in os_release_data:
                        info["os_full_name"] = os_release_data["PRETTY_NAME"]
                    if "VERSION_ID" in os_release_data:
                        info["os_release"] = os_release_data["VERSION_ID"]
                    if "VERSION_CODENAME" in os_release_data:
                        info["os_codename"] = os_release_data["VERSION_CODENAME"]
                except Exception:
                    pass
                # Kernel version from uname
                info["os_version_detail"] = platform.uname().release

            elif system == "Darwin":
                mac_ver, _, arch = platform.mac_ver()
                info["os_release"]   = mac_ver
                info["os_full_name"] = f"macOS {mac_ver} ({arch})"

        except Exception as e:
            logger.error(f"Error getting system info: {e}")

        return info

    @staticmethod
    def get_os_install_date() -> str:
        """Return the OS installation date as YYYY-MM-DD, or empty string if unavailable."""
        import datetime
        system = platform.system()
        try:
            if system == "Windows":
                import winreg
                key = winreg.OpenKey(
                    winreg.HKEY_LOCAL_MACHINE,
                    r"SOFTWARE\Microsoft\Windows NT\CurrentVersion"
                )
                install_ts = winreg.QueryValueEx(key, "InstallDate")[0]
                winreg.CloseKey(key)
                return datetime.datetime.utcfromtimestamp(install_ts).strftime("%Y-%m-%d")
            elif system == "Linux":
                # Try to read install date from /etc/machine-id creation time as a proxy
                import os
                for path in ("/var/log/installer/syslog", "/var/log/installation.log"):
                    if os.path.exists(path):
                        st = os.stat(path)
                        return datetime.datetime.utcfromtimestamp(st.st_mtime).strftime("%Y-%m-%d")
                # Fallback: dpkg log first entry
                result = subprocess.run(
                    ["head", "-1", "/var/log/dpkg.log"],
                    capture_output=True, text=True, timeout=3
                )
                if result.returncode == 0 and result.stdout.strip():
                    return result.stdout.strip()[:10]  # "YYYY-MM-DD"
            elif system == "Darwin":
                result = subprocess.run(
                    ["system_profiler", "SPSoftwareDataType"],
                    capture_output=True, text=True, timeout=8
                )
                for line in result.stdout.splitlines():
                    if "Install Date" in line or "System Version" in line:
                        # Rough date extraction
                        parts = line.split(":")
                        if len(parts) > 1:
                            return parts[1].strip()
        except Exception as e:
            logger.debug(f"Could not get OS install date: {e}")
        return ""

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
    def get_mac_address() -> str:
        """Get primary non-loopback MAC address using psutil, with uuid.getnode() fallback."""
        import re as _re
        _mac_pattern = _re.compile(r'^([0-9a-fA-F]{2}[:\-]){5}[0-9a-fA-F]{2}$')

        try:
            stats = psutil.net_if_stats()
            for name, addrs in psutil.net_if_addrs().items():
                if name.lower() in ('lo', 'loopback'):
                    continue
                # Prefer interfaces that are up
                iface_stats = stats.get(name)
                if iface_stats and not iface_stats.isup:
                    continue
                for addr in addrs:
                    mac = str(addr.address or "")
                    if _mac_pattern.match(mac):
                        mac = mac.upper().replace('-', ':')
                        if mac != '00:00:00:00:00:00':
                            return mac
        except Exception as e:
            logger.debug(f"psutil MAC lookup failed: {e}")

        # Fallback: uuid.getnode()
        try:
            raw = uuid.getnode()
            mac = ':'.join(['{:02x}'.format((raw >> (8 * i)) & 0xFF) for i in range(5, -1, -1)])
            if mac != '00:00:00:00:00:00':
                return mac.upper()
        except Exception as e:
            logger.error(f"Error getting MAC address: {e}")

        return "00:00:00:00:00:00"
    
    @staticmethod
    def detect_device_type() -> dict:
        """
        Detect whether this machine is a server, laptop, desktop, workstation,
        virtual machine, or container using hardware chassis data.

        Returns:
            {
                "device_type":       "laptop" | "desktop" | "workstation" |
                                     "server" | "virtual_machine" | "container" | "unknown",
                "chassis_label":     human-readable chassis description,
                "is_virtual":        bool,
                "detection_method":  "wmi" | "dmi" | "model_name" | "heuristic",
                "raw_chassis_code":  int | None,
            }
        """
        import os

        # DMI chassis code → label
        CHASSIS_LABELS = {
            1: "Other", 2: "Unknown", 3: "Desktop", 4: "Low Profile Desktop",
            5: "Pizza Box", 6: "Mini Tower", 7: "Tower", 8: "Portable",
            9: "Laptop", 10: "Notebook", 11: "Hand Held", 12: "Docking Station",
            13: "All In One", 14: "Sub Notebook", 15: "Space-saving",
            16: "Lunch Box", 17: "Main Server Chassis", 18: "Expansion Chassis",
            19: "Sub Chassis", 20: "Bus Expansion Chassis", 21: "Peripheral Chassis",
            22: "RAID Chassis", 23: "Rack Mount Chassis", 24: "Sealed-Case PC",
            25: "Multi-system Chassis", 26: "CompactPCI", 27: "AdvancedTCA",
            28: "Blade", 29: "Blade Enclosure", 30: "Tablet",
            31: "Convertible", 32: "Detachable", 33: "IoT Gateway",
            34: "Embedded PC", 35: "Mini PC", 36: "Stick PC",
        }
        LAPTOP_CODES    = {8, 9, 10, 11, 14, 30, 31, 32}
        SERVER_CODES    = {17, 18, 19, 20, 21, 22, 23, 25, 26, 27, 28, 29}
        DESKTOP_CODES   = {3, 4, 5, 6, 7, 12, 13, 15, 16, 24, 34, 35, 36}

        VM_STRINGS = {
            "virtualbox", "vmware", "virtual machine", "kvm", "qemu",
            "hyper-v", "xen", "parallels", "bochs", "innotek",
        }

        result = {
            "device_type": "unknown",
            "chassis_label": "Unknown",
            "is_virtual": False,
            "detection_method": "heuristic",
            "raw_chassis_code": None,
        }

        system = platform.system()

        # ── Container / VM detection (universal) ─────────────────────────
        def _is_container():
            if os.path.exists("/.dockerenv"):
                return True
            try:
                with open("/proc/1/cgroup") as f:
                    content = f.read()
                    return any(k in content for k in ("docker", "lxc", "kubepods", "containerd"))
            except Exception:
                return False

        def _is_vm_by_strings(vendor: str, product: str) -> bool:
            combined = (vendor + " " + product).lower()
            return any(s in combined for s in VM_STRINGS)

        if system == "Linux" and _is_container():
            result["device_type"] = "container"
            result["is_virtual"] = True
            result["detection_method"] = "cgroup"
            return result

        # ── Windows ───────────────────────────────────────────────────────
        if system == "Windows":
            try:
                # Primary: PCSystemType via PowerShell (more reliable than wmic)
                ps = subprocess.run(
                    ["powershell", "-NoProfile", "-Command",
                     "(Get-WmiObject Win32_ComputerSystem).PCSystemType"],
                    capture_output=True, text=True, timeout=8
                )
                pc_type = int(ps.stdout.strip()) if ps.stdout.strip().isdigit() else 0

                # Secondary: chassis type
                ch = subprocess.run(
                    ["powershell", "-NoProfile", "-Command",
                     "(Get-WmiObject Win32_SystemEnclosure).ChassisTypes"],
                    capture_output=True, text=True, timeout=8
                )
                chassis_code = None
                raw = ch.stdout.strip().strip("{}")
                if raw.isdigit():
                    chassis_code = int(raw)

                # VM / Hyper-V check
                vm_check = subprocess.run(
                    ["powershell", "-NoProfile", "-Command",
                     "(Get-WmiObject Win32_ComputerSystem).Model"],
                    capture_output=True, text=True, timeout=8
                )
                model = vm_check.stdout.strip().lower()
                is_virtual = any(s in model for s in VM_STRINGS)

                result["is_virtual"] = is_virtual
                result["detection_method"] = "wmi"

                if is_virtual:
                    result["device_type"] = "virtual_machine"
                    result["chassis_label"] = "Virtual Machine"
                    return result

                if chassis_code:
                    result["raw_chassis_code"] = chassis_code
                    result["chassis_label"] = CHASSIS_LABELS.get(chassis_code, "Unknown")
                    if chassis_code in LAPTOP_CODES:
                        result["device_type"] = "laptop"
                        return result
                    if chassis_code in SERVER_CODES:
                        result["device_type"] = "server"
                        return result

                # PCSystemType mapping
                PC_TYPE_MAP = {
                    1: "desktop", 2: "laptop", 3: "workstation",
                    4: "server",  5: "server", 6: "desktop",
                    7: "server",
                }
                if pc_type in PC_TYPE_MAP:
                    result["device_type"] = PC_TYPE_MAP[pc_type]
                    if chassis_code:
                        result["chassis_label"] = CHASSIS_LABELS.get(chassis_code, "Unknown")
                    return result

                # Fallback: battery presence → laptop
                bat = subprocess.run(
                    ["powershell", "-NoProfile", "-Command",
                     "(Get-WmiObject Win32_Battery) -ne $null"],
                    capture_output=True, text=True, timeout=5
                )
                if "True" in bat.stdout:
                    result["device_type"] = "laptop"
                    result["chassis_label"] = "Portable"
                    return result

                # OS SKU check — Windows Server SKUs
                sku_check = subprocess.run(
                    ["powershell", "-NoProfile", "-Command",
                     "(Get-WmiObject Win32_OperatingSystem).Caption"],
                    capture_output=True, text=True, timeout=5
                )
                if "server" in sku_check.stdout.lower():
                    result["device_type"] = "server"
                    result["chassis_label"] = "Server"

            except Exception as e:
                logger.warning(f"Windows device type detection failed: {e}")

        # ── Linux ─────────────────────────────────────────────────────────
        elif system == "Linux":
            try:
                # Read DMI chassis type
                chassis_code = None
                try:
                    with open("/sys/class/dmi/id/chassis_type") as f:
                        val = f.read().strip()
                        if val.isdigit():
                            chassis_code = int(val)
                except Exception:
                    pass

                # Read product/vendor for VM detection
                sys_vendor = ""
                product_name = ""
                try:
                    with open("/sys/class/dmi/id/sys_vendor") as f:
                        sys_vendor = f.read().strip()
                    with open("/sys/class/dmi/id/product_name") as f:
                        product_name = f.read().strip()
                except Exception:
                    pass

                # Try systemd-detect-virt
                virt_result = subprocess.run(
                    ["systemd-detect-virt", "--quiet"],
                    capture_output=True, text=True, timeout=3
                )
                is_virtual = virt_result.returncode == 0 or _is_vm_by_strings(sys_vendor, product_name)

                result["is_virtual"] = is_virtual
                result["detection_method"] = "dmi"

                if is_virtual:
                    result["device_type"] = "virtual_machine"
                    result["chassis_label"] = "Virtual Machine"
                    return result

                if chassis_code:
                    result["raw_chassis_code"] = chassis_code
                    result["chassis_label"] = CHASSIS_LABELS.get(chassis_code, "Unknown")
                    if chassis_code in LAPTOP_CODES:
                        result["device_type"] = "laptop"
                        return result
                    if chassis_code in SERVER_CODES:
                        result["device_type"] = "server"
                        return result
                    if chassis_code in DESKTOP_CODES:
                        # Distinguish workstation from plain desktop by CPU count
                        cpu_count = psutil.cpu_count(logical=False) or 1
                        result["device_type"] = "workstation" if cpu_count >= 8 else "desktop"
                        return result

                # Battery fallback → laptop
                has_battery = any(
                    "Battery" in open(os.path.join("/sys/class/power_supply", d, "type")).read()
                    for d in (os.listdir("/sys/class/power_supply")
                              if os.path.exists("/sys/class/power_supply") else [])
                    if os.path.exists(os.path.join("/sys/class/power_supply", d, "type"))
                )
                if has_battery:
                    result["device_type"] = "laptop"
                    result["chassis_label"] = "Portable"
                    result["detection_method"] = "battery"
                    return result

                # Hostname heuristic
                hostname = socket.gethostname().lower()
                if any(k in hostname for k in ("srv", "server", "dc", "node", "prod", "rack")):
                    result["device_type"] = "server"
                    result["detection_method"] = "hostname_heuristic"

            except Exception as e:
                logger.warning(f"Linux device type detection failed: {e}")

        # ── macOS ─────────────────────────────────────────────────────────
        elif system == "Darwin":
            try:
                sp = subprocess.run(
                    ["system_profiler", "SPHardwareDataType"],
                    capture_output=True, text=True, timeout=10
                )
                model_line = ""
                for line in sp.stdout.split("\n"):
                    if "Model Name" in line or "Model Identifier" in line:
                        model_line = line.lower()
                        break

                result["detection_method"] = "model_name"
                if "macbook" in model_line:
                    result["device_type"] = "laptop"
                    result["chassis_label"] = "MacBook"
                elif "xserve" in model_line:
                    result["device_type"] = "server"
                    result["chassis_label"] = "Xserve"
                elif "mac pro" in model_line:
                    result["device_type"] = "workstation"
                    result["chassis_label"] = "Mac Pro"
                elif "imac" in model_line or "mac mini" in model_line:
                    result["device_type"] = "desktop"
                    result["chassis_label"] = "Mac Desktop"
                else:
                    # VM strings in model
                    if _is_vm_by_strings("", model_line):
                        result["device_type"] = "virtual_machine"
                        result["is_virtual"] = True
                        result["chassis_label"] = "Virtual Machine"
            except Exception as e:
                logger.warning(f"macOS device type detection failed: {e}")

        return result

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

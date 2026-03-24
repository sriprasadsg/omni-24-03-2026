"""
Server-Side Network Discovery
Scans the local network where the server is running to identify active devices.
"""
import socket
import threading
import time
from typing import Dict, Any, List
import logging
import platform
import subprocess
import re
from datetime import datetime
import ipaddress
import urllib.request
import json

try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False
    logging.warning("psutil not available, multi-network scanning may be limited")

# Optional Scapy import
SCAPY_AVAILABLE = False
ARP = Ether = srp = ICMP = IP = sr1 = None

try:
    # Force disable Scapy for now due to Windows interface issues
    # from scapy.all import ARP as _ARP, Ether as _Ether, srp as _srp, ICMP as _ICMP, IP as _IP, sr1 as _sr1
    # ARP, Ether, srp, ICMP, IP, sr1 = _ARP, _Ether, _srp, _ICMP, _IP, _sr1
    # SCAPY_AVAILABLE = True
    raise ImportError("Scapy disabled intentionally")
except (ImportError, Exception):
    logging.warning("Scapy not available on server or disabled. Falling back to ping sweep.")
    SCAPY_AVAILABLE = False

try:
    import nmap
    NMAP_LIBRARY_AVAILABLE = True
except ImportError:
    NMAP_LIBRARY_AVAILABLE = False
    logging.warning("python-nmap library not found. Nmap scanning will be disabled.")


class ServerDiscovery:
    
    @staticmethod
    def start_scan(subnet: str = None, scan_all_networks: bool = True, subnets: List[str] = None) -> List[Dict[str, Any]]:
        """
        Perform a network scan from the server.
        Args:
            subnet: Single subnet to scan (e.g., "192.168.1.0/24")
            scan_all_networks: If True, scan all detected network interfaces
            subnets: Optional list of specific subnets to scan
        """
        results = []
        subnet_vlan_map = {}
        
        # Determine which subnets to scan
        if subnets:
            target_subnets = subnets
            logging.info(f"Scanning manually specified subnets: {subnets}")
        elif subnet:
            target_subnets = [subnet]
            logging.info(f"Scanning single subnet: {subnet}")
        elif scan_all_networks:
            detected_networks = ServerDiscovery._get_all_local_subnets_info()
            target_subnets = [n["subnet"] for n in detected_networks]
            subnet_vlan_map = {n["subnet"]: n.get("vlan_id") for n in detected_networks}
            logging.info(f"Scanning all detected subnets: {target_subnets}")
        else:
            # Default to primary subnet
            primary_sub = ServerDiscovery._get_local_subnet()
            target_subnets = [primary_sub]
            logging.info(f"Scanning default subnet: {primary_sub}")
        
        # Scan each subnet
        for sub in target_subnets:
            logging.info(f"Scanning subnet: {sub}")
            
            # Try Nmap first (Gold Standard)
            nmap_success = False
            if NMAP_LIBRARY_AVAILABLE:
                try:
                    logging.info(f"Attempting Nmap scan on {sub}...")
                    subnet_results = ServerDiscovery._scan_nmap(sub)
                    if subnet_results:
                        nmap_success = True
                        logging.info(f"Nmap scan successful for {sub}. Found {len(subnet_results)} devices.")
                except Exception as e:
                    logging.warning(f"Nmap scan failed for {sub} (Binary might be missing): {e}")
            
            if not nmap_success:
                logging.info(f"Falling back to Python-based scanner for {sub}...")
                if SCAPY_AVAILABLE:
                    try:
                        subnet_results = ServerDiscovery._scan_arp(sub)
                        if not subnet_results:
                            logging.warning(f"ARP scan returned no results for {sub}. Trying Ping Sweep...")
                            subnet_results = ServerDiscovery._scan_ping_sweep(sub)
                    except Exception as e:
                        logging.error(f"ARP scan failed for {sub}: {e}")
                        subnet_results = ServerDiscovery._scan_ping_sweep(sub)
                else:
                    subnet_results = ServerDiscovery._scan_ping_sweep(sub)
            
            # Add subnet and VLAN info to each device
            for device in subnet_results:
                device["subnet"] = sub
                if sub in subnet_vlan_map and subnet_vlan_map[sub]:
                    device["vlanId"] = subnet_vlan_map[sub]
            
            results.extend(subnet_results)
        
        # Deduplicate results by IP address
        unique_results = {}
        for dev in results:
            ip = dev.get("ip")
            if not ip:
                continue
            
            # If duplicate, keep the one with more information (MAC address, vendor, etc.)
            if ip not in unique_results:
                unique_results[ip] = dev
            else:
                existing = unique_results[ip]
                # Prioritize valid MAC over "Unknown"
                if existing.get("mac") == "Unknown" and dev.get("mac") != "Unknown":
                    unique_results[ip] = dev
                # If both have MAC or both are Unknown, keep the one with more open ports or vendor info
                elif (existing.get("mac") != "Unknown" or dev.get("mac") == "Unknown"):
                    if not existing.get("vendor") or existing.get("vendor") == "Unknown":
                        if dev.get("vendor") and dev.get("vendor") != "Unknown":
                            unique_results[ip] = dev
                
        final_results = list(unique_results.values())
        logging.info(f"Network scan complete. Found {len(final_results)} unique devices (removed {len(results) - len(final_results)} duplicates)")
        return final_results

    @staticmethod
    def get_public_ip() -> str:
        """
        Fetch the public IP address of the server.
        """
        try:
            with urllib.request.urlopen("https://api.ipify.org?format=json", timeout=5) as response:
                data = json.loads(response.read().decode())
                return data.get("ip", "8.8.8.8")
        except Exception as e:
            logging.warning(f"Failed to fetch public IP: {e}")
            return "8.8.8.8"

    @staticmethod
    def _get_local_subnet() -> str:
        """Get local IP and assume /24 subnet"""
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            local_ip = s.getsockname()[0]
            logging.info(f"Detected local IP: {local_ip}")
            s.close()
            # Assume /24
            base_ip = ".".join(local_ip.split(".")[:3]) + ".0/24"
            return base_ip
        except Exception:
            return "192.168.1.0/24"
    
    @staticmethod
    def _get_all_local_subnets_info() -> List[Dict[str, Any]]:
        """
        Detect all network interfaces, their subnets, and attempt to extract VLAN IDs.
        Returns list of dicts: [{'subnet': '192.168.1.0/24', 'vlan_id': 10, 'interface': 'eth0.10'}]
        """
        networks = []
        
        if not PSUTIL_AVAILABLE:
            logging.warning("psutil not available, falling back to single subnet detection")
            return [{"subnet": ServerDiscovery._get_local_subnet()}]
        
        try:
            # Get all network interfaces
            net_if_addrs = psutil.net_if_addrs()
            
            for interface_name, addrs in net_if_addrs.items():
                vlan_id = ServerDiscovery._extract_vlan_id(interface_name)
                
                for addr in addrs:
                    # Only process IPv4 addresses
                    if addr.family == socket.AF_INET:
                        ip = addr.address
                        netmask = addr.netmask
                        
                        # Skip loopback and link-local addresses
                        if ip.startswith("127.") or ip.startswith("169.254."):
                            continue
                        
                        # Calculate CIDR subnet
                        try:
                            subnet_cidr = ServerDiscovery._calculate_subnet_cidr(ip, netmask)
                            if subnet_cidr:
                                # Avoid duplicates for the same subnet across interfaces
                                if not any(n["subnet"] == subnet_cidr for n in networks):
                                    networks.append({
                                        "subnet": subnet_cidr,
                                        "vlan_id": vlan_id,
                                        "interface": interface_name
                                    })
                                    logging.info(f"Detected interface {interface_name}: {subnet_cidr} (VLAN: {vlan_id or 'None'})")
                        except Exception as e:
                            logging.warning(f"Failed to calculate subnet for {interface_name} ({ip}/{netmask}): {e}")
            
            if not networks:
                logging.warning("No valid subnets detected, using default")
                return [{"subnet": ServerDiscovery._get_local_subnet()}]
            
            return networks
            
        except Exception as e:
            logging.error(f"Error detecting network interfaces: {e}")
            return [{"subnet": ServerDiscovery._get_local_subnet()}]

    @staticmethod
    def _extract_vlan_id(interface_name: str) -> Any:
        """
        Attempt to extract a VLAN ID from an interface name.
        Supports common patterns: eth0.10, vlan20, vEthernet (VLAN 30)
        """
        # Pattern 1: eth0.10 or enp0s3.100
        match = re.search(r'\.(\d+)$', interface_name)
        if match:
            return match.group(1)
            
        # Pattern 2: vlan10 or VLAN20
        match = re.search(r'vlan(\d+)', interface_name, re.IGNORECASE)
        if match:
            return match.group(1)
            
        # Pattern 3: vEthernet (VLAN 30) - Windows Hyper-V
        match = re.search(r'VLAN\s*(\d+)', interface_name, re.IGNORECASE)
        if match:
            return match.group(1)
            
        return None
    
    @staticmethod
    def _calculate_subnet_cidr(ip: str, netmask: str) -> str:
        """
        Calculate CIDR notation from IP and netmask.
        Example: ('192.168.1.100', '255.255.255.0') -> '192.168.1.0/24'
        """
        try:
            # Create network object
            network = ipaddress.IPv4Network(f"{ip}/{netmask}", strict=False)
            return str(network)
        except Exception as e:
            logging.warning(f"Failed to calculate CIDR for {ip}/{netmask}: {e}")
            # Fallback: assume /24
            base_ip = ".".join(ip.split(".")[:3]) + ".0/24"
            return base_ip

    @staticmethod
    def _scan_nmap(subnet: str) -> List[Dict[str, Any]]:
        """
        Perform a scan using Nmap.
        Requires nmap binary to be installed on the system.
        """
        if not NMAP_LIBRARY_AVAILABLE:
            raise ImportError("python-nmap library not installed")
            
        nm = nmap.PortScanner()
        devices = []
        
        # Arguments:
        # -sn: Ping Scan (disable port scan) - Faster for discovery
        # -PR: ARP Ping - More reliable on local network
        # For more detail (OS detection), we would use -O but it requires Admin execution
        # Let's try a balanced approach: -sn first. If we want OS, we need sudo/admin.
        # We will use -sn for speed and reliability as a base.
        # If we want service info, we can add -sV --top-ports 20
        
        args = "-sn -PR" 
        # On Windows, -PR (ARP) works well for local subnets.
        
        try:
            nm.scan(hosts=subnet, arguments=args)
        except nmap.PortScannerError as e:
            raise Exception(f"Nmap binary not found or execution failed: {e}")
            
        for host in nm.all_hosts():
            try:
                # Basic Info
                hostname = nm[host].hostname()
                if not hostname:
                    # Try manual resolution if Nmap didn't find one
                    hostname = ServerDiscovery._resolve_hostname(host)
                
                # If still IP, keep as IP
                if not hostname:
                    hostname = host

                # Clean up hostname (remove domain if it's too long for display? No, user wants proper hostname)
                status = nm[host].state() # up/down
                
                # MAC Address & Vendor
                mac = "Unknown"
                vendor = "Unknown"
                if 'addresses' in nm[host] and 'mac' in nm[host]['addresses']:
                    mac = nm[host]['addresses']['mac']
                    if 'vendor' in nm[host] and mac in nm[host]['vendor']:
                        vendor = nm[host]['vendor'][mac]
                
                # Device Type Guess based on Vendor/Hostname
                device_type = "Unknown"
                lower_vendor = vendor.lower()
                lower_host = hostname.lower()
                
                if "apple" in lower_vendor: device_type = "Apple Device"
                elif "dell" in lower_vendor or "hp" in lower_vendor or "lenovo" in lower_vendor: device_type = "Workstation/Laptop"
                elif "cisco" in lower_vendor: device_type = "Network Device"
                elif "vmware" in lower_vendor: device_type = "Virtual Machine"
                elif "server" in lower_host: device_type = "Server"
                elif "print" in lower_host: device_type = "Printer"
                
                # Heuristics based on ports (Nmap doesn't always give device type directly)
                # If we have open ports, verify
                open_ports = []
                if 'tcp' in nm[host]:
                    open_ports = [int(p) for p in nm[host]['tcp'].keys() if nm[host]['tcp'][p]['state'] == 'open']

                if device_type == "Unknown":
                     if 3389 in open_ports or 445 in open_ports or 135 in open_ports:
                         device_type = "Windows Workstation" # Default to workstation
                     elif 22 in open_ports:
                         device_type = "Linux Device"
                
                # Extract OS if available (requires -O scan usually, but we can try to guess from osmatch if present)
                os_version = "Unknown"
                if 'osmatch' in nm[host] and nm[host]['osmatch']:
                    # Take the first match
                    os_version = nm[host]['osmatch'][0]['name']
                
                # Extract Open Ports (if we did a port scan)
                open_ports = []
                if 'tcp' in nm[host]:
                    open_ports = [int(p) for p in nm[host]['tcp'].keys() if nm[host]['tcp'][p]['state'] == 'open']
                
                devices.append({
                    "ip": host,
                    "mac": mac,
                    "hostname": hostname,
                    "status": status.capitalize(),
                    "device_type": device_type,
                    "vendor": vendor,
                    "os_version": os_version,
                    "open_ports": open_ports,
                    "params": "nmap",
                    "lastSeen": datetime.utcnow().isoformat()
                })
            except Exception as e:
                 logging.warning(f"Error parsing Nmap result for {host}: {e}")
                 
        return devices

    @staticmethod
    def _scan_arp(subnet: str) -> List[Dict[str, Any]]:
        """
        Use Scapy to send ARP requests.
        """
        devices = []
        try:
            # Create ARP request packet
            arp_req = ARP(pdst=subnet)
            ether = Ether(dst="ff:ff:ff:ff:ff:ff")
            packet = ether/arp_req

            # Send and receive
            result = srp(packet, timeout=2, verbose=0)[0]

            for sent, received in result:
                devices.append({
                    "ip": received.psrc,
                    "mac": received.hwsrc,
                    "hostname": ServerDiscovery._resolve_hostname(received.psrc),
                    "status": "Up",
                    "device_type": ServerDiscovery._guess_device_type(received.psrc),
                    "lastSeen": datetime.utcnow().isoformat()
                })
        except Exception as e:
            logging.error(f"ARP scan failed: {e}")
        
        return devices

    @staticmethod
    def _scan_ping_sweep(subnet: str) -> List[Dict[str, Any]]:
        """
        Multi-threaded ping sweep with enhanced service discovery.
        """
        devices = []
        threads = []
        
        # Extract base IP
        match = re.match(r"(\d+\.\d+\.\d+)\.", subnet)
        if not match:
            return []
        
        base_ip = match.group(1)
        
        def scan_host(ip):
            is_up = False
            # Try ping first
            if ServerDiscovery._ping(ip):
                is_up = True
            
            # If ping fails, try common ports (firewall might block ICMP but allow TCP)
            # This makes the scan slower but "deeper"
            details = ServerDiscovery._fingerprint_host(ip, check_ports_if_ping_fails=not is_up)
            
            if is_up or details.get("open_ports"):
                hostname = ServerDiscovery._resolve_hostname(ip)
                # If hostname is just IP, try to look it up in ARP table (local CLI) to get MAC?
                # For now, sticking to python native.
                
                devices.append({
                    "ip": ip,
                    "hostname": hostname,
                    "mac": ServerDiscovery._get_mac_address(ip), # Attempt to get MAC
                    "status": "Up",
                    "device_type": details.get("device_type", "Unknown"),
                    "vendor": details.get("vendor", "Unknown"),
                    "os_version": details.get("os_version", "Unknown"),
                    "open_ports": details.get("open_ports", []),
                    "params": "fallback_ping",
                    "lastSeen": datetime.utcnow().isoformat()
                })

        # Scan full /24 subnet
        scan_range = 254
        logging.info(f"Scanning {subnet}...")
        
        # Batch threads to avoid OS limits
        active_threads = []
        for i in range(1, scan_range + 1):
            ip = f"{base_ip}.{i}"
            t = threading.Thread(target=scan_host, args=(ip,))
            t.start()
            active_threads.append(t)
            
            if len(active_threads) >= 100: # Higher concurrency
                for thread in active_threads:
                    thread.join()
                active_threads = []
        
        for thread in active_threads:
            thread.join()
            
        return devices

    @staticmethod
    def _ping(ip: str) -> bool:
        param = "-n" if platform.system().lower() == "windows" else "-c"
        # Reduced timeout to speeds up scan
        command = ["ping", param, "1", "-w", "200", ip]
        try:
            return subprocess.call(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) == 0
        except:
            return False

    @staticmethod
    def _get_mac_address(ip: str) -> str:
        """
        Attempt to get MAC address from local ARP table using 'arp -a'
        """
        try:
            command = ["arp", "-a", ip]
            output = subprocess.check_output(command).decode("utf-8", errors="ignore")
            # Regex to find MAC address
            mac_regex = r"([0-9A-Fa-f]{2}[:-]){5}([0-9A-Fa-f]{2})"
            match = re.search(mac_regex, output)
            if match:
                return match.group(0).replace("-", ":").upper()
        except:
            pass
        return "Unknown"

    @staticmethod
    def _resolve_hostname(ip: str) -> str:
        try:
            return socket.gethostbyaddr(ip)[0]
        except socket.herror:
            return ip

    @staticmethod
    def _fingerprint_host(ip: str, check_ports_if_ping_fails: bool = False) -> Dict[str, Any]:
        """
        Check common ports to guess device type.
        """
        # Extended port list
        common_ports = {
            21: "FTP Server",
            22: "SSH (Linux/Network Device)",
            23: "Telnet (Legacy Device)",
            25: "SMTP Server",
            53: "DNS Server",
            80: "Web Server (HTTP)",
            135: "Windows RPC",
            139: "Windows NetBIOS",
            443: "Web Server (HTTPS)",
            445: "Windows SMB",
            631: "Printer (IPP)",
            1433: "SQL Server",
            3306: "MySQL Database",
            3389: "Windows RDP",
            5432: "PostgreSQL Database",
            8080: "Web Proxy/App",
            8443: "Web App (HTTPS)"
        }
        
        if check_ports_if_ping_fails:
             # Check a few critical ports to see if host is up essentially
             critical_ports = [80, 443, 22, 135, 445, 3389]
             first_check = False
             for p in critical_ports:
                 if ServerDiscovery._check_port(ip, p):
                     first_check = True
                     break
             if not first_check:
                 return {}

        open_ports = []
        device_type = "Unknown"
        vendor = "Unknown"
        
        try:
            for port, desc in common_ports.items():
                if ServerDiscovery._check_port(ip, port):
                    open_ports.append(port)
                    
            # Improved Heuristics for Icon Mapping & OS Guessing
            os_version = "Unknown"
            if 3389 in open_ports or 445 in open_ports or 135 in open_ports:
                device_type = "Windows Workstation" # changed from Windows Server
                vendor = "Microsoft"
                os_version = "Windows 10/11/Server"
            elif 22 in open_ports:
                if 80 in open_ports or 443 in open_ports:
                     device_type = "Web Server" # Could be Linux or otherwise
                     os_version = "Linux/Unix"
                elif 53 in open_ports:
                     device_type = "DNS Server"
                     os_version = "Linux"
                else:
                     device_type = "Linux Server" # Generic Linux likely a server
                     os_version = "Linux"
            elif 631 in open_ports:
                device_type = "Printer"
            elif 80 in open_ports or 443 in open_ports:
                # Could be router interface or web server
                # Simple check: many routers don't respond well to random port scans, but let's assume unknown web = IoT/Device
                device_type = "IoT Device" 
            elif 5432 in open_ports or 3306 in open_ports or 1433 in open_ports:
                device_type = "Database Server"
            
            return {
                "open_ports": open_ports,
                "device_type": device_type,
                "vendor": vendor,
                "os_version": os_version
            }
        except:
            return {}

    @staticmethod
    def _check_port(ip: str, port: int) -> bool:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(0.3) # Fast timeout
        try:
            s.connect((ip, port))
            s.close()
            return True
        except:
            return False

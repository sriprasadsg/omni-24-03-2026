"""
Network Discovery Capability
Scans the local network to identify active devices using ARP and Ping.
"""
from .base import BaseCapability
import socket
import threading
import time
from typing import Dict, Any, List
import logging
import platform
import subprocess
import re

SCAPY_AVAILABLE = False
ARP = Ether = srp = ICMP = IP = sr1 = None

def _import_scapy():
    global SCAPY_AVAILABLE, ARP, Ether, srp, ICMP, IP, sr1
    if SCAPY_AVAILABLE:
        return True
    try:
        from scapy.all import ARP as _ARP, Ether as _Ether, srp as _srp, ICMP as _ICMP, IP as _IP, sr1 as _sr1
        ARP, Ether, srp, ICMP, IP, sr1 = _ARP, _Ether, _srp, _ICMP, _IP, _sr1
        SCAPY_AVAILABLE = True
        return True
    except (ImportError, Exception, BaseException) as e:
        import logging
        logging.warning(f"Scapy import failed or panicked: {e}. Network discovery will use fallback methods.")
        SCAPY_AVAILABLE = False
        return False

# Initial attempt to import, but handle failure gracefully
# _import_scapy() # Commented out to avoid backend crash on some systems

class NetworkDiscoveryCapability(BaseCapability):
    
    @property
    def capability_id(self) -> str:
        return "network_discovery"
    
    @property
    def capability_name(self) -> str:
        return "Network Discovery"
    
    def collect(self) -> Dict[str, Any]:
        """Discovery is usually triggered, but collect can return last scan results"""
        return {
            "status": "ready",
            "scapy_available": SCAPY_AVAILABLE,
            "last_scan": getattr(self, '_last_scan_results', [])
        }

    def start_scan(self, subnet: str = None) -> List[Dict[str, Any]]:
        """
        Perform a network scan.
        If subnet is not provided, it attempts to guess the local subnet.
        """
        _import_scapy() # Attempt import before scanning
        
        if not subnet:
            subnet = self._get_local_subnet()
            
        logging.info(f"Starting network scan on {subnet}...")
        results = []

        if SCAPY_AVAILABLE:
            try:
                results = self._scan_arp(subnet)
                if not results:
                     logging.warning("ARP scan returned no results. Trying Ping Sweep...")
                     results = self._scan_ping_sweep(subnet)
            except Exception as e:
                logging.error(f"ARP scan failed (likely missing Npcap): {e}")
                results = self._scan_ping_sweep(subnet)
        else:
            logging.warning("Scapy not available. Falling back to multi-threaded ping sweep.")
            results = self._scan_ping_sweep(subnet)

        self._last_scan_results = results
        return results

    def _get_local_subnet(self) -> str:
        """Get local IP and assume /24 subnet for simplicity"""
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            local_ip = s.getsockname()[0]
            s.close()
            # Assume /24
            base_ip = ".".join(local_ip.split(".")[:3]) + ".0/24"
            return base_ip
        except Exception:
            return "192.168.1.0/24"

    def _scan_arp(self, subnet: str) -> List[Dict[str, Any]]:
        """
        Use Scapy to send ARP requests.
        Returns list of discovered devices.
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
                    "hostname": self._resolve_hostname(received.psrc),
                    "status": "Up",
                    "device_type": self._guess_device_type(received.psrc),
                    "last_seen": self._get_timestamp()
                })
        except Exception as e:
            logging.error(f"ARP scan failed: {e}")
        
        return devices

    def _scan_ping_sweep(self, subnet: str) -> List[Dict[str, Any]]:
        """
        Multi-threaded ping sweep for non-scapy environments or as fallback.
        """
        devices = []
        threads = []
        
        # Extract base IP (e.g., 192.168.1.)
        match = re.match(r"(\d+\.\d+\.\d+)\.", subnet)
        if not match:
            return []
        
        base_ip = match.group(1)
        
        def ping_ip(ip):
            if self._ping(ip):
                devices.append({
                    "ip": ip,
                    "hostname": self._resolve_hostname(ip),
                    "mac": "Unknown",
                    "status": "Up",
                    "device_type": self._guess_device_type(ip),
                    "last_seen": self._get_timestamp()
                })

        # Scan 1 to 254
        for i in range(1, 255):
            ip = f"{base_ip}.{i}"
            t = threading.Thread(target=ping_ip, args=(ip,))
            t.start()
            threads.append(t)
            
            # Limit concurrent threads to avoid system strain
            if len(threads) >= 50:
                for thread in threads:
                    thread.join()
                threads = []
        
        for thread in threads:
            thread.join()
            
        return devices

    def _ping(self, ip: str) -> bool:
        """Ping an IP address and return True if it responds"""
        param = "-n" if platform.system().lower() == "windows" else "-c"
        command = ["ping", param, "1", "-w", "500", ip]
        try:
            return subprocess.call(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) == 0
        except:
            return False

    def _resolve_hostname(self, ip: str) -> str:
        try:
            return socket.gethostbyaddr(ip)[0]
        except socket.herror:
            return ip

    def _guess_device_type(self, ip: str) -> str:
        """
        Try to guess device type by checking a few ports.
        Very basic.
        """
        common_ports = {
            80: "Router/Web",
            443: "Router/Web",
            22: "Linux/Switch",
            3389: "Windows",
            631: "Printer"
        }
        
        for port, type_guess in common_ports.items():
            if self._check_port(ip, port):
                return type_guess
        
        return "Unknown"

    def _check_port(self, ip: str, port: int) -> bool:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(0.5)
        try:
            s.connect((ip, port))
            s.close()
            return True
        except:
            return False
            
    def _get_timestamp(self) -> str:
        from datetime import datetime
        return datetime.now().isoformat()

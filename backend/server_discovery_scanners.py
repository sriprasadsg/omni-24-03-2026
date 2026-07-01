"""Server discovery scanner implementations: nmap, ARP, ping sweep, host fingerprinting."""

import ipaddress
import logging
import re
import threading
from datetime import datetime, timezone
from typing import Any, Dict, List

from server_discovery_net import (
    _check_port, _get_mac_address, _ping, _resolve_hostname,
)

logger = logging.getLogger(__name__)

# Optional Scapy import
SCAPY_AVAILABLE = False
ARP = Ether = srp = ICMP = IP = sr1 = None

try:
    # Disabled intentionally due to Windows interface issues
    raise ImportError("Scapy disabled intentionally")
except (ImportError, Exception):
    logging.warning("Scapy not available on server or disabled. Falling back to ping sweep.")

try:
    import nmap
    NMAP_LIBRARY_AVAILABLE = True
except ImportError:
    NMAP_LIBRARY_AVAILABLE = False
    logging.warning("python-nmap library not found. Nmap scanning will be disabled.")


_COMMON_PORTS = {
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
    8443: "Web App (HTTPS)",
}


def _fingerprint_host(ip: str, check_ports_if_ping_fails: bool = False) -> Dict[str, Any]:
    """Check common ports to guess device type and OS."""
    if check_ports_if_ping_fails:
        critical_ports = [80, 443, 22, 135, 445, 3389]
        if not any(_check_port(ip, p) for p in critical_ports):
            return {}

    open_ports = []
    device_type = "Unknown"
    vendor = "Unknown"

    try:
        open_ports = [port for port in _COMMON_PORTS if _check_port(ip, port)]

        os_version = "Unknown"
        if 3389 in open_ports or 445 in open_ports or 135 in open_ports:
            device_type = "Windows Workstation"
            vendor = "Microsoft"
            os_version = "Windows 10/11/Server"
        elif 22 in open_ports:
            if 80 in open_ports or 443 in open_ports:
                device_type = "Web Server"
                os_version = "Linux/Unix"
            elif 53 in open_ports:
                device_type = "DNS Server"
                os_version = "Linux"
            else:
                device_type = "Linux Server"
                os_version = "Linux"
        elif 631 in open_ports:
            device_type = "Printer"
        elif 80 in open_ports or 443 in open_ports:
            device_type = "IoT Device"
        elif 5432 in open_ports or 3306 in open_ports or 1433 in open_ports:
            device_type = "Database Server"

        return {"open_ports": open_ports, "device_type": device_type, "vendor": vendor, "os_version": os_version}
    except Exception as e:
        logger.debug("Port scan fingerprinting failed: %s", e)
        return {}


def _scan_nmap(subnet: str) -> List[Dict[str, Any]]:
    """Perform a scan using Nmap (requires nmap binary installed on the system)."""
    if not NMAP_LIBRARY_AVAILABLE:
        raise ImportError("python-nmap library not installed")

    if not re.fullmatch(r'(\d{1,3}\.){3}\d{1,3}/\d{1,2}', subnet or ""):
        raise ValueError(f"Invalid subnet format: {subnet!r}. Expected CIDR notation e.g. 192.168.1.0/24")
    try:
        ipaddress.ip_network(subnet, strict=False)
    except ValueError:
        raise ValueError(f"Invalid subnet: {subnet!r}")

    nm = nmap.PortScanner()
    try:
        nm.scan(hosts=subnet, arguments="-sn -PR")
    except nmap.PortScannerError as e:
        raise Exception(f"Nmap binary not found or execution failed: {e}")

    devices = []
    for host in nm.all_hosts():
        try:
            hostname = nm[host].hostname() or _resolve_hostname(host) or host
            status = nm[host].state()
            mac = "Unknown"
            vendor = "Unknown"
            if "addresses" in nm[host] and "mac" in nm[host]["addresses"]:
                mac = nm[host]["addresses"]["mac"]
                if "vendor" in nm[host] and mac in nm[host]["vendor"]:
                    vendor = nm[host]["vendor"][mac]

            device_type = "Unknown"
            lower_vendor = vendor.lower()
            lower_host = hostname.lower()
            if "apple" in lower_vendor:
                device_type = "Apple Device"
            elif any(v in lower_vendor for v in ("dell", "hp", "lenovo")):
                device_type = "Workstation/Laptop"
            elif "cisco" in lower_vendor:
                device_type = "Network Device"
            elif "vmware" in lower_vendor:
                device_type = "Virtual Machine"
            elif "server" in lower_host:
                device_type = "Server"
            elif "print" in lower_host:
                device_type = "Printer"

            open_ports = []
            if "tcp" in nm[host]:
                open_ports = [int(p) for p in nm[host]["tcp"] if nm[host]["tcp"][p]["state"] == "open"]
                if device_type == "Unknown":
                    if 3389 in open_ports or 445 in open_ports or 135 in open_ports:
                        device_type = "Windows Workstation"
                    elif 22 in open_ports:
                        device_type = "Linux Device"

            os_version = "Unknown"
            if "osmatch" in nm[host] and nm[host]["osmatch"]:
                os_version = nm[host]["osmatch"][0]["name"]

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
                "lastSeen": datetime.now(timezone.utc).isoformat(),
            })
        except Exception as e:
            logging.warning("Error parsing Nmap result for %s: %s", host, e)

    return devices


def _scan_arp(subnet: str) -> List[Dict[str, Any]]:
    """Use Scapy to send ARP requests (only available when SCAPY_AVAILABLE is True)."""
    devices = []
    try:
        arp_req = ARP(pdst=subnet)
        ether = Ether(dst="ff:ff:ff:ff:ff:ff")
        packet = ether / arp_req
        result = srp(packet, timeout=2, verbose=0)[0]
        for _sent, received in result:
            devices.append({
                "ip": received.psrc,
                "mac": received.hwsrc,
                "hostname": _resolve_hostname(received.psrc),
                "status": "Up",
                "device_type": "Unknown",
                "lastSeen": datetime.now(timezone.utc).isoformat(),
            })
    except Exception as e:
        logging.error("ARP scan failed: %s", e)
    return devices


def _scan_ping_sweep(subnet: str) -> List[Dict[str, Any]]:
    """Multi-threaded ping sweep with service discovery."""
    devices: List[Dict[str, Any]] = []

    match = re.match(r"(\d+\.\d+\.\d+)\.", subnet)
    if not match:
        return []
    base_ip = match.group(1)

    def scan_host(ip: str) -> None:
        is_up = _ping(ip)
        details = _fingerprint_host(ip, check_ports_if_ping_fails=not is_up)
        if is_up or details.get("open_ports"):
            devices.append({
                "ip": ip,
                "hostname": _resolve_hostname(ip),
                "mac": _get_mac_address(ip),
                "status": "Up",
                "device_type": details.get("device_type", "Unknown"),
                "vendor": details.get("vendor", "Unknown"),
                "os_version": details.get("os_version", "Unknown"),
                "open_ports": details.get("open_ports", []),
                "params": "fallback_ping",
                "lastSeen": datetime.now(timezone.utc).isoformat(),
            })

    logging.info("Scanning %s...", subnet)
    active_threads: List[threading.Thread] = []
    for i in range(1, 255):
        t = threading.Thread(target=scan_host, args=(f"{base_ip}.{i}",))
        t.start()
        active_threads.append(t)
        if len(active_threads) >= 100:
            for thread in active_threads:
                thread.join()
            active_threads = []
    for thread in active_threads:
        thread.join()

    return devices

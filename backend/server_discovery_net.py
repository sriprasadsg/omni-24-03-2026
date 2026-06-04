"""Server discovery network utilities: subnet detection, ping, port check, host fingerprinting."""

import ipaddress
import logging
import platform
import re
import socket
import subprocess
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False
    logging.warning("psutil not available, multi-network scanning may be limited")


def _ping(ip: str) -> bool:
    param = "-n" if platform.system().lower() == "windows" else "-c"
    command = ["ping", param, "1", "-w", "200", ip]
    try:
        return subprocess.call(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) == 0
    except OSError:
        return False


def _check_port(ip: str, port: int) -> bool:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(0.3)
    try:
        s.connect((ip, port))
        s.close()
        return True
    except OSError:
        return False


def _resolve_hostname(ip: str) -> str:
    try:
        return socket.gethostbyaddr(ip)[0]
    except socket.herror:
        return ip


def _get_mac_address(ip: str) -> str:
    """Attempt to get MAC address from local ARP table using 'arp -a'."""
    try:
        output = subprocess.check_output(["arp", "-a", ip]).decode("utf-8", errors="ignore")
        match = re.search(r"([0-9A-Fa-f]{2}[:-]){5}([0-9A-Fa-f]{2})", output)
        if match:
            return match.group(0).replace("-", ":").upper()
    except Exception as e:
        logger.debug("MAC lookup failed for host: %s", e)
    return "Unknown"


def _extract_vlan_id(interface_name: str) -> Optional[str]:
    """Extract VLAN ID from interface name (e.g. eth0.10, vlan20, vEthernet (VLAN 30))."""
    match = re.search(r'\.(\d+)$', interface_name)
    if match:
        return match.group(1)
    match = re.search(r'vlan(\d+)', interface_name, re.IGNORECASE)
    if match:
        return match.group(1)
    match = re.search(r'VLAN\s*(\d+)', interface_name, re.IGNORECASE)
    if match:
        return match.group(1)
    return None


def _calculate_subnet_cidr(ip: str, netmask: str) -> str:
    """Calculate CIDR notation from IP and netmask. Falls back to /24."""
    try:
        return str(ipaddress.IPv4Network(f"{ip}/{netmask}", strict=False))
    except Exception as e:
        logging.warning("Failed to calculate CIDR for %s/%s: %s", ip, netmask, e)
        return ".".join(ip.split(".")[:3]) + ".0/24"


def _get_local_subnet() -> str:
    """Get primary local subnet assuming /24."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        local_ip = s.getsockname()[0]
        s.close()
        return ".".join(local_ip.split(".")[:3]) + ".0/24"
    except Exception:
        return "192.168.1.0/24"


def _get_all_local_subnets_info() -> List[Dict[str, Any]]:
    """Detect all network interfaces with their subnets and VLAN IDs."""
    if not PSUTIL_AVAILABLE:
        logging.warning("psutil not available, falling back to single subnet detection")
        return [{"subnet": _get_local_subnet()}]

    networks: List[Dict[str, Any]] = []
    try:
        for interface_name, addrs in psutil.net_if_addrs().items():
            vlan_id = _extract_vlan_id(interface_name)
            for addr in addrs:
                if addr.family != socket.AF_INET:
                    continue
                ip = addr.address
                if ip.startswith("127.") or ip.startswith("169.254."):
                    continue
                try:
                    subnet_cidr = _calculate_subnet_cidr(ip, addr.netmask)
                    if subnet_cidr and not any(n["subnet"] == subnet_cidr for n in networks):
                        networks.append({"subnet": subnet_cidr, "vlan_id": vlan_id, "interface": interface_name})
                        logging.info("Detected interface %s: %s (VLAN: %s)", interface_name, subnet_cidr, vlan_id or "None")
                except Exception as e:
                    logging.warning("Failed to calculate subnet for %s (%s/%s): %s", interface_name, ip, addr.netmask, e)

        if not networks:
            logging.warning("No valid subnets detected, using default")
            return [{"subnet": _get_local_subnet()}]
        return networks

    except Exception as e:
        logging.error("Error detecting network interfaces: %s", e)
        return [{"subnet": _get_local_subnet()}]

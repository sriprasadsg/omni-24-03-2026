"""
Server-Side Network Discovery
Scans the local network where the server is running to identify active devices.
"""

import json
import logging
import urllib.request
from typing import Any, Dict, List

from server_discovery_net import _get_all_local_subnets_info, _get_local_subnet
from server_discovery_scanners import (
    NMAP_LIBRARY_AVAILABLE, SCAPY_AVAILABLE,
    _scan_arp, _scan_nmap, _scan_ping_sweep,
)

logger = logging.getLogger(__name__)


class ServerDiscovery:

    @staticmethod
    def start_scan(
        subnet: str = None,
        scan_all_networks: bool = True,
        subnets: List[str] = None,
    ) -> List[Dict[str, Any]]:
        """Perform a network scan from the server.

        Args:
            subnet: Single subnet to scan (e.g., "192.168.1.0/24")
            scan_all_networks: If True, scan all detected network interfaces
            subnets: Optional list of specific subnets to scan
        """
        subnet_vlan_map: Dict[str, Any] = {}

        if subnets:
            target_subnets = subnets
            logging.info("Scanning manually specified subnets: %s", subnets)
        elif subnet:
            target_subnets = [subnet]
            logging.info("Scanning single subnet: %s", subnet)
        elif scan_all_networks:
            detected_networks = _get_all_local_subnets_info()
            target_subnets = [n["subnet"] for n in detected_networks]
            subnet_vlan_map = {n["subnet"]: n.get("vlan_id") for n in detected_networks}
            logging.info("Scanning all detected subnets: %s", target_subnets)
        else:
            target_subnets = [_get_local_subnet()]
            logging.info("Scanning default subnet: %s", target_subnets[0])

        results: List[Dict[str, Any]] = []
        for sub in target_subnets:
            logging.info("Scanning subnet: %s", sub)
            subnet_results: List[Dict[str, Any]] = []

            nmap_success = False
            if NMAP_LIBRARY_AVAILABLE:
                try:
                    logging.info("Attempting Nmap scan on %s...", sub)
                    subnet_results = _scan_nmap(sub)
                    if subnet_results:
                        nmap_success = True
                        logging.info("Nmap scan successful for %s. Found %d devices.", sub, len(subnet_results))
                except Exception as e:
                    logging.warning("Nmap scan failed for %s (Binary might be missing): %s", sub, e)

            if not nmap_success:
                logging.info("Falling back to Python-based scanner for %s...", sub)
                if SCAPY_AVAILABLE:
                    try:
                        subnet_results = _scan_arp(sub)
                        if not subnet_results:
                            logging.warning("ARP scan returned no results for %s. Trying Ping Sweep...", sub)
                            subnet_results = _scan_ping_sweep(sub)
                    except Exception as e:
                        logging.error("ARP scan failed for %s: %s", sub, e)
                        subnet_results = _scan_ping_sweep(sub)
                else:
                    subnet_results = _scan_ping_sweep(sub)

            for device in subnet_results:
                device["subnet"] = sub
                if sub in subnet_vlan_map and subnet_vlan_map[sub]:
                    device["vlanId"] = subnet_vlan_map[sub]

            results.extend(subnet_results)

        unique_results: Dict[str, Dict[str, Any]] = {}
        for dev in results:
            ip = dev.get("ip")
            if not ip:
                continue
            if ip not in unique_results:
                unique_results[ip] = dev
            else:
                existing = unique_results[ip]
                if existing.get("mac") == "Unknown" and dev.get("mac") != "Unknown":
                    unique_results[ip] = dev
                elif existing.get("mac") != "Unknown" or dev.get("mac") == "Unknown":
                    if not existing.get("vendor") or existing.get("vendor") == "Unknown":
                        if dev.get("vendor") and dev.get("vendor") != "Unknown":
                            unique_results[ip] = dev

        final_results = list(unique_results.values())
        logging.info(
            "Network scan complete. Found %d unique devices (removed %d duplicates)",
            len(final_results), len(results) - len(final_results),
        )
        return final_results

    @staticmethod
    def get_public_ip() -> str:
        """Fetch the public IP address of the server."""
        try:
            with urllib.request.urlopen("https://api.ipify.org?format=json", timeout=5) as response:
                data = json.loads(response.read().decode())
                return data.get("ip", "8.8.8.8")
        except Exception as e:
            logging.warning("Failed to fetch public IP: %s", e)
            return "8.8.8.8"

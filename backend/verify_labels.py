import sys
import os
import asyncio
from pprint import pprint

# Add backend directory to sys.path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from server_discovery import ServerDiscovery

def verify_scan():
    print("Starting verification scan...")
    # Scan local subnet (likely 192.168.x.x or similar)
    results = ServerDiscovery.start_scan()
    
    print(f"\nScan Complete. Found {len(results)} devices.\n")
    
    for device in results:
        print(f"IP: {device.get('ip')}", flush=True)
        print(f"Hostname: {device.get('hostname')}", flush=True)
        print(f"Type: {device.get('device_type')}", flush=True)
        print(f"OS: {device.get('os_version')}", flush=True)
        print(f"Vendor: {device.get('vendor')}", flush=True)
        print(f"Ports: {device.get('open_ports')}", flush=True)
        print("-" * 30, flush=True)

if __name__ == "__main__":
    verify_scan()

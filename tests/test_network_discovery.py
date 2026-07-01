import asyncio
import logging
import sys
import os

# Add the project root to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from agent.capabilities.network_discovery import NetworkDiscoveryCapability

async def test_network_discovery():
    logging.basicConfig(level=logging.INFO)
    capability = NetworkDiscoveryCapability()
    
    print("Starting network scan...")
    # We'll use a small subnet or let it guess
    results = capability.start_scan()
    
    print(f"Scan complete. Found {len(results)} devices.")
    for device in results:
        print(f" - {device['ip']} ({device.get('hostname', 'Unknown')}) [{device.get('mac', 'Unknown')}]")

if __name__ == "__main__":
    asyncio.run(test_network_discovery())

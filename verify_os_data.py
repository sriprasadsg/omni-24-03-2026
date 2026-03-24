
import asyncio
import aiohttp
import json
import socket
import platform

BASE_URL = "http://localhost:5000/api"

async def verify_os_data():
    """
    Register a mock agent with enhanced OS/Network data and verify backend storage.
    """
    async with aiohttp.ClientSession() as session:
        # 1. Register Mock Agent with Enhanced Data
        hostname = "verify-os-test-host"
        print(f"Testing with hostname: {hostname}")
        
        payload = {
            "hostname": hostname,
            "tenantId": "default-tenant",
            "status": "Online",
            "platform": "Windows",
            "version": "2.1.0",
            "ipAddress": "192.168.1.100",
            "meta": {
                "os": "Windows",
                "os_full_name": "Windows 10 Pro",
                "os_release": "10",
                "os_version_detail": "10.0.19045",
                "service_pack": "Service Pack 1",
                "os_version": "10.0.19045",
                "macAddress": "00:11:22:33:44:55",
                "metrics_collection": {
                    "network": {
                        "interfaces": [
                            {"interface": "Ethernet", "mac": "00:11:22:33:44:55"},
                            {"interface": "Wi-Fi", "mac": "AA:BB:CC:DD:EE:FF"}
                        ]
                    },
                    "installedSoftware": [
                        {"name": "Google Chrome", "version": "120.0.0", "installDate": "2023-12-01", "updateAvailable": True},
                        {"name": "Notepad++", "version": "8.5.8", "installDate": "2023-11-15", "updateAvailable": False}
                    ]
                }
            }
        }
        
        print("Sending Heartbeat...")
        async with session.post(f"{BASE_URL}/agents/heartbeat", json=payload) as resp:
            if resp.status != 200:
                print(f"Error sending heartbeat: {resp.status} - {await resp.text()}")
                return False
            print("Heartbeat success.")
            
        # 2. Verify Asset Data
        print("Waiting for data to persist...")
        await asyncio.sleep(2)
        print("Verifying Asset Data...")
        # Get assets
        async with session.get(f"{BASE_URL}/assets") as resp:
            assets = await resp.json()
            target_asset = next((a for a in assets if a.get("hostname") == hostname), None)
            
            if not target_asset:
                print("Error: Asset not found after heartbeat.")
                return False
                
            # Check Fields
            print(f"Asset Found: {target_asset['id']}")
            
            # Check OS Version
            expected_os_ver = "10 10.0.19045 Service Pack 1"
            if target_asset.get("osVersion") == expected_os_ver:
                print(f"✅ OS Version correct: {target_asset['osVersion']}")
            else:
                print(f"❌ OS Version mismatch. Expected '{expected_os_ver}', Got '{target_asset.get('osVersion')}'")
                
            # Check MAC Addresses
            macs = target_asset.get("macAddresses", [])
            if len(macs) == 2:
                print(f"✅ MAC Addresses count correct: {len(macs)}")
            else:
                print(f"❌ MAC Addresses count mismatch. Expected 2, Got {len(macs)}")
                
            # Check Software
            software = target_asset.get("installedSoftware", [])
            chrome = next((s for s in software if s["name"] == "Google Chrome"), None)
            if chrome:
                if chrome.get("installDate") == "2023-12-01" and chrome.get("updateAvailable") is True:
                     print(f"✅ Software 'Google Chrome' data correct (Date & Update flag)")
                else:
                     print(f"❌ Software data mismatch: {chrome}")
            else:
                 print("❌ Software 'Google Chrome' not found")
                 
            return True

if __name__ == "__main__":
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(verify_os_data())

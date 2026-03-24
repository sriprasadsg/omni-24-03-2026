import requests
import os
import sys

BASE_URL = "http://localhost:5001"

def verify_update_system():
    print("Verifying Remote Agent Update System...")
    
    # 1. Check latest version endpoint
    try:
        print(f"Checking {BASE_URL}/api/agent-updates/latest?platform=python")
        resp = requests.get(f"{BASE_URL}/api/agent-updates/latest?platform=python", timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            print(f"✅ Latest Version Response: {data}")
            
            if data.get("filename") == "agent.py":
                print("✅ Correctly identified agent.py update")
            else:
                print(f"⚠️ Unexpected filename: {data.get('filename')}")
                
            download_url = data.get("url")
            if download_url:
                # 2. Check download
                print(f"Checking download: {download_url}")
                dl_resp = requests.get(download_url, timeout=10)
                if dl_resp.status_code == 200:
                    print(f"✅ Download successful ({len(dl_resp.content)} bytes)")
                    if b"AGENT_VERSION" in dl_resp.content:
                        print("✅ Content looks like agent.py")
                    else:
                        print("⚠️ Content does not contain AGENT_VERSION")
                else:
                    print(f"❌ Download failed: {dl_resp.status_code}")
        else:
            print(f"❌ Failed to get latest version: {resp.status_code} {resp.text}")
            
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    verify_update_system()

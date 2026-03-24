import requests
import sys
import os

BASE_URL = "http://127.0.0.1:5000"
EMAIL = "super@omni.ai"
PASSWORD = "superadmin"

def verify_network_features():
    print(f"[*] Testing connectivity to {BASE_URL}...")
    try:
        # 1. Login
        print(f"[*] Attempting login as {EMAIL}...")
        resp = requests.post(f"{BASE_URL}/api/auth/login", json={"email": EMAIL, "password": PASSWORD})
        if resp.status_code != 200:
            print(f"[!] Login failed: {resp.status_code} - {resp.text}")
            return False
        
        data = resp.json()
        token = data.get("access_token")
        if not token:
            print("[!] No access token returned.")
            return False
        
        headers = {"Authorization": f"Bearer {token}"}
        print("[+] Login successful.")

        # 2. Trigger Scan
        print("[*] Triggering server-side network scan...")
        scan_resp = requests.post(f"{BASE_URL}/api/network-devices/scan", headers=headers)
        if scan_resp.status_code == 200:
            scan_res = scan_resp.json()
            print(f"[+] Scan triggered. Devices found: {scan_res.get('devices_found', 'unknown')}")
        else:
            print(f"[!] Scan trigger failed: {scan_resp.status_code} - {scan_resp.text}")

        # 3. Get Network Devices List
        print("[*] Fetching network devices list...")
        list_resp = requests.get(f"{BASE_URL}/api/network-devices", headers=headers)
        if list_resp.status_code != 200:
            print(f"[!] Failed to fetch device list: {list_resp.status_code} - {list_resp.text}")
            return False
        
        devices = list_resp.json()
        print(f"[+] Device list fetched. Count: {len(devices)}")
        for d in devices[:3]: 
            print(f"    - {d.get('hostname', 'Unknown')} ({d.get('ipAddress')}) [{d.get('status')}]")

        # 4. Get Topology Image
        print("[*] Fetching topology image...")
        img_resp = requests.get(f"{BASE_URL}/api/network-devices/topology-image", headers=headers)
        if img_resp.status_code != 200:
            print(f"[!] Failed to fetch image: {img_resp.status_code}")
            return False
        
        content_type = img_resp.headers.get("content-type", "")
        print(f"[+] Image fetched. Size: {len(img_resp.content)} bytes. Type: {content_type}")
        
        if len(img_resp.content) > 0 and "image" in content_type:
            print("[+] Network Visualization feature verified successfully.")
            return True
        else:
            print("[!] Image content invalid.")
            return False

    except Exception as e:
        print(f"[!] Exception during verification: {e}")
        return False

if __name__ == "__main__":
    if verify_network_features():
        sys.exit(0)
    else:
        sys.exit(1)

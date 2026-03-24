#!/usr/bin/env python3
import argparse
import time
import sys
import platform
import socket
import json
from urllib import request

# In a real scenario, this would be the actual API endpoint.
# For this simulation, we'll just print the request.
API_ENDPOINT = "http://127.0.0.1:5000/api/agents/register" 
AGENT_VERSION = "3.1.0-python"

def get_ip_address():
    """Gets the local IP address of the machine."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # doesn't have to be reachable
        s.connect(('10.255.255.255', 1))
        IP = s.getsockname()[0]
    except Exception:
        IP = '127.0.0.1'
    finally:
        s.close()
    return IP

def main():
    parser = argparse.ArgumentParser(description="Omni-Agent AI Installer")
    parser.add_argument(
        "--registration-key",
        required=True,
        help="The tenant-specific registration key for agent installation."
    )
    parser.add_argument(
        "--api-url",
        default="http://REPLACE_WITH_SERVER_IP:5000",
        help="The base URL of the Omni-Agent AI Platform (e.g., http://192.168.1.10:5000)"
    )
    args = parser.parse_args()

    print("Omni-Agent AI Python Installer")
    print("==============================")

    try:
        # Step 1: Simulate download
        print("[1/5] Downloading agent dependencies...")
        time.sleep(1)
        print("      Download complete.")

        # Step 2: Simulate verification
        print("[2/5] Verifying package integrity...")
        time.sleep(1)
        print("      Verification successful.")

        # Step 3: Simulate installation
        install_path = "/opt/omni-agent" if platform.system() != "Windows" else "C:\\\\Program Files\\\\OmniAgent"
        print(f"[3/5] Installing agent to {install_path}...")
        time.sleep(2)
        print("      Installation complete.")
        
        # Step 4: Gather system information
        print("[4/5] Gathering system information for registration...")
        hostname = socket.gethostname()
        ip_address = get_ip_address()
        os_platform = platform.system() # e.g., 'Linux', 'Windows', 'Darwin' (for macOS)
        
        # Map to platform types used in the UI
        platform_map = {
            'Linux': 'Linux',
            'Windows': 'Windows',
            'Darwin': 'macOS'
        }
        agent_platform = platform_map.get(os_platform, os_platform)

        payload = {
            "hostname": hostname,
            "ipAddress": ip_address,
            "platform": agent_platform,
            "version": AGENT_VERSION,
            "assetId": "new", # Instructs the backend to create a new asset
            "registrationKey": args.registration_key
        }
        time.sleep(1)
        print("      System information gathered.")

        # Step 5: Simulate registration with the backend
        api_endpoint = f"{args.api_url.rstrip('/')}/api/agents/register"
        print(f"[5/5] Registering agent with the Omni-Agent AI Platform...")
        print("--------------------------------------------------")
        print(f"CALLING API TO: {api_endpoint}")
        print("METHOD: POST")
        print("HEADERS: {'Content-Type': 'application/json'}")
        print("PAYLOAD:")
        print(json.dumps(payload, indent=2))
        print("--------------------------------------------------")
        
        try:
            data = json.dumps(payload).encode('utf-8')
            req = request.Request(api_endpoint, data=data, headers={'Content-Type': 'application/json'})
            with request.urlopen(req) as response:
                if 200 <= response.status < 300:
                    print("      Registration successful.")
                    resp_body = response.read().decode('utf-8')
                    print(f"      Server response: {resp_body}")
                else:
                    print(f"      Registration failed with status: {response.status}")
                    print(response.read().decode('utf-8'))
                    sys.exit(1)
        except Exception as e:
            print(f"      Error during registration: {e}")
            sys.exit(1)

        print("\n✅ Omni-Agent AI (Python) has been installed and registered successfully!")

    except Exception as e:
        print(f"\\n❌ An error occurred during installation: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()

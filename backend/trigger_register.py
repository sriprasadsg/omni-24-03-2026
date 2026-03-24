import requests
import socket
import json
import time

def register(hostname_override=None):
    hostname = hostname_override if hostname_override else socket.gethostname()
    url = "http://localhost:5000/api/agents/register"
    
    # Read key from file
    try:
        with open("key.txt", "r") as f:
            reg_key = f.read().strip()
    except:
        reg_key = "default-key-if-missing"

    payload = {
        "hostname": hostname,
        "registrationKey": reg_key,
        "platform": "Windows",
        "ipAddress": "127.0.0.1",
        "macAddress": "00:00:00:00:00:00",
        "version": "1.0.0",
        "meta": {
             "os_info": {"version": "10.0.22631"}
        }
    }
    
    print(f"Attempting to register agent for hostname: {hostname}")
    print(f"Target URL: {url}")
    
    try:
        resp = requests.post(url, json=payload, timeout=5)
        print(f"Response Code: {resp.status_code}")
        print(f"Response Body: {resp.content}")
        if resp.status_code == 200:
            print("Registration successful!")
        else:
            print("Registration failed/unexpected status.")
    except Exception as e:
        print(f"An error occurred: {e}")

if __name__ == "__main__":
    # Register current machine
    register()
    # Register the test asset to clean up orphans
    register("TEST-WIN-EVIDENCE")

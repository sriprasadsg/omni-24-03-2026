import requests
import socket
import datetime

def register_test_agent():
    api_url = "http://localhost:5000/api/agents/register"
    # Same ID as seen in UI to update the existing record
    agent_id = "agent-EILT0197"
    
    payload = {
        "id": agent_id,
        "hostname": "EILT0197",
        "ipAddress": "192.168.240.1",
        "platform": "Windows",
        "version": "2.0.0",
        "registrationKey": "reg_62a4b18a91ec461b",
        "cpuModel": "Intel(R) Core(TM) Ultra 7 255H",
        "cpuCores": 16,
        "ram": "31.43 GB",
        "totalMemoryGB": 31.43,
        "disks": [
            {
                "device": "C:\\",
                "mountpoint": "C:\\",
                "type": "NTFS",
                "total": "475.0 GB",
                "used": "120.0 GB",
                "free": "355.0 GB",
                "usedPercent": 25.3,
                "isRemovable": False
            },
            {
                "device": "D:\\",
                "mountpoint": "D:\\",
                "type": "FAT32",
                "total": "1.8 TB",
                "used": "200.0 GB",
                "free": "1.6 TB",
                "usedPercent": 10.5,
                "isRemovable": True
            }
        ]
    }
    
    print(f"Registering agent {agent_id} with enhanced storage metrics...")
    response = requests.post(api_url, json=payload)
    if response.status_code == 200:
        print("✅ Registration successful!")
        data = response.json()
        token = data.get("token")
        
        # Now send a heartbeat to update currentMetrics
        heartbeat_url = f"http://localhost:5000/api/agents/{agent_id}/heartbeat"
        heartbeat_payload = {
            "hostname": "EILT0197",
            "status": "Online",
            "platform": "Windows",
            "meta": {
                "disk_usage": 25.3,
                "disk_total_gb": 475.0,
                "disk_used_gb": 120.0,
                "disk_free_gb": 355.0,
                "disks": payload["disks"]
            }
        }
        headers = {"Authorization": f"Bearer {token}"}
        resp = requests.post(heartbeat_url, json=heartbeat_payload, headers=headers)
        if resp.status_code == 200:
            print("✅ Heartbeat successful!")
        else:
            print(f"❌ Heartbeat failed: {resp.status_code} - {resp.text}")
    else:
        print(f"❌ Registration failed: {response.status_code} - {response.text}")

if __name__ == "__main__":
    register_test_agent()

import requests
import time
import json

BASE_URL = "http://localhost:5000/api/swarm"

def verify_swarm():
    print("--- Verifying Autonomous Swarm Features ---")

    # 1. Check Topology
    try:
        print("1. Fetching Swarm Topology...")
        res = requests.get(f"{BASE_URL}/topology")
        if res.status_code == 200:
            data = res.json()
            print(f"   -> Success. Nodes: {len(data.get('nodes', []))}, Links: {len(data.get('links', []))}")
        else:
            print(f"   -> Failed: {res.status_code} {res.text}")
    except Exception as e:
        print(f"   -> Error: {e}")

    # 2. Start Mission
    mission_id = ""
    try:
        print("\n2. Starting Swarm Mission...")
        payload = {"goal": "Verify system security and patch defects", "priority": "High"}
        res = requests.post(f"{BASE_URL}/start", json=payload)
        if res.status_code == 200:
            mission_id = res.json().get("mission_id")
            print(f"   -> Mission Started. ID: {mission_id}")
        else:
            print(f"   -> Failed: {res.status_code} {res.text}")
            return
    except Exception as e:
        print(f"   -> Error: {e}")
        return

    # 3. Monitor Logs (Simulate real-time feed)
    print("\n3. Monitoring Swarm Logs (10s)...")
    for i in range(5):
        time.sleep(2.5)
        try:
            res = requests.get(f"{BASE_URL}/list")
            missions = res.json()
            my_mission = next((m for m in missions if m["id"] == mission_id), None)
            
            if my_mission:
                logs = my_mission.get("logs", [])
                status = my_mission.get("status")
                print(f"   [t={i*2.5}s] Status: {status}, Logs: {len(logs)}")
                if logs:
                    last_log = logs[-1]
                    # Handle both dict and object (if pydantic leaked) - but endpoint converts to dict
                    msg = last_log.get("message", "")
                    role = last_log.get("role", "")
                    print(f"      -> {role}: {msg}")
                
                if status == "Completed":
                    print("   -> Mission Completed Successfully!")
                    break
        except Exception as e:
            print(f"   -> Polling Error: {e}")

if __name__ == "__main__":
    verify_swarm()

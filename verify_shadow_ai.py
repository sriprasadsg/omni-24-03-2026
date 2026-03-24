import requests
import time

BASE_URL = "http://127.0.0.1:5000/api"

def verify_shadow_ai():
    print("1. Sending Shadow AI Event...")
    payload = {
        "agent_id": "TEST_AGENT_001",
        "process": "python.exe",
        "remote_ip": "1.1.1.1",
        "remote_host": "api.openai.com",
        "timestamp": "2026-01-24T12:00:00Z"
    }
    
    try:
        res = requests.post(f"{BASE_URL}/ueba/shadow-ai", json=payload)
        res.raise_for_status()
        print("   [+] Event sent successfully")
    except Exception as e:
        print(f"   [-] Failed to send event: {e}")
        return

    print("2. Verifying Event Retrieval...")
    time.sleep(1) # Allow for DB write
    try:
        res = requests.get(f"{BASE_URL}/ueba/shadow-ai/events")
        res.raise_for_status()
        events = res.json()
        
        found = any(e['agent_id'] == 'TEST_AGENT_001' for e in events)
        if found:
            print(f"   [+] Found event in list (Total: {len(events)})")
        else:
            print("   [-] Event NOT found in list")
            print(events)
            return

    except Exception as e:
        print(f"   [-] Failed to get events: {e}")
        return

    print("3. Verifying Stats...")
    try:
        res = requests.get(f"{BASE_URL}/ueba/stats")
        stats = res.json()
        print(f"   [+] Stats Received: {stats}")
        if stats['shadow_ai_detections'] > 0:
            print("   [+] Shadow AI Count > 0")
        else:
            print("   [-] Shadow AI Count is 0")

    except Exception as e:
        print(f"   [-] Failed to get stats: {e}")

if __name__ == "__main__":
    verify_shadow_ai()

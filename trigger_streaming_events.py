import requests
import time
import random

BASE_URL = "http://localhost:5000"

def trigger_events():
    print(f"Triggering streaming events to {BASE_URL}...")
    
    topics = ["logs", "security_events"]
    
    # Send 60 events over 30 seconds
    for i in range(60):
        topic = random.choice(topics)
        event_data = {
            "source": f"service-{random.randint(1,5)}",
            "message": f"Simulated event {i+1}",
            "level": random.choice(["info", "warning", "error"]),
            "severity": random.choice(["low", "medium", "high"])
        }
        
        try:
            resp = requests.post(f"{BASE_URL}/api/stream/publish/{topic}", json=event_data)
            if resp.status_code == 200:
                print(f"[{i+1}/20] Published to {topic}: {event_data['level']}")
            else:
                print(f"Error publishing: {resp.status_code}")
        except Exception as e:
            print(f"Connection error: {e}")
            
        time.sleep(0.5)

if __name__ == "__main__":
    trigger_events()

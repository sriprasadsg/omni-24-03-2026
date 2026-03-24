import requests
import time
import threading
import random

BASE_URL = "http://localhost:5000"

def inject_traffic():
    """Simulate a stream of events"""
    print("Starting traffic injection...")
    for i in range(20):
        # 1. Publish Log
        try:
            requests.post(f"{BASE_URL}/api/stream/publish/logs", json={
                "source": "app-server-1",
                "level": "info",
                "message": f"Request processed {i}",
                "timestamp": None # Let backend set it
            })
        except:
            pass
            
        # 2. Publish Threat (occasionally)
        if random.random() < 0.3:
            try:
                requests.post(f"{BASE_URL}/api/stream/publish/security_events", json={
                    "source": "firewall",
                    "severity": "high",
                    "message": "Port scan detected",
                    "timestamp": None
                })
            except:
                pass
        
        time.sleep(0.5)

def run_test():
    print("Starting Streaming Verification...")
    
    # 1. Start traffic injection in background
    t = threading.Thread(target=inject_traffic)
    t.start()
    
    # 2. Monitor Metrics
    print("Monitoring metrics for 10 seconds...")
    for _ in range(5):
        time.sleep(2)
        try:
            res = requests.get(f"{BASE_URL}/api/stream/metrics")
            if res.status_code == 200:
                print(f"Metrics: {res.json()}")
            else:
                print(f"Failed to get metrics: {res.text}")
        except Exception as e:
            print(f"Error fetching metrics: {e}")
            
    t.join()
    print("Test Completed.")

if __name__ == "__main__":
    run_test()

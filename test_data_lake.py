import requests
import json
import os
import time

BASE_URL = "http://localhost:5000/api/data-lake"

def test_ingest():
    print("Testing Ingest...")
    payload = {
        "event": "test_event",
        "value": 42,
        "timestamp": time.time()
    }
    
    try:
        response = requests.post(f"{BASE_URL}/ingest", json=payload, params={"category": "test-data", "zone": "raw"})
        if response.status_code == 200:
            print("✅ Ingest Success:", response.json())
        else:
            print("❌ Ingest Failed:", response.text)
    except Exception as e:
        print(f"❌ Ingest Connection Error: {e}")

def test_list():
    print("\nTesting List Files...")
    # Give background task a moment to write to disk
    time.sleep(1) 
    
    try:
        response = requests.get(f"{BASE_URL}/files", params={"category": "test-data", "zone": "raw"})
        if response.status_code == 200:
            data = response.json()
            print("✅ List Success:", json.dumps(data, indent=2))
            if data["count"] > 0:
                print("✅ File verified in list!")
            else:
                print("⚠️ No files found in list (Background task might be slow or failed)")
        else:
            print("❌ List Failed:", response.text)
    except Exception as e:
        print(f"❌ List Connection Error: {e}")

if __name__ == "__main__":
    print(f"Checking Data Lake at {BASE_URL}")
    test_ingest()
    test_list()

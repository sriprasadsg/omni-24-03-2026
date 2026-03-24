import requests
import sys

base_url = "http://127.0.0.1:8000/api/assets/asset-EILT0197/metrics"

ranges = ["1h", "24h", "7d", "30d"]

for r in ranges:
    try:
        response = requests.get(f"{base_url}?range={r}")
        data = response.json()
        print(f"Range: {r}, Status: {response.status_code}, Count: {len(data)}")
        if len(data) > 0:
            print(f"  Sample timestamp: {data[0]['timestamp']}")
    except Exception as e:
        print(f"Error for {r}: {e}")

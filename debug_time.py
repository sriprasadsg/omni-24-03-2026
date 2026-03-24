
import requests
import datetime
import sys

base_url = "http://localhost:5000/api"

try:
    # 1. Get Assets
    print("Fetching assets...")
    resp = requests.get(f"{base_url}/assets/")
    resp.raise_for_status()
    assets = resp.json()
    
    if not assets:
        print("No assets found in DB.")
        sys.exit(0)
        
    asset_id = assets[0]['id']
    print(f"Using Asset ID: {asset_id}")

    # 2. Get Metrics
    url = f"{base_url}/assets/{asset_id}/metrics?range=1h"
    print(f"Fetching metrics from {url}...")
    
    resp = requests.get(url)
    resp.raise_for_status()
    data = resp.json()
    
    print("\n--- API Response ---")
    metrics = data.get("metrics", [])
    if metrics:
        last_metric = metrics[-1]
        timestamp_str = last_metric["timestamp"]
        print(f"Latest Metric Timestamp (Raw): {timestamp_str}")
        
        # Parse
        dt = datetime.datetime.fromisoformat(timestamp_str)
        print(f"Parsed Object: {dt}")
        print(f"Parsed TZ: {dt.tzinfo}")
        
        # Local time check
        now_utc = datetime.datetime.now(datetime.timezone.utc)
        print(f"System UTC Time: {now_utc}")
        
    else:
        print("No metrics found in response.")

except Exception as e:
    print(f"Error: {e}")

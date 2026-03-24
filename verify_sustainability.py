import requests
import json
import time

BASE_URL = "http://localhost:5000/api/sustainability"

def verify_sustainability():
    print("--- Verifying Sustainability & GreenOps ---")
    
    # 1. Carbon Footprint
    try:
        print("1. Checking 30-Day Carbon Footprint...")
        res = requests.get(f"{BASE_URL}/carbon-footprint")
        if res.status_code == 200:
            data = res.json()
            print(f"   -> Success: Retrieved {len(data)} daily records.")
            if len(data) > 0:
                print(f"   -> Latest: {data[0]['timestamp']} Emissions: {data[0]['totalEmissions']} kg CO2e")
        else:
             print(f"   -> Failed: {res.status_code} {res.text}")
    except Exception as e:
        print(f"   -> Error: {e}")

    # 2. Green Metrics
    try:
        print("\n2. Checking GreenOps Metrics...")
        res = requests.get(f"{BASE_URL}/metrics")
        if res.status_code == 200:
            metrics = res.json()
            print(f"   -> Success: Retrieved {len(metrics)} metrics.")
            pue = next((m for m in metrics if m['name'].startswith("PUE")), None)
            if pue:
                print(f"   -> PUE: {pue['value']} (Target: {pue['target']})")
        else:
             print(f"   -> Failed: {res.status_code} {res.text}")
    except Exception as e:
        print(f"   -> Error: {e}")


if __name__ == "__main__":
    verify_sustainability()


import requests
import json
import sys

BASE_URL = "http://localhost:5000/api"

def test_get_assets():
    print(f"Testing GET {BASE_URL}/assets ...")
    try:
        response = requests.get(f"{BASE_URL}/assets")
        print(f"Status Code: {response.status_code}")
        if response.status_code == 200:
            assets = response.json()
            print(f"Found {len(assets)} assets.")
            if len(assets) > 0:
                print("First asset sample:", json.dumps(assets[0], indent=2))
            return assets
        else:
            print("Response:", response.text)
            return []
    except Exception as e:
        print(f"Error: {e}")
        return []

def test_get_single_asset(asset_id):
    print(f"Testing GET {BASE_URL}/assets/{asset_id} ...")
    try:
        response = requests.get(f"{BASE_URL}/assets/{asset_id}")
        print(f"Status Code: {response.status_code}")
        if response.status_code == 200:
            print("Asset found:", json.dumps(response.json(), indent=2))
        else:
            print("Response:", response.text)
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    assets = test_get_assets()
    
    target_id = "agent-EILT0197"
    test_get_single_asset(target_id)
    
    if assets and assets[0]['id'] != target_id:
        print(f"Testing with existing asset ID: {assets[0]['id']}")
        test_get_single_asset(assets[0]['id'])

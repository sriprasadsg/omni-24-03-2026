import requests
import json
import sys

BASE_URL = 'http://127.0.0.1:5000/api'

def test():
    try:
        # 1. Login
        print("Logging in...")
        login_res = requests.post(f"{BASE_URL}/auth/login", json={
            'email': 'super@omni.ai', 
            'password': 'password123'
        })
        if login_res.status_code != 200:
            print(f"Login failed: {login_res.text}")
            return
            
        token = login_res.json()['access_token']
        headers = {'Authorization': f'Bearer {token}'}
        
        # 2. List Assets
        print("Fetching assets...")
        assets_res = requests.get(f"{BASE_URL}/assets", headers=headers)
        if assets_res.status_code != 200:
            print(f"Fetch assets failed: {assets_res.text}")
            return
            
        assets_data = assets_res.json()
        items = assets_data.get('items', [])
        print(f"Found {len(items)} assets.")
        
        if not items:
            print("No assets found in DB. Registration might be needed.")
            return

        asset_id = items[0]['id']
        print(f"Testing asset: {asset_id}")
        
        # 3. Get Detail
        detail_res = requests.get(f"{BASE_URL}/assets/{asset_id}", headers=headers)
        print(f"Detail Status: {detail_res.status_code}")
        
        # 4. Get Metrics
        metrics_res = requests.get(f"{BASE_URL}/assets/{asset_id}/metrics", headers=headers)
        print(f"Metrics Status: {metrics_res.status_code}")
        if metrics_res.status_code == 200:
            print(f"Metrics count: {len(metrics_res.json().get('metrics', []))}")
            
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test()

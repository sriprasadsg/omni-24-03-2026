import requests
import json

try:
    response = requests.get("http://localhost:5000/api/assets")
    if response.status_code == 200:
        assets = response.json()
        print(f"✅ Found {len(assets)} assets in database:")
        for asset in assets:
            print(f"   - {asset.get('id')}: {asset.get('hostname')}")
    else:
        print(f"❌ API returned status code: {response.status_code}")
except Exception as e:
    print(f"❌ Error: {e}")

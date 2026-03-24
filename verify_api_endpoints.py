
import requests
import json
import sys

BASE_URL = "http://localhost:5000/api"

def test_endpoint(name, url):
    try:
        print(f"Testing {name} ({url})...")
        response = requests.get(url)
        if response.status_code == 200:
            data = response.json()
            count = len(data) if isinstance(data, list) else len(data.keys())
            print(f"✅ {name}: OK ({count} items)")
            return True
        else:
            print(f"❌ {name}: Failed ({response.status_code})")
            print(response.text[:200])
            return False
    except Exception as e:
        print(f"❌ {name}: Error - {e}")
        return False

def main():
    endpoints = [
        ("Pricing", f"{BASE_URL}/admin/pricing"),
        ("Agents", f"{BASE_URL}/agents"),
        ("Jobs", f"{BASE_URL}/jobs"),
        ("Prompts", f"{BASE_URL}/prompts"),
    ]
    
    success = True
    for name, url in endpoints:
        if not test_endpoint(name, url):
            success = False
            
    if success:
        print("\nAll endpoints verified successfully.")
        sys.exit(0)
    else:
        print("\nSome endpoints failed.")
        sys.exit(1)

if __name__ == "__main__":
    main()

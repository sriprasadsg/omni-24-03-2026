import requests
import sys

API_URL = "http://127.0.0.1:5000/api/compliance"

def verify_sorting():
    try:
        response = requests.get(API_URL)
        if response.status_code != 200:
            print(f"❌ API Error: {response.status_code}")
            sys.exit(1)

        frameworks = response.json()
        names = [f.get("name", "") for f in frameworks]
        
        sorted_names = sorted(names)
        
        print("Fetched Names:")
        for n in names:
            print(f" - {n}")
            
        if names == sorted_names:
            print("\n✅ SUCCESS: Frameworks are sorted alphabetically.")
            sys.exit(0)
        else:
            print("\n❌ FAILURE: Frameworks are NOT sorted.")
            print(f"Expected: {sorted_names[:3]}...")
            print(f"Actual:   {names[:3]}...")
            sys.exit(1)

    except Exception as e:
        print(f"❌ Exception: {e}")
        sys.exit(1)

if __name__ == "__main__":
    verify_sorting()

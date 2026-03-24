
import urllib.request
import json

def test_api():
    url = "http://localhost:5000/api/patches/outdated"
    print(f"Testing API: {url} ...")
    
    try:
        with urllib.request.urlopen(url) as response:
            data = json.loads(response.read().decode())
            print(f"Total Checked: {data.get('total_checked')}")
            print(f"Outdated Count: {data.get('outdated_count')}")
            
            packages = data.get('packages', [])
            if packages:
                print("\nTop 5 Outdated Packages:")
                for pkg in packages[:5]:
                    print(f" - {pkg.get('name')}: {pkg.get('current_version')} -> {pkg.get('latest_version')} ({pkg.get('update_status')})")
            else:
                print("\nNo outdated packages found in the response.")
                
    except Exception as e:
        print(f"API Error: {e}")

if __name__ == "__main__":
    test_api()

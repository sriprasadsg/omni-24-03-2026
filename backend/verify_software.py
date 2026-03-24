
import urllib.request
import json
import time

def verify_software():
    print("Verifying Software Updates in API...")
    url = "http://localhost:5000/api/assets"
    
    try:
        with urllib.request.urlopen(url) as response:
            data = json.loads(response.read().decode())
            
            for asset in data:
                print(f"\nAsset: {asset.get('hostname')}")
                software = asset.get('installedSoftware', [])
                print(f"Total Software: {len(software)}")
                
                updates_found = 0
                for sw in software:
                    if sw.get('updateAvailable'):
                        updates_found += 1
                        print(f"   [UPDATE] {sw.get('name')}: {sw.get('version')} -> {sw.get('latestVersion')}")
                
                if updates_found == 0:
                    print("   No updates detected yet (checking winget might take time or no updates available).")
                else:
                    print(f"   ✅ Detected {updates_found} available updates!")

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    verify_software()

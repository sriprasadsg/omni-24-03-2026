
import requests
import json

BASE_URL = "http://localhost:5000"

def verify():
    # 1. Get Assets
    try:
        resp = requests.get(f"{BASE_URL}/api/assets")
        assets = resp.json()
        if not assets:
            print("No assets found.")
            return

        asset_id = assets[0]['id']
        print(f"Checking Asset: {asset_id}")

        # 2. Get Compliance
        resp = requests.get(f"{BASE_URL}/api/assets/{asset_id}/compliance")
        report = resp.json()
        
        # 3. Find Backup Rule
        backup_rule = next((r for r in report['rules'] if r['id'] == 'backups'), None)
        
        if backup_rule:
             print(f"Backup Rule Status: {backup_rule['status']}")
             print(f"Evidence: {backup_rule['evidence']}")
             if backup_rule['status'] == 'passed':
                 print("✅ SUCCESS: Backup check passed.")
             else:
                 print("❌ FAILURE: Backup check failed.")
        else:
             print("Backup rule not found in report.")

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    verify()

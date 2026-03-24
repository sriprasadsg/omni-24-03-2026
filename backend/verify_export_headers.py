
import requests

def check_export_headers():
    url = "http://localhost:5000/api/reports/export"
    params = {"type": "Asset Inventory", "format": "csv"}
    try:
        response = requests.get(url, params=params)
        print(f"Status Code: {response.status_code}")
        print("Headers:")
        for k, v in response.headers.items():
            print(f"{k}: {v}")
            
        cd = response.headers.get("Content-Disposition")
        if cd and "filename=" in cd:
            print(f"\nSUCCESS: Content-Disposition header found: {cd}")
        else:
            print(f"\nFAILURE: Content-Disposition header missing or invalid. Got: {cd}")
            
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    check_export_headers()

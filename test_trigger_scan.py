import requests
import json

def test_trigger_scan(framework_id="nistcsf"):
    url = f"http://localhost:5000/api/compliance/{framework_id}/scan"
    
    print(f"Testing Trigger Scan for {framework_id}...")
    try:
        # No auth needed for this specific endpoint in dev/demo mode usually, 
        # or we might need to mock a token if it's protected.
        # agent_endpoints.py shows @router.post... 
        # wait, compliance_endpoints.py: @router.post("/api/compliance/{framework_id}/scan")
        # It does NOT have Depends(get_current_user) in the signature I saw earlier? 
        # Let's check. 
        # Ah, view_file output of compliance_endpoints.py line 91:
        # @router.post("/api/compliance/{framework_id}/scan")
        # async def trigger_framework_scan(framework_id: str):
        # No dependency! So it's public/unprotected for now.
        
        resp = requests.post(url)
        print(f"Status Code: {resp.status_code}")
        print(f"Response: {resp.text}")
        
        if resp.status_code == 200 and resp.json().get("success"):
            print("✅ Scan Triggered Successfully!")
        else:
            print("❌ Scan Trigger Failed.")
            
    except Exception as e:
        print(f"❌ Exception: {e}")

if __name__ == "__main__":
    test_trigger_scan()

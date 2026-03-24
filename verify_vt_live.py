import httpx
import asyncio
import json

async def verify_vt_live():
    # Credentials (Super Admin)
    email = "super@omni.ai"
    password = "password123"
    api_url = "http://localhost:5000/api"
    
    async with httpx.AsyncClient() as client:
        # 1. Login
        print(f"Logging in as {email}...")
        try:
            login_resp = await client.post(f"{api_url}/auth/login", json={"email": email, "password": password})
        except Exception as e:
            print(f"❌ Login request failed: {e}")
            return

        if login_resp.status_code != 200:
            print(f"❌ Login failed: {login_resp.text}")
            return
        
        token = login_resp.json().get("access_token")
        headers = {"Authorization": f"Bearer {token}"}
        user = login_resp.json().get("user", {})
        tenant_id = user.get("tenantId", "default")
        
        print(f"✅ Login successful. Tenant: {tenant_id}\n")
        
        # 2. Scan a known domain (google.com)
        artifact = "google.com"
        artifact_type = "domain"
        print(f"Scanning {artifact_type}: {artifact} via VirusTotal...")
        
        scan_payload = {
            "artifact": artifact,
            "artifact_type": artifact_type,
            "tenant_id": tenant_id
        }
        
        try:
            # Use 60 second timeout for VT API
            scan_resp = await client.post(f"{api_url}/threat-intel/scan", json=scan_payload, headers=headers, timeout=60.0)
            
            if scan_resp.status_code == 200:
                result = scan_resp.json()
                print(f"✅ Scan successful!")
                print(f"  Verdict: {result.get('verdict')}")
                print(f"  Detection Ratio: {result.get('detection_ratio')}")
                print(f"  Malicious: {result.get('malicious')}")
                print(f"  Suspicious: {result.get('suspicious')}")
                print(f"  Harmless: {result.get('harmless')}")
                
                # Check message for "MOCK"
                raw_details = result.get('raw_result', {})
                if 'MOCK' in str(result.get('message', '')):
                    print("\n⚠️ Still using mock data - API key may not be loaded properly in backend.")
                else:
                    print("\n✅ VirusTotal integration working with REAL API!")
            else:
                print(f"❌ Scan failed: {scan_resp.status_code} - {scan_resp.text}")
        except httpx.ReadTimeout:
            print("❌ Scan failed: Timeout after 60 seconds. Backend might be blocking.")
        except Exception as e:
            print(f"❌ Scan failed: {e}")

if __name__ == "__main__":
    asyncio.run(verify_vt_live())

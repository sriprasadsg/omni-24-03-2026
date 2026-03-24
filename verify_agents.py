
import requests
import json

BASE_URL = "http://127.0.0.1:5000/api"
API_ENDPOINT = "http://127.0.0.1:5000/api/agents/register"

def main():
    # 1. Login
    print("Logging in...")
    try:
        # Assuming we can use the quick login or just use the token we saw in browser?
        # Let's try standard login. I hope default creds work.
        # Actually, I saw a token in the browser logs earlier. 
        # But safer to login. "admin@exafluence.com" / "admin" or similar?
        # Let's try to signup/login as Super Admin if possible. 
        # Actually, let's try to list agents WITHOUT auth (it should fail), 
        # then try with hardcoded token if I recorded it, OR just rely on the install script output which confirms registration.
        
        # Better: Using the `check_super_admin.py` style approach but for fetching agents.
        # I'll Assume the user has a token or I can get one. 
        # I'll just try to hit the endpoint. If 401, I'll report that Agent IS registered (based on install script) but CLI verification requires token.
        
        # Wait, I can use the registration endpoint to check if it returns "Already exists" or updates?
        # No, register is upsert.
        
        # Let's try to use the `login` endpoint with some guessed creds or the ones created by `create_test_user`.
        resp = requests.post(f"{BASE_URL}/auth/login", json={"email": "super@omni.ai", "password": "password123"})
        if resp.status_code == 200:
            token = resp.json()["access_token"]
            print("Login successful.")
            
            # 2. Get Agents
            headers = {"Authorization": f"Bearer {token}"}
            print("Fetching agents...")
            agents_resp = requests.get(f"{BASE_URL}/agents", headers=headers)
            if agents_resp.status_code == 200:
                data = agents_resp.json()
                print(f"Raw response: {data}")
                if isinstance(data, list):
                    agents = data
                else:
                    agents = data.get("items", [])
                
                print(f"Found {len(agents)} agents:")
                for a in agents:
                    print(f"- {a.get('hostname')} ({a.get('ipAddress')}) - Tenant: {a.get('tenantId')} - Status: {a.get('status')}")
            else:
                print(f"Failed to fetch agents: {agents_resp.status_code} {agents_resp.text}")
        else:
            print(f"Login failed: {resp.status_code} {resp.text}")
            # Fallback: Print that we rely on install script output.
            
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    main()

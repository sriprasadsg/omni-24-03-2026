
import requests
import json
from collections import Counter

API_URL = "http://localhost:5000/api/agents"
# Assuming no auth needed for local dev or simple admin token? 
# The backend usually requires auth. I need a token.
# I'll try to login first.

def check_endpoint():
    try:
        # Login
        session = requests.Session()
        login_payload = {"email": "super@omni.ai", "password": "admin123"}
        resp = session.post("http://localhost:5000/api/auth/login", json=login_payload)
        
        if resp.status_code != 200:
            print(f"Login failed: {resp.status_code} {resp.text}")
            # Try alternate login
            login_payload = {"email": "admin@acmecorp.com", "password": "admin123"}
            resp = session.post("http://localhost:5000/api/auth/login", json=login_payload)
            if resp.status_code != 200:
                print("Double login failure.")
                return

        token = resp.json().get("access_token")
        headers = {"Authorization": f"Bearer {token}"}
        
        # Fetch Agents
        print("Fetching agents from API...")
        resp = session.get(API_URL, headers=headers)
        if resp.status_code != 200:
            print(f"Fetch failed: {resp.status_code} {resp.text}")
            return
            
        data = resp.json()
        items = data.get("items", data) if isinstance(data, dict) else data
        
        print(f"Fetched {len(items)} agents.")
        
        ids = [a.get("id") for a in items]
        counts = Counter(ids)
        dupes = {k: v for k, v in counts.items() if v > 1}
        
        if dupes:
            print(f"❌ Found duplicate IDs in API response: {dupes}")
        else:
            print("✅ No duplicates in API response.")
            
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    check_endpoint()

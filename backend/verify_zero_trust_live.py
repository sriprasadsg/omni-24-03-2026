import httpx
import asyncio
import json

BASE_URL = "http://127.0.0.1:5000/api"

async def test_zero_trust():
    async with httpx.AsyncClient(timeout=10.0) as client:
        # Login to get token
        print("Logging in...")
        login_res = await client.post(f"{BASE_URL}/auth/login", json={
            "email": "super@omni.ai",
            "password": "password123"
        })
        
        if login_res.status_code != 200 or not login_res.json().get("success"):
            print(f"Login failed: {login_res.text}")
            return
            
        token = login_res.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        
        # Test Device Trust Scores
        print("\nTesting /zero-trust/device-trust-scores...")
        res = await client.get(f"{BASE_URL}/zero-trust/device-trust-scores", headers=headers)
        print(f"Status: {res.status_code}")
        if res.status_code == 200:
            print(f"Count: {len(res.json())}")
            if len(res.json()) > 0:
                print(f"First result: {json.dumps(res.json()[0], indent=2)}")
        else:
            print(f"Error: {res.text}")
            
        # Test Session Risks
        print("\nTesting /zero-trust/session-risks...")
        res = await client.get(f"{BASE_URL}/zero-trust/session-risks", headers=headers)
        print(f"Status: {res.status_code}")
        if res.status_code == 200:
            print(f"Count: {len(res.json())}")
        else:
            print(f"Error: {res.text}")
            
        # Test Crypto Inventory
        print("\nTesting /quantum-security/cryptographic-inventory...")
        res = await client.get(f"{BASE_URL}/quantum-security/cryptographic-inventory", headers=headers)
        print(f"Status: {res.status_code}")
        if res.status_code == 200:
            print(f"Count: {len(res.json())}")
            if len(res.json()) > 0:
                print(f"First result: {json.dumps(res.json()[0], indent=2)}")
        else:
            print(f"Error: {res.text}")

if __name__ == "__main__":
    asyncio.run(test_zero_trust())

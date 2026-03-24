import asyncio
import httpx
import os
import sys

# We need the JWT token to authenticate to the protected endpoints.
# Let's write a simple script that logs in, gets a token, and hits the endpoints.
async def verify_system_apis():
    print("--- FULL SYSTEM API AUDIT ---")
    
    # 1. Login to get token
    login_data = {
        "username": "super@omni.ai",
        "password": "password123"
    }
    
    async with httpx.AsyncClient() as client:
        try:
            # Login
            print("\n1. Verifying Authentication (Login)...")
            resp = await client.post("http://localhost:5000/api/auth/login", json=login_data, timeout=10)
            if resp.status_code == 200:
                print(" [SUCCESS] Login Success")
                token = resp.json().get("access_token")
            else:
                print(f" [FAILED] Login Failed: {resp.status_code} {resp.text}")
                return
            
            headers = {"Authorization": f"Bearer {token}"}
            
            # 2. CISSP Oracle
            print("\n2. Verifying CISSP Oracle...")
            # Let's check the endpoint route. Probably /api/cissp/ask or something similar.
            oracle_data = {"question": "What is Domain 1?", "framework_id": "cissp"}
            # The oracle might be under /api/cissp-oracle/ask
            resp = await client.post("http://localhost:5000/api/cissp-oracle/ask", json=oracle_data, headers=headers)
            if resp.status_code == 200:
                print(" [SUCCESS] CISSP Oracle Success: " + resp.json().get('answer', '')[:50] + "...")
            else:
                print(f" [FAILED] CISSP Oracle Failed: {resp.status_code} {resp.text}")
            
            # 3. Billing & Subscriptions
            print("\n3. Verifying Billing & Subscriptions...")
            resp = await client.get("http://localhost:5000/api/billing/plans", headers=headers)
            if resp.status_code == 200:
                plans = resp.json()
                print(f" [SUCCESS] Billing Success: Found {len(plans)} plans.")
            else:
                print(f" [FAILED] Billing Failed: {resp.status_code} {resp.text}")
                
            # 4. A/B Testing
            print("\n4. Verifying A/B Testing Dashboard...")
            resp = await client.get("http://localhost:5000/api/ab-testing/experiments", headers=headers)
            if resp.status_code == 200:
                exps = resp.json()
                print(f" [SUCCESS] A/B Testing Success: Found {len(exps)} experiments.")
            else:
                print(f" [FAILED] A/B Testing Failed: {resp.status_code} {resp.text}")

            # 5. BI Analytics
            print("\n5. Verifying BI Analytics...")
            resp = await client.get("http://localhost:5000/api/analytics/metrics", headers=headers)
            if resp.status_code == 200:
                print(" [SUCCESS] BI Analytics Success: " + str(resp.json())[:50] + "...")
            else:
                # Sometimes it might need specific params, checking basic active users
                print(f" [FAILED] BI Analytics Failed: {resp.status_code} {resp.text}")

            # 6. Tenant Management / RBAC
            print("\n6. Verifying Users (RBAC)...")
            resp = await client.get("http://localhost:5000/api/users", headers=headers)
            if resp.status_code == 200:
                users = resp.json()
                print(f" [SUCCESS] User Management Success: Found {len(users)} users.")
            else:
                print(f" [FAILED] User Management Failed: {resp.status_code} {resp.text}")
                
        except Exception as e:
            print(f"Exception during tests: {e}")

if __name__ == "__main__":
    asyncio.run(verify_system_apis())

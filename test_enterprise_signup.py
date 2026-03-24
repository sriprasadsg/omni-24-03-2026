
import asyncio
import httpx
import json

async def verify_signup():
    url = "http://127.0.0.1:5000/api/auth/signup"
    payload = {
        "companyName": "Test Enterprise Corp",
        "name": "Enterprise Admin",
        "email": f"admin-{json.dumps(asyncio.get_event_loop().time())}@testenterprise.com",
        "password": "password123"
    }
    
    print(f"Performing signup for {payload['email']}...")
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            resp = await client.post(url, json=payload)
            print(f"Status: {resp.status_code}")
            if resp.status_code == 200:
                data = resp.json()
                print("Signup Successful!")
                
                user = data.get("user", {})
                tenant = data.get("tenant", {})
                
                print(f"User Subscription Tier: {user.get('subscriptionTier')}")
                print(f"User Permissions Count: {len(user.get('permissions', []))}")
                print(f"Tenant Subscription Tier: {tenant.get('subscriptionTier')}")
                print(f"Tenant Enabled Features Count: {len(tenant.get('enabledFeatures', []))}")
                
                # Check for specific expected features
                expected_features = ["view:finops", "view:cloud_security", "view:threat_hunting"]
                missing_features = [f for f in expected_features if f not in tenant.get('enabledFeatures', [])]
                
                if not missing_features:
                    print("SUCCESS: All expected enterprise features are present.")
                else:
                    print(f"FAILURE: Missing features: {missing_features}")
                    
                if user.get('subscriptionTier') == "Enterprise" and tenant.get('subscriptionTier') == "Enterprise":
                    print("SUCCESS: Subscription tiers are correctly set to Enterprise.")
                else:
                    print(f"FAILURE: Subscription tier mismatch. User: {user.get('subscriptionTier')}, Tenant: {tenant.get('subscriptionTier')}")
            else:
                print(f"Signup Failed: {resp.text}")
        except Exception as e:
            print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(verify_signup())

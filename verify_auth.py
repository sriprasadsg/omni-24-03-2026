import requests
import json

BASE_URL = "http://127.0.0.1:5000"

def verify_auth():
    # 1. Login
    login_url = f"{BASE_URL}/api/auth/login"
    # Using the credentials from reset_tenants.py / seed data
    # Assuming default password is 'admin' for super@omni.ai based on common practices in this repo
    # or I will check how user is created in reset_tenants.py. 
    # Ah, reset_tenants.py doesn't create user, it only deletes tenants/agents.
    # The user should already exist from previous sessions.
    
    payload = {
        "email": "super@omni.ai",
        "password": "admin" 
    }
    
    print(f"Attempting login to {login_url}...")
    try:
        print(f"Request Payload: {json.dumps(payload)}")
        response = requests.post(login_url, json=payload)
        print(f"Login Status: {response.status_code}")
        print(f"Login Headers: {response.headers}")
        print(f"Login Response: {response.text}")
        
        if response.status_code != 200:
            print("Login failed, cannot proceed.")
            return

        token_data = response.json()
        access_token = token_data.get("access_token")
        
        if not access_token:
            print("No access token found in response.")
            return
            
        print(f"Access Token: {access_token[:20]}...")
        
        # 2. Access Protected Endpoint
        agents_url = f"{BASE_URL}/api/agents"
        headers = {
            "Authorization": f"Bearer {access_token}"
        }
        
        print(f"Attempting to fetch agents from {agents_url}...")
        agent_response = requests.get(agents_url, headers=headers)
        
        print(f"Agent Fetch Status: {agent_response.status_code}")
        print(f"Agent Fetch Response: {agent_response.text}")
        
    except Exception as e:
        print(f"Error during verification: {e}")

async def debug_user():
    import sys
    import os
    sys.path.append(os.path.join(os.getcwd(), 'backend'))
    from database import connect_to_mongo, get_database
    from auth_utils import verify_password
    
    await connect_to_mongo()
    db = get_database()
    
    user = await db.users.find_one({"email": "super@omni.ai"})
    if user:
        print(f"User found: {user['email']}")
        print(f"Stored Password Hash: {user['password']}")
        is_valid = verify_password("admin", user['password'])
        print(f"Password 'admin' valid? {is_valid}")
    else:
        print("User super@omni.ai NOT found in DB")

if __name__ == "__main__":
    import asyncio
    verify_auth()
    # loop = asyncio.get_event_loop()
    # loop.run_until_complete(debug_user())

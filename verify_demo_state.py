
import httpx
import asyncio
import json

async def test_demo_flow():
    base_url = "http://127.0.0.1:5000/api"
    login_url = f"{base_url}/auth/login"
    chat_url = f"{base_url}/ai/chat"
    
    # 1. Login to get token
    async with httpx.AsyncClient() as client:
        print("--- Logging in ---")
        login_resp = await client.post(login_url, json={
            "email": "browser-test-demo@omni.ai",
            "password": "password123"
        })
        
        if login_resp.status_code != 200:
            print(f"Login failed ({login_resp.status_code}): {login_resp.text}")
            print("Trying signup...")
            signup_resp = await client.post(f"{base_url}/auth/signup", json={
                "email": "browser-test-demo@omni.ai",
                "password": "password123",
                "companyName": "Test Corp",
                "name": "Tester"
            })
            if signup_resp.status_code != 200:
                 print(f"Signup failed ({signup_resp.status_code}): {signup_resp.text}")
                 return
            token = signup_resp.json()["access_token"]
        else:
            token = login_resp.json()["access_token"]
            
        headers = {"Authorization": f"Bearer {token}"}
        
        # 2. Start Demo with new keyword
        print("\n--- Starting Demo (Keyword: 'overview') ---")
        resp = await client.post(chat_url, json={"message": "give me a project overview"}, headers=headers)
        print(f"Input: 'give me a project overview'")
        print(f"Output: {resp.json().get('response')}")
        
        # 3. Interrupt with a question
        print("\n--- Interrupting ---")
        resp = await client.post(chat_url, json={"message": "What is an agent?"}, headers=headers)
        print(f"Input: 'What is an agent?'")
        print(f"Output: {resp.json().get('response')}")
        
        # 4. Confirm satisfaction and resume
        print("\n--- Resuming ---")
        resp = await client.post(chat_url, json={"message": "Yes, I am satisfied with that. Continue."}, headers=headers)
        print(f"Input: 'Yes, I am satisfied with that. Continue.'")
        print(f"Output: {resp.json().get('response')}")
        
        # 5. Check if it actually resumed (should mention 'Agent Management' or 'Step 1' in DEMO_STEPS)
        output = resp.json().get('response')
        if "Agent Management" in output or "Step 1" in output or "1." in output:
             print("\nSUCCESS: Demo resumed to Phase 1 (Agent Management).")
        else:
             print(f"\nFAILURE: Demo did not seem to resume to Phase 1. Output: {output}")

if __name__ == "__main__":
    asyncio.run(test_demo_flow())

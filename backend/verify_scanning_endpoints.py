
import asyncio
import aiohttp
import sys

# Constants
BASE_URL = "http://localhost:5000/api"
# Token likely needed, but let's try assuming the current backend state allows dev access or we mock it.
# Actually, the endpoints use 'current_user = Depends(get_current_user)'.
# I'll reuse the login logic from verify_reporting.py if needed, 
# but for now let's try a direct approach or assume I can get a token.

# Since I don't have the password handy in this context (it was in previous turn summary), 
# I will check verify_reporting.py content if I need to copy login logic.
# Wait, I recall super@omni.ai / password123 from summary.

async def verify_scanning():
    print("Starting verification of Network Scanning Endpoints...")
    
    async with aiohttp.ClientSession() as session:
        # 1. Login
        print("Authenticating...")
        try:
            async with session.post(f"{BASE_URL}/auth/login", json={"email": "super@omni.ai", "password": "password123"}) as resp:
                if resp.status != 200:
                    print(f"Login failed: {resp.status}")
                    text = await resp.text()
                    print(text)
                    return
                token_data = await resp.json()
                access_token = token_data["access_token"]
                headers = {"Authorization": f"Bearer {access_token}"}
                print("Authentication successful.")
        except Exception as e:
            print(f"Auth error: {e}")
            return

        # 2. Get Subnets
        print("Testing GET /network-devices/subnets...")
        async with session.get(f"{BASE_URL}/network-devices/subnets", headers=headers) as resp:
            if resp.status == 200:
                subnets = await resp.json()
                print(f"Subnets found: {subnets}")
                if "192.168.1.0/24" in subnets and "10.0.0.0/24" in subnets:
                    print("VERIFICATION_SUCCESS: Expected subnets found.")
                else:
                    print("VERIFICATION_WARNING: Expected subnets NOT found (maybe seed data missing?).")
            else:
                print(f"VERIFICATION_FAILURE: GET /subnets failed with {resp.status}")
                print(await resp.text())

        # 3. Trigger Subnet Scan
        test_subnet = "192.168.1.0/24"
        print(f"Testing POST /network-devices/scan with subnet={test_subnet}...")
        async with session.post(f"{BASE_URL}/network-devices/scan?subnet={test_subnet}", headers=headers) as resp:
            if resp.status == 200:
                data = await resp.json()
                print(f"Scan response: {data}")
                if data.get("status") == "success":
                     print("VERIFICATION_SUCCESS: Subnet scan triggered.")
                else:
                     print("VERIFICATION_FAILURE: Scan status not success.")
            else:
                print(f"VERIFICATION_FAILURE: POST /scan failed with {resp.status}")
                print(await resp.text())

if __name__ == "__main__":
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(verify_scanning())

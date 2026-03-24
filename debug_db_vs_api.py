import asyncio
import json
import urllib.request
import os
from motor.motor_asyncio import AsyncIOMotorClient

# API Config
API_URL = "http://localhost:5001/api"
ADMIN_EMAIL = "admin@example.com"
ADMIN_PASS = "admin123"

# DB Config
MONGO_URL = os.getenv("MONGODB_URL", "mongodb://localhost:27017")
DB_NAME = os.getenv("MONGODB_DB_NAME", "omni_platform")

def api_login():
    try:
        data = json.dumps({"email": ADMIN_EMAIL, "password": ADMIN_PASS}).encode("utf-8")
        req = urllib.request.Request(f"{API_URL}/auth/login", data=data, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req) as response:
            return json.loads(response.read().decode("utf-8")).get("access_token")
    except Exception as e:
        print(f"API Login Failed: {e}")
        return None

def api_get_tenants(token):
    try:
        req = urllib.request.Request(f"{API_URL}/tenants", headers={"Authorization": f"Bearer {token}"})
        with urllib.request.urlopen(req) as response:
            return json.loads(response.read().decode("utf-8"))
    except Exception as e:
        print(f"API Get Tenants Failed: {e}")
        return []

async def db_get_tenants():
    client = AsyncIOMotorClient(MONGO_URL)
    db = client[DB_NAME]
    return await db.tenants.find({}).to_list(length=None)

async def compare():
    print("--- STARTING COMPARISON ---")
    
    # 1. API Fetch
    print("Fetching via API...")
    token = api_login()
    if not token:
        return
    api_tenants = api_get_tenants(token)
    print(f"API returned {len(api_tenants)} tenants.")
    
    # 2. DB Fetch
    print("Fetching via DB...")
    db_tenants = await db_get_tenants()
    print(f"DB returned {len(db_tenants)} tenants.")
    
    # 3. Compare
    api_map = {t['id']: t for t in api_tenants}
    db_map = {t['id']: t for t in db_tenants}
    
    all_ids = set(api_map.keys()) | set(db_map.keys())
    
    for tid in all_ids:
        in_api = tid in api_map
        in_db = tid in db_map
        
        if not in_api or not in_db:
             print(f"Tenant {tid}: API={in_api}, DB={in_db} MISMATCH")
             continue
             
        t_api = api_map[tid]
        t_db = db_map[tid]
        
        # Check finOpsData
        fd_api = t_api.get('finOpsData') or t_api.get('finopsData')
        fd_db = t_db.get('finOpsData') or t_db.get('finopsData')
        
        print(f"Tenant {tid} ({t_api.get('name')}):")
        print(f"   API keys count: {len(t_api.keys())}")
        print(f"   DB keys count: {len(t_db.keys())}")
        print(f"   Has finOpsData in API? {fd_api is not None}")
        print(f"   Has finOpsData in DB?  {fd_db is not None}")
        
        if fd_db and not fd_api:
            print("   CRITICAL: Data exists in DB but missing in API!")
            print(f"   DB Keys: {list(t_db.keys())}")
            print(f"   API Keys: {list(t_api.keys())}")

if __name__ == "__main__":
    asyncio.run(compare())

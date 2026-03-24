
import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
import certifi

MONGO_URI = "mongodb://localhost:27017"
DB_NAME = "omni_platform"

async def check_permissions():
    client = AsyncIOMotorClient(MONGO_URI, tlsCAFile=certifi.where())
    db = client[DB_NAME]
    
    print("--- User Check ---")
    # Finding the user 'sriprasad'
    user = await db.users.find_one({"email": {"$regex": "sriprasad@ex", "$options": "i"}})
    if user:
        print(f"User: {user['email']}")
        print(f"Role: {user.get('role')}")
        print(f"Tenant ID: {user.get('tenantId')}")
        user_tenant_id = user.get('tenantId')
    else:
        print("User sriprasad not found!")
        user_tenant_id = None

    print("\n--- Agent Check ---")
    agent_id = "agent-EILT0197"
    agent = await db.agents.find_one({"id": agent_id})
    if agent:
        print(f"Agent ID: {agent['id']}")
        print(f"Hostname: {agent.get('hostname')}")
        print(f"Tenant ID: {agent.get('tenantId')}")
        agent_tenant_id = agent.get('tenantId')
    else:
        print(f"Agent {agent_id} not found!")
        agent_tenant_id = None
        
    print("\n--- Conclusion ---")
    if user_tenant_id and agent_tenant_id:
        match = (user_tenant_id == agent_tenant_id)
        print(f"Tenant IDs Match: {match}")
        if not match:
            print("FAILURE: User cannot delete agent due to tenant mismatch.")
    
    admin_roles = ["Super Admin", "super_admin", "admin"]
    user_role = user.get('role') if user else "None"
    print(f"User Role '{user_role}' in Admin List?: {user_role in admin_roles}")
    
    if user_tenant_id and agent_tenant_id:
        can_delete = (user_role in admin_roles) or (user_tenant_id == agent_tenant_id)
        print(f"Should be able to delete?: {can_delete}")

if __name__ == "__main__":
    asyncio.run(check_permissions())

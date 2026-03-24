import sys
import os
import asyncio
from motor.motor_asyncio import AsyncIOMotorClient

async def debug_tenants():
    client = AsyncIOMotorClient('mongodb://127.0.0.1:27017')
    db = client['omni_platform']
    
    print("--- Agents ---")
    agents = await db.agents.find({}).to_list(100)
    for a in agents:
        print(f"Agent Hostname: {a.get('hostname')}")
        print(f"Agent ID: {a.get('id')}")
        print(f"Agent TenantID: {a.get('tenantId')}")
        print(f"Agent Status: {a.get('status')}")
    
    print("\n--- Users ---")
    users = await db.users.find({}).to_list(100)
    for u in users:
        print(f"User Email: {u.get('email')}")
        print(f"User TenantID: {u.get('tenantId')}")
        print(f"User Role: {u.get('role')}")

if __name__ == "__main__":
    asyncio.run(debug_tenants())

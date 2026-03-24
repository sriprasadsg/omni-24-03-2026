#!/usr/bin/env python3
"""
Force database seeding for roles
"""
import os
import sys
import asyncio
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv()

# Import the seed function
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend'))
from app import seed_database
from database import connect_to_mongo, get_database

async def main():
    print("="*60)
    print("  FORCING DATABASE SEEDING")
    print("="*60)
    
    # Connect to MongoDB
    await connect_to_mongo()
    
    # Run seed
    await seed_database()
    
    # Verify roles
    db = get_database()
    roles = await db.roles.find({}).to_list(length=100)
    
    print(f"\n✓ Found {len(roles)} roles:")
    for role in roles:
        print(f"\n  Role: {role.get('name')}")
        print(f"    ID: {role.get('id')}")
        perms = role.get('permissions', [])
        print(f"    Permissions: {len(perms)}")
        # Check critical permissions
        if 'view:agents' in perms:
            print(f"      ✓ Has 'view:agents'")
        if 'remediate:agents' in perms:
            print(f"      ✓ Has 'remediate:agents'")
    
    print("\n" + "="*60)

if __name__ == "__main__":
    asyncio.run(main())

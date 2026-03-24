import asyncio
from database import get_database, connect_to_mongo

async def check_super_admin():
    await connect_to_mongo()
    db = get_database()
    user = await db.users.find_one({'email': 'super@omni.ai'})
    
    if user:
        print("\n" + "="*60)
        print("USER ACCOUNT DETAILS")
        print("="*60)
        print(f"Email: {user.get('email')}")
        print(f"Username: {user.get('username', 'N/A')}")
        print(f"Role: {user.get('role')}")
        print(f"ID: {user.get('id', user.get('_id'))}")
        print(f"Tenant ID: {user.get('tenantId', 'N/A')}")
        print(f"Created: {user.get('createdAt', 'N/A')}")
        print("="*60)
        
        # Check if it's Super Admin
        role = user.get('role', '').lower()
        if 'super' in role and 'admin' in role:
            print("\n✅ YES - This account HAS Super Admin privileges!")
            print("\nSuper Admin capabilities:")
            print("  • Access all tenants")
            print("  • Manage all users")
            print("  • Configure platform settings")
            print("  • View all data across tenants")
            print("  • Full RBAC permissions")
        else:
            print(f"\n❌ NO - This account has role: '{user.get('role')}'")
            print("It does NOT have Super Admin privileges.")
    else:
        print("❌ User not found!")

asyncio.run(check_super_admin())

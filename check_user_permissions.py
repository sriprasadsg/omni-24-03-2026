import yaml
from pymongo import MongoClient
import os
from dotenv import load_dotenv

load_dotenv()

def check_permissions():
    mongodb_url = os.getenv("MONGODB_URL", "mongodb://localhost:27017/")
    db_name = os.getenv("MONGODB_DB_NAME", "omni_agent_db")
    
    client = MongoClient(mongodb_url)
    db = client[db_name]
    
    # Use the known user email
    email = "admin@exafleucne.com"
    
    print(f"Checking permissions for user: {email}")
    
    user = db.users.find_one({'email': email}, {'_id': 0, 'password': 0})
    if user:
        print(f"\nUser Details:")
        print(f"  Email: {user.get('email')}")
        print(f"  Name: {user.get('name')}")
        print(f"  Role: {user.get('role')}")
        print(f"  Tenant ID: {user.get('tenantId')}")
        
        # Get role details
        role_name = user.get('role')
        role = db.roles.find_one({'name': role_name}, {'_id': 0})
        
        if role:
            print(f"\nRole: {role.get('name')}")
            print(f"  Description: {role.get('description')}")
            permissions = role.get('permissions', [])
            print(f"\n  Total Permissions: {len(permissions)}")
            print(f"\n  Permissions:")
            for perm in sorted(permissions):
                print(f"    - {perm}")
            
            # Check specific permission
            print(f"\n  Permission Checks:")
            print(f"    'remediate:agents': {'✅ YES' if 'remediate:agents' in permissions else '❌ NO'}")
            print(f"    'view:agents': {'✅ YES' if 'view:agents' in permissions else '❌ NO'}")
            print(f"    'manage:agents': {'✅ YES' if 'manage:agents' in permissions else '❌ NO (not in permission list)'}")
        else:
            print(f"\n❌ Role '{role_name}' not found!")
    else:
        print(f"❌ User not found!")
    
    client.close()

if __name__ == "__main__":
    check_permissions()

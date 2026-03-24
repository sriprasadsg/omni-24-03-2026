
import pymongo
import certifi

MONGO_URI = "mongodb://localhost:27017"
DB_NAME = "omni_platform"

def check_role_permissions():
    try:
        client = pymongo.MongoClient(MONGO_URI, socketTimeoutMS=2000, serverSelectionTimeoutMS=2000)
        db = client[DB_NAME]
        
        print("--- Role Permission Check ---")
        role_name = "Tenant Admin"
        role = db.roles.find_one({"name": role_name})
        
        if role:
            perms = role.get("permissions", [])
            print(f"Role: {role_name}")
            print(f"Permissions Count: {len(perms)}")
            has_remediate = "remediate:agents" in perms
            print(f"Has 'remediate:agents': {has_remediate}")
            if not has_remediate:
                print("Permissions list:", perms)
        else:
            print(f"Role {role_name} not found!")

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    check_role_permissions()

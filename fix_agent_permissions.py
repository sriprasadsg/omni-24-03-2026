"""
Fix agent installation permissions by ensuring proper roles exist in the database
and users are assigned to roles with appropriate permissions.
"""
from pymongo import MongoClient
import os
import sys
from dotenv import load_dotenv

# Add backend to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend'))
from auth_utils import hash_password

load_dotenv()

def fix_agent_permissions():
    mongodb_url = os.getenv("MONGODB_URL", "mongodb://localhost:27017/")
    db_name = os.getenv("MONGODB_DB_NAME", "omni_agent_db")
    
    client = MongoClient(mongodb_url)
    db = client[db_name]
    
    print("=" * 70)
    print("FIXING AGENT INSTALLATION PERMISSIONS")
    print("=" * 70)
    
    # Define all permissions for Super Admin
    all_permissions = [
        'view:dashboard', 'view:reporting', 'export:reports', 'view:agents',
        'view:software_deployment', 'view:agent_logs', 'remediate:agents', 'view:assets',
        'view:patching', 'manage:patches', 'view:security', 'manage:security_cases',
        'manage:security_playbooks', 'investigate:security', 'view:compliance',
        'manage:compliance_evidence', 'view:ai_governance', 'manage:ai_risks',
        'manage:settings', 'manage:tenants', 'view:cloud_security', 'view:finops',
        'view:audit_log', 'manage:rbac', 'manage:api_keys', 'view:logs',
        'view:threat_hunting', 'view:profile', 'view:automation', 'manage:automation',
        'view:devsecops', 'view:developer_hub', 'view:insights', 'view:tracing',
        'view:dspm', 'view:attack_path', 'view:service_catalog', 'view:dora_metrics',
        'view:chaos', 'view:network', 'manage:pricing', 'view:software_updates'
    ]
    
    # Define Tenant Admin permissions (subset of Super Admin)
    tenant_admin_permissions = [
        'view:dashboard', 'view:reporting', 'export:reports', 
        'view:agents', 'view:software_deployment', 'view:agent_logs', 'remediate:agents',
        'view:assets', 'view:patching', 'manage:patches', 'view:security', 
        'manage:security_cases', 'investigate:security', 'view:compliance',
        'manage:compliance_evidence', 'view:ai_governance', 'manage:ai_risks',
        'manage:settings', 'view:cloud_security', 'view:finops', 'view:audit_log',
        'manage:rbac', 'manage:api_keys', 'view:logs', 'view:profile',
        'view:automation', 'manage:automation', 'view:devsecops', 'view:insights',
        'view:software_updates'
    ]
    
    print("\n[1/4] Updating Super Admin role...")
    result = db.roles.update_one(
        {"name": "Super Admin"},
        {"$set": {
            "id": "role-super-admin",
            "name": "Super Admin",
            "description": "Has all permissions across all tenants.",
            "permissions": all_permissions,
            "isEditable": False,
            "tenantId": "platform"
        }},
        upsert=True
    )
    if result.upserted_id:
        print("   ✅ Super Admin role created")
    else:
        print("   ✅ Super Admin role updated")
    
    print("\n[2/4] Creating/Updating Tenant Admin role...")
    result = db.roles.update_one(
        {"name": "Tenant Admin"},
        {"$set": {
            "id": "role-tenant-admin",
            "name": "Tenant Admin",
            "description": "Administrator for a specific tenant with full permissions except cross-tenant management.",
            "permissions": tenant_admin_permissions,
            "isEditable": False,
            "tenantId": "all"  # Can be used by any tenant
        }},
        upsert=True
    )
    if result.upserted_id:
        print("   ✅ Tenant Admin role created")
    else:
        print("   ✅ Tenant Admin role updated")
    
    print("\n[3/4] Checking for existing users...")
    users = list(db.users.find({}, {'_id': 0, 'email': 1, 'name': 1, 'role': 1, 'tenantId': 1}))
    
    if len(users) == 0:
        print("   ⚠️  No users found in database")
        print("   ℹ️  The backend startup will create a default super@omni.ai user")
    else:
        print(f"   Found {len(users)} user(s):")
        for user in users:
            print(f"      - {user.get('email')} ({user.get('role')}) - Tenant: {user.get('tenantId')}")
            
            # Verify role exists for this user
            role_name = user.get('role')
            role = db.roles.find_one({'name': role_name}, {'_id': 0})
            if role:
                perms = role.get('permissions', [])
                has_view_agents = 'view:agents' in perms
                has_remediate = 'remediate:agents' in perms
                print(f"        Role permissions: {len(perms)} total")
                print(f"        Can view agents: {'✅' if has_view_agents else '❌'}")
                print(f"        Can remediate agents: {'✅' if has_remediate else '❌'}")
            else:
                print(f"        ⚠️  WARNING: Role '{role_name}' not found in database!")
    
    print("\n[4/4] Verifying roles in database...")
    roles = list(db.roles.find({}, {'_id': 0, 'name': 1, 'permissions': 1}))
    print(f"   Found {len(roles)} role(s):")
    for role in roles:
        perms = role.get('permissions', [])
        has_view_agents = 'view:agents' in perms
        has_remediate = 'remediate:agents' in perms
        print(f"      - {role.get('name')}: {len(perms)} permissions")
        print(f"        'view:agents': {'✅' if has_view_agents else '❌'}")
        print(f"        'remediate:agents': {'✅' if has_remediate else '❌'}")
    
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"✅ Roles created/updated: {len(roles)}")
    print(f"✅ Users in database: {len(users)}")
    print("\nℹ️  Next Steps:")
    print("   1. Restart the backend to ensure seeding runs")
    print("   2. Login to the frontend at http://localhost:3000")
    print("   3. Navigate to Agents dashboard")
    print("   4. Agent installation commands should now be visible")
    print("=" * 70)
    
    client.close()

if __name__ == "__main__":
    fix_agent_permissions()

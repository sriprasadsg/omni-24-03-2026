
import sys
import os
sys.path.append(os.path.join(os.getcwd(), 'backend'))
import asyncio
from backend.auth_types import TokenData
from backend.rbac_service import rbac_service

# Mock TokenData
class MockUser(TokenData):
    def __init__(self, role, tenant_id):
        self.username = "test"
        self.email = "test@omni.ai"
        self.role = role
        self.user_id = "123"
        self.tenant_id = tenant_id

async def test_permissions():
    print("Testing RBAC Service Logic...")
    
    # Test Case 1: 'superadmin' (lowercase)
    user = MockUser(role="superadmin", tenant_id="platform-admin")
    perms = await rbac_service.get_user_permissions(user)
    print(f"Role 'superadmin' permissions: {perms}")
    
    if "*" in perms:
        print("✅ PASS: 'superadmin' has wildcard permission")
    else:
        print("❌ FAIL: 'superadmin' missing wildcard permission")

    # Test Case 2: 'Super Admin' (Title Case)
    user2 = MockUser(role="Super Admin", tenant_id="platform-admin")
    perms2 = await rbac_service.get_user_permissions(user2)
    print(f"Role 'Super Admin' permissions: {perms2}")

    if "*" in perms2:
        print("✅ PASS: 'Super Admin' has wildcard permission")
    else:
        print("❌ FAIL: 'Super Admin' missing wildcard permission")

if __name__ == "__main__":
    try:
        if asyncio.get_event_loop().is_closed():
            asyncio.run(test_permissions())
        else:
            loop = asyncio.get_event_loop()
            loop.run_until_complete(test_permissions())
    except RuntimeError:
         asyncio.run(test_permissions())

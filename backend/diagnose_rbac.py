import asyncio
from rbac_service import rbac_service
from auth_types import TokenData
from database import connect_to_mongo

async def diagnose_rbac():
    await connect_to_mongo()
    
    # Simulate a TokenData for Tenant Admin
    token_ta = TokenData(username="test_user", role="Tenant Admin", tenant_id="tenant_1234")
    
    # Call get_user_permissions
    perms_ta = await rbac_service.get_user_permissions(token_ta)
    
    print(f"Tenant Admin Permissions ({len(perms_ta)}):")
    print("Has view:sbom:", "view:sbom" in perms_ta)
    print("Has manage:sbom:", "manage:sbom" in perms_ta)
    
    # Simulate a TokenData for user
    token_u = TokenData(username="test_user", role="user", tenant_id="tenant_1234")
    perms_u = await rbac_service.get_user_permissions(token_u)
    print(f"User Permissions ({len(perms_u)}):")
    print("Has view:sbom:", "view:sbom" in perms_u)

asyncio.run(diagnose_rbac())

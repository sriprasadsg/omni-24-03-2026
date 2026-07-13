import os
from typing import List, Optional
from fastapi import Request, Depends
from database import mongodb
from authentication_service import get_current_user
from rbac_utils import require_permission
from backend.graphql.types import ComplianceControl, Evidence, Risk
from auth_types import TokenData

async def get_compliance_controls(info) -> List:
    """Resolver for compliance controls with tenant isolation and RBAC."""
    request: Request = info.context.get("request")
    if not request:
        return []

    # Get current user via dependency
    current_user = await get_current_user(request)
    if not current_user:
        return []

    tenant_id = getattr(current_user, "tenant_id", None)
    if not tenant_id:
        return []

    # Check RBAC
    from rbac_utils import verify_permission
    if not await verify_permission(current_user, "view:compliance"):
        return []

    db = mongodb.db
    controls = await db.compliance_controls.find(
        {"tenantId": tenant_id},
        {"_id": 0}
    ).to_list(length=1000)

    return controls

async def get_evidence_items(info) -> List:
    """Resolver for evidence items with tenant isolation and RBAC."""
    request: Request = info.context.get("request")
    if not request:
        return []

    current_user = await get_current_user(request)
    if not current_user:
        return []

    tenant_id = getattr(current_user, "tenant_id", None)
    if not tenant_id:
        return []

    from rbac_utils import verify_permission
    if not await verify_permission(current_user, "view:compliance"):
        return []

    db = mongodb.db
    evidence = await db.evidence.find(
        {"tenantId": tenant_id},
        {"_id": 0}
    ).to_list(length=1000)

    return evidence

async def get_risks(info) -> List:
    """Resolver for risks with tenant isolation and RBAC."""
    request: Request = info.context.get("request")
    if not request:
        return []

    current_user = await get_current_user(request)
    if not current_user:
        return []

    tenant_id = getattr(current_user, "tenant_id", None)
    if not tenant_id:
        return []

    from rbac_utils import verify_permission
    if not await verify_permission(current_user, "view:risk"):
        return []

    db = mongodb.db
    risks = await db.risks.find(
        {"tenantId": tenant_id},
        {"_id": 0}
    ).to_list(length=1000)

    return risks

async def get_users(info) -> List:
    """Resolver for users with tenant isolation and RBAC."""
    request: Request = info.context.get("request")
    if not request:
        return []

    current_user = await get_current_user(request)
    if not current_user:
        return []

    tenant_id = getattr(current_user, "tenant_id", None)
    if not tenant_id:
        return []

    from rbac_utils import verify_permission
    if not await verify_permission(current_user, "manage:users"): # Assuming 'manage:users' for listing users
        return []

    db = mongodb.db
    users = await db.users.find(
        {"tenantId": tenant_id},
        {"_id": 0}
    ).to_list(length=1000)
    return users

async def get_tenants(info) -> List:
    """Resolver for tenants with super admin access."""
    request: Request = info.context.get("request")
    if not request:
        return []

    current_user = await get_current_user(request)
    if not current_user:
        return []

    from rbac_utils import is_super_admin
    if not is_super_admin(getattr(current_user, "role", "")):
        raise HTTPException(status_code=403, detail="Super Admin access required")

    db = mongodb.db
    tenants = await db.tenants.find({}, {"_id": 0}).to_list(length=1000)
    return tenants
"""GraphQL resolvers — every resolver enforces the same tenant-isolation and
RBAC checks as the REST endpoints, so the GraphQL surface cannot become an
auth bypass (Phase 35 goal).

The authenticated user is resolved ONCE in CustomGraphQLRouter.get_context
(from the Authorization bearer header) and read here from info.context —
resolvers never re-parse credentials themselves.
"""
from typing import Any, Dict, List, Optional

from database import mongodb
from rbac_utils import verify_permission, is_super_admin
from graphql_api.types import ComplianceControl, Evidence, Risk, User, Tenant


def _ctx_user(info):
    return info.context.get("current_user")


def _tenant_of(user) -> Optional[str]:
    return getattr(user, "tenant_id", None)


async def _authorized_tenant(info, permission: str) -> Optional[str]:
    """Return the caller's tenant id iff authenticated and permitted."""
    user = _ctx_user(info)
    if not user:
        return None
    tenant_id = _tenant_of(user)
    if not tenant_id:
        return None
    if not await verify_permission(user, permission):
        return None
    return tenant_id


async def get_compliance_controls(info) -> List[ComplianceControl]:
    tenant_id = await _authorized_tenant(info, "view:compliance")
    if not tenant_id:
        return []

    docs = await mongodb.db.compliance_controls.find(
        {"tenantId": tenant_id}, {"_id": 0}
    ).to_list(length=1000)
    return [
        ComplianceControl(
            id=d.get("id", ""),
            framework=d.get("framework", ""),
            control_id=d.get("controlId", d.get("control_id", "")),
            title=d.get("title", d.get("name", "")),
            description=d.get("description"),
            status=d.get("status", "unknown"),
            risk_score=d.get("risk_score"),
            owner_id=d.get("owner_id"),
            viewer_user_ids=d.get("viewer_user_ids"),
        )
        for d in docs
    ]


async def get_evidence_items(info) -> List[Evidence]:
    tenant_id = await _authorized_tenant(info, "view:compliance")
    if not tenant_id:
        return []

    docs = await mongodb.db.evidence.find(
        {"tenantId": tenant_id}, {"_id": 0}
    ).to_list(length=1000)
    return [
        Evidence(
            id=d.get("id", ""),
            title=d.get("title", d.get("filename", "")),
            description=d.get("description"),
            file_type=d.get("file_type", d.get("fileType", "unknown")),
            url=d.get("url"),
            uploaded_at=str(d.get("uploaded_at", d.get("uploadedAt", ""))),
            status=d.get("status", "unknown"),
        )
        for d in docs
    ]


async def get_risks(info) -> List[Risk]:
    tenant_id = await _authorized_tenant(info, "view:risk")
    if not tenant_id:
        return []

    docs = await mongodb.db.risks.find(
        {"tenantId": tenant_id}, {"_id": 0}
    ).to_list(length=1000)
    return [
        Risk(
            id=d.get("id", ""),
            title=d.get("title", ""),
            description=d.get("description", ""),
            category=d.get("category", "general"),
            status=d.get("status", "Open"),
            likelihood=int(d.get("likelihood") or 0),
            impact=int(d.get("impact") or 0),
            risk_score=int(d.get("risk_score") or 0),
        )
        for d in docs
    ]


async def get_users(info) -> List[User]:
    tenant_id = await _authorized_tenant(info, "manage:users")
    if not tenant_id:
        return []

    docs = await mongodb.db.users.find(
        {"tenantId": tenant_id}, {"_id": 0, "password": 0, "hashed_password": 0}
    ).to_list(length=1000)
    return [
        User(
            id=d.get("id", ""),
            username=d.get("username", ""),
            email=d.get("email", d.get("username", "")),
            role=d.get("role", ""),
            tenant_id=d.get("tenantId", ""),
            created_at=str(d.get("created_at")) if d.get("created_at") else None,
            updated_at=str(d.get("updated_at")) if d.get("updated_at") else None,
        )
        for d in docs
    ]


async def get_tenants(info) -> List[Tenant]:
    """Super-admin only; non-admins get an empty list rather than a leak."""
    user = _ctx_user(info)
    if not user or not is_super_admin(getattr(user, "role", "")):
        return []

    docs = await mongodb.db.tenants.find({}, {"_id": 0}).to_list(length=1000)
    return [
        Tenant(
            id=d.get("id", ""),
            name=d.get("name", ""),
            subscription_tier=d.get("subscription_tier", d.get("tier", "standard")),
            enabled_features=d.get("enabled_features", []),
        )
        for d in docs
    ]

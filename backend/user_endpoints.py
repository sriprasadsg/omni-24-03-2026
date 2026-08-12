import logging
import re
from datetime import timezone
from fastapi import APIRouter, HTTPException, Depends, Query, Response
from typing import List, Optional
from pydantic import BaseModel
from database import get_database
from authentication_service import get_current_user
from auth_utils import hash_password as get_password_hash, validate_password_complexity
from rbac_utils import is_super_admin
from itam_asset_endpoints import _require_itam_admin
from rbac_service import rbac_service
from auth_types import TokenData
from tenant_context import get_tenant_id
import datetime
from pymongo.errors import DuplicateKeyError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/users", tags=["User Management"])

# --- Role helpers ------------------------------------------------------------
# Reuse rbac_service's canonical normalizer so Title-Case names surfaced by the
# /api/roles UI stub ("Admin", "User", "Viewer") compare equal to their
# rbac_service.default_roles counterparts ("admin"/"user"/"viewer") — ITAM-USR-01
# item 2: role must validate against rbac_service.default_roles keys.
_normalize_role = rbac_service._normalize_role
_VALID_ROLE_KEYS = {_normalize_role(k) for k in rbac_service.default_roles.keys()}
# The only role tier a non-super-admin caller may never assign.
_ELEVATED_ROLE_KEYS = {"super_admin"}

# --- Status (lifecycle) helpers ----------------------------------------------
# Stored canonically as Title-Case ("Active"/"Inactive"/"Pending") because
# authentication_endpoints.py's /api/auth/signup already writes "status":
# "Active" on every new user and its /refresh-token path gates on
# `user.get("status") != "Active"` — storing a lowercase value here would
# silently break refresh tokens for any user created/edited via this router.
_STATUS_VALUES = {"active", "inactive", "pending"}


def _normalize_status(raw: Optional[str]) -> str:
    s = (raw or "active").strip().lower()
    if s not in _STATUS_VALUES:
        raise HTTPException(status_code=400, detail=f"Invalid status '{raw}'. Must be one of: active, inactive, pending")
    return s.capitalize()


def _display_status(doc: dict) -> str:
    """Map the stored lifecycle status onto the two-value contract
    ('Active' | 'Disabled') that services/apiService.ts and
    SettingsUsersTab.tsx already depend on. Falls back to the legacy
    is_active boolean for docs written before the status field existed."""
    raw = doc.get("status")
    if raw:
        return "Active" if raw == "Active" else "Disabled"
    return "Active" if doc.get("is_active", True) else "Disabled"


async def _tenant_exists(db, tenant_id: str) -> bool:
    return await db.tenants.find_one({"id": tenant_id}) is not None


async def _audit(db, action: str, actor: str, target: str, tenant_id: str):
    try:
        await db.audit_logs.insert_one({
            "action": action,
            "actor": actor,
            "target": target,
            "tenant_id": tenant_id,
            "timestamp": datetime.datetime.now(timezone.utc).isoformat(),
        })
    except Exception as e:
        logger.error("Audit log write failed: %s", e)


def _to_response(u: dict) -> dict:
    full_name = u.get("full_name", u.get("name", u.get("email", "User")))
    created = u.get("createdAt") or u.get("created_at") or ""
    return {
        "id": str(u.get("_id", "")),
        "email": u.get("email", ""),
        "name": full_name,
        "role": u.get("role", "user"),
        "status": _display_status(u),
        "avatar": u.get("avatar", f"https://ui-avatars.com/api/?name={full_name}&background=random"),
        "tenantId": u.get("tenantId"),
        "createdAt": created,
        "updatedAt": u.get("updatedAt") or created,
        "lastLogin": u.get("lastLogin") or u.get("last_login"),
    }


class UserCreate(BaseModel):
    email: str
    password: str
    full_name: str
    role: str = "user"
    tenantId: str
    status: Optional[str] = "active"

class UserUpdate(BaseModel):
    full_name: Optional[str] = None
    role: Optional[str] = None
    password: Optional[str] = None
    status: Optional[str] = None
    tenantId: Optional[str] = None

class UserResponse(BaseModel):
    id: str
    email: str
    name: str  # Frontend expects "name" instead of "full_name"
    role: str
    status: str  # Frontend expects "status" ('Active' | 'Disabled') instead of "is_active" boolean
    avatar: str
    tenantId: str
    createdAt: str
    updatedAt: str
    lastLogin: Optional[str] = None


@router.get("/me", response_model=UserResponse)
async def get_my_profile(current_user: TokenData = Depends(get_current_user)):
    """
    Return the caller's own profile. Unlike the rest of this router, this
    endpoint is intentionally not admin-gated — every authenticated user may
    read their own record.
    """
    db = get_database()
    user_doc = await db.users.find_one(
        {"$or": [{"email": current_user.username}, {"username": current_user.username}]},
        {"password": 0, "hashed_password": 0},
    )
    if not user_doc:
        raise HTTPException(status_code=404, detail="User not found")
    return _to_response(user_doc)


@router.get("", response_model=List[UserResponse])
async def list_users(
    response: Response,
    skip: int = 0,
    limit: int = 100,
    role: Optional[str] = None,
    status_filter: Optional[str] = Query(None, alias="status"),
    tenantId: Optional[str] = None,
    search: Optional[str] = None,
    current_user: TokenData = Depends(_require_itam_admin),
):
    """
    List users with pagination and filtering. Super Admins may list/filter
    across tenants; everyone else is always confined to their own tenant
    regardless of any tenantId they pass.

    The default (no query params) response stays a bare JSON array — matching
    what it returned before pagination existed — because
    services/apiService.ts fetchUsers() assigns the body straight into an
    array-typed cache. Total match count (post-filter, pre-pagination) is
    exposed via the X-Total-Count header instead of wrapping the body.
    """
    db = get_database()
    caller_is_super_admin = is_super_admin(current_user.role)

    query: dict = {}
    if caller_is_super_admin:
        if tenantId:
            query["tenantId"] = tenantId
    else:
        query["tenantId"] = get_tenant_id()

    if role:
        query["role"] = role
    if status_filter:
        query["status"] = _normalize_status(status_filter)
    if search:
        pattern = re.escape(search)
        query["$or"] = [
            {"email": {"$regex": pattern, "$options": "i"}},
            {"full_name": {"$regex": pattern, "$options": "i"}},
        ]

    total = await db.users.count_documents(query)
    users = await db.users.find(query, {"password": 0, "hashed_password": 0}) \
        .skip(skip).limit(limit).to_list(length=limit or None)

    response.headers["X-Total-Count"] = str(total)
    return [_to_response(u) for u in users]

@router.post("", response_model=UserResponse, status_code=201)
async def create_user(user: UserCreate, current_user: TokenData = Depends(_require_itam_admin)):
    """
    Create a new user.
    """
    caller_role = current_user.role
    caller_is_super_admin = is_super_admin(caller_role)

    requested_role_key = _normalize_role(user.role)
    if requested_role_key not in _VALID_ROLE_KEYS:
        raise HTTPException(status_code=400, detail=f"Invalid role '{user.role}'")
    # Prevent privilege escalation: non-super-admins cannot assign elevated roles
    if requested_role_key in _ELEVATED_ROLE_KEYS and not caller_is_super_admin:
        raise HTTPException(status_code=403, detail=f"Not authorized to assign role '{user.role}'")

    db = get_database()

    # If Super Admin passes a tenantId, use it; otherwise use requester's context
    if caller_is_super_admin and user.tenantId:
        target_tenant_id = user.tenantId
    else:
        target_tenant_id = get_tenant_id()

    if not target_tenant_id or not await _tenant_exists(db, target_tenant_id):
        raise HTTPException(status_code=400, detail=f"Tenant '{target_tenant_id}' does not exist")

    # Check existing
    existing = await db.users.find_one({"email": user.email, "tenantId": target_tenant_id})
    if existing:
        raise HTTPException(status_code=400, detail="User already exists")

    pwd_error = validate_password_complexity(user.password)
    if pwd_error:
        raise HTTPException(status_code=400, detail=pwd_error)

    now = datetime.datetime.now(timezone.utc).isoformat()
    new_user = {
        "email": user.email,
        "hashed_password": get_password_hash(user.password),
        "full_name": user.full_name,
        "role": user.role,
        "tenantId": target_tenant_id,
        "status": _normalize_status(user.status),
        "createdAt": now,
        "updatedAt": now,
    }

    try:
        result = await db.users.insert_one(new_user)
    except DuplicateKeyError:
        raise HTTPException(status_code=400, detail="A user with this email already exists.")

    new_user["_id"] = result.inserted_id
    await _audit(db, "user.created", getattr(current_user, "username", "unknown"),
                 user.email, target_tenant_id)
    return _to_response(new_user)

@router.put("/{user_id}", response_model=UserResponse)
async def update_user(user_id: str, updates: UserUpdate, current_user: TokenData = Depends(_require_itam_admin)):
    """
    Update an existing user.
    """
    db = get_database()
    caller_is_super_admin = is_super_admin(current_user.role)

    try:
        from bson import ObjectId
        obj_id = ObjectId(user_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid user ID")

    # Find the user to update
    target_user = await db.users.find_one({"_id": obj_id}, {"password": 0, "hashed_password": 0})
    if not target_user:
        raise HTTPException(status_code=404, detail="User not found")

    # Access control: Tenant Admins can only update users in their own tenant
    if not caller_is_super_admin:
        tenant_id = get_tenant_id()
        if target_user.get("tenantId") != tenant_id:
            raise HTTPException(status_code=403, detail="Not authorized to update users in other tenants")

    # Prepare update data
    update_data = {}
    if updates.full_name is not None:
        update_data["full_name"] = updates.full_name
    if updates.role is not None:
        requested_role_key = _normalize_role(updates.role)
        if requested_role_key not in _VALID_ROLE_KEYS:
            raise HTTPException(status_code=400, detail=f"Invalid role '{updates.role}'")
        if requested_role_key in _ELEVATED_ROLE_KEYS and not caller_is_super_admin:
            raise HTTPException(status_code=403, detail=f"Not authorized to assign role '{updates.role}'")
        update_data["role"] = updates.role
    if updates.password is not None:
        # ITAM-USR-03 Pitfall 4 / T-64-12: local password changes are
        # blocked for LDAP-sourced users — LDAP is the source of truth for
        # their credentials.
        # ITAM-USR-04 Pitfall 4 / T-64-17: same block for SAML-sourced users —
        # the IdP is the source of truth for their credentials, not this API.
        target_source = target_user.get("source")
        if target_source in ("ldap", "saml"):
            raise HTTPException(
                status_code=403,
                detail=f"Password changes for {target_source.upper()}-sourced users must be made "
                        f"in the {'directory' if target_source == 'ldap' else 'identity provider'}, not via this API",
            )
        update_data["hashed_password"] = get_password_hash(updates.password)
    if updates.status is not None:
        update_data["status"] = _normalize_status(updates.status)
    if updates.tenantId is not None:
        if not caller_is_super_admin:
            raise HTTPException(status_code=403, detail="Not authorized to move users between tenants")
        if not await _tenant_exists(db, updates.tenantId):
            raise HTTPException(status_code=400, detail=f"Tenant '{updates.tenantId}' does not exist")
        update_data["tenantId"] = updates.tenantId

    if not update_data:
        # Just return the current user if no updates provided
        return _to_response(target_user)

    update_data["updatedAt"] = datetime.datetime.now(timezone.utc).isoformat()
    await db.users.update_one({"_id": obj_id}, {"$set": update_data})
    await _audit(db, "user.updated", getattr(current_user, "username", "unknown"),
                 target_user.get("email", user_id), target_user.get("tenantId", ""))
    # Reload and return
    updated_user = await db.users.find_one({"_id": obj_id}, {"password": 0, "hashed_password": 0})
    return _to_response(updated_user)

@router.delete("/{user_id}")
async def delete_user(user_id: str, current_user: TokenData = Depends(_require_itam_admin)):
    """
    Delete a user.
    """
    db = get_database()
    caller_is_super_admin = is_super_admin(current_user.role)

    try:
        from bson import ObjectId
        obj_id = ObjectId(user_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid user ID")

    # Find the user
    target_user = await db.users.find_one({"_id": obj_id}, {"password": 0, "hashed_password": 0})
    if not target_user:
        raise HTTPException(status_code=404, detail="User not found")

    # Access control
    if not caller_is_super_admin:
        tenant_id = get_tenant_id()
        if target_user.get("tenantId") != tenant_id:
            raise HTTPException(status_code=403, detail="Not authorized to delete users in other tenants")

    # Cannot delete yourself
    if getattr(current_user, "username", "") == target_user.get("email"):
        raise HTTPException(status_code=400, detail="Cannot delete your own account")

    await db.users.delete_one({"_id": obj_id})
    await _audit(db, "user.deleted", getattr(current_user, "username", "unknown"),
                 target_user.get("email", user_id), target_user.get("tenantId", ""))
    return {"message": "User deleted successfully"}

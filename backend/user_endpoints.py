from fastapi import APIRouter, HTTPException, Depends, status
from typing import List, Optional
from pydantic import BaseModel
from database import get_database
from authentication_service import get_current_user
from auth_utils import hash_password as get_password_hash
from tenant_context import get_tenant_id
import datetime
import uuid
from pymongo.errors import DuplicateKeyError

router = APIRouter(prefix="/api/users", tags=["User Management"])

class UserCreate(BaseModel):
    email: str
    password: str
    full_name: str
    role: str = "user"
    tenantId: Optional[str] = None

class UserUpdate(BaseModel):
    full_name: Optional[str] = None
    role: Optional[str] = None
    password: Optional[str] = None

class UserResponse(BaseModel):
    id: str
    email: str
    name: str  # Frontend expects "name" instead of "full_name"
    role: str
    status: str  # Frontend expects "status" ('Active' | 'Disabled') instead of "is_active" boolean
    avatar: str  # Frontend expects "avatar"
    tenantId: str
    created_at: str

@router.get("", response_model=List[UserResponse])
async def list_users(current_user: dict = Depends(get_current_user)):
    """
    List all users. Super Admins see all users, others see only their tenant users.
    """
    db = get_database()
    
    role = getattr(current_user, "role", None)
    is_super_admin = role in ["super_admin", "superadmin", "Super Admin"]
    
    if is_super_admin:
        # Super Admin sees everything
        users = await db.users.find({}).to_list(length=1000)
    else:
        # Regular users only see their own tenant
        tenant_id = get_tenant_id()
        users = await db.users.find({"tenantId": tenant_id}).to_list(length=100)
    
    return [
        {
            "id": str(u.get("_id", "")),
            "email": u.get("email", ""),
            "name": u.get("full_name", u.get("name", u.get("email", "User"))),
            "role": u.get("role", "user"),
            "status": "Active" if u.get("is_active", True) or u.get("status") == "Active" else "Disabled",
            "avatar": u.get("avatar", f"https://ui-avatars.com/api/?name={u.get('full_name', u.get('name', 'User'))}&background=random"),
            "tenantId": u.get("tenantId", "platform-admin"), # Default to platform if missing
            "created_at": u.get("created_at", u.get("createdAt", ""))
        }
        for u in users
    ]

@router.post("", response_model=UserResponse)
async def create_user(user: UserCreate, current_user: dict = Depends(get_current_user)):
    """
    Create a new user.
    """
    if getattr(current_user, "role", None) not in ["admin", "super_admin", "Super Admin"]:
        raise HTTPException(status_code=403, detail="Not authorized to create users")
        
    db = get_database()
    
    # If Super Admin passes a tenantId, use it; otherwise use requester's context
    if getattr(current_user, "role", None) in ["super_admin", "Super Admin"] and user.tenantId:
        target_tenant_id = user.tenantId
    else:
        target_tenant_id = get_tenant_id()
    
    # Check existing
    existing = await db.users.find_one({"email": user.email, "tenantId": target_tenant_id})
    if existing:
        raise HTTPException(status_code=400, detail="User already exists")
    
    new_user = {
        "email": user.email,
        "hashed_password": get_password_hash(user.password),
        "full_name": user.full_name,
        "role": user.role,
        "tenantId": target_tenant_id,
        "is_active": True,
        "created_at": datetime.datetime.utcnow().isoformat()
    }
    
    try:
        result = await db.users.insert_one(new_user)
        new_user["id"] = str(result.inserted_id)
        
        return {
            "id": new_user["id"],
            "email": new_user["email"],
            "name": new_user["full_name"],
            "role": new_user["role"],
            "status": "Active" if new_user["is_active"] else "Disabled",
            "avatar": f"https://ui-avatars.com/api/?name={new_user['full_name']}&background=random",
            "tenantId": new_user["tenantId"],
            "created_at": new_user["created_at"]
        }
    except DuplicateKeyError:
        raise HTTPException(status_code=400, detail="A user with this email already exists.")
@router.put("/{user_id}", response_model=UserResponse)
async def update_user(user_id: str, updates: UserUpdate, current_user: dict = Depends(get_current_user)):
    """
    Update an existing user.
    """
    db = get_database()
    current_role = getattr(current_user, "role", None)
    is_super_admin = current_role in ["super_admin", "superadmin", "Super Admin"]
    
    if current_role not in ["admin", "super_admin", "Super Admin", "Tenant Admin"]:
        raise HTTPException(status_code=403, detail="Not authorized to update users")

    try:
        from bson import ObjectId
        obj_id = ObjectId(user_id)
    except:
        raise HTTPException(status_code=400, detail="Invalid user ID")

    # Find the user to update
    target_user = await db.users.find_one({"_id": obj_id})
    if not target_user:
        raise HTTPException(status_code=404, detail="User not found")

    # Access control: Tenant Admins can only update users in their own tenant
    if not is_super_admin:
        tenant_id = get_tenant_id()
        if target_user.get("tenantId") != tenant_id:
            raise HTTPException(status_code=403, detail="Not authorized to update users in other tenants")

    # Prepare update data
    update_data = {}
    if updates.full_name is not None:
        update_data["full_name"] = updates.full_name
    if updates.role is not None:
        # Only Super Admins can assign Super Admin role
        if updates.role in ["super_admin", "superadmin", "Super Admin"] and not is_super_admin:
            raise HTTPException(status_code=403, detail="Not authorized to assign Super Admin role")
        update_data["role"] = updates.role
    if updates.password is not None:
        update_data["hashed_password"] = get_password_hash(updates.password)

    if not update_data:
        # Just return the current user if no updates provided
        target_user["id"] = user_id
        return {
            "id": user_id,
            "email": target_user["email"],
            "name": target_user.get("full_name", target_user.get("name", "")),
            "role": target_user.get("role", "user"),
            "status": "Active" if target_user.get("is_active", True) else "Disabled",
            "avatar": target_user.get("avatar", f"https://ui-avatars.com/api/?name={target_user.get('full_name', 'User')}&background=random"),
            "tenantId": target_user.get("tenantId", "platform-admin"),
            "created_at": target_user.get("created_at", "")
        }

    await db.users.update_one({"_id": obj_id}, {"$set": update_data})
    
    # Reload and return
    updated_user = await db.users.find_one({"_id": obj_id})
    updated_user["id"] = user_id
    return {
        "id": user_id,
        "email": updated_user["email"],
        "name": updated_user.get("full_name", updated_user.get("name", "")),
        "role": updated_user.get("role", "user"),
        "status": "Active" if updated_user.get("is_active", True) or updated_user.get("status") == "Active" else "Disabled",
        "avatar": updated_user.get("avatar", f"https://ui-avatars.com/api/?name={updated_user.get('full_name', 'User')}&background=random"),
        "tenantId": updated_user.get("tenantId", "platform-admin"),
        "created_at": updated_user.get("created_at", "")
    }

@router.delete("/{user_id}")
async def delete_user(user_id: str, current_user: dict = Depends(get_current_user)):
    """
    Delete a user.
    """
    db = get_database()
    current_role = getattr(current_user, "role", None)
    is_super_admin = current_role in ["super_admin", "superadmin", "Super Admin"]

    if current_role not in ["admin", "super_admin", "Super Admin", "Tenant Admin"]:
        raise HTTPException(status_code=403, detail="Not authorized to delete users")

    try:
        from bson import ObjectId
        obj_id = ObjectId(user_id)
    except:
        raise HTTPException(status_code=400, detail="Invalid user ID")

    # Find the user
    target_user = await db.users.find_one({"_id": obj_id})
    if not target_user:
        raise HTTPException(status_code=404, detail="User not found")

    # Access control
    if not is_super_admin:
        tenant_id = get_tenant_id()
        if target_user.get("tenantId") != tenant_id:
            raise HTTPException(status_code=403, detail="Not authorized to delete users in other tenants")

    # Cannot delete yourself
    if str(getattr(current_user, "id", "")) == user_id or getattr(current_user, "username", "") == target_user.get("email"):
         raise HTTPException(status_code=400, detail="Cannot delete your own account")

    await db.users.delete_one({"_id": obj_id})
    return {"message": "User deleted successfully"}

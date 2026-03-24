from typing import Any, List, Dict, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Body
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from authentication_service import create_access_token, create_refresh_token, get_current_user, Token, ACCESS_TOKEN_EXPIRE_MINUTES
from database import get_database
from models import User
from auth_utils import verify_password, hash_password
from pydantic import BaseModel
from datetime import timedelta, timezone
import uuid
import datetime

class LoginRequest(BaseModel):
    username: str | None = None
    email: str | None = None
    password: str
    
    def get_identifier(self):
        """Get the username or email field"""
        return self.email or self.username

router = APIRouter(
    prefix="/api/auth",
    tags=["Authentication"]
)

@router.post("/login")
async def login_for_access_token(login_request: LoginRequest):
    db = get_database()
    identifier = login_request.get_identifier()
    print(f"[DEBUG] Login attempt for identifier: {identifier}")
    
    # Check username OR email
    # Bypass tenant isolation for initial auth lookup since tenant might not be known yet
    user = await db._db.users.find_one({
        "$or": [
            {"username": identifier},
            {"email": identifier}
        ]
    })
    
    # 1. Check if user exists
    if not user:
        print(f"[DEBUG] User NOT found for identifier: {identifier}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"DEBUG: User not found for {identifier}",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # 2. Verify Password 
    if not verify_password(login_request.password, user['password']):
        print(f"[DEBUG] Password verification FAILED for user: {identifier}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"DEBUG: Password verification FAILED for {identifier}",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # 3. If MFA is enabled — return short-lived session token instead of full JWT
    mfa = user.get("mfa", {})
    if mfa.get("enabled"):
        try:
            import mfa_service
            session_token = mfa_service.create_mfa_session(user["email"])
            print(f"[DEBUG] MFA required for {identifier} — issuing mfa_session_token")
            return {
                "access_token": "",
                "token_type": "mfa_required",
                "success": True,
                "mfa_required": True,
                "mfa_session_token": session_token,
                "user": {},
            }
        except ImportError:
            pass  # MFA service unavailable — fall through to direct login

    # 4. Create full JWT (MFA not enabled or MFA service unavailable)
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    role = user.get("role", "user")
    tenant_id = user.get("tenantId", "default")
    
    access_token = create_access_token(
        data={"sub": user["email"], "role": role, "tenant_id": tenant_id},
        expires_delta=access_token_expires
    )
    
    # Prepare user object for frontend (exclude sensitive fields)
    user_data = {k: v for k, v in user.items() if k not in ('password', '_id', 'mfa')}
    if 'id' not in user_data:
        user_data['id'] = str(user.get('_id', ''))
        
    # Add permissions from role
    role_obj = await db.roles.find_one({"name": role})
    if role_obj:
        user_data['permissions'] = role_obj.get('permissions', [])
    else:
        user_data['permissions'] = []

    return {
        "access_token": access_token, 
        "token_type": "bearer",
        "success": True,
        "user": user_data
    }

@router.get("/me")
async def read_users_me(current_user: dict = Depends(get_current_user)):
    """
    Get the current authenticated user's full profile including role permissions.
    
    Returns user data with permissions from their role attached.
    """
    db = get_database()
    
    # Fetch full user data from database bypassing tenant isolation since tenant context might not be fully established
    user = await db._db.users.find_one({"email": current_user.username})
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    # Get role permissions
    role_name = user.get("role", "user")
    role = await db.roles.find_one({"name": role_name})
    
    # Build user response object (exclude sensitive fields)
    user_data = {k: v for k, v in user.items() if k not in ('password', '_id', 'mfa')}
    if 'id' not in user_data:
        user_data['id'] = str(user.get('_id', ''))
    
    # Add permissions from role if found
    if role:
        user_data['permissions'] = role.get('permissions', [])
    else:
        user_data['permissions'] = []
    
    # Expose MFA enabled flag (not the secret)
    user_data['mfa_enabled'] = user.get('mfa', {}).get('enabled', False)
    
    print(f"[DEBUG] /me endpoint - User: {user_data.get('email')}, Role: {role_name}, Permissions: {user_data.get('permissions')}")
    
    return user_data

@router.post("/signup")
async def signup(data: dict[str, Any] = Body(...)):
    from auth_utils import hash_password
    import uuid
    from datetime import datetime, timezone
    from typing import Any
    company_name = data.get('companyName', '').strip()
    name = data.get('name', '').strip()
    email = data.get('email', '').strip().lower()
    password = data.get('password', '')
    if not all([company_name, name, email, password]):
        raise HTTPException(status_code=400, detail="All fields are required")
    db = get_database()
    existing_user = await db.users.find_one({"email": email})
    if existing_user:
        raise HTTPException(status_code=400, detail="Email already registered")
    tenant_id = f"tenant_{uuid.uuid4().hex[:12]}"
    registration_key = f"reg_{uuid.uuid4().hex[:16]}"
    
    # 3. Create Tenant & User
    # ALL enterprise features - matching TenantCreate in tenant_endpoints.py
    enterprise_features = [
        "view:dashboard", "view:cxo_dashboard", "view:profile", "view:insights", 
        "view:tracing", "view:logs", "view:network", "view:agents", "view:assets", 
        "view:patching", "view:security", "view:cloud_security", "view:threat_hunting", 
        "view:dspm", "view:attack_path", "view:sbom", "view:persistence", 
        "view:vulnerabilities", "view:devsecops", "view:dora_metrics", "view:service_catalog", 
        "view:chaos", "view:compliance", "view:ai_governance", "view:security_audit", 
        "view:audit_log", "view:reporting", "view:automation", "view:finops", 
        "view:developer_hub", "view:advanced_bi", "view:llmops", "view:unified_ops", 
        "view:swarm", "manage:settings" # No manage:tenants for regular tenant admin
    ]

    tenant_doc = {
        "id": tenant_id, 
        "name": company_name, 
        "subscriptionTier": "Enterprise",
        "registrationKey": registration_key, 
        "apiKeys": [], 
        "enabledFeatures": enterprise_features,
        "createdAt": datetime.now(timezone.utc).isoformat()
    }
    await db.tenants.insert_one(tenant_doc)
    
    # Standard full permissions for Tenant Admin - matching app.py seed_database
    enterprise_permissions = [
        'view:dashboard', 'view:reporting', 'export:reports', 
        'view:agents', 'view:software_deployment', 'view:agent_logs', 'remediate:agents',
        'view:assets', 'view:patching', 'manage:patches', 'view:security', 
        'manage:security_cases', 'investigate:security', 'view:compliance',
        'manage:compliance_evidence', 'view:ai_governance', 'manage:ai_risks',
        'view:cloud_security', 'view:finops', 'view:audit_log',
        'manage:rbac', 'manage:api_keys', 'view:logs', 'view:profile',
        'view:automation', 'manage:automation', 'view:devsecops', 'manage:devsecops',
        'view:sbom', 'manage:sbom', 'view:insights', 'view:software_updates',
        'view:threat_hunting', 'view:tracing', 'view:dspm', 'view:attack_path',
        'view:service_catalog', 'view:dora_metrics', 'view:chaos', 'view:network',
        'view:zero_trust', 'view:developer_hub', 'manage:security_playbooks',
        'view:cxo_dashboard', 'view:unified_ops', 'view:advanced_bi',
        'view:sustainability', 'view:web_monitoring', 'view:analytics', 
        'view:threat_intel', 'view:vulnerabilities', 'view:persistence',
        'view:security_audit', 'view:mlops', 'view:llmops', 'view:automl',
        'manage:experiments', 'view:xai', 'view:governance', 'manage:playbooks',
        'view:swarm'
    ]

    user_id = f"user_{uuid.uuid4().hex[:12]}"
    user_doc = {
        "id": user_id, 
        "email": email, 
        "password": hash_password(password),
        "name": name, 
        "role": "Tenant Admin", 
        "tenantId": tenant_id,
        "status": "Active", 
        "subscriptionTier": "Enterprise", 
        "maxAgents": 5, 
        "permissions": enterprise_permissions,
        "createdAt": datetime.now(timezone.utc).isoformat()
    }
    await db.users.insert_one(user_doc)
    
    # 4. Prepare return data (similar to login)
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    
    access_token = create_access_token(
        data={"sub": email, "role": "Tenant Admin", "tenant_id": tenant_id},
        expires_delta=access_token_expires
    )
    refresh_token = create_refresh_token(data={"sub": email})
    
    # Prepare user object for frontend (exclude sensitive fields)
    user_data = {k: v for k, v in user_doc.items() if k not in ('password', '_id', 'mfa')}
    if 'id' not in user_data:
        user_data['id'] = user_id
        
    return {
        "success": True, 
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "user": user_data,
        "tenant": {
            "id": tenant_id,
            "name": company_name,
            "subscriptionTier": "Enterprise",
            "maxAgents": 5,
            "enabledFeatures": enterprise_features
        }
    }

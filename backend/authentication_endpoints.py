from typing import Any
from fastapi import APIRouter, Depends, HTTPException, status, Body, Request
from authentication_service import create_access_token, create_refresh_token, get_current_user, ACCESS_TOKEN_EXPIRE_MINUTES, SECRET_KEY, ALGORITHM, oauth2_scheme
from database import get_database
from auth_utils import verify_password, hash_password
from rate_limiter import limiter
from pydantic import BaseModel, Field
from datetime import timedelta, timezone
import uuid
import datetime
import re
import jwt
import logging

logger = logging.getLogger(__name__)

_MAX_LOGIN_ATTEMPTS = 5
_LOCKOUT_MINUTES = 30
_ATTEMPT_WINDOW_MINUTES = 15


async def _check_login_lockout(db, identifier: str) -> None:
    """Raise 429 if the identifier is currently locked out."""
    record = await db._db.login_attempts.find_one({"identifier": identifier})
    if not record:
        return
    locked_until = record.get("locked_until")
    if not locked_until:
        return
    now = datetime.datetime.now(timezone.utc)
    locked_dt = datetime.datetime.fromisoformat(locked_until)
    if locked_dt.tzinfo is None:
        locked_dt = locked_dt.replace(tzinfo=timezone.utc)
    if now < locked_dt:
        retry_after = int((locked_dt - now).total_seconds())
        raise HTTPException(
            status_code=429,
            detail="Too many failed attempts — try again later",
            headers={"Retry-After": str(retry_after)},
        )


async def _record_login_failure(db, identifier: str) -> None:
    """Atomically increment failure counter; lock the account if threshold is reached."""
    now = datetime.datetime.now(timezone.utc)
    window_start = (now - timedelta(minutes=_ATTEMPT_WINDOW_MINUTES)).isoformat()
    # Atomic push + set — avoids TOCTOU race between concurrent requests
    await db._db.login_attempts.update_one(
        {"identifier": identifier},
        {"$push": {"attempts": now.isoformat()}, "$set": {"last_attempt": now.isoformat()}},
        upsert=True,
    )
    # Read back the (now-updated) record to evaluate lockout — single authoritative check
    record = await db._db.login_attempts.find_one({"identifier": identifier})
    if record:
        recent = [a for a in record.get("attempts", []) if a >= window_start]
        if len(recent) >= _MAX_LOGIN_ATTEMPTS:
            locked_until = (now + timedelta(minutes=_LOCKOUT_MINUTES)).isoformat()
            await db._db.login_attempts.update_one(
                {"identifier": identifier},
                {"$set": {"locked_until": locked_until}},
            )
            logger.warning("Login lockout triggered for identifier (redacted)")


async def _clear_login_failures(db, identifier: str) -> None:
    await db._db.login_attempts.delete_one({"identifier": identifier})


def _validate_password_complexity(password: str) -> str | None:
    """Return an error message if the password fails complexity requirements, else None."""
    if len(password) < 8:
        return "Password must be at least 8 characters"
    if not re.search(r"[A-Z]", password):
        return "Password must contain at least one uppercase letter"
    if not re.search(r"[a-z]", password):
        return "Password must contain at least one lowercase letter"
    if not re.search(r"\d", password):
        return "Password must contain at least one digit"
    if not re.search(r"[^A-Za-z0-9]", password):
        return "Password must contain at least one special character"
    return None

class LoginRequest(BaseModel):
    username: str | None = Field(None, max_length=254)
    email: str | None = Field(None, max_length=254)
    password: str = Field(..., max_length=1024)
    
    def get_identifier(self):
        """Get the username or email field"""
        return self.email or self.username

router = APIRouter(
    prefix="/api/auth",
    tags=["Authentication"]
)

async def _run_ueba_analysis(db, user_id: str, ip_address: str, user_agent: str) -> None:
    """Fire-and-forget UEBA behavioral analysis after successful login."""
    try:
        from ueba_service import analyze_login, LoginEvent
        event = LoginEvent(
            user_id=user_id,
            ip_address=ip_address,
            user_agent=user_agent,
            timestamp=datetime.datetime.now(timezone.utc).isoformat(),
            login_success=True,
        )
        await analyze_login(db, event)
        await db.login_events.update_one(
            {"user_id": user_id, "ip_address": ip_address},
            {"$setOnInsert": event.dict()},
            upsert=True,
        )
    except Exception:
        pass


@router.post("/login")
@limiter.limit("10/minute")
async def login_for_access_token(request: Request, login_request: LoginRequest):  # noqa: ARG001
    db = get_database()
    identifier = login_request.get_identifier()

    # Check username OR email
    # Bypass tenant isolation for initial auth lookup since tenant might not be known yet
    await _check_login_lockout(db, identifier)

    user = await db._db.users.find_one({
        "$or": [
            {"username": identifier},
            {"email": identifier}
        ]
    })

    # Validate credentials — use a single generic message to prevent user enumeration
    if not user or not verify_password(login_request.password, user['password']):
        await _record_login_failure(db, identifier)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    await _clear_login_failures(db, identifier)

    # 3. If MFA is enabled — return short-lived session token instead of full JWT
    mfa = user.get("mfa", {})
    if mfa.get("enabled"):
        try:
            import mfa_service
            session_token = mfa_service.create_mfa_session(user["email"])
            return {
                "access_token": "",
                "token_type": "mfa_required",
                "success": True,
                "mfa_required": True,
                "mfa_session_token": session_token,
                "user": {},
            }
        except ImportError:
            raise HTTPException(
                status_code=503,
                detail="MFA is required for this account but the MFA service is unavailable. Contact your administrator.",
            )

    # 4. Create full JWT (MFA not enabled or MFA service unavailable)
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    role = user.get("role", "user")
    tenant_id = user.get("tenantId", "default")
    
    token_payload = {"sub": user["email"], "role": role, "tenant_id": tenant_id}
    access_token = create_access_token(data=token_payload, expires_delta=access_token_expires)
    refresh_token = create_refresh_token(data={"sub": user["email"]})

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

    # UEBA behavioral analysis (non-blocking)
    import asyncio as _asyncio
    client_ip = request.client.host if request.client else "unknown"
    client_ua = request.headers.get("user-agent", "")
    _asyncio.create_task(_run_ueba_analysis(db._db, user["email"], client_ip, client_ua))

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
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
    user = await db.users.find_one({"email": current_user.username})
    
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
    
    return user_data

@router.post("/signup")
@limiter.limit("3/hour")
async def signup(request: Request, data: dict[str, Any] = Body(...)):
    from auth_utils import hash_password
    import uuid
    from datetime import datetime, timezone
    from typing import Any
    from tenant_context import set_tenant_id
    
    # Bypass tenant isolation for signup flow to check global existence and insert with correct tenantId
    set_tenant_id("platform-admin")
    
    company_name = data.get('companyName', '').strip()
    name = data.get('name', '').strip()
    email = data.get('email', '').strip().lower()
    password = data.get('password', '')
    if not all([company_name, name, email, password]):
        raise HTTPException(status_code=400, detail="All fields are required")
    complexity_error = _validate_password_complexity(password)
    if complexity_error:
        raise HTTPException(status_code=400, detail=complexity_error)
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

    # Seed GDPR/CCPA consent record for the new user
    await db.user_consents.insert_one({
        "user_id": user_id,
        "email": email,
        "tenantId": tenant_id,
        "status": "granted",
        "consent_type": "platform_terms",
        "granted_at": datetime.now(timezone.utc).isoformat(),
        "ip_address": None,
        "version": "1.0",
    })

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


@router.post("/refresh")
@limiter.limit("20/minute")
async def refresh_access_token(request: Request, data: dict[str, Any] = Body(...)):
    """Exchange a valid refresh token for a new access token and a rotated refresh token."""
    refresh_token = data.get("refresh_token", "")
    if not refresh_token:
        raise HTTPException(status_code=400, detail="Refresh token is required")

    try:
        payload = jwt.decode(refresh_token, SECRET_KEY, algorithms=[ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Refresh token has expired")
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid refresh token")

    if payload.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="Invalid token type")

    email = payload.get("sub")
    if not email:
        raise HTTPException(status_code=401, detail="Invalid refresh token")

    jti = payload.get("jti")
    db = get_database()

    # Check if this refresh token's jti has been revoked (e.g. after logout)
    if jti:
        revoked = await db._db.revoked_tokens.find_one({"jti": jti}, {"_id": 1})
        if revoked:
            raise HTTPException(status_code=401, detail="Could not validate credentials")

    # Enforce account lockout — prevent refresh even if the token is technically valid
    await _check_login_lockout(db, email)

    # Refresh token only contains email (no tenant_id), so bypass isolation for lookup
    user = await db._db.users.find_one({"email": email})
    if not user or user.get("status") != "Active":
        raise HTTPException(status_code=401, detail="Could not validate credentials")

    # Rotate: revoke the consumed refresh token immediately so it cannot be reused
    if jti:
        await db._db.revoked_tokens.insert_one({
            "jti": jti,
            "type": "refresh",
            "revoked_at": datetime.now(timezone.utc).isoformat(),
        })

    token_data = {
        "sub": email,
        "role": user.get("role", "user"),
        "tenant_id": user.get("tenantId", "default"),
    }
    new_access_token = create_access_token(data=token_data)
    new_refresh_token = create_refresh_token(data={"sub": email})
    return {"success": True, "access_token": new_access_token, "refresh_token": new_refresh_token}


@router.post("/logout")
async def logout(
    _current_user=Depends(get_current_user),
    token: str = Depends(oauth2_scheme),
):
    """Revoke the current access token by storing its jti in the blocklist."""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        jti = payload.get("jti")
        if jti:
            db = get_database()
            exp = payload.get("exp")
            await db.revoked_tokens.insert_one({"jti": jti, "exp": exp})
            from authentication_service import _revoked_jti_cache
            _revoked_jti_cache.add(jti)
    except Exception:
        pass
    return {"success": True, "message": "Logged out successfully"}


class PasswordResetRequest(BaseModel):
    email: str = Field(..., max_length=254)


class PasswordResetConfirm(BaseModel):
    token: str = Field(..., max_length=512)
    new_password: str = Field(..., max_length=1024)


# In-memory reset token store — replace with DB collection in production
_reset_tokens: dict[str, dict] = {}


@router.post("/reset-password/request")
@limiter.limit("3/minute")
async def request_password_reset(request: Request, body: PasswordResetRequest):
    """Issue a password-reset token (returned in response for demo; send via email in production)."""
    db = get_database()
    user = await db._db.users.find_one({"email": body.email})
    # Always return 200 to prevent email enumeration
    if not user:
        return {"success": True, "message": "If that address is registered you will receive a reset link"}

    reset_token = uuid.uuid4().hex
    expires_at = datetime.datetime.now(timezone.utc) + timedelta(minutes=30)
    _reset_tokens[reset_token] = {"email": body.email, "expires_at": expires_at}

    # Persist to DB so token survives process restarts; fall back to in-memory dict
    try:
        await db._db.password_reset_tokens.insert_one({
            "token": reset_token,
            "email": body.email,
            "expires_at": expires_at.isoformat(),
        })
    except Exception:
        pass  # in-memory dict is the fallback

    # NOTE: in production wire this to an email delivery service (SES/SendGrid)
    # and remove the token from the response body entirely.
    import logging as _log
    _log.getLogger(__name__).info("[PasswordReset] Token issued for %s", body.email)
    return {
        "success": True,
        "message": "If that address is registered you will receive a reset link",
    }


@router.post("/reset-password/confirm")
@limiter.limit("5/minute")
async def confirm_password_reset(request: Request, body: PasswordResetConfirm):
    """Apply a new password using a valid reset token."""
    now = datetime.datetime.now(timezone.utc)
    entry = _reset_tokens.get(body.token)

    # Fall back to DB lookup (handles server-restart case)
    db = get_database()
    if not entry:
        try:
            db_token = await db._db.password_reset_tokens.find_one({"token": body.token})
            if db_token:
                expires_at = datetime.datetime.fromisoformat(db_token["expires_at"])
                if expires_at.tzinfo is None:
                    expires_at = expires_at.replace(tzinfo=timezone.utc)
                entry = {"email": db_token["email"], "expires_at": expires_at}
        except Exception:
            pass

    if not entry:
        raise HTTPException(status_code=400, detail="Invalid or expired reset token")

    if now > entry["expires_at"]:
        _reset_tokens.pop(body.token, None)
        raise HTTPException(status_code=400, detail="Reset token has expired")

    complexity_error = _validate_password_complexity(body.new_password)
    if complexity_error:
        raise HTTPException(status_code=400, detail=complexity_error)

    hashed = hash_password(body.new_password)
    await db._db.users.update_one(
        {"email": entry["email"]},
        {"$set": {"password": hashed}},
    )
    _reset_tokens.pop(body.token, None)
    try:
        await db._db.password_reset_tokens.delete_one({"token": body.token})
    except Exception:
        pass
    return {"success": True, "message": "Password updated successfully"}

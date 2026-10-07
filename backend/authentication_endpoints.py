from typing import Any
from fastapi import APIRouter, Depends, HTTPException, status, Body, Request, Response

# Fields that must never appear in any user-facing API response
_SENSITIVE_USER_FIELDS = frozenset({
    'password', 'hashed_password', 'password_hash',
    '_id', 'mfa',
    'reset_token', 'invite_token', 'api_key', 'secret',
})
from authentication_service import create_access_token, create_refresh_token, ACCESS_TOKEN_EXPIRE_MINUTES, ALGORITHM, SECRET_KEY, account_is_active, refresh_token_cut_off
from authentication_service import REFRESH_COOKIE, set_refresh_cookie, clear_refresh_cookie, _oauth2_optional, _revoked_jti_cache
from authentication_service import get_current_user_mfa_pending, mfa_action_for
from database import get_database
from rbac_service import find_role_doc

# WHY db._db.* IS USED IN THIS FILE
# ─────────────────────────────────────────────────────────────────────────────
# Authentication endpoints must bypass tenant isolation (db._db.*) for three
# reasons:
#   1. LOGIN — the caller has no JWT yet, so we cannot derive tenant_id from the
#      token. We must find the user record globally (across all tenants) to verify
#      the password and mint the first JWT.
#   2. BRUTE-FORCE TRACKING — login_attempts are keyed by email/IP, not tenant,
#      so the lockout check must read across all tenants.
#   3. TOKEN REVOCATION — revoked_tokens and revoked JTIs must be checked globally
#      because a token can be presented to any endpoint regardless of tenant.
#
# Do NOT copy this pattern in new endpoints. Use db.<collection> (tenant-scoped)
# for all operations performed after a user is authenticated.
# ─────────────────────────────────────────────────────────────────────────────
from auth_utils import verify_password, hash_password, validate_password_complexity
from rate_limiter import limiter
from pydantic import BaseModel, Field
from datetime import timedelta, timezone
from pymongo.errors import PyMongoError
import uuid
import datetime
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
    except Exception as e:
        logger.debug("UEBA analysis failed (non-fatal): %s", e)


@router.post("/login")
@limiter.limit("10/minute")
async def login_for_access_token(request: Request, response: Response, login_request: LoginRequest):  # noqa: ARG001
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
    stored_hash = user.get('password') or user.get('hashed_password') if user else None
    if not user or not stored_hash or not verify_password(login_request.password, stored_hash):
        await _record_login_failure(db, identifier)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    await _clear_login_failures(db, identifier)

    # A disabled account gets no session (and no MFA step). Only reachable
    # with the right password, so naming the reason leaks nothing new.
    if not account_is_active(user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="This account is disabled. Contact your administrator.")

    # 3. If MFA is enabled — return short-lived session token instead of full JWT
    mfa = user.get("mfa", {})
    if mfa.get("enabled"):
        try:
            import mfa_service
            session_token = await mfa_service.create_mfa_session(user["email"])
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
        except PyMongoError as e:
            # WR-07: create_mfa_session is a real async Mongo insert_one (and,
            # on first call, create_index) — a connectivity/timeout error from
            # the driver is a failure mode that didn't exist under the prior
            # synchronous in-memory implementation, and ImportError alone
            # never caught it. Without this clause the driver error surfaced
            # as an unhandled 500 instead of the intended 503.
            logger.error("MFA session creation failed: %s", e)
            raise HTTPException(
                status_code=503,
                detail="MFA is required for this account but the MFA service is unavailable. Contact your administrator.",
            )

    # 4. Create full JWT (MFA not enabled or MFA service unavailable)
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    role = user.get("role", "user")
    tenant_id = user.get("tenantId") or None
    
    token_payload = {"sub": user["email"], "role": role, "tenant_id": tenant_id}
    access_token = create_access_token(data=token_payload, expires_delta=access_token_expires)
    refresh_token = create_refresh_token(data={"sub": user["email"]})

    # Prepare user object for frontend (exclude sensitive fields)
    user_data = {k: v for k, v in user.items() if k not in _SENSITIVE_USER_FIELDS}
    if 'id' not in user_data:
        user_data['id'] = str(user.get('_id', ''))

    # Add permissions from role. DB-F10: roles is no longer exempt from
    # tenant isolation, so a bare find_one with no tenantId would auto-scope
    # to the caller's own tenant and never match a global role (real
    # tenantId "all"/"platform") — find_role_doc tries both correctly.
    role_obj = await find_role_doc(db, role, tenant_id)
    if role_obj:
        user_data['permissions'] = role_obj.get('permissions', [])
    else:
        user_data['permissions'] = []

    # Admin-tier accounts without MFA may only enroll until they do
    user_data['mfa_action'] = mfa_action_for(role, mfa_verified=False, mfa_enabled=False)

    # UEBA behavioral analysis (non-blocking)
    import asyncio as _asyncio
    client_ip = request.client.host if request.client else "unknown"
    client_ua = request.headers.get("user-agent", "")
    _asyncio.create_task(_run_ueba_analysis(db._db, user["email"], client_ip, client_ua))

    set_refresh_cookie(response, request, refresh_token)
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "success": True,
        "user": user_data
    }

@router.get("/me")
async def read_users_me(current_user: dict = Depends(get_current_user_mfa_pending)):
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
    
    # Get role permissions. DB-F10: see the /login handler's identical fix
    # above — a bare find_one would auto-scope to the caller's own tenant
    # and never match a global role.
    role_name = user.get("role", "user")
    role = await find_role_doc(db, role_name, user.get("tenantId"))
    
    # Build user response object (exclude sensitive fields)
    user_data = {k: v for k, v in user.items() if k not in _SENSITIVE_USER_FIELDS}
    if 'id' not in user_data:
        user_data['id'] = str(user.get('_id', ''))
    
    # Add permissions from role if found
    if role:
        user_data['permissions'] = role.get('permissions', [])
    else:
        user_data['permissions'] = []
    
    # Expose MFA enabled flag (not the secret)
    user_data['mfa_enabled'] = user.get('mfa', {}).get('enabled', False)
    user_data['mfa_action'] = mfa_action_for(
        current_user.role, bool(getattr(current_user, "mfa_verified", False)), user_data['mfa_enabled'])
    
    return user_data

@router.post("/signup")
@limiter.limit("3/hour")
async def signup(request: Request, response: Response, data: dict[str, Any] = Body(...)):
    from datetime import datetime, timezone
    from tenant_context import set_tenant_id
    
    # Bypass tenant isolation for signup flow to check global existence and insert with correct tenantId
    set_tenant_id("platform-admin")
    
    company_name = data.get('companyName', '').strip()
    name = data.get('name', '').strip()
    email = data.get('email', '').strip().lower()
    password = data.get('password', '')
    if not all([company_name, name, email, password]):
        raise HTTPException(status_code=400, detail="All fields are required")
    complexity_error = validate_password_complexity(password)
    if complexity_error:
        raise HTTPException(status_code=400, detail=complexity_error)
    db = get_database()
    existing_user = await db.users.find_one({"email": email})
    if existing_user:
        raise HTTPException(status_code=400, detail="Email already registered")
    tenant_id = f"tenant_{uuid.uuid4().hex[:12]}"
    registration_key = f"reg_{uuid.uuid4().hex[:16]}"
    
    # 3. Create Tenant & User
    # Free tier features — limited set available without a paid subscription.
    # Upgrade to Pro/Enterprise unlocks advanced security, AI, cloud, and analytics features.
    free_features = [
        "view:dashboard", "view:profile",
        "view:agents", "view:assets",
        "view:patching", "view:security",
        "view:compliance", "view:audit_log",
        "view:logs", "view:reporting",
        "view:automation", "view:finops",
        "manage:settings",
        "view:itam", "manage:itam",
    ]

    tenant_doc = {
        "id": tenant_id,
        "name": company_name,
        "subscriptionTier": "Free",
        "maxAgents": 5,
        "registrationKey": registration_key,
        "apiKeys": [],
        "enabledFeatures": free_features,
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
        'view:swarm', 'view:itam', 'manage:itam'
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
        "subscriptionTier": "Free",
        "maxAgents": 5,
        "permissions": enterprise_permissions,
        "createdAt": datetime.now(timezone.utc).isoformat()
    }
    try:
        await db.users.insert_one(user_doc)
    except Exception as _dup:
        # A unique index on users.email catches concurrent signups with the same address
        if "duplicate" in str(_dup).lower() or "E11000" in str(_dup):
            raise HTTPException(status_code=400, detail="Email already registered")
        raise

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
    user_data = {k: v for k, v in user_doc.items() if k not in _SENSITIVE_USER_FIELDS}
    if 'id' not in user_data:
        user_data['id'] = user_id
    user_data['mfa_action'] = mfa_action_for("Tenant Admin", mfa_verified=False, mfa_enabled=False)
        
    set_refresh_cookie(response, request, refresh_token)
    return {
        "success": True, 
        "access_token": access_token,
        "token_type": "bearer",
        "user": user_data,
        "tenant": {
            "id": tenant_id,
            "name": company_name,
            "subscriptionTier": "Free",
            "maxAgents": 5,
            "enabledFeatures": free_features
        }
    }


@router.post("/refresh")
@limiter.limit("20/minute")
async def refresh_access_token(request: Request, response: Response, data: dict[str, Any] | None = Body(None)):
    """Exchange the refresh cookie for a new access token and a rotated cookie.
    A refresh token in the body is still accepted, so tabs opened before the
    cookie existed move over on their next refresh."""
    refresh_token = request.cookies.get(REFRESH_COOKIE) or (data or {}).get("refresh_token", "")
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

    # Enforce account lockout — prevent refresh even if the token is technically valid
    await _check_login_lockout(db, email)

    # Refresh token only contains email (no tenant_id), so bypass isolation for lookup
    user = await db._db.users.find_one({"email": email})
    if not account_is_active(user):
        raise HTTPException(status_code=401, detail="Could not validate credentials")
    # Disabling, re-roling or a password change ends refresh tokens too.
    if await refresh_token_cut_off(db, email, float(payload.get("iat") or 0)):
        raise HTTPException(status_code=401, detail="Could not validate credentials")

    # Atomically consume this refresh token's JTI — prevents double-use under concurrency.
    # find_one_and_update with $setOnInsert + a unique index on jti guarantees only one
    # request wins; the second sees inserted_id=None and gets a 401.
    if jti:
        try:
            existing = await db._db.revoked_tokens.find_one_and_update(
                {"jti": jti},
                {"$setOnInsert": {
                    "jti": jti,
                    "type": "refresh",
                    "revoked_at": datetime.datetime.now(timezone.utc).isoformat(),
                }},
                upsert=True,
                return_document=False,
            )
            if existing is not None:
                # Document already existed → token was already consumed
                raise HTTPException(status_code=401, detail="Could not validate credentials")
        except HTTPException:
            raise
        except Exception:
            # Duplicate key from a concurrent request lost the race
            raise HTTPException(status_code=401, detail="Could not validate credentials")

    # Preserve tenant_id: prefer the field stored in the user document.
    # Fall back to the original token's tenant_id so Tenant Admins aren't locked out
    # if their document was created before tenantId was indexed.
    tenant_id_for_token = user.get("tenantId") or payload.get("tenant_id") or None
    # A session that passed MFA stays MFA-verified across refreshes.
    mfa_verified = bool(payload.get("mfa_verified"))
    token_data = {
        "sub": email,
        "role": user.get("role", "user"),
        "tenant_id": tenant_id_for_token,
        "mfa_verified": mfa_verified,
    }
    new_access_token = create_access_token(data=token_data)
    new_refresh_token = create_refresh_token(data={"sub": email, "mfa_verified": mfa_verified})
    set_refresh_cookie(response, request, new_refresh_token)
    return {"success": True, "access_token": new_access_token}


async def _revoke_presented_token(db, token: str, want_refresh: bool) -> None:
    """Blocklist the jti of a token the caller holds. Expired or forged
    tokens have nothing left to revoke."""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except jwt.PyJWTError:
        return
    jti = payload.get("jti")
    if not jti or (payload.get("type") == "refresh") != want_refresh:
        return
    _revoked_jti_cache.add(jti)  # block in-process immediately, even if the DB write fails
    try:
        await db._db.revoked_tokens.update_one(
            {"jti": jti},
            {"$setOnInsert": {
                "jti": jti,
                "type": "refresh" if want_refresh else "access",
                "exp": payload.get("exp"),
                "revoked_at": datetime.datetime.now(timezone.utc).isoformat(),
            }},
            upsert=True,
        )
    except Exception as db_err:
        logger.warning("Token revocation DB write failed — token blocked in-process cache only: %s", db_err)


@router.post("/logout")
async def logout(
    request: Request,
    response: Response,
    token: str | None = Depends(_oauth2_optional),
):
    """End this browser session: revoke the access token and the refresh
    cookie, then clear the cookie. Needs no valid access token, so a session
    whose access token already expired can still sign out."""
    db = get_database()
    if token:
        await _revoke_presented_token(db, token, want_refresh=False)
    refresh_token = request.cookies.get(REFRESH_COOKIE)
    if refresh_token:
        await _revoke_presented_token(db, refresh_token, want_refresh=True)
    clear_refresh_cookie(response, request)
    return {"success": True, "message": "Logged out successfully"}



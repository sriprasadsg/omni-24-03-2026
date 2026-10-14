import jwt
import logging
import os
from app_env import environment, is_production
import secrets
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional
from fastapi import HTTPException, status, Depends, Request, Response
from fastapi.security import OAuth2PasswordBearer
from auth_types import TokenData  # Token re-exported by auth_types directly
from tenant_context import set_tenant_id as _set_tenant_id

logger = logging.getLogger(__name__)

SECRET_KEY = os.getenv("JWT_SECRET_KEY", "")
if not SECRET_KEY:
    import logging as _logging
    _env = environment()
    if is_production():
        # Block startup for production, staging, or any unrecognised environment
        raise RuntimeError(
            f"JWT_SECRET_KEY is not set (ENVIRONMENT={_env!r}). "
            "Refusing to start without a stable signing key outside local development. "
            "Generate one: python -c \"import secrets; print(secrets.token_urlsafe(64))\""
        )
    _logging.getLogger(__name__).warning(
        "⚠ JWT_SECRET_KEY not set — using ephemeral key (dev only). "
        "All sessions will be lost on restart. Set JWT_SECRET_KEY before deploying."
    )
    SECRET_KEY = secrets.token_urlsafe(64)
_ALLOWED_JWT_ALGORITHMS = {"HS256", "HS384", "HS512"}
ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
if ALGORITHM not in _ALLOWED_JWT_ALGORITHMS:
    raise RuntimeError(
        f"JWT_ALGORITHM '{ALGORITHM}' is not in the allowed set {_ALLOWED_JWT_ALGORITHMS}. "
        "Only HMAC-based algorithms are supported for this deployment."
    )
ACCESS_TOKEN_EXPIRE_MINUTES = min(int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60")), 120)
REFRESH_TOKEN_EXPIRE_DAYS = 7

# JTI revocation cache — mirrored from the `revoked_tokens` MongoDB collection.
# Populated eagerly by verify_token_async; also refreshed from DB on every async
# verification so multi-worker deployments eventually converge (max lag = one
# request cycle). The sync verify_token path uses this cache as a best-effort
# check — prefer async get_current_user (Depends) in all new endpoints.
_revoked_jti_cache: set[str] = set()
_revocation_cache_last_sync: float = 0.0  # epoch seconds of last full DB sync

# Per-user session cutoffs. Disabling, deleting, re-roling or re-passwording a
# user records a cutoff; every token issued to that user before it is dead.
# The cutoff lives in revoked_tokens under a synthetic jti, so the per-request
# check stays a single indexed lookup alongside the jti check. Tokens carry a
# float `iat` so a login right after the change is not caught by it.
_USER_CUTOFF_PREFIX = "user-cutoff:"
_user_cutoff_cache: dict[str, float] = {}


def _cutoff_key(username: str) -> str:
    return _USER_CUTOFF_PREFIX + (username or "").strip().lower()


def _cut_off(username: str, iat: float) -> bool:
    return _user_cutoff_cache.get(_cutoff_key(username), 0.0) > iat


# Admin-tier roles must use MFA. A session that hasn't passed it is held to
# the routes behind get_current_user_mfa_pending (who am I, MFA status,
# enroll, step up) until it does.
MFA_REQUIRED_DETAIL = "Two-factor authentication is required for your role. Set it up or confirm it to continue."
_MFA_REQUIRED_ROLE_KEYS = frozenset({"super_admin", "platform_support", "platform_billing",
                                     "tenant_admin", "admin", "itam_admin"})


def mfa_required_for(role: Optional[str]) -> bool:
    from rbac_service import RBACService  # rbac_service imports this module
    return RBACService._normalize_role(role or "") in _MFA_REQUIRED_ROLE_KEYS


def _enforce_admin_mfa(payload: dict, role: str, allow_mfa_pending: bool) -> None:
    if allow_mfa_pending or payload.get("mfa_verified") or is_agent_payload(payload):
        return
    if mfa_required_for(role):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=MFA_REQUIRED_DETAIL,
            headers={"X-MFA-Required": "1"},
        )


def mfa_action_for(role: Optional[str], mfa_verified: bool, mfa_enabled: bool) -> Optional[str]:
    """What a session must do before it can use the app: "enroll" (set up
    MFA) or "verify" (confirm a code for this session); None when nothing."""
    if mfa_verified or not mfa_required_for(role):
        return None
    return "verify" if mfa_enabled else "enroll"


def account_is_active(user: Optional[dict]) -> bool:
    """False for a missing, disabled, inactive or pending account. Docs that
    predate the status field fall back to the legacy is_active flag."""
    if not user:
        return False
    status_value = user.get("status")
    if status_value is not None:
        return str(status_value).strip().lower() == "active"
    return user.get("is_active", True) is not False


async def revoke_user_sessions(username: str, reason: str) -> None:
    """End every access and refresh token issued to ``username`` so far.
    Logins after this call are unaffected. Raises if the cutoff can't be
    stored, so a caller never reports success for a revocation that didn't
    happen."""
    if not username:
        return
    key = _cutoff_key(username)
    now = time.time()
    _user_cutoff_cache[key] = max(now, _user_cutoff_cache.get(key, 0.0))
    from database import get_database
    db = get_database()
    await db._db.revoked_tokens.update_one(
        {"jti": key},
        {
            "$max": {"cutoff": now},
            "$set": {
                "type": "user_cutoff",
                "reason": reason,
                "updatedAt": datetime.now(timezone.utc).isoformat(),
                # TTL cleanup once every token issued before the cutoff has expired.
                "expiresAt": datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS + 1),
            },
        },
        upsert=True,
    )
    logger.info("Revoked existing sessions for a user (%s)", reason)


async def refresh_token_cut_off(db, username: str, iat: float) -> bool:
    """True when ``username`` has a session cutoff later than ``iat``."""
    if _cut_off(username, iat):
        return True
    doc = await db._db.revoked_tokens.find_one({"jti": _cutoff_key(username), "cutoff": {"$gt": iat}}, {"cutoff": 1})
    if doc:
        _user_cutoff_cache[_cutoff_key(username)] = float(doc["cutoff"])
        return True
    return False


REFRESH_COOKIE = "omni_refresh"
_REFRESH_COOKIE_PATH = "/api/auth"  # only /refresh and /logout ever see it


def _cookie_secure(request: Request) -> bool:
    proto = request.headers.get("x-forwarded-proto", request.url.scheme)
    return is_production() or proto == "https"


def set_refresh_cookie(response: Response, request: Request, refresh_token: str) -> None:
    """Give the browser the refresh token as an httpOnly cookie, so page
    scripts (and an XSS payload) can't read it. No max-age: like the
    sessionStorage copy it replaces, it ends with the browser session; the
    token inside still expires after REFRESH_TOKEN_EXPIRE_DAYS. SameSite=Strict
    keeps cross-site requests from carrying it."""
    response.set_cookie(
        REFRESH_COOKIE, refresh_token, path=_REFRESH_COOKIE_PATH,
        httponly=True, secure=_cookie_secure(request), samesite="strict",
    )


def clear_refresh_cookie(response: Response, request: Request) -> None:
    response.delete_cookie(
        REFRESH_COOKIE, path=_REFRESH_COOKIE_PATH,
        httponly=True, secure=_cookie_secure(request), samesite="strict",
    )


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)

    to_encode.update({"exp": expire, "iat": time.time(), "jti": uuid.uuid4().hex})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def create_refresh_token(data: dict):
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    to_encode.update({"exp": expire, "iat": time.time(), "type": "refresh", "jti": uuid.uuid4().hex})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

AGENT_ROLE = "agent"


def is_agent_payload(payload: dict) -> bool:
    """True for endpoint-agent JWTs (issued by POST /api/agents/register)."""
    return payload.get("role") == AGENT_ROLE or payload.get("typ") == AGENT_ROLE


def _reject_agent_token(payload: dict, allow_agent: bool) -> None:
    # Agent tokens are handed to every endpoint that installs the agent (and
    # the Windows tray copies them into a user-readable file), so they must
    # not double as user sessions. Routes agents call opt in explicitly via
    # get_current_user_or_agent; everything else gets a 401.
    if not allow_agent and is_agent_payload(payload):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Agent credentials are not valid for this endpoint",
            headers={"WWW-Authenticate": "Bearer"},
        )


def verify_token(token: str, allow_agent: bool = True, allow_mfa_pending: bool = False) -> TokenData:
    """Decode an access token. Direct callers that serve agents (WebSocket
    registry, deployment results) keep the default; user-only paths pass
    allow_agent=False. allow_mfa_pending is only for MFA enrollment/step-up."""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        # CRIT-01: refresh tokens carry no tenant_id/role claim by design (see
        # create_refresh_token) and must never be accepted as access tokens —
        # otherwise the missing-tenant_id branch below would escalate any
        # holder of their own refresh token to a full cross-tenant bypass.
        if payload.get("type") == "refresh":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Could not validate credentials - refresh token used as access token",
                headers={"WWW-Authenticate": "Bearer"},
            )
        _reject_agent_token(payload, allow_agent)
        username: str = payload.get("sub")
        role: str = payload.get("role", "user")
        tenant_id: str = payload.get("tenant_id")
        if username is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Could not validate credentials - missing sub",
                headers={"WWW-Authenticate": "Bearer"},
            )
        # CRIT-01: a missing tenant_id must never fall back to the
        # "platform-admin" isolation-bypass sentinel — reject instead. Every
        # legitimately-issued token (including the real Super Admin's) always
        # carries an explicit tenant_id (app_startup.py seeds the Super Admin
        # user with tenantId="platform-admin" and login puts it on the token
        # verbatim), so this can only fire for a malformed/incomplete token.
        if not tenant_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Could not validate credentials - missing tenant_id",
                headers={"WWW-Authenticate": "Bearer"},
            )

        # Sync JTI revocation: use a cached in-process set populated by the async path.
        jti: str = payload.get("jti", "")
        if (jti and jti in _revoked_jti_cache) or _cut_off(username, float(payload.get("iat") or 0)):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Could not validate credentials",
                headers={"WWW-Authenticate": "Bearer"},
            )
        _enforce_admin_mfa(payload, role, allow_mfa_pending)

        token_data = TokenData(
            username=username,
            role=role,
            tenant_id=tenant_id,
            mfa_verified=payload.get("mfa_verified", False),
        )
        _set_tenant_id(tenant_id)
        return token_data
    except jwt.PyJWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials - invalid token",
            headers={"WWW-Authenticate": "Bearer"},
        )


async def verify_token_async(token: str, allow_agent: bool = True, allow_mfa_pending: bool = False) -> TokenData:
    """Async version of verify_token — performs DB revocation check properly.
    ``allow_agent`` and ``allow_mfa_pending`` as in verify_token."""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        # CRIT-01: reject a refresh token presented as an access token — see
        # the identical check and full rationale in verify_token() above.
        if payload.get("type") == "refresh":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Could not validate credentials - refresh token used as access token",
                headers={"WWW-Authenticate": "Bearer"},
            )
        _reject_agent_token(payload, allow_agent)
        username: str = payload.get("sub")
        role: str = payload.get("role", "user")
        tenant_id: str = payload.get("tenant_id")
        jti: str = payload.get("jti", "")

        if username is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Could not validate credentials - missing sub",
                headers={"WWW-Authenticate": "Bearer"},
            )
        # CRIT-01: reject a missing tenant_id rather than defaulting to the
        # "platform-admin" isolation-bypass sentinel — see verify_token() above.
        if not tenant_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Could not validate credentials - missing tenant_id",
                headers={"WWW-Authenticate": "Bearer"},
            )

        iat = float(payload.get("iat") or 0)  # tokens minted before iat existed predate any cutoff
        if (jti and jti in _revoked_jti_cache) or _cut_off(username, iat):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Could not validate credentials",
                headers={"WWW-Authenticate": "Bearer"},
            )
        try:
            from database import get_database
            db = get_database()
            # One indexed lookup covers both this token's jti and the user's cutoff.
            clauses = [{"jti": _cutoff_key(username), "cutoff": {"$gt": iat}}]
            if jti:
                clauses.append({"jti": jti})
            revoked = await db._db.revoked_tokens.find_one({"$or": clauses}, {"_id": 0, "jti": 1, "cutoff": 1})
            if revoked:
                if revoked.get("jti") == jti:
                    _revoked_jti_cache.add(jti)
                else:
                    _user_cutoff_cache[_cutoff_key(username)] = float(revoked["cutoff"])
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Could not validate credentials",
                    headers={"WWW-Authenticate": "Bearer"},
                )
            # Periodically bulk-sync revocations into the in-process caches
            # so the sync verify_token path stays current across workers.
            global _revocation_cache_last_sync
            now = time.monotonic()
            if now - _revocation_cache_last_sync > 60:  # refresh every 60 s
                _revocation_cache_last_sync = now
                async for doc in db._db.revoked_tokens.find({}, {"jti": 1, "cutoff": 1, "_id": 0}).limit(5000):
                    key = doc.get("jti")
                    if not key:
                        continue
                    if key.startswith(_USER_CUTOFF_PREFIX):
                        _user_cutoff_cache[key] = max(float(doc.get("cutoff") or 0), _user_cutoff_cache.get(key, 0.0))
                    else:
                        _revoked_jti_cache.add(key)
        except HTTPException:
            raise
        except Exception as _db_err:
            # Fail-open: a transient DB error must not log out every active user.
            # The in-process caches provide best-effort protection.
            logger.warning("Token revocation DB check failed (fail-open): %s", _db_err)
        _enforce_admin_mfa(payload, role, allow_mfa_pending)

        token_data = TokenData(
            username=username,
            role=role,
            tenant_id=tenant_id,
            mfa_verified=payload.get("mfa_verified", False),
        )
        _set_tenant_id(tenant_id)
        return token_data
    except jwt.PyJWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials - invalid token",
            headers={"WWW-Authenticate": "Bearer"},
        )

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")
_oauth2_optional = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)

async def get_current_user(token: str = Depends(oauth2_scheme)):
    """Dependency to get the current user; performs async revocation check.
    Endpoint-agent tokens are rejected — see get_current_user_or_agent."""
    return await verify_token_async(token, allow_agent=False)


async def get_current_user_mfa_pending(token: str = Depends(oauth2_scheme)):
    """get_current_user for the few routes an admin session that hasn't passed
    MFA may still use: who am I, MFA status, enroll, step up."""
    return await verify_token_async(token, allow_agent=False, allow_mfa_pending=True)


async def get_current_user_or_agent(token: str = Depends(oauth2_scheme), request: Request = None):
    """Like get_current_user, but also accepts endpoint-agent tokens
    (role="agent", username=agent id). Only for routes the agent itself calls.
    An agent named in the URL path (agent_id / hostname) must be the caller."""
    token_data = await verify_token_async(token, allow_agent=True)
    if token_data.role == AGENT_ROLE and request is not None:
        from agent_auth import bind_path_agent
        from database import get_database
        import pending_agents
        await bind_path_agent(request, token_data.username, token_data.tenant_id, get_database())
        # Pending/Rejected agents reach only their heartbeat and uninstall report (spec C3).
        await pending_agents.assert_admitted(get_database(), token_data.username, request.url.path)
    return token_data

async def get_optional_user(token: Optional[str] = Depends(_oauth2_optional)):
    """Like get_current_user but returns None instead of raising 401 when no token is provided.
    Used by endpoints that accept alternative auth (e.g. one-time download tokens)."""
    if not token:
        return None
    try:
        return await verify_token_async(token, allow_agent=False)
    except HTTPException:
        return None

async def require_mfa(user: TokenData = Depends(get_current_user)):
    """
    Dependency that strictly requires MFA verification.
    """
    if not user.mfa_verified:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="MFA verification required for this action"
        )
    return user

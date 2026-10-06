import jwt
import logging
import os
from app_env import environment, is_production
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional
from fastapi import HTTPException, status, Depends
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

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)

    to_encode.update({"exp": expire, "jti": uuid.uuid4().hex})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def create_refresh_token(data: dict):
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    to_encode.update({"exp": expire, "type": "refresh", "jti": uuid.uuid4().hex})
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


def verify_token(token: str, allow_agent: bool = True) -> TokenData:
    """Decode an access token. Direct callers that serve agents (WebSocket
    registry, deployment results) keep the default; user-only paths pass
    allow_agent=False."""
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
        if jti and jti in _revoked_jti_cache:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Could not validate credentials",
                headers={"WWW-Authenticate": "Bearer"},
            )

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


async def verify_token_async(token: str, allow_agent: bool = True) -> TokenData:
    """Async version of verify_token — performs DB revocation check properly.
    ``allow_agent`` as in verify_token."""
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

        if jti:
            try:
                from database import get_database
                import time as _time
                db = get_database()
                revoked = await db._db.revoked_tokens.find_one({"jti": jti}, {"_id": 1})
                if revoked:
                    _revoked_jti_cache.add(jti)
                    raise HTTPException(
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        detail="Could not validate credentials",
                        headers={"WWW-Authenticate": "Bearer"},
                    )
                # Periodically bulk-sync recently revoked JTIs into the in-process cache
                # so the sync verify_token path stays current across workers.
                global _revocation_cache_last_sync
                now = _time.monotonic()
                if now - _revocation_cache_last_sync > 60:  # refresh every 60 s
                    _revocation_cache_last_sync = now
                    async for doc in db._db.revoked_tokens.find({}, {"jti": 1, "_id": 0}).limit(5000):
                        if doc.get("jti"):
                            _revoked_jti_cache.add(doc["jti"])
            except HTTPException:
                raise
            except Exception as _db_err:
                # Fail-open: a transient DB error must not log out every active user.
                # The in-process _revoked_jti_cache provides best-effort protection.
                logger.warning("Token revocation DB check failed (fail-open): %s", _db_err)

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


async def get_current_user_or_agent(token: str = Depends(oauth2_scheme)):
    """Like get_current_user, but also accepts endpoint-agent tokens
    (role="agent", username=agent id). Only for routes the agent itself calls."""
    return await verify_token_async(token, allow_agent=True)

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

async def require_admin(user: TokenData = Depends(get_current_user)):
    """
    Dependency to require admin role.
    """
    if user.role != "admin" and user.role != "super_admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not enough permissions"
        )
    return user

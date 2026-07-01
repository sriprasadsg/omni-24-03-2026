import jwt
import logging
import os
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
    _env = os.getenv("ENVIRONMENT", "development").lower()
    _dev_envs = {"development", "dev", "local", "test"}
    if _env not in _dev_envs:
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

def verify_token(token: str) -> TokenData:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        role: str = payload.get("role", "user")
        tenant_id: str = payload.get("tenant_id")
        if username is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Could not validate credentials - missing sub",
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
        _set_tenant_id(tenant_id or "platform-admin")
        return token_data
    except jwt.PyJWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials - invalid token",
            headers={"WWW-Authenticate": "Bearer"},
        )


async def verify_token_async(token: str) -> TokenData:
    """Async version of verify_token — performs DB revocation check properly."""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
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
        _set_tenant_id(tenant_id or "platform-admin")
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
    """Dependency to get the current user; performs async revocation check."""
    return await verify_token_async(token)

async def get_optional_user(token: Optional[str] = Depends(_oauth2_optional)):
    """Like get_current_user but returns None instead of raising 401 when no token is provided.
    Used by endpoints that accept alternative auth (e.g. one-time download tokens)."""
    if not token:
        return None
    try:
        return await verify_token_async(token)
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

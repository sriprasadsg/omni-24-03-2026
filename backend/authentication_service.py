import jwt
import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional
from fastapi import HTTPException, status, Depends
from fastapi.security import OAuth2PasswordBearer
from auth_types import TokenData  # Token re-exported by auth_types directly

# Load JWT secret from environment; generate a secure random key if not set
SECRET_KEY = os.getenv("JWT_SECRET_KEY") or secrets.token_urlsafe(64)
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60  # 1 hour
REFRESH_TOKEN_EXPIRE_DAYS = 30  # 30 days

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def create_refresh_token(data: dict):
    """Create a long-lived refresh token (30 days)"""
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    to_encode.update({"exp": expire, "type": "refresh"})
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

        # Revocation check handled by verify_token_async (async context).
        # Sync callers skip the DB check — use verify_token_async where possible.

        return TokenData(
            username=username,
            role=role,
            tenant_id=tenant_id,
            mfa_verified=payload.get("mfa_verified", False),
        )
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
                db = get_database()
                revoked = await db.revoked_tokens.find_one({"jti": jti}, {"_id": 1})
                if revoked:
                    raise HTTPException(
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        detail="Token has been revoked",
                        headers={"WWW-Authenticate": "Bearer"},
                    )
            except HTTPException:
                raise
            except Exception:
                pass

        return TokenData(
            username=username,
            role=role,
            tenant_id=tenant_id,
            mfa_verified=payload.get("mfa_verified", False),
        )
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

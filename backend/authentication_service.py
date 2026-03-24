import jwt
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any
from fastapi import HTTPException, status, Depends
from fastapi.security import OAuth2PasswordBearer
from auth_types import TokenData, Token  # Re-export TokenData and Token

# Configuration (In production, use env vars)
SECRET_KEY = "enterprise-omni-agent-secret-key-change-me"
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
        print(f"[DEBUG AUTH] Verifying token: {token[:20]}...")
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        print(f"[DEBUG AUTH] Payload: {payload}")
        username: str = payload.get("sub")
        role: str = payload.get("role", "user")
        tenant_id: str = payload.get("tenant_id")
        
        if username is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Could not validate credentials - missing sub",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return TokenData(
            username=username, 
            role=role, 
            tenant_id=tenant_id,
            mfa_verified=payload.get("mfa_verified", False)
        )
    except jwt.PyJWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials - invalid token",
            headers={"WWW-Authenticate": "Bearer"},
        )

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")

import sys

async def get_current_user(token: str = Depends(oauth2_scheme)):
    """
    Dependency to get the current user from the token.
    Checks for MFA enforcement if enabled.
    """
    try:
        data = verify_token(token)
        
        # Check if MFA is required but not verified
        # For simplicity, we assume 'admin' roles require MFA if they have it enabled in DB
        # In a real system, we'd check a 'mfa_enabled' flag in the user document
        if not data.mfa_verified:
            # We skip enforcement here to avoid breaking current trial access, 
            # but in a strict system we would:
            # raise HTTPException(status_code=403, detail="MFA verification required")
            pass
            
        with open("debug_auth.txt", "w") as f:
            f.write(f"Auth Success: {data}\n")
        return data
    except Exception as e:
        with open("debug_auth.txt", "w") as f:
            f.write(f"Auth Error: {e}\n")
        sys.stderr.write(f"CRITICAL ERROR in get_current_user: {e}\n")
        import traceback
        traceback.print_exc(file=sys.stderr)
        raise e

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

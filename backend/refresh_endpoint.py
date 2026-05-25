@app.post("/api/auth/refresh")
async def refresh_token(data: dict[str, Any]):
    """
    Refresh access token using refresh token
    """
    from authentication_service import SECRET_KEY, ALGORITHM, create_access_token, create_refresh_token, _revoked_jti_cache
    
    refresh_token = data.get('refresh_token', '')
    
    if not refresh_token:
        raise HTTPException(status_code=400, detail="Refresh token is required")
    
    try:
        # Verify and decode refresh token
        payload = jwt.decode(refresh_token, SECRET_KEY, algorithms=[ALGORITHM])
        
        # Check if token is of type 'refresh'
        token_type = payload.get('type')
        if token_type != 'refresh':
            raise HTTPException(status_code=401, detail="Invalid token type")
        
        email = payload.get('sub')
        role = payload.get('role')
        tenant_id = payload.get('tenant_id')
        
        if not email:
            raise HTTPException(status_code=401, detail="Invalid refresh token")
        
        # Verify user still exists and is active
        db = get_database()
        user = await db.users.find_one({"email": email})
        
        if not user or user.get('status') != 'Active':
            raise HTTPException(status_code=401, detail="User not found or inactive")
        
        # Generate new access token
        token_data = {"sub": email, "role": role, "tenant_id": tenant_id}
        new_access_token = create_access_token(data=token_data)

        # Rotate refresh token: revoke the old one, issue a fresh one
        old_jti = payload.get('jti', '')
        if old_jti:
            _revoked_jti_cache.add(old_jti)
            try:
                from datetime import datetime
                await db.revoked_tokens.insert_one({"jti": old_jti, "revokedAt": datetime.utcnow()})
            except Exception:
                pass
        new_refresh_token = create_refresh_token(data=token_data)

        return {
            "success": True,
            "access_token": new_access_token,
            "refresh_token": new_refresh_token
        }
        
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Refresh token has expired")
    except jwt.JWTError:
        raise HTTPException(status_code=401, detail="Invalid refresh token")

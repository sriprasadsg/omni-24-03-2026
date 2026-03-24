import sys

# Read the file
with open('backend/app.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Find the line after signup endpoint closing brace
insert_index = None
for i, line in enumerate(lines):
    if line.strip() == '}' and i > 400 and i < 435:
        # Check if this is near the signup endpoint
        if i - 2 >= 0 and 'subscription' in lines[i-2].lower():
            insert_index = i + 1
            break

if insert_index:
    # Insert the new endpoint
    new_lines = [
        '\n',
        '@app.post("/api/auth/refresh")\n',
        'async def refresh_token_endpoint(data: dict[str, Any]):\n',
        '    """\n',
        '    Refresh access token using refresh token\n',
        '    """\n',
        '    from authentication_service import SECRET_KEY, ALGORITHM, create_access_token\n',
        '    \n',
        '    refresh_token = data.get("refresh_token", "")\n',
        '    \n',
        '    if not refresh_token:\n',
        '        raise HTTPException(status_code=400, detail="Refresh token is required")\n',
        '    \n',
        '    try:\n',
        '        # Verify and decode refresh token\n',
        '        payload = jwt.decode(refresh_token, SECRET_KEY, algorithms=[ALGORITHM])\n',
        '        \n',
        '        # Check if token is of type "refresh"\n',
        '        token_type = payload.get("type")\n',
        '        if token_type != "refresh":\n',
        '            raise HTTPException(status_code=401, detail="Invalid token type")\n',
        '        \n',
        '        email = payload.get("sub")\n',
        '        role = payload.get("role")\n',
        '        tenant_id = payload.get("tenant_id")\n',
        '        \n',
        '        if not email:\n',
        '            raise HTTPException(status_code=401, detail="Invalid refresh token")\n',
        '        \n',
        '        # Verify user still exists and is active\n',
        '        db = get_database()\n',
        '        user = await db.users.find_one({"email": email})\n',
        '        \n',
        '        if not user or user.get("status") != "Active":\n',
        '            raise HTTPException(status_code=401, detail="User not found or inactive")\n',
        '        \n',
        '        # Generate new access token\n',
        '        token_data = {"sub": email, "role": role, "tenant_id": tenant_id}\n',
        '        new_access_token = create_access_token(data=token_data)\n',
        '        \n',
        '        return {\n',
        '            "success": True,\n',
        '            "access_token": new_access_token\n',
        '        }\n',
        '        \n',
        '    except jwt.ExpiredSignatureError:\n',
        '        raise HTTPException(status_code=401, detail="Refresh token has expired")\n',
        '    except jwt.JWTError:\n',
        '        raise HTTPException(status_code=401, detail="Invalid refresh token")\n',
        '\n'
    ]
    
    lines[insert_index:insert_index] = new_lines
    
    # Write back
    with open('backend/app.py', 'w', encoding='utf-8') as f:
        f.writelines(lines)
    
    print(f"Successfully added refresh endpoint at line {insert_index}")
else:
    print("Could not find insertion point")
    sys.exit(1)

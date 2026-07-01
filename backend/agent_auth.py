from fastapi import Depends, HTTPException, Header
from typing import Optional, Dict, Any
from database import get_database
import logging
import jwt
from authentication_service import SECRET_KEY, ALGORITHM

logger = logging.getLogger("agent_auth")


async def verify_agent_key(
    x_tenant_key: Optional[str] = Header(None, alias="X-Tenant-Key"),
    authorization: Optional[str] = Header(None),
    db=Depends(get_database),
) -> Dict[str, Any]:
    from tenant_context import set_tenant_id

    # 1. Try X-Tenant-Key (Legacy)
    if x_tenant_key:
        tenant = await db.tenants.find_one({"registrationKey": x_tenant_key})
        if not tenant:
            raise HTTPException(status_code=403, detail="Invalid Tenant Key")
        set_tenant_id(tenant["id"])
        return tenant

    # 2. Try Authorization Bearer Token (Agent v2)
    if authorization and authorization.startswith("Bearer "):
        token = authorization.split(" ")[1]
        try:
            payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
            tenant_id = payload.get("tenant_id")
            if not tenant_id:
                raise HTTPException(status_code=403, detail="Invalid Agent Token: No tenant_id")

            jti = payload.get("jti")
            if jti:
                revoked = await db.revoked_tokens.find_one({"jti": jti}, {"_id": 1})
                if revoked:
                    raise HTTPException(status_code=403, detail="Agent token has been revoked")

            tenant = await db.tenants.find_one({"id": tenant_id})
            if not tenant:
                logger.warning("Agent token references unknown tenant_id: %s", tenant_id)
                raise HTTPException(status_code=403, detail="Invalid Agent Token")
            set_tenant_id(tenant["id"])
            return tenant
        except HTTPException:
            raise
        except jwt.PyJWTError:
            raise HTTPException(status_code=403, detail="Invalid Agent Token")

    raise HTTPException(status_code=401, detail="Authentication required (X-Tenant-Key or Bearer Token)")

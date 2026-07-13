import hashlib
from typing import Optional
from fastapi import Depends, HTTPException, Security
from fastapi.security import APIKeyHeader
from auth_types import TokenData
from authentication_service import verify_token_async, _oauth2_optional
from database import mongodb
from tenant_context import set_tenant_id

_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

async def get_current_user_or_api_key(
    api_key: Optional[str] = Security(_api_key_header),
    token: Optional[str] = Depends(_oauth2_optional)
) -> TokenData:
    if api_key:
        key_hash = hashlib.sha256(api_key.encode()).hexdigest()
        tenant_doc = await mongodb.db.tenants.find_one({"apiKeys.keyHash": key_hash}, {"id": 1, "apiKeys.$": 1})

        if not tenant_doc:
            raise HTTPException(status_code=401, detail="Invalid or expired API Key")

        # Check if the key is revoked (apiKeys.$ operator ensures we only get the matched element)
        matched_key = tenant_doc["apiKeys"][0] if "apiKeys" in tenant_doc and tenant_doc["apiKeys"] else None
        if not matched_key or matched_key.get("revoked", False):
             raise HTTPException(status_code=401, detail="Invalid or expired API Key")

        set_tenant_id(tenant_doc["id"])
        return TokenData(tenant_id=tenant_doc["id"], role="api-integration", username="api-key")
    elif token:
        return await verify_token_async(token)
    else:
        raise HTTPException(status_code=401, detail="Authentication required")
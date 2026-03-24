from fastapi import Request, HTTPException, status
from starlette.middleware.base import BaseHTTPMiddleware
from tenant_context import set_tenant_id
from authentication_service import verify_token
import jwt

class TenantMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Skip tenant check for public endpoints
        public_paths = [
            "/health",
            "/api/health",
            "/api/auth/login",
            "/api/auth/signup",
            "/static",
            "/docs",
            "/openapi.json"
        ]
        
        if any(request.url.path.startswith(path) for path in public_paths):
            return await call_next(request)

        # Extract token from Authorization header
        auth_header = request.headers.get("Authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
            # If no token, we let it pass to the route handler which might have @require_auth or Depends(get_current_user)
            # But we can't set tenant_id yet.
            return await call_next(request)

        token = auth_header.split(" ")[1]
        try:
            # We don't use verify_token here to avoid redundant HTTPExceptions if the route doesn't require auth
            # We just peek into the token to set the context if it's valid
            from authentication_service import SECRET_KEY, ALGORITHM
            payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
            
            # Default tenant from token
            tenant_id = payload.get("tenant_id")
            role = payload.get("role", "user")
            
            # NEW: Support X-Tenant-ID override for Super Admins
            override_tenant = request.headers.get("X-Tenant-ID")
            if override_tenant and role in ["super_admin", "Super Admin", "superadmin"]:
                tenant_id = override_tenant
                print(f"[DEBUG TENANT] Super Admin overriding tenant to: {tenant_id}")
            
            if tenant_id:
                set_tenant_id(tenant_id)
        except Exception as e:
            print(f"[DEBUG TENANT] Error in middleware: {e}")
            # Invalid token, let the route handler handle auth failure if needed
            pass

        response = await call_next(request)
        return response

import logging
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from tenant_context import set_tenant_id

logger = logging.getLogger(__name__)

class TenantMiddleware(BaseHTTPMiddleware):
    _PUBLIC_PATHS = [
        "/health",
        "/api/health",
        "/api/auth/login",
        "/api/auth/signup",
        "/api/auth/reset-password",
        "/api/response/tasks",
        "/api/agent/heartbeat",
        "/static",
        "/docs",
        "/openapi.json",
        "/redoc",
    ]

    async def dispatch(self, request: Request, call_next):
        if any(request.url.path.startswith(p) for p in self._PUBLIC_PATHS):
            return await call_next(request)

        auth_header = request.headers.get("Authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
            return await call_next(request)

        token = auth_header.split(" ")[1]
        try:
            import jwt
            from authentication_service import SECRET_KEY, ALGORITHM
            payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])

            tenant_id = payload.get("tenant_id")
            role = payload.get("role", "user")

            override_tenant = request.headers.get("X-Tenant-ID")
            if override_tenant and role in ["super_admin", "Super Admin", "superadmin"]:
                logger.info(
                    "Tenant override by super admin: user=%s from=%s to=%s path=%s",
                    payload.get("sub", "unknown"),
                    tenant_id,
                    override_tenant,
                    request.url.path,
                )
                tenant_id = override_tenant

            if tenant_id:
                set_tenant_id(tenant_id)

        except jwt.ExpiredSignatureError:
            logger.debug("Expired JWT on %s — route handler will reject if auth required", request.url.path)
        except jwt.InvalidTokenError as exc:
            logger.debug("Invalid JWT on %s: %s", request.url.path, exc)
        except Exception as exc:
            logger.warning("Unexpected error in TenantMiddleware on %s: %s", request.url.path, exc)

        return await call_next(request)

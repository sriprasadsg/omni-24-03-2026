import logging
from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from tenant_context import set_tenant_id, reset_tenant_id, get_tenant_id

logger = logging.getLogger(__name__)

# Paths exempt from IP-ban enforcement (auth flows must remain accessible
# so admins can still log in to manage bans)
_BAN_EXEMPT_PATHS = ["/health", "/api/health", "/docs", "/openapi.json", "/redoc", "/static"]


class TenantMiddleware(BaseHTTPMiddleware):
    _PUBLIC_PATHS = [
        "/health",
        "/api/health",
        "/api/auth/login",
        "/api/auth/signup",
        "/api/auth/reset-password",
        "/api/response/tasks",
        "/static",
        "/docs",
        "/openapi.json",
        "/redoc",
    ]

    async def dispatch(self, request: Request, call_next):
        # ARCH-011/SEC-03: checkpoint the ContextVar's pre-request value
        # *unconditionally*, for every request, before anything below can
        # set it — and reset to it exactly once in the finally block
        # wrapping the rest of this method. contextvars.Token.reset()
        # restores the value captured at set() time regardless of how many
        # further set() calls happened afterwards, so this one checkpoint
        # also unwinds set_tenant_id() calls made deeper in the stack during
        # call_next — e.g. get_current_user_or_api_key's API-key auth path,
        # or the /api/auth/signup handler's own set_tenant_id("platform-
        # admin"), neither of which resets anything itself. Both of those
        # are on paths this middleware used to return from early (public
        # path / no Bearer header) without ever setting up a reset, so a
        # signup request or an API-key-authenticated request would
        # otherwise leave "platform-admin" (or a real tenant_id) live in
        # the ContextVar for the rest of the underlying asyncio Task's
        # lifetime — visible to whatever unrelated work reuses that task
        # next. The checkpoint must be taken before the public-path/IP-ban
        # early returns, not just around the Bearer-JWT branch, to cover
        # those cases too.
        _request_ctx_token = set_tenant_id(get_tenant_id())
        try:
            # ── IP Ban check ────────────────────────────────────────────
            # Use request.client.host (actual TCP socket IP) — never the
            # client-supplied X-Forwarded-For header, which can be
            # trivially spoofed to bypass bans.
            if not any(request.url.path.startswith(p) for p in _BAN_EXEMPT_PATHS):
                client_ip = request.client.host if request.client else None
                if client_ip:
                    try:
                        from ip_ban_service import is_banned as _is_banned
                        if await _is_banned(client_ip):
                            logger.warning("Blocked banned IP: %s → %s", client_ip, request.url.path)
                            return JSONResponse(
                                status_code=403,
                                content={"detail": "Access denied: your IP address has been blocked."},
                            )
                    except Exception as _ban_err:
                        logger.debug("IP ban check failed (non-fatal): %s", _ban_err)

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
        finally:
            reset_tenant_id(_request_ctx_token)

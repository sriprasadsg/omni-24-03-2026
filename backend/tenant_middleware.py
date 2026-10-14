import json
import logging
import re
from typing import Optional

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

import rbac_defaults
import tenant_features
from tenant_context import set_tenant_id, reset_tenant_id, get_tenant_id

logger = logging.getLogger(__name__)

# ── Read-only platform tiers (spec C1) ────────────────────────────────────────
# Platform Support and Platform Billing live in the platform-admin tenant, whose
# context makes the DB wrapper skip tenant scoping for reads AND writes. Their
# permissions already refuse writes; this guard is the second wall: an /api/ write
# is refused unless it is the caller's own sign-in/MFA/profile, or (billing) a
# seat-license or Pending-agent decision.
_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
_SELF_SERVICE_WRITES = (re.compile(r"^/api/(auth|mfa|passkey)/"), re.compile(r"^/api/users/me/"))
_BILLING_WRITES = (  # exactly the license, enrollment-control and Pending-decision routes
    re.compile(r"^/api/tenants/[^/]+/license$"),
    re.compile(r"^/api/tenants/[^/]+/(allowlist|allowlist/import|allowlist/[^/]+|enrollment-keys"
               r"|enrollment-keys/[^/]+/revoke)$"),
    re.compile(r"^/api/agents/pending/(bulk|[^/]+/approve|[^/]+/reject)$"),
)


def platform_write_refusal(role: Optional[str], method: str, path: str) -> Optional[str]:
    """Why this write is refused to a read-only platform tier, or None when it may proceed."""
    tier = rbac_defaults.platform_tier(role)
    if tier not in ("support", "billing") or method.upper() in _SAFE_METHODS or not path.startswith("/api/"):
        return None
    if any(p.match(path) for p in _SELF_SERVICE_WRITES):
        return None
    if tier == "billing" and any(p.match(path) for p in _BILLING_WRITES):
        return None
    return f"Platform {tier.capitalize()} is read-only here: this change needs a Platform Owner"


class PlatformReadOnlyMiddleware:
    """Pure ASGI middleware applying platform_write_refusal to every HTTP request."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http" or scope.get("method", "GET").upper() in _SAFE_METHODS:
            return await self.app(scope, receive, send)
        role = _bearer_role(scope)
        reason = platform_write_refusal(role, scope.get("method", ""), scope.get("path", "")) if role else None
        if not reason:
            return await self.app(scope, receive, send)
        logger.info("Refused %s %s to read-only platform role %r", scope.get("method"), scope.get("path"), role)
        body = json.dumps({"error": reason, "status_code": 403}).encode()
        await send({"type": "http.response.start", "status": 403,
                    "headers": [(b"content-type", b"application/json"),
                                (b"content-length", str(len(body)).encode())]})
        await send({"type": "http.response.body", "body": body})


class ScreenSwitchMiddleware:
    """Spec C6 per-screen switches: a tenant user's request to a route that a switched-off
    Security or Compliance screen owns (tenant_features.screen_of) gets 403. Runs inside
    TenantMiddleware, so the tenant context is already set; platform roles, requests without
    a bearer JWT and routes no switched screen owns pass through. Fails closed when the
    tenant's switches cannot be read."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        view = tenant_features.screen_of(scope.get("path", "")) if scope.get("type") == "http" else None
        role = _bearer_role(scope) if view else None
        if not view or not role or not tenant_features.applies_to(role):
            return await self.app(scope, receive, send)
        try:
            from database import get_database
            enabled = await tenant_features.enabled_features(get_tenant_id(), get_database)
            parent = tenant_features.SCREEN_SWITCHES[view]
            allowed = f"{tenant_features.SCREEN_PREFIX}{view}" in tenant_features.screen_permissions([parent], enabled)
        except Exception as exc:
            logger.warning("Screen switch lookup failed for %s (refusing %s): %s", get_tenant_id(), scope.get("path"), exc)
            allowed = False
        if allowed:
            return await self.app(scope, receive, send)
        body = json.dumps({"error": "This screen is not enabled for your organization", "status_code": 403}).encode()
        await send({"type": "http.response.start", "status": 403,
                    "headers": [(b"content-type", b"application/json"),
                                (b"content-length", str(len(body)).encode())]})
        await send({"type": "http.response.body", "body": body})


def _bearer_role(scope) -> Optional[str]:
    """The role claim of a valid bearer JWT; None for no token or an invalid one (the route rejects it)."""
    auth = next((v.decode("latin-1") for k, v in scope.get("headers") or [] if k == b"authorization"), "")
    if not auth.startswith("Bearer "):
        return None
    try:
        import jwt
        from authentication_service import ALGORITHM, SECRET_KEY
        return jwt.decode(auth[7:], SECRET_KEY, algorithms=[ALGORITHM]).get("role")
    except Exception:
        return None

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
                if override_tenant and rbac_defaults.platform_tier(role) == "owner":
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

"""Application middleware classes and registration helper."""
import os
import socket
import logging
import uuid as _uuid

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request as StarletteRequest
from starlette.responses import Response as StarletteResponse

logger = logging.getLogger(__name__)


class RateLimitHeaderMiddleware(BaseHTTPMiddleware):
    """Pass-through middleware: only sets X-RateLimit-* headers when slowapi has NOT already set them.
    Previously this middleware injected a hardcoded 'Remaining: 9' which misled API clients
    into believing they always had 9 requests left regardless of their actual consumption."""

    async def dispatch(self, request: StarletteRequest, call_next):
        response: StarletteResponse = await call_next(request)
        # Only inject defaults when slowapi has not already set a real rate-limit header
        if "x-ratelimit-remaining" not in response.headers and "x-ratelimit-limit" not in response.headers:
            # Do NOT inject fake values here — omitting the header is safer than lying about it.
            # If slowapi is configured (REDIS_URL set), real headers will appear automatically.
            pass
        return response


class APMMiddleware(BaseHTTPMiddleware):
    """Record every HTTP request into apm_metrics for the APM dashboard."""

    _SKIP_PREFIXES = ("/static", "/api/apm", "/api/stream", "/socket.io")

    async def dispatch(self, request: StarletteRequest, call_next):
        import time as _time
        from datetime import datetime as _dt, timezone as _tz
        from database import get_database

        start = _time.monotonic()
        response: StarletteResponse = await call_next(request)
        duration_ms = (_time.monotonic() - start) * 1000

        path = request.url.path
        if not any(path.startswith(p) for p in self._SKIP_PREFIXES):
            try:
                db = get_database()
                await db.apm_metrics.insert_one({
                    "type": "http_request",
                    "endpoint": path,
                    "method": request.method,
                    "duration_ms": round(duration_ms, 2),
                    "status_code": response.status_code,
                    "is_error": response.status_code >= 400,
                    "is_slow": duration_ms > 500,
                    # DB-F02: native datetime, not .isoformat() — the
                    # apm_metrics TTL index (database.py) only expires
                    # BSON Date-typed fields, not ISO-8601 strings.
                    "timestamp": _dt.now(_tz.utc),
                })
            except Exception as e:
                logger.debug("APM metrics insert failed (non-fatal): %s", e)
        return response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Add OWASP-recommended security headers to every response."""

    async def dispatch(self, request: StarletteRequest, call_next):
        response: StarletteResponse = await call_next(request)
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; "
            "script-src 'self'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data: https:; "
            "connect-src 'self' ws: wss:; "
            "font-src 'self' data:; "
            "object-src 'none'; "
            "base-uri 'self'; "
            "form-action 'self';",
        )
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("X-XSS-Protection", "1; mode=block")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        response.headers.setdefault("X-Permitted-Cross-Domain-Policies", "none")
        # Set HSTS unconditionally — when behind a TLS-terminating reverse proxy
        # the internal scheme is http but browsers receive the header over HTTPS.
        # The header is harmless on plain-HTTP responses.
        response.headers.setdefault(
            "Strict-Transport-Security", "max-age=31536000; includeSubDomains"
        )
        return response


_MAX_BODY_BYTES = 50 * 1024 * 1024  # 50 MB


class MaxBodySizeMiddleware(BaseHTTPMiddleware):
    """Reject requests whose Content-Length exceeds the platform limit."""

    async def dispatch(self, request: StarletteRequest, call_next):
        content_length = request.headers.get("content-length")
        if content_length and int(content_length) > _MAX_BODY_BYTES:
            return StarletteResponse(
                content='{"detail":"Request body too large"}',
                status_code=413,
                media_type="application/json",
            )
        return await call_next(request)


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Attach a unique request ID to every request for log correlation."""

    async def dispatch(self, request: StarletteRequest, call_next):
        request_id = request.headers.get("X-Request-ID") or str(_uuid.uuid4())
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response


def _detect_local_ips() -> set:
    """Return all local IPv4 addresses so CORS works on any network."""
    ips = set()
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            ips.add(s.getsockname()[0])
    except Exception as e:
        logger.debug("Primary IP detection failed: %s", e)
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None):
            if info[0] == socket.AF_INET:
                ips.add(info[4][0])
    except Exception as e:
        logger.debug("Hostname IP detection failed: %s", e)
    return ips


def register_middleware(app: FastAPI, rate_limiter) -> None:
    """Attach all middleware to the FastAPI application.

    ARCH-007 (2026-08-25 audit): Starlette's add_middleware() prepends, so
    the LAST middleware added is the OUTERMOST — the first to see an
    incoming request and the last to touch the outgoing response (see the
    RequestIDMiddleware comment below, which already relied on this).
    SlowAPIMiddleware/MaxBodySizeMiddleware used to be added *first*
    (innermost), meaning a flood of requests — or oversized bodies — paid
    for TenantMiddleware's JWT decode, UsageTrackingMiddleware, CORS, and
    APMMiddleware's DB insert on every single request *before* ever
    reaching the check that would reject them. Registering them late
    (just inside RequestIDMiddleware) means oversized/rate-limited requests
    are rejected before any of that other work runs.
    """
    from rate_limiter import limiter  # noqa: F401 (re-exported via parameter)

    app.state.limiter = rate_limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

    app.add_middleware(APMMiddleware)
    app.add_middleware(SecurityHeadersMiddleware)

    # CORS — explicit allowlist only; no wildcard subnet regex.
    # The previous regex allowed *any* device on the local LAN to make credentialed
    # cross-origin requests, which is a session-hijack risk on shared networks.
    cors_env = os.getenv("CORS_ORIGINS", "")
    if cors_env:
        allowed_origins = [o.strip() for o in cors_env.split(",") if o.strip()]
    else:
        # Auto-detect the exact IPs the server listens on — not a subnet wildcard.
        allowed_origins = ["http://localhost:3000", "http://127.0.0.1:3000"]
        for _ip in _detect_local_ips():
            if _ip not in ("127.0.0.1",):
                allowed_origins.append(f"https://{_ip}")  # default-port TLS (nginx/reverse-proxy)
                for _port in ("3000", "4173", "5173"):
                    allowed_origins.append(f"http://{_ip}:{_port}")
                    allowed_origins.append(f"https://{_ip}:{_port}")
        allowed_origins = list(dict.fromkeys(allowed_origins))  # dedup, preserve order

    logger.info("CORS allowed origins (%d): %s", len(allowed_origins), allowed_origins)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_origin_regex=None,  # never use a wildcard regex with allow_credentials=True
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Tenant-ID", "X-Request-ID", "Accept"],
        expose_headers=[
            "Content-Disposition",
            "X-RateLimit-Limit",
            "X-RateLimit-Remaining",
            "X-RateLimit-Reset",
            "X-Export-Truncated",
        ],
    )

    from tenant_middleware import TenantMiddleware
    from usage_middleware import UsageTrackingMiddleware
    app.add_middleware(TenantMiddleware)
    app.add_middleware(UsageTrackingMiddleware)

    # Rate limiting / body-size rejection — added late (outer) so they run
    # before the more expensive middleware above; see the docstring note.
    app.add_middleware(MaxBodySizeMiddleware)
    app.add_middleware(SlowAPIMiddleware)
    app.add_middleware(RateLimitHeaderMiddleware)

    # RequestIDMiddleware added last so it is outermost — every request gets an ID first
    app.add_middleware(RequestIDMiddleware)

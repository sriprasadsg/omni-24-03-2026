"""Shared SlowAPI limiter instances used across routers."""
import os
import logging
from slowapi import Limiter
from slowapi.util import get_remote_address
from fastapi import Request

logger = logging.getLogger(__name__)

_REDIS_URL = os.getenv("REDIS_URL", "").strip()

# Exposed as a constant so tests can verify the configured rate strings directly.
# NOTE: the SPA polls ~47 endpoints every 30s (~6,700 req/hour per tab), and the
# Vite dev proxy collapses every browser onto one source IP (127.0.0.1), so all
# clients share a single bucket. Limits must cover several concurrent tabs or
# the hour bucket exhausts and every request — including /api/health — 429s,
# which the UI renders as "Backend connection lost".
LIMITER_DEFAULT_LIMITS = ["600/minute", "30000/hour"]


def _agent_key(request: Request) -> str:
    """Rate limit key: agent ID + real socket IP (cannot be forged via X-Forwarded-For)."""
    agent_id = request.path_params.get("agent_id") or request.path_params.get("id", "")
    ip = request.client.host if request.client else "unknown"
    return f"agent:{agent_id}:{ip}" if agent_id else ip


def _make_storage_uri() -> str | None:
    """Return a Redis URI for distributed rate-limit state, or None for in-memory.

    Falls back to in-memory if REDIS_URL is unset or the Redis server is unreachable
    at startup, so a missing Redis instance never takes down the API.
    """
    if not _REDIS_URL:
        logger.info("[RateLimiter] Redis not configured (REDIS_URL unset); using in-memory (single-instance only)")
        return None
    try:
        import redis as _redis
        _client = _redis.from_url(_REDIS_URL, socket_connect_timeout=2)
        _client.ping()
        _client.close()
        logger.info("[RateLimiter] Using Redis storage: %s", _REDIS_URL.split("@")[-1])
        return _REDIS_URL
    except Exception as _exc:
        logger.warning(
            "[RateLimiter] Redis unreachable (%s); falling back to in-memory rate limiting. "
            "Start Redis or unset REDIS_URL to suppress this warning.",
            _exc,
        )
        return None


_storage_uri = _make_storage_uri()

# Global limiter — keyed by real socket IP to prevent header-spoofing bypass.
# Redis storage enables consistent limits across horizontally-scaled instances.
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=LIMITER_DEFAULT_LIMITS,
    headers_enabled=True,
    storage_uri=_storage_uri,
)

# Per-agent limiter — used on heartbeat and agent command endpoints
agent_limiter = Limiter(
    key_func=_agent_key,
    default_limits=["60/minute"],
    headers_enabled=True,
    storage_uri=_storage_uri,
)

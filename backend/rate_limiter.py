"""Shared SlowAPI limiter instances used across routers."""
from slowapi import Limiter
from fastapi import Request


def _real_ip(request: Request) -> str:
    """Use the actual TCP socket IP — never trust X-Forwarded-For for rate limiting."""
    return request.client.host if request.client else "unknown"


# Global limiter — keyed by real socket IP to prevent header-spoofing bypass
limiter = Limiter(
    key_func=_real_ip,
    default_limits=["200/minute", "2000/hour"],
    headers_enabled=True,
)


def _agent_key(request: Request) -> str:
    """Rate limit key that combines agent ID (from path) + socket-level remote IP.
    Uses request.client.host (the actual TCP connection IP) so the key cannot be
    forged by spoofing X-Forwarded-For headers.
    """
    agent_id = request.path_params.get("agent_id") or request.path_params.get("id", "")
    # Always use the real socket IP — never trust client-supplied forwarding headers
    # for security-critical rate limiting.
    ip = request.client.host if request.client else "unknown"
    return f"agent:{agent_id}:{ip}" if agent_id else ip


# Per-agent limiter — used on heartbeat and agent command endpoints
agent_limiter = Limiter(
    key_func=_agent_key,
    default_limits=["60/minute"],
    headers_enabled=True,
)

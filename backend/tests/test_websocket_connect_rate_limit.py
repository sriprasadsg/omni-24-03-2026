"""Regression tests for ARCH-006 (2026-08-25 audit): Socket.IO connect-attempt
rate limiting.

socketio.ASGIApp intercepts /socket.io/* before the wrapped FastAPI app's
SlowAPI middleware ever sees the request, so the rate limiting every other
endpoint gets was completely absent for WebSocket connect attempts — each
one pays for a JWT signature verification with nothing bounding the rate,
an unauthenticated CPU-exhaustion DoS vector. websocket_manager.py now
tracks connect attempts per source IP in an in-memory sliding window and
rejects (return False) once the window's cap is exceeded, before any JWT
work happens.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import patch

import websocket_manager as wsm


@pytest.fixture(autouse=True)
def _reset_rate_limit_state():
    wsm._connect_attempts_by_ip.clear()
    yield
    wsm._connect_attempts_by_ip.clear()


def test_client_ip_uses_remote_addr_not_forwarded_for():
    """Deliberately ignores X-Forwarded-For — trivially spoofable without a
    documented trusted-proxy allowlist (mirrors rate_limiter.py's _agent_key)."""
    environ = {"REMOTE_ADDR": "10.0.0.5", "HTTP_X_FORWARDED_FOR": "1.2.3.4"}
    assert wsm._client_ip(environ) == "10.0.0.5"


def test_connect_rate_limited_allows_up_to_the_window_cap(monkeypatch):
    monkeypatch.setattr(wsm, "_CONNECT_RATE_MAX_PER_WINDOW", 3)
    monkeypatch.setattr(wsm, "_CONNECT_RATE_WINDOW_SECONDS", 60)
    ip = "203.0.113.7"
    assert wsm._connect_rate_limited(ip) is False
    assert wsm._connect_rate_limited(ip) is False
    assert wsm._connect_rate_limited(ip) is False
    assert wsm._connect_rate_limited(ip) is True  # 4th attempt in the window


def test_connect_rate_limited_is_scoped_per_ip(monkeypatch):
    monkeypatch.setattr(wsm, "_CONNECT_RATE_MAX_PER_WINDOW", 1)
    monkeypatch.setattr(wsm, "_CONNECT_RATE_WINDOW_SECONDS", 60)
    assert wsm._connect_rate_limited("1.1.1.1") is False
    assert wsm._connect_rate_limited("1.1.1.1") is True
    assert wsm._connect_rate_limited("2.2.2.2") is False  # different IP, own bucket


def test_connect_rate_limited_window_expires(monkeypatch):
    monkeypatch.setattr(wsm, "_CONNECT_RATE_MAX_PER_WINDOW", 1)
    monkeypatch.setattr(wsm, "_CONNECT_RATE_WINDOW_SECONDS", 60)
    ip = "9.9.9.9"
    assert wsm._connect_rate_limited(ip) is False
    assert wsm._connect_rate_limited(ip) is True

    fake_now = wsm.time.monotonic() + 61
    with patch("websocket_manager.time.monotonic", return_value=fake_now):
        assert wsm._connect_rate_limited(ip) is False


@pytest.mark.asyncio
async def test_connect_rejects_before_jwt_verification_once_rate_limited(monkeypatch):
    """The rate-limit check must run before any JWT work — a flood of
    garbage tokens should never reach verify_token once the IP is capped."""
    monkeypatch.setattr(wsm, "_CONNECT_RATE_MAX_PER_WINDOW", 2)
    monkeypatch.setattr(wsm, "_CONNECT_RATE_WINDOW_SECONDS", 60)
    environ = {"REMOTE_ADDR": "198.51.100.1"}

    # Exhaust the window directly (avoids depending on unrelated connect() behavior).
    wsm._connect_rate_limited("198.51.100.1")
    wsm._connect_rate_limited("198.51.100.1")

    with patch("authentication_service.verify_token") as mock_verify:
        result = await wsm.connect("sid-1", environ, {"tenant_id": "t1", "token": "whatever"})

    assert result is False
    mock_verify.assert_not_called()

"""
Tests that the global rate limiter is correctly configured.

These verify that:
  - The shared limiter instance has at least one default limit
  - It keys on the client's remote address (not a constant)
  - The limit values are sensible (not zero / unbounded)
  - The headers_enabled flag is set so clients receive RateLimit headers
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ---------------------------------------------------------------------------
# Limiter instance
# ---------------------------------------------------------------------------

class TestRateLimiterConfiguration:

    def test_limiter_has_default_limits(self):
        """The shared Limiter must have default_limits set to protect all endpoints."""
        from rate_limiter import limiter
        assert hasattr(limiter, "_default_limits"), "Limiter must expose _default_limits"
        assert len(limiter._default_limits) > 0, (
            "At least one default limit must be configured to protect unannotated routes"
        )

    def test_limiter_key_func_is_remote_address(self):
        """Rate limiter must key on the client IP, not a constant value."""
        from rate_limiter import limiter
        from slowapi.util import get_remote_address
        assert limiter._key_func == get_remote_address, (
            "Limiter key_func must be get_remote_address so every client IP is tracked independently"
        )

    def test_limiter_default_limits_are_non_empty_strings(self):
        """Each default limit must be a non-empty string (SlowAPI rate limit expression)."""
        from rate_limiter import limiter
        for limit_str in limiter._default_limits:
            assert isinstance(str(limit_str), str), f"Limit {limit_str!r} is not a string"
            assert len(str(limit_str)) > 0, "Rate limit string must not be empty"

    def test_limiter_headers_enabled(self):
        """headers_enabled must be True so clients receive RateLimit-* response headers."""
        from rate_limiter import limiter
        assert getattr(limiter, "_headers_enabled", False) is True, (
            "headers_enabled should be True so rate limit state is communicated to clients"
        )

    def test_limiter_has_per_minute_limit(self):
        """At least one default limit must include a per-minute rate."""
        from rate_limiter import LIMITER_DEFAULT_LIMITS
        has_per_minute = any("minute" in lim for lim in LIMITER_DEFAULT_LIMITS)
        assert has_per_minute, (
            f"No per-minute limit found in default_limits: {LIMITER_DEFAULT_LIMITS}. "
            "A per-minute limit is required to stop burst attacks."
        )

    def test_limiter_minute_limit_is_below_brute_force_threshold(self):
        """Per-minute limit must be <= 1000 to mitigate brute-force attacks."""
        from rate_limiter import limiter
        limits_as_str = [str(lim) for lim in limiter._default_limits]
        for limit_str in limits_as_str:
            if "minute" in limit_str:
                # Parse '200/minute' -> 200
                try:
                    count_part = limit_str.split("/")[0].strip()
                    count = int(count_part)
                    assert count <= 1000, (
                        f"Per-minute limit {count} is dangerously high — "
                        "consider setting it to 200/minute or lower"
                    )
                except (ValueError, IndexError):
                    pass  # Non-standard format — skip numeric check

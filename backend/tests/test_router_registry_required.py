"""Regression test for ARCH-003 (2026-08-25 audit): authentication_endpoints
must be a required (fail-fast) router.

Before this fix, a broken import of authentication_endpoints (bad merge,
missing dependency, typo) was silently logged and swallowed by
router_registry._load()'s generic except clause, same as any other feature
router — the app would boot "healthy" (neither /health nor /health/ready
check router load state) with /api/auth/login, /signup, /refresh, and /me
entirely absent, locking out 100% of users with no way to log in at all.
That is qualitatively worse than any single feature router being down and
should abort startup instead.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from unittest.mock import MagicMock, patch

from fastapi import FastAPI
import router_registry


def test_authentication_endpoints_is_a_required_router():
    assert "authentication_endpoints" in router_registry._REQUIRED_ROUTERS


def test_load_reraises_for_authentication_endpoints_on_import_failure():
    app = FastAPI()
    with patch("router_registry.importlib.import_module", side_effect=ImportError("broken merge")):
        try:
            router_registry._load(app, "authentication_endpoints", "router")
            assert False, "expected the import failure to propagate for a required router"
        except ImportError:
            pass


def test_load_swallows_failure_for_a_non_required_router():
    """Contrast case: an ordinary feature router's broken import must still
    be logged and swallowed, not abort the whole app."""
    app = FastAPI()
    with patch("router_registry.importlib.import_module", side_effect=ImportError("broken")):
        router_registry._load(app, "some_optional_feature_router", "router")  # must not raise

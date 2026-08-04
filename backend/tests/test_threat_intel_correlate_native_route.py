"""Live-route test for Phase 55 Plan 05 (INT-04, 55-VERIFICATION.md gap #1).

`backend/threat_intel_endpoints.py` line 17 imports
`from virustotal_client import get_virustotal_client` — a factory that did
not exist. The file's only pre-existing class extended an undefined
`BaseCapability`, raising `NameError` at import time. `router_registry._load()`
swallows this for the non-required `threat_intel_endpoints` router, so the
already-correct `/api/threat-intel/correlate-native` route (lines 254-274)
never mounted and every request 404'd.

This test drives the REAL `app` module (not a router-only test app) so it
actually exercises the import chain that was broken: `import app` ->
`register_all_routers` -> `_load(app, "threat_intel_endpoints")` ->
`from virustotal_client import get_virustotal_client`. It uses the
`_fastapi_app` escape hatch documented in STATE.md (2026-07-14 session) since
`app.py` reassigns the module-level `app` name to a `socketio.ASGIApp` wrapper
with no usable route table. `TestClient` is instantiated WITHOUT the `with`
context manager so the app's real `lifespan` (live Mongo connect) never runs
— hermetic, no live Mongo/network required.
"""
import importlib
import os
import subprocess
import sys

import pytest
from fastapi.testclient import TestClient

_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

from authentication_service import get_current_user
from auth_types import TokenData


def _super_admin():
    # Super Admin bypasses rbac_utils.verify_permission's DB role lookup
    # entirely (short-circuit `if is_super_admin(user.role): return True`),
    # so require_permission("manage:security") passes without needing a
    # real database for the permission check itself.
    return TokenData(username="admin@example.com", role="Super Admin", tenant_id="tenant-a", mfa_verified=True)


@pytest.fixture
def real_app_client():
    import app as app_module
    from database import get_database

    fastapi_app = app_module._fastapi_app
    fastapi_app.dependency_overrides[get_current_user] = _super_admin
    fastapi_app.dependency_overrides[get_database] = lambda: object()
    client = TestClient(fastapi_app)
    try:
        yield client
    finally:
        fastapi_app.dependency_overrides.pop(get_current_user, None)
        fastapi_app.dependency_overrides.pop(get_database, None)


def test_import_virustotal_client_and_threat_intel_endpoints_clean():
    """No NameError at import — the abandoned BaseCapability class is gone."""
    importlib.import_module("virustotal_client")
    importlib.import_module("threat_intel_endpoints")


def test_fresh_app_import_no_longer_logs_router_load_failure():
    """Grep-pinned acceptance criterion: a fresh `python -c "import app"` must
    not emit the router-registry warning for threat_intel_endpoints."""
    result = subprocess.run(
        [sys.executable, "-c", "import app"],
        cwd=_BACKEND_DIR,
        capture_output=True,
        text=True,
        timeout=60,
    )
    combined = (result.stdout or "") + (result.stderr or "")
    assert "Failed to load threat_intel_endpoints" not in combined


def test_correlate_native_route_returns_200_through_mounted_router(monkeypatch, real_app_client):
    """The core of INT-04: POST /api/threat-intel/correlate-native must be
    reachable (200, not 404) now that the router actually mounts."""
    import threat_intel_endpoints as tie

    known_summary = {
        "tenant_id": "tenant-a",
        "correlated_findings": 3,
        "cases_created": 1,
        "sources": ["security_scan_results", "vulnerabilities", "fim_events", "remediation_audit"],
    }

    class _FakeSiem:
        async def correlate_native_findings(self, tenant_id):
            assert tenant_id == "tenant-a"
            return known_summary

    monkeypatch.setattr(tie, "get_siem_engine", lambda db: _FakeSiem())

    response = real_app_client.post("/api/threat-intel/correlate-native")

    assert response.status_code == 200
    assert response.json() == known_summary

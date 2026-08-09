"""Shared pytest fixtures for all backend tests."""
import sys
import os
import pytest
from unittest.mock import MagicMock, AsyncMock

# Ensure backend/ is importable regardless of which directory pytest is invoked from
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Process-global sentinel recording whether AI_ROUTER_URL was set in the REAL
# shell environment when pytest started. Several Phase 39 eval test modules
# transitively import `database.py`, whose module-level `load_dotenv()` leaks
# backend/.env values (including a possibly-stale AI_ROUTER_URL) into
# os.environ mid-collection — the live 9router smoke test's skip guard reads
# this sentinel instead so a gateway-less sandbox still skips deterministically.
# Stored in os.environ (not a module attribute) because pytest and test code
# can import this conftest under different module names; setdefault keeps the
# first (pre-dotenv) capture.
os.environ.setdefault("_AI_ROUTER_URL_PRE_DOTENV", os.environ.get("AI_ROUTER_URL", ""))


# ---------------------------------------------------------------------------
# JWT / Auth helpers (standalone functions — usable outside fixtures)
# ---------------------------------------------------------------------------

def make_token_data(
    user_id: str = "user-test",
    username: str = "test@example.com",
    role: str = "User",
    tenant_id: str = "tenant-test",
):
    """Create a minimal TokenData-like object for auth injection."""
    from auth_types import TokenData
    td = TokenData(username=username, role=role, tenant_id=tenant_id)
    # Attach user_id as an extra attribute for tests that inspect it
    td.user_id = user_id
    return td


def make_super_admin_token():
    return make_token_data(role="Super Admin", tenant_id="platform-admin")


def make_tenant_token(tenant_id: str = "tenant-a"):
    return make_token_data(tenant_id=tenant_id)


# ---------------------------------------------------------------------------
# Database mock
# ---------------------------------------------------------------------------

def _make_col(**overrides):
    col = MagicMock()
    col.find_one = AsyncMock(return_value=None)
    col.insert_one = AsyncMock()
    col.update_one = AsyncMock(return_value=MagicMock(matched_count=1))
    col.delete_one = AsyncMock()
    col.find = MagicMock(return_value=AsyncMock())
    col.find.return_value.to_list = AsyncMock(return_value=[])
    col.distinct = AsyncMock(return_value=[])
    col.aggregate = MagicMock(return_value=AsyncMock())
    col.aggregate.return_value.to_list = AsyncMock(return_value=[])
    for k, v in overrides.items():
        setattr(col, k, v)
    return col


@pytest.fixture
def mock_db():
    """Minimal async MongoDB mock — every collection returns the same col mock."""
    col = _make_col()
    db = MagicMock()
    db.__getattr__ = MagicMock(return_value=col)
    # Common collections accessed by name
    for name in (
        "assets", "security_cases", "security_events", "vulnerability_scans",
        "vulnerability_scan_jobs", "attack_paths", "patches", "alerts",
        "compliance_frameworks", "asset_compliance", "agent_instructions",
        "agents", "agent_versions", "signing_keys", "security_audit_log",
        "users", "tenants",
    ):
        setattr(db, name, _make_col())
    return db


# ---------------------------------------------------------------------------
# Auth fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def tenant_user():
    """Authenticated user scoped to tenant 't1'."""
    from auth_types import TokenData
    return TokenData(username="user@tenant.com", role="Viewer", tenant_id="t1", mfa_verified=True)


@pytest.fixture
def admin_user():
    """Tenant-scoped admin user."""
    from auth_types import TokenData
    return TokenData(username="admin@tenant.com", role="Admin", tenant_id="t1", mfa_verified=True)


@pytest.fixture
def super_admin_user():
    """Super-admin user — no tenant scope restriction."""
    from auth_types import TokenData
    return TokenData(username="superadmin@platform.com", role="Super Admin", tenant_id=None, mfa_verified=True)


@pytest.fixture
def super_admin():
    """Alias: Super Admin token using make_token_data helper."""
    return make_super_admin_token()


@pytest.fixture
def tenant_user_b():
    """Authenticated user scoped to a second tenant ('tenant-b') for cross-tenant tests."""
    return make_tenant_token("tenant-b")


# ---------------------------------------------------------------------------
# App-factory helper
# ---------------------------------------------------------------------------

def make_test_app(*routers, current_user_override=None, db_override=None):
    """
    Build a minimal FastAPI app mounting the given routers.

    If current_user_override is supplied it replaces the get_current_user
    dependency so no real JWT validation happens.
    If db_override is supplied every call to get_database() returns it.
    """
    from fastapi import FastAPI
    from authentication_service import get_current_user

    app = FastAPI()
    for router in routers:
        app.include_router(router)

    if current_user_override is not None:
        app.dependency_overrides[get_current_user] = lambda: current_user_override

    return app, db_override

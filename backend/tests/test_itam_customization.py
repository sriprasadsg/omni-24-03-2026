"""ITAM console global settings tests — Phase 65 Plan 04 (ITAM-SET-01/02/03).

These routes read/write through the RAW `db._db` handle (65-RESEARCH.md Pitfall 2), not
the tenant-wrapping `MockTenantIsolatedDatabase` convention `test_itam_catalog.py` and
friends use — that wrapper is precisely the accessor this feature must not go through, so
reusing it here would test the wrong code path. Instead the fake `get_database()` return
value exposes a `_db` attribute pointing directly at a small in-memory-store-backed
`system_settings` collection double, matching `itam_finance_test_support.py`'s
`self._db = raw_db_mock` convention (assigned as a real attribute, not routed through
`__getattr__`, so `db._db` resolves without waking a tenant-wrapping proxy).
"""
import sys
import os
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from httpx import AsyncClient, ASGITransport

from tests.conftest import make_test_app, make_token_data
from authentication_service import get_current_user as real_get_current_user


def _matches(doc: dict, filt: dict) -> bool:
    for key, value in filt.items():
        if isinstance(value, dict) and "$exists" in value:
            if (key in doc) != value["$exists"]:
                return False
        elif doc.get(key) != value:
            return False
    return True


class FakeSystemSettingsCollection:
    """Minimal in-memory-store-backed double for the raw `system_settings` collection —
    supports exactly the two operations `itam_customization_endpoints.py` performs
    (`find_one` with an `$exists` filter, `update_one` with `upsert=True`)."""

    def __init__(self):
        self.store: list = []

    async def find_one(self, filt: dict, projection=None):
        for doc in self.store:
            if _matches(doc, filt):
                result = dict(doc)
                result.pop("_id", None)
                return result
        return None

    async def update_one(self, filt: dict, update: dict, upsert: bool = False):
        set_fields = update.get("$set", {})
        for doc in self.store:
            if _matches(doc, filt):
                doc.update(set_fields)
                return MagicMock(matched_count=1)
        if upsert:
            new_doc = {k: v for k, v in filt.items() if not isinstance(v, dict)}
            new_doc.update(set_fields)
            self.store.append(new_doc)
            return MagicMock(matched_count=0, upserted_id=new_doc.get("tenantId"))
        return MagicMock(matched_count=0)


@pytest.fixture
def raw_db():
    db = MagicMock()
    db.system_settings = FakeSystemSettingsCollection()
    return db


@pytest.fixture
def settings_app(raw_db, monkeypatch):
    """Test FastAPI app mounting only itam_customization_endpoints.router, with
    get_database() patched at the module's own bound name (name-binding import) to return
    an object whose `._db` attribute is the raw fake collection above."""
    import itam_customization_endpoints as endpoints

    wrapper = SimpleNamespace(_db=raw_db)
    monkeypatch.setattr(endpoints, "get_database", lambda: wrapper)

    logged_calls: list = []

    async def _fake_log_itam_action(current_user, action, resource_type, resource_id, details, previous_state=None):
        logged_calls.append({
            "action": action,
            "resource_type": resource_type,
            "resource_id": resource_id,
            "details": details,
        })

    monkeypatch.setattr(endpoints, "log_itam_action", _fake_log_itam_action)

    app, _ = make_test_app(endpoints.router)
    return app, logged_calls


def _as(app, tenant_id="tenant-a", role="admin"):
    token = make_token_data(tenant_id=tenant_id, role=role)
    app.dependency_overrides[real_get_current_user] = lambda: token
    return token


class TestGetItamSettings:
    @pytest.mark.asyncio
    async def test_get_with_no_stored_document_returns_defaults(self, settings_app):
        app, _logged = settings_app
        _as(app)

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
            r = await ac.get("/api/itam/settings")
            assert r.status_code == 200, r.text
            data = r.json()
            assert data["branding"] == {"companyName": "", "logoUrl": "", "primaryColor": "#0891b2"}
            assert data["locale"] == "en"


class TestRoundTrip:
    @pytest.mark.asyncio
    async def test_post_then_get_round_trips_branding_fields(self, settings_app):
        app, logged = settings_app
        _as(app)

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
            payload = {
                "branding": {"companyName": "Acme Corp", "logoUrl": "https://example.com/logo.png", "primaryColor": "#ff00aa"},
                "locale": "en",
            }
            r = await ac.post("/api/itam/settings", json=payload)
            assert r.status_code == 200, r.text
            assert r.json()["branding"]["companyName"] == "Acme Corp"

            r2 = await ac.get("/api/itam/settings")
            assert r2.status_code == 200, r2.text
            data = r2.json()
            assert data["branding"]["companyName"] == "Acme Corp"
            assert data["branding"]["logoUrl"] == "https://example.com/logo.png"
            assert data["branding"]["primaryColor"] == "#ff00aa"


class TestAdminGate:
    @pytest.mark.asyncio
    async def test_non_admin_post_returns_403(self, settings_app):
        app, _logged = settings_app
        _as(app, role="User")

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
            r = await ac.post("/api/itam/settings", json={"branding": {"companyName": "Nope"}})
            assert r.status_code == 403, r.text


class TestGlobalFallback:
    @pytest.mark.asyncio
    async def test_get_falls_back_to_seeded_global_document(self, settings_app):
        """A global document (no `tenantId` field) is seeded directly on the fake
        collection's store — the route always writes a `tenantId` on save, so a
        no-`tenantId` global-fallback document must be seeded another way, exactly how it
        would be seeded by a migration or a dedicated global-save path."""
        app, _logged = settings_app

        import itam_customization_endpoints as endpoints
        wrapper = endpoints.get_database()
        wrapper._db.system_settings.store.append({
            "type": "itam_settings",
            "branding": {"companyName": "Global Co", "logoUrl": "", "primaryColor": "#123456"},
            "locale": "en",
        })

        _as(app, tenant_id="tenant-unconfigured", role="admin")
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
            r = await ac.get("/api/itam/settings")
            assert r.status_code == 200, r.text
            assert r.json()["branding"]["companyName"] == "Global Co"


@pytest.mark.asyncio
async def test_post_logs_one_itam_settings_update_action(settings_app):
    app, logged = settings_app
    _as(app)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        r = await ac.post("/api/itam/settings", json={"branding": {"companyName": "Audited Co"}})
        assert r.status_code == 200, r.text

    assert len(logged) == 1
    assert logged[0]["resource_type"] == "itam_settings"
    assert logged[0]["action"] == "itam_settings.update"


# ── Task 2: field-rejection and unexpected-key-stripping coverage ──────────────────────


class TestFieldRejection:
    @pytest.mark.asyncio
    async def test_logo_url_with_disallowed_scheme_rejected_with_400(self, settings_app):
        app, _logged = settings_app
        _as(app)

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
            r = await ac.post("/api/itam/settings", json={"branding": {"logoUrl": "javascript:alert(1)"}})
            assert r.status_code == 400, r.text
            problems = r.json()["detail"]["problems"]
            assert any("logoUrl" in p for p in problems)

    @pytest.mark.asyncio
    async def test_primary_color_not_six_hex_digits_rejected_with_400(self, settings_app):
        app, _logged = settings_app
        _as(app)

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
            r = await ac.post("/api/itam/settings", json={"branding": {"primaryColor": "blue"}})
            assert r.status_code == 400, r.text
            problems = r.json()["detail"]["problems"]
            assert any("primaryColor" in p for p in problems)

    @pytest.mark.asyncio
    async def test_company_name_over_cap_rejected_with_400(self, settings_app):
        app, _logged = settings_app
        _as(app)

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
            r = await ac.post("/api/itam/settings", json={"branding": {"companyName": "x" * 200}})
            assert r.status_code == 400, r.text
            problems = r.json()["detail"]["problems"]
            assert any("companyName" in p for p in problems)

    @pytest.mark.asyncio
    async def test_unexpected_top_level_key_not_persisted(self, settings_app):
        app, _logged = settings_app
        _as(app)

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
            r = await ac.post(
                "/api/itam/settings",
                json={"branding": {"companyName": "Acme"}, "unexpectedKey": "should-not-persist"},
            )
            assert r.status_code == 200, r.text
            assert "unexpectedKey" not in r.json()

            r2 = await ac.get("/api/itam/settings")
            assert "unexpectedKey" not in r2.json()

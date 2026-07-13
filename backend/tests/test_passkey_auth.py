"""Tests for Passkey (WebAuthn) Authentication (WF-01)."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import FastAPI
from fastapi.testclient import TestClient
from auth_types import TokenData
from authentication_service import get_current_user, create_access_token
from api_key_auth import get_current_user_or_api_key

# ─── helpers ─────────────────────────────────────────────────────────────────

def _col():
    col = MagicMock()
    col.find_one = AsyncMock(return_value=None)
    col.insert_one = AsyncMock(return_value=MagicMock(inserted_id="x"))
    col.update_one = AsyncMock(return_value=MagicMock(matched_count=1))
    # find().sort().to_list pattern
    col.find = MagicMock()
    col.find.return_value.sort = MagicMock(return_value=MagicMock())
    col.find.return_value.sort.return_value.to_list = AsyncMock(return_value=[])
    return col

def _db(tenants=_col(), users=_col()):
    db = MagicMock()
    db.tenants = tenants
    db.users = users
    return db

def _user(tenant="tenant-a", role="admin", username="user@tenant.com"):
    user = MagicMock(spec=TokenData)
    user.tenant_id = tenant
    user.role = role
    user.username = username
    return user

def _app(router_mod, user, db):
    app = FastAPI()
    app.include_router(router_mod.router)
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_current_user_or_api_key] = lambda: user # For webhook tests
    app.dependency_overrides[router_mod.get_database] = lambda: db # Assuming router uses get_database directly
    return app

# ─── tests ─────────────────────────────────────────────────────────────────

class TestPasskeyAuth:

    @pytest.fixture(autouse=True)
    def setup_mocks(self):
        self.db = _db()
        self.user_admin = _user(role="admin")
        self.user_basic = _user(role="user")

        # Patch mongodb.db.users for credential persistence
        self.patch_mongodb_users = patch('database.mongodb.db.users', new_callable=MagicMock, return_value=self.db.users)
        self.patch_mongodb_tenants = patch('database.mongodb.db.tenants', new_callable=MagicMock, return_value=self.db.tenants)

        self.patch_mongodb_users.start()
        self.patch_mongodb_tenants.start()
        yield
        self.patch_mongodb_users.stop()
        self.patch_mongodb_tenants.stop()

    @patch('passkey_service.webauthn.generate_registration_options', AsyncMock(return_value={"challenge": "reg_challenge"}))
    @patch('passkey_service.secrets.token_bytes', return_value=b'test_challenge_bytes')
    @patch('passkey_service.store_challenge', MagicMock())
    def test_build_registration_options(self, mock_store_challenge):
        from passkey_service import build_registration_options
        options = build_registration_options("user-123", "test@user.com", "Test User")
        assert options["challenge"] == "reg_challenge"
        mock_store_challenge.assert_called_once()

    @patch('passkey_service.webauthn.verify_registration_response', MagicMock())
    @patch('passkey_service.consume_challenge', return_value=b'test_challenge_bytes')
    def test_verify_and_store_registration(self, mock_consume_challenge):
        from passkey_service import verify_and_store_registration
        credential_response = {
            "id": "cred_id",
            "rawId": "cred_id",
            "type": "public-key",
            "response": {
                "clientDataJSON": "client_data_json",
                "attestationObject": "attestation_object",
            }
        }
        verify_and_store_registration(
            user_id="user-123",
            credential_response=credential_response,
            db=self.db,
            users_collection=self.db.users,
            tenant_id=self.user_admin.tenant_id
        )
        self.db.users.update_one.assert_called_once()

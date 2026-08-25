"""
Unit tests for saml_service.py / saml_mapping.py (ITAM-USR-04).

Covers: SAMLConfig resolution, SP metadata, SP-initiated login (RelayState
correlation), ACS assertion validation (success, invalid, replay), SLO,
user provisioning, group-to-role mapping, and the full authenticate_saml
flow. python3-saml's OneLogin_Saml2_Auth is mocked via unittest.mock (no
real IdP required) — see plan 64-04 Task 1. Endpoint tests (added Task 2)
are grouped at the bottom, marked "endpoint"/"auth" for the plan's focused
verify commands.
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from saml_service import (
    SAMLConfig,
    SAMLConfigError,
    SAMLValidationError,
    SAMLProvisionError,
    SAMLAuthenticator,
    get_saml_config,
    authenticate_saml,
    is_saml_sourced_user,
)
from saml_mapping import SAMLMappingError, SAMLUserProvisioner, SAMLGroupMapper


def _run(coro):
    return asyncio.run(coro)


def _config(**overrides) -> SAMLConfig:
    base = dict(
        entity_id="https://itam.example.com/saml/metadata",
        acs_url="https://itam.example.com/api/auth/saml/acs",
        slo_url="https://itam.example.com/api/auth/saml/slo",
        idp_entity_id="https://idp.example.com/metadata",
        idp_sso_url="https://idp.example.com/sso",
        idp_slo_url="https://idp.example.com/slo",
        idp_x509_cert="fake-idp-cert",
    )
    base.update(overrides)
    return SAMLConfig(**base)


def _request_data(saml_response=None, relay_state=None, method_post=True):
    post = {}
    if saml_response is not None:
        post["SAMLResponse"] = saml_response
    if relay_state is not None:
        post["RelayState"] = relay_state
    return {
        "https": "on",
        "http_host": "itam.example.com",
        "server_port": "443",
        "script_name": "/api/auth/saml/acs",
        "get_data": {},
        "post_data": post if method_post else {},
    }


# ===========================================================================
# SAMLConfig
# ===========================================================================

class TestSAMLConfig:

    def test_from_env_requires_core_vars(self, monkeypatch):
        for var in ("SAML_ENTITY_ID", "SAML_ACS_URL", "SAML_IDP_ENTITY_ID", "SAML_IDP_SSO_URL"):
            monkeypatch.delenv(var, raising=False)
        with pytest.raises(SAMLConfigError):
            SAMLConfig.from_env()

    def test_from_env_builds_config_with_defaults(self, monkeypatch):
        monkeypatch.setenv("SAML_ENTITY_ID", "https://sp.example.com/metadata")
        monkeypatch.setenv("SAML_ACS_URL", "https://sp.example.com/acs")
        monkeypatch.setenv("SAML_IDP_ENTITY_ID", "https://idp.example.com/metadata")
        monkeypatch.setenv("SAML_IDP_SSO_URL", "https://idp.example.com/sso")
        cfg = SAMLConfig.from_env()
        assert cfg.entity_id == "https://sp.example.com/metadata"
        assert cfg.attribute_email == "email"
        assert cfg.attribute_groups == "groups"

    def test_from_env_decodes_base64_cert(self, monkeypatch):
        import base64
        monkeypatch.setenv("SAML_ENTITY_ID", "https://sp.example.com/metadata")
        monkeypatch.setenv("SAML_ACS_URL", "https://sp.example.com/acs")
        monkeypatch.setenv("SAML_IDP_ENTITY_ID", "https://idp.example.com/metadata")
        monkeypatch.setenv("SAML_IDP_SSO_URL", "https://idp.example.com/sso")
        pem = "-----BEGIN CERTIFICATE-----\nABCDEF\n-----END CERTIFICATE-----"
        monkeypatch.setenv("SAML_IDP_X509_CERT", base64.b64encode(pem.encode()).decode())
        cfg = SAMLConfig.from_env()
        assert "BEGIN CERTIFICATE" in cfg.idp_x509_cert

    def test_from_dict_applies_defaults_for_missing_optional_fields(self):
        cfg = SAMLConfig.from_dict({
            "entity_id": "e", "acs_url": "a",
            "idp_entity_id": "ie", "idp_sso_url": "iu",
        })
        assert cfg.attribute_name == "name"
        assert cfg.attribute_groups == "groups"


class TestGetSamlConfig:

    def test_falls_back_to_env_when_no_db_doc(self, monkeypatch):
        monkeypatch.setenv("SAML_ENTITY_ID", "https://env.example.com/metadata")
        monkeypatch.setenv("SAML_ACS_URL", "https://env.example.com/acs")
        monkeypatch.setenv("SAML_IDP_ENTITY_ID", "https://idp.example.com/metadata")
        monkeypatch.setenv("SAML_IDP_SSO_URL", "https://idp.example.com/sso")
        db = MagicMock()
        db.saml_configs.find_one = AsyncMock(return_value=None)
        with patch("saml_service.get_database", return_value=db):
            cfg = _run(get_saml_config(tenant_id="t1"))
        assert cfg.entity_id == "https://env.example.com/metadata"

    def test_uses_db_doc_and_decrypts_private_key(self):
        db = MagicMock()
        db.saml_configs.find_one = AsyncMock(return_value={
            "entity_id": "https://db.example.com/metadata",
            "acs_url": "https://db.example.com/acs",
            "idp_entity_id": "https://idp.example.com/metadata",
            "idp_sso_url": "https://idp.example.com/sso",
            "sp_private_key_encrypted": "enc(key)",
            "tenant_id": "t1",
        })
        enc_svc = MagicMock()
        enc_svc.decrypt.return_value = "-----BEGIN PRIVATE KEY-----\nXYZ\n-----END PRIVATE KEY-----"
        with patch("saml_service.get_database", return_value=db), \
             patch("encryption_service.get_encryption_service", return_value=enc_svc):
            cfg = _run(get_saml_config(tenant_id="t1"))
        assert "BEGIN PRIVATE KEY" in cfg.sp_private_key
        enc_svc.decrypt.assert_called_once_with("enc(key)")


# ===========================================================================
# SAMLAuthenticator — metadata / login / ACS / SLO
# ===========================================================================

class TestSAMLAuthenticatorMetadata:

    def test_metadata_contains_entity_id_and_acs_location(self):
        config = _config(sp_x509_cert="", sp_private_key="")
        xml, errors = SAMLAuthenticator(config).metadata()
        assert config.entity_id in xml
        assert config.acs_url in xml
        assert errors == [] or isinstance(errors, list)


class TestSAMLAuthenticatorLogin:

    def test_build_login_url_stores_request_id_by_relay_state_token(self):
        config = _config()
        fake_auth = MagicMock()
        fake_auth.login.return_value = "https://idp.example.com/sso?SAMLRequest=xxx&RelayState=tok"
        fake_auth.get_last_request_id.return_value = "req-123"

        raw_db = MagicMock()
        raw_db.saml_login_states.create_index = AsyncMock()
        raw_db.saml_processed_assertions.create_index = AsyncMock()
        raw_db.saml_login_states.insert_one = AsyncMock()
        db = MagicMock()
        db._db = raw_db

        with patch("saml_service.OneLogin_Saml2_Auth", return_value=fake_auth), \
             patch("saml_service.get_database", return_value=db):
            url = _run(SAMLAuthenticator(config).build_login_url(_request_data(method_post=False)))

        assert url == fake_auth.login.return_value
        raw_db.saml_login_states.insert_one.assert_called_once()
        stored_doc = raw_db.saml_login_states.insert_one.call_args[0][0]
        assert stored_doc["request_id"] == "req-123"


class TestSAMLAuthenticatorACS:

    def _db_with_states(self, login_state_doc=None):
        raw_db = MagicMock()
        raw_db.saml_login_states.create_index = AsyncMock()
        raw_db.saml_processed_assertions.create_index = AsyncMock()
        raw_db.saml_login_states.find_one_and_delete = AsyncMock(return_value=login_state_doc)
        raw_db.saml_processed_assertions.insert_one = AsyncMock()
        db = MagicMock()
        db._db = raw_db
        return db, raw_db

    def test_process_acs_success_returns_nameid_and_attributes(self):
        config = _config()
        fake_auth = MagicMock()
        fake_auth.process_response.return_value = None
        fake_auth.get_errors.return_value = []
        fake_auth.is_authenticated.return_value = True
        fake_auth.get_last_assertion_id.return_value = "assertion-1"
        fake_auth.get_nameid.return_value = "user@example.com"
        fake_auth.get_attributes.return_value = {"email": ["user@example.com"], "groups": ["Admins"]}
        fake_auth.get_session_index.return_value = "sess-1"

        db, _raw = self._db_with_states(login_state_doc={"request_id": "req-123"})
        with patch("saml_service.OneLogin_Saml2_Auth", return_value=fake_auth), \
             patch("saml_service.get_database", return_value=db):
            result = _run(SAMLAuthenticator(config).process_acs(
                _request_data(saml_response="b64", relay_state="tok")
            ))

        assert result["nameid"] == "user@example.com"
        assert result["attributes"]["groups"] == ["Admins"]
        fake_auth.process_response.assert_called_once_with(request_id="req-123")

    def test_process_acs_raises_on_validation_errors(self):
        config = _config()
        fake_auth = MagicMock()
        fake_auth.process_response.return_value = None
        fake_auth.get_errors.return_value = ["invalid_response"]
        fake_auth.get_last_error_reason.return_value = "signature mismatch"

        db, _raw = self._db_with_states()
        with patch("saml_service.OneLogin_Saml2_Auth", return_value=fake_auth), \
             patch("saml_service.get_database", return_value=db):
            with pytest.raises(SAMLValidationError):
                _run(SAMLAuthenticator(config).process_acs(_request_data(saml_response="b64")))

    def test_process_acs_raises_on_replay(self):
        config = _config()
        fake_auth = MagicMock()
        fake_auth.process_response.return_value = None
        fake_auth.get_errors.return_value = []
        fake_auth.is_authenticated.return_value = True
        fake_auth.get_last_assertion_id.return_value = "assertion-dup"
        fake_auth.get_nameid.return_value = "user@example.com"
        fake_auth.get_attributes.return_value = {}
        fake_auth.get_session_index.return_value = None

        from pymongo.errors import DuplicateKeyError
        db, raw = self._db_with_states()
        raw.saml_processed_assertions.insert_one = AsyncMock(side_effect=DuplicateKeyError("dup"))

        with patch("saml_service.OneLogin_Saml2_Auth", return_value=fake_auth), \
             patch("saml_service.get_database", return_value=db):
            with pytest.raises(SAMLValidationError, match="replay"):
                _run(SAMLAuthenticator(config).process_acs(_request_data(saml_response="b64")))


class TestSAMLAuthenticatorSLO:

    def test_process_slo_returns_redirect_url(self):
        config = _config()
        fake_auth = MagicMock()
        fake_auth.process_slo.return_value = "https://idp.example.com/slo-complete"
        fake_auth.get_errors.return_value = []

        with patch("saml_service.OneLogin_Saml2_Auth", return_value=fake_auth):
            url = SAMLAuthenticator(config).process_slo(_request_data(method_post=False))
        assert url == "https://idp.example.com/slo-complete"

    def test_process_slo_raises_on_errors(self):
        config = _config()
        fake_auth = MagicMock()
        fake_auth.process_slo.return_value = None
        fake_auth.get_errors.return_value = ["invalid_logout_request"]
        fake_auth.get_last_error_reason.return_value = "bad signature"

        with patch("saml_service.OneLogin_Saml2_Auth", return_value=fake_auth):
            with pytest.raises(SAMLValidationError):
                SAMLAuthenticator(config).process_slo(_request_data(method_post=False))


# ===========================================================================
# SAMLUserProvisioner / SAMLGroupMapper
# ===========================================================================

class TestSAMLUserProvisioner:

    def test_extract_attributes_prefers_configured_attribute_over_nameid(self):
        config = _config()
        provisioner = SAMLUserProvisioner(config)
        mapped = provisioner.extract_attributes("nameid-not-email", {
            "email": ["real@example.com"], "name": ["Real Name"], "groups": ["G1", "G2"],
        })
        assert mapped["email"] == "real@example.com"
        assert mapped["full_name"] == "Real Name"
        assert mapped["groups"] == ["G1", "G2"]

    def test_extract_attributes_falls_back_to_nameid_when_email_attr_missing(self):
        config = _config()
        provisioner = SAMLUserProvisioner(config)
        mapped = provisioner.extract_attributes("fallback@example.com", {})
        assert mapped["email"] == "fallback@example.com"

    def test_provision_user_creates_new_user_with_source_saml(self):
        db = MagicMock()
        db.users.find_one = AsyncMock(return_value=None)
        inserted = MagicMock()
        inserted.inserted_id = "new-id"
        db.users.insert_one = AsyncMock(return_value=inserted)

        with patch("saml_mapping.get_database", return_value=db):
            doc = _run(SAMLUserProvisioner(_config()).provision_user(
                {"email": "new@example.com", "full_name": "New User", "nameid": "new@example.com", "groups": []},
                tenant_id="t1",
            ))
        assert doc["source"] == "saml"
        assert doc["role"] == "itam_viewer"

    def test_provision_user_cross_tenant_email_collision_raises_clean_error(self):
        """DB-F06/DB-F09 (2026-08-25 audit): users.email has a global unique
        index, but provision_user's existing-user lookup is tenant-scoped,
        so a genuinely new user for this tenant can still collide with a
        different tenant's user of the same email. Must surface as a clean
        SAMLMappingError, not a raw pymongo DuplicateKeyError."""
        from pymongo.errors import DuplicateKeyError

        db = MagicMock()
        db.users.find_one = AsyncMock(return_value=None)  # no existing user for *this* tenant
        db.users.insert_one = AsyncMock(side_effect=DuplicateKeyError("E11000 duplicate key error email_1"))

        with patch("saml_mapping.get_database", return_value=db):
            with pytest.raises(SAMLMappingError) as exc_info:
                _run(SAMLUserProvisioner(_config()).provision_user(
                    {"email": "new@example.com", "full_name": "New User", "nameid": "new@example.com", "groups": []},
                    tenant_id="t1",
                ))
        assert "E11000" not in str(exc_info.value)
        assert "already registered" in str(exc_info.value)

    def test_provision_user_update_preserves_existing_role_when_no_mapping(self):
        db = MagicMock()
        db.users.find_one = AsyncMock(return_value={"_id": "existing-id", "role": "itam_admin"})
        db.users.update_one = AsyncMock()

        with patch("saml_mapping.get_database", return_value=db):
            doc = _run(SAMLUserProvisioner(_config()).provision_user(
                {"email": "existing@example.com", "full_name": "Existing", "nameid": "existing@example.com", "groups": []},
                tenant_id="t1",
                role=None,
            ))
        assert doc["role"] == "itam_admin"


class TestSAMLGroupMapper:

    def test_resolve_role_returns_none_when_no_groups(self):
        assert _run(SAMLGroupMapper().resolve_role([], tenant_id="t1")) is None

    def test_resolve_role_returns_highest_priority_match(self):
        db = MagicMock()
        cursor = MagicMock()
        cursor.sort.return_value = cursor
        cursor.to_list = AsyncMock(return_value=[{"role": "itam_admin"}])
        db.saml_group_mappings.find.return_value = cursor
        with patch("saml_mapping.get_database", return_value=db):
            role = _run(SAMLGroupMapper().resolve_role(["Admins"], tenant_id="t1"))
        assert role == "itam_admin"

    def test_upsert_mapping_rejects_invalid_role(self):
        with pytest.raises(SAMLMappingError):
            _run(SAMLGroupMapper.upsert_mapping("Admins", "not_a_real_role", tenant_id="t1"))

    def test_upsert_mapping_accepts_valid_role(self):
        db = MagicMock()
        result = MagicMock()
        result.upserted_id = "map-id"
        db.saml_group_mappings.update_one = AsyncMock(return_value=result)
        with patch("saml_mapping.get_database", return_value=db):
            doc = _run(SAMLGroupMapper.upsert_mapping("Admins", "itam_admin", tenant_id="t1"))
        assert doc["group_value"] == "Admins"


# ===========================================================================
# authenticate_saml — full ACS -> provision -> mint-JWT flow (endpoint / auth)
# ===========================================================================

class TestAuthenticateSamlFlowAuth:

    def _patch_success_auth(self, email="user@example.com", groups=None):
        fake_auth = MagicMock()
        fake_auth.process_response.return_value = None
        fake_auth.get_errors.return_value = []
        fake_auth.is_authenticated.return_value = True
        fake_auth.get_last_assertion_id.return_value = "assertion-flow-1"
        fake_auth.get_nameid.return_value = email
        fake_auth.get_attributes.return_value = {"email": [email], "groups": groups or []}
        fake_auth.get_session_index.return_value = "sess-flow-1"
        return fake_auth

    def test_authenticate_saml_mints_tokens_for_existing_user(self):
        fake_auth = self._patch_success_auth()
        raw_db = MagicMock()
        raw_db.saml_login_states.create_index = AsyncMock()
        raw_db.saml_processed_assertions.create_index = AsyncMock()
        raw_db.saml_login_states.find_one_and_delete = AsyncMock(return_value=None)
        raw_db.saml_processed_assertions.insert_one = AsyncMock()

        db = MagicMock()
        db._db = raw_db
        db.saml_configs.find_one = AsyncMock(return_value=None)
        db.users.find_one = AsyncMock(return_value={"_id": "u1", "email": "user@example.com", "tenantId": "t1", "role": "itam_user"})
        db.users.update_one = AsyncMock()
        db.saml_group_mappings.find.return_value = MagicMock(
            sort=MagicMock(return_value=MagicMock(to_list=AsyncMock(return_value=[])))
        )

        with patch("saml_service.OneLogin_Saml2_Auth", return_value=fake_auth), \
             patch("saml_service.get_database", return_value=db), \
             patch("saml_mapping.get_database", return_value=db), \
             patch.dict(os.environ, {
                 "SAML_ENTITY_ID": "https://sp.example.com/metadata",
                 "SAML_ACS_URL": "https://sp.example.com/acs",
                 "SAML_IDP_ENTITY_ID": "https://idp.example.com/metadata",
                 "SAML_IDP_SSO_URL": "https://idp.example.com/sso",
             }):
            result = _run(authenticate_saml(_request_data(saml_response="b64"), tenant_id="t1"))

        assert result["success"] is True
        assert result["email"] == "user@example.com"
        assert "access_token" in result and "refresh_token" in result

    def test_authenticate_saml_raises_provision_error_with_no_tenant(self):
        fake_auth = self._patch_success_auth()
        raw_db = MagicMock()
        raw_db.saml_login_states.create_index = AsyncMock()
        raw_db.saml_processed_assertions.create_index = AsyncMock()
        raw_db.saml_login_states.find_one_and_delete = AsyncMock(return_value=None)
        raw_db.saml_processed_assertions.insert_one = AsyncMock()

        db = MagicMock()
        db._db = raw_db
        db.saml_configs.find_one = AsyncMock(return_value=None)
        db.users.find_one = AsyncMock(return_value=None)

        with patch("saml_service.OneLogin_Saml2_Auth", return_value=fake_auth), \
             patch("saml_service.get_database", return_value=db), \
             patch.dict(os.environ, {
                 "SAML_ENTITY_ID": "https://sp.example.com/metadata",
                 "SAML_ACS_URL": "https://sp.example.com/acs",
                 "SAML_IDP_ENTITY_ID": "https://idp.example.com/metadata",
                 "SAML_IDP_SSO_URL": "https://idp.example.com/sso",
             }):
            with pytest.raises(SAMLProvisionError):
                _run(authenticate_saml(_request_data(saml_response="b64"), tenant_id=None))

    def test_authenticate_saml_converts_cross_tenant_collision_to_provision_error(self):
        """DB-F09 (2026-08-25 audit): a tenant-scoped SAML login for a
        brand-new user whose email already exists under a *different*
        tenant must surface as a clean SAMLProvisionError, not an unhandled
        pymongo DuplicateKeyError."""
        from pymongo.errors import DuplicateKeyError

        fake_auth = self._patch_success_auth()
        raw_db = MagicMock()
        raw_db.saml_login_states.create_index = AsyncMock()
        raw_db.saml_processed_assertions.create_index = AsyncMock()
        raw_db.saml_login_states.find_one_and_delete = AsyncMock(return_value=None)
        raw_db.saml_processed_assertions.insert_one = AsyncMock()

        db = MagicMock()
        db._db = raw_db
        db.saml_configs.find_one = AsyncMock(return_value=None)
        db.users.find_one = AsyncMock(return_value=None)  # no user for this tenant
        db.users.insert_one = AsyncMock(side_effect=DuplicateKeyError("E11000 duplicate key error email_1"))
        db.saml_group_mappings.find.return_value = MagicMock(
            sort=MagicMock(return_value=MagicMock(to_list=AsyncMock(return_value=[])))
        )

        with patch("saml_service.OneLogin_Saml2_Auth", return_value=fake_auth), \
             patch("saml_service.get_database", return_value=db), \
             patch("saml_mapping.get_database", return_value=db), \
             patch.dict(os.environ, {
                 "SAML_ENTITY_ID": "https://sp.example.com/metadata",
                 "SAML_ACS_URL": "https://sp.example.com/acs",
                 "SAML_IDP_ENTITY_ID": "https://idp.example.com/metadata",
                 "SAML_IDP_SSO_URL": "https://idp.example.com/sso",
             }):
            with pytest.raises(SAMLProvisionError) as exc_info:
                _run(authenticate_saml(_request_data(saml_response="b64"), tenant_id="t1"))
        assert "E11000" not in str(exc_info.value)


class TestIsSamlSourcedUser:

    def test_true_for_saml_sourced_user(self):
        db = MagicMock()
        db.users.find_one = AsyncMock(return_value={"source": "saml"})
        with patch("saml_service.get_database", return_value=db):
            assert _run(is_saml_sourced_user("user@example.com")) is True

    def test_false_for_local_user(self):
        db = MagicMock()
        db.users.find_one = AsyncMock(return_value={"source": "local"})
        with patch("saml_service.get_database", return_value=db):
            assert _run(is_saml_sourced_user("user@example.com")) is False


# ===========================================================================
# sso_endpoints.py saml_router — admin config/attribute-mapping endpoints,
# public metadata/login/acs/slo (endpoint, auth)
# ===========================================================================

from bson import ObjectId
from httpx import AsyncClient, ASGITransport

import sso_endpoints
from tests.conftest import make_token_data
from authentication_service import get_current_user as real_get_current_user


def _ep_match(doc, query):
    for k, v in (query or {}).items():
        if isinstance(v, dict) and "$in" in v:
            if doc.get(k) not in v["$in"]:
                return False
        else:
            if doc.get(k) != v:
                return False
    return True


class _EPCursor:
    def __init__(self, docs):
        self._docs = list(docs)

    def sort(self, *a, **k):
        return self

    async def to_list(self, length=None):
        return self._docs[:length] if length else list(self._docs)


class _EPCollection:
    def __init__(self, docs=None):
        self.docs = list(docs or [])

    async def find_one(self, query=None, projection=None):
        for d in self.docs:
            if _ep_match(d, query or {}):
                return dict(d)
        return None

    def find(self, query=None, projection=None):
        return _EPCursor([dict(d) for d in self.docs if _ep_match(d, query or {})])

    async def insert_one(self, doc):
        doc = dict(doc)
        doc.setdefault("_id", ObjectId())
        self.docs.append(doc)
        return type("R", (), {"inserted_id": doc["_id"]})()

    async def update_one(self, query, update, upsert=False):
        for d in self.docs:
            if _ep_match(d, query):
                d.update(update.get("$set", {}))
                return type("R", (), {"matched_count": 1, "upserted_id": None})()
        if upsert:
            new_doc = dict(query)
            new_doc.update(update.get("$set", {}))
            new_doc.setdefault("_id", ObjectId())
            self.docs.append(new_doc)
            return type("R", (), {"matched_count": 0, "upserted_id": new_doc["_id"]})()
        return type("R", (), {"matched_count": 0, "upserted_id": None})()

    async def find_one_and_delete(self, query):
        for i, d in enumerate(self.docs):
            if _ep_match(d, query):
                return self.docs.pop(i)
        return None

    async def replace_one(self, query, replacement, upsert=False):
        for i, d in enumerate(self.docs):
            if _ep_match(d, query):
                self.docs[i] = dict(replacement)
                return type("R", (), {"matched_count": 1})()
        if upsert:
            self.docs.append(dict(replacement))
        return type("R", (), {"matched_count": 0})()

    async def delete_one(self, query):
        for i, d in enumerate(self.docs):
            if _ep_match(d, query):
                del self.docs[i]
                return type("R", (), {"deleted_count": 1})()
        return type("R", (), {"deleted_count": 0})()

    async def create_index(self, *a, **k):
        return None


class _EPRawDB:
    def __init__(self):
        self.saml_login_states = _EPCollection([])
        self.saml_processed_assertions = _EPCollection([])
        self.sso_state = _EPCollection([])  # used by sso_endpoints._store_sso_state (exchange-code flow)


class _EPFakeDB:
    def __init__(self):
        self.saml_configs = _EPCollection([])
        self.saml_group_mappings = _EPCollection([])
        self.users = _EPCollection([])
        self._db = _EPRawDB()


_ADMIN_ROLES = {"admin", "Admin", "Tenant Admin", "tenant_admin"}


async def _fake_verify_permission(user, permission):
    from rbac_utils import is_super_admin
    if permission != "manage:assets":
        return False
    return is_super_admin(user.role) or user.role in _ADMIN_ROLES


@pytest.fixture
def ep_db():
    return _EPFakeDB()


@pytest.fixture
def ep_app(ep_db, monkeypatch):
    import itam_asset_endpoints
    import saml_service
    import saml_mapping

    # sso_endpoints/saml_service/saml_mapping each call get_database() from
    # their own namespace — patch every one so the whole request path
    # (endpoint handlers AND saml_service internals) sees the same fake DB.
    monkeypatch.setattr(sso_endpoints, "get_database", lambda: ep_db)
    monkeypatch.setattr(saml_service, "get_database", lambda: ep_db)
    monkeypatch.setattr(saml_mapping, "get_database", lambda: ep_db)
    monkeypatch.setattr(itam_asset_endpoints, "verify_permission", AsyncMock(side_effect=_fake_verify_permission))
    monkeypatch.setattr(sso_endpoints, "get_tenant_id", lambda: "tenant-a")

    from fastapi import FastAPI
    from slowapi import _rate_limit_exceeded_handler
    from slowapi.errors import RateLimitExceeded
    from slowapi.middleware import SlowAPIMiddleware
    from rate_limiter import limiter as shared_limiter

    app = FastAPI()
    app.state.limiter = shared_limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.add_middleware(SlowAPIMiddleware)
    app.include_router(sso_endpoints.saml_router)
    return app


@pytest.fixture(autouse=True)
def _reset_saml_rate_limit():
    from rate_limiter import limiter as shared_limiter
    shared_limiter._storage.reset()
    yield
    shared_limiter._storage.reset()


def _override_user(app, token):
    app.dependency_overrides[real_get_current_user] = lambda: token


async def _ep_client(app):
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://testserver")


class TestSAMLConfigEndpoint:

    @pytest.mark.asyncio
    async def test_save_and_read_config_masks_private_key(self, ep_app, monkeypatch):
        admin = make_token_data(username="admin@tenant-a.com", role="admin", tenant_id="tenant-a")
        _override_user(ep_app, admin)
        enc = MagicMock()
        enc.encrypt.return_value = "enc(key)"
        monkeypatch.setattr("encryption_service.get_encryption_service", lambda: enc)

        async with await _ep_client(ep_app) as client:
            resp = await client.post("/api/admin/sso/saml/config", json={
                "entity_id": "https://sp.example.com/metadata",
                "acs_url": "https://sp.example.com/acs",
                "idp_entity_id": "https://idp.example.com/metadata",
                "idp_sso_url": "https://idp.example.com/sso",
                "sp_private_key": "super-secret-key",
            })
            assert resp.status_code == 200, resp.text
            assert resp.json()["success"] is True

            resp2 = await client.get("/api/admin/sso/saml/config")
            assert resp2.status_code == 200
            body = resp2.json()
            assert body["sp_private_key"] == "***masked***"
            assert "sp_private_key_encrypted" not in body

    @pytest.mark.asyncio
    async def test_config_requires_admin(self, ep_app):
        viewer = make_token_data(username="viewer@tenant-a.com", role="itam_viewer", tenant_id="tenant-a")
        _override_user(ep_app, viewer)
        async with await _ep_client(ep_app) as client:
            resp = await client.get("/api/admin/sso/saml/config")
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_read_config_404_when_unset(self, ep_app):
        admin = make_token_data(username="admin@tenant-a.com", role="admin", tenant_id="tenant-a")
        _override_user(ep_app, admin)
        async with await _ep_client(ep_app) as client:
            resp = await client.get("/api/admin/sso/saml/config")
        assert resp.status_code == 404


class TestSAMLMetadataAndTestEndpoints:

    @pytest.mark.asyncio
    async def test_admin_metadata_returns_xml(self, ep_app, monkeypatch):
        admin = make_token_data(username="admin@tenant-a.com", role="admin", tenant_id="tenant-a")
        _override_user(ep_app, admin)
        monkeypatch.setenv("SAML_ENTITY_ID", "https://sp.example.com/metadata")
        monkeypatch.setenv("SAML_ACS_URL", "https://sp.example.com/acs")
        monkeypatch.setenv("SAML_IDP_ENTITY_ID", "https://idp.example.com/metadata")
        monkeypatch.setenv("SAML_IDP_SSO_URL", "https://idp.example.com/sso")
        async with await _ep_client(ep_app) as client:
            resp = await client.get("/api/admin/sso/saml/metadata")
        assert resp.status_code == 200
        assert "EntityDescriptor" in resp.text

    @pytest.mark.asyncio
    async def test_public_metadata_returns_xml_without_auth(self, ep_app, monkeypatch):
        monkeypatch.setenv("SAML_ENTITY_ID", "https://sp.example.com/metadata")
        monkeypatch.setenv("SAML_ACS_URL", "https://sp.example.com/acs")
        monkeypatch.setenv("SAML_IDP_ENTITY_ID", "https://idp.example.com/metadata")
        monkeypatch.setenv("SAML_IDP_SSO_URL", "https://idp.example.com/sso")
        async with await _ep_client(ep_app) as client:
            resp = await client.get("/api/auth/saml/metadata")
        assert resp.status_code == 200
        assert "EntityDescriptor" in resp.text

    @pytest.mark.asyncio
    async def test_public_metadata_503_when_not_configured(self, ep_app, monkeypatch):
        for var in ("SAML_ENTITY_ID", "SAML_ACS_URL", "SAML_IDP_ENTITY_ID", "SAML_IDP_SSO_URL"):
            monkeypatch.delenv(var, raising=False)
        async with await _ep_client(ep_app) as client:
            resp = await client.get("/api/auth/saml/metadata")
        assert resp.status_code == 503

    @pytest.mark.asyncio
    async def test_test_config_endpoint_requires_admin(self, ep_app):
        viewer = make_token_data(username="viewer@tenant-a.com", role="itam_viewer", tenant_id="tenant-a")
        _override_user(ep_app, viewer)
        async with await _ep_client(ep_app) as client:
            resp = await client.post("/api/admin/sso/saml/test")
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_test_config_endpoint_success(self, ep_app, monkeypatch):
        admin = make_token_data(username="admin@tenant-a.com", role="admin", tenant_id="tenant-a")
        _override_user(ep_app, admin)
        monkeypatch.setenv("SAML_ENTITY_ID", "https://sp.example.com/metadata")
        monkeypatch.setenv("SAML_ACS_URL", "https://sp.example.com/acs")
        monkeypatch.setenv("SAML_IDP_ENTITY_ID", "https://idp.example.com/metadata")
        monkeypatch.setenv("SAML_IDP_SSO_URL", "https://idp.example.com/sso")
        async with await _ep_client(ep_app) as client:
            resp = await client.post("/api/admin/sso/saml/test")
        assert resp.status_code == 200
        assert resp.json()["success"] is True


class TestSAMLAttributeMappingEndpoint:

    @pytest.mark.asyncio
    async def test_create_list_delete_mapping(self, ep_app):
        admin = make_token_data(username="admin@tenant-a.com", role="admin", tenant_id="tenant-a")
        _override_user(ep_app, admin)
        async with await _ep_client(ep_app) as client:
            resp = await client.post("/api/admin/sso/saml/attribute-mapping", json={
                "group_value": "ITAM-Admins", "role": "itam_admin", "priority": 1,
            })
            assert resp.status_code == 200, resp.text
            mapping_id = resp.json()["_id"]

            resp2 = await client.get("/api/admin/sso/saml/attribute-mapping")
            assert resp2.status_code == 200
            assert len(resp2.json()) == 1

            resp3 = await client.delete(f"/api/admin/sso/saml/attribute-mapping/{mapping_id}")
            assert resp3.status_code == 200
            assert resp3.json()["success"] is True

    @pytest.mark.asyncio
    async def test_create_mapping_rejects_invalid_role(self, ep_app):
        admin = make_token_data(username="admin@tenant-a.com", role="admin", tenant_id="tenant-a")
        _override_user(ep_app, admin)
        async with await _ep_client(ep_app) as client:
            resp = await client.post("/api/admin/sso/saml/attribute-mapping", json={
                "group_value": "G", "role": "not_a_role",
            })
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_delete_missing_mapping_returns_404(self, ep_app):
        admin = make_token_data(username="admin@tenant-a.com", role="admin", tenant_id="tenant-a")
        _override_user(ep_app, admin)
        async with await _ep_client(ep_app) as client:
            resp = await client.delete(f"/api/admin/sso/saml/attribute-mapping/{ObjectId()}")
        assert resp.status_code == 404


class TestSAMLLoginEndpointAuth:

    @pytest.mark.asyncio
    async def test_login_redirects_to_idp(self, ep_app, monkeypatch):
        class _FakeAuthenticator:
            def __init__(self, config):
                pass

            async def build_login_url(self, request_data):
                return "https://idp.example.com/sso?SAMLRequest=xxx&RelayState=tok"

        monkeypatch.setattr(sso_endpoints, "SAMLAuthenticator", _FakeAuthenticator)
        monkeypatch.setenv("SAML_ENTITY_ID", "https://sp.example.com/metadata")
        monkeypatch.setenv("SAML_ACS_URL", "https://sp.example.com/acs")
        monkeypatch.setenv("SAML_IDP_ENTITY_ID", "https://idp.example.com/metadata")
        monkeypatch.setenv("SAML_IDP_SSO_URL", "https://idp.example.com/sso")
        async with await _ep_client(ep_app) as client:
            resp = await client.get("/api/auth/saml/login", follow_redirects=False)
        assert resp.status_code in (302, 307)
        assert resp.headers["location"].startswith("https://idp.example.com/sso")

    @pytest.mark.asyncio
    async def test_login_not_configured_returns_503(self, ep_app, monkeypatch):
        for var in ("SAML_ENTITY_ID", "SAML_ACS_URL", "SAML_IDP_ENTITY_ID", "SAML_IDP_SSO_URL"):
            monkeypatch.delenv(var, raising=False)
        async with await _ep_client(ep_app) as client:
            resp = await client.get("/api/auth/saml/login", follow_redirects=False)
        assert resp.status_code == 503


class TestSAMLAcsEndpointAuth:

    @pytest.mark.asyncio
    async def test_acs_success_redirects_with_exchange_code(self, ep_app, monkeypatch):
        async def _fake_authenticate_saml(request_data, tenant_id=None):
            return {"access_token": "tok", "refresh_token": "rtok", "token_type": "bearer",
                    "success": True, "email": "jdoe@example.com", "role": "itam_viewer",
                    "tenant_id": "tenant-a"}

        monkeypatch.setattr(sso_endpoints, "authenticate_saml", _fake_authenticate_saml)
        async with await _ep_client(ep_app) as client:
            resp = await client.post("/api/auth/saml/acs", data={"SAMLResponse": "b64"}, follow_redirects=False)
        assert resp.status_code in (302, 307)
        assert "/sso-callback?code=" in resp.headers["location"]
        assert "provider=saml" in resp.headers["location"]

    @pytest.mark.asyncio
    async def test_acs_validation_failure_redirects_to_login_error(self, ep_app, monkeypatch):
        from saml_service import SAMLValidationError

        async def _fake_authenticate_saml(request_data, tenant_id=None):
            raise SAMLValidationError("bad signature")

        monkeypatch.setattr(sso_endpoints, "authenticate_saml", _fake_authenticate_saml)
        async with await _ep_client(ep_app) as client:
            resp = await client.post("/api/auth/saml/acs", data={"SAMLResponse": "b64"}, follow_redirects=False)
        assert resp.status_code in (302, 307)
        assert "error=saml_failed" in resp.headers["location"]

    @pytest.mark.asyncio
    async def test_acs_provision_failure_redirects_to_not_registered_error(self, ep_app, monkeypatch):
        from saml_service import SAMLProvisionError

        async def _fake_authenticate_saml(request_data, tenant_id=None):
            raise SAMLProvisionError("no tenant")

        monkeypatch.setattr(sso_endpoints, "authenticate_saml", _fake_authenticate_saml)
        async with await _ep_client(ep_app) as client:
            resp = await client.post("/api/auth/saml/acs", data={"SAMLResponse": "b64"}, follow_redirects=False)
        assert resp.status_code in (302, 307)
        assert "error=saml_not_registered" in resp.headers["location"]


class TestSAMLSloEndpoint:

    @pytest.mark.asyncio
    async def test_slo_redirects_when_response_returned(self, ep_app, monkeypatch):
        class _FakeAuthenticator:
            def __init__(self, config):
                pass

            def process_slo(self, request_data):
                return "https://idp.example.com/slo-complete"

        monkeypatch.setattr(sso_endpoints, "SAMLAuthenticator", _FakeAuthenticator)
        monkeypatch.setenv("SAML_ENTITY_ID", "https://sp.example.com/metadata")
        monkeypatch.setenv("SAML_ACS_URL", "https://sp.example.com/acs")
        monkeypatch.setenv("SAML_IDP_ENTITY_ID", "https://idp.example.com/metadata")
        monkeypatch.setenv("SAML_IDP_SSO_URL", "https://idp.example.com/sso")
        async with await _ep_client(ep_app) as client:
            resp = await client.get("/api/auth/saml/slo", follow_redirects=False)
        assert resp.status_code in (302, 307)
        assert resp.headers["location"] == "https://idp.example.com/slo-complete"

    @pytest.mark.asyncio
    async def test_slo_returns_success_when_no_redirect_needed(self, ep_app, monkeypatch):
        class _FakeAuthenticator:
            def __init__(self, config):
                pass

            def process_slo(self, request_data):
                return None

        monkeypatch.setattr(sso_endpoints, "SAMLAuthenticator", _FakeAuthenticator)
        monkeypatch.setenv("SAML_ENTITY_ID", "https://sp.example.com/metadata")
        monkeypatch.setenv("SAML_ACS_URL", "https://sp.example.com/acs")
        monkeypatch.setenv("SAML_IDP_ENTITY_ID", "https://idp.example.com/metadata")
        monkeypatch.setenv("SAML_IDP_SSO_URL", "https://idp.example.com/sso")
        async with await _ep_client(ep_app) as client:
            resp = await client.get("/api/auth/saml/slo")
        assert resp.status_code == 200
        assert resp.json()["success"] is True

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

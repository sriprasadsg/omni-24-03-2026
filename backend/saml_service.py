"""SAML 2.0 Service Provider integration (ITAM-USR-04).

Replaces the demo-stub SAML block that used to live in sso_service.py
(metadata-only, no real assertion validation — see RESEARCH.md Q1) with a
full SP implementation built on python3-saml's OneLogin_Saml2_Auth
(human-approved via the plan's blocking checkpoint).

Provides:
 - SAMLConfig: configuration resolved from environment variables or an
   admin-saved MongoDB document (POST /api/admin/sso/saml/config).
 - SAMLAuthenticator: SP metadata, SP-initiated AuthnRequest (login),
   ACS assertion validation (signature, audience, NotBefore/NotOnOrAfter,
   InResponseTo via a short-lived RelayState-token correlation store, plus
   an independent assertion-ID replay cache — T-64-13), and SLO handling.
 - authenticate_saml(): the full ACS -> provision -> mint-JWT flow, reusing
   authentication_service.create_access_token/create_refresh_token rather
   than duplicating token-minting logic (mirrors ldap_service.authenticate_ldap).
 - is_saml_sourced_user(): used to block local password changes for
   SAML-sourced users (Pitfall 4 / T-64-17), mirroring ldap_service's
   is_ldap_sourced_user.

Group/attribute-to-role mapping (SAMLUserProvisioner, SAMLGroupMapper)
lives in saml_mapping.py — split out up front per this plan's
<module_budget> to keep this file under the CLAUDE.md 500-line cap.

All python3-saml calls are synchronous (no native asyncio support); the
ones that do meaningful CPU/IO work here are cheap (in-memory XML parsing
of a single assertion), so they are called directly rather than wrapped in
asyncio.to_thread() — consistent with the library's typical WSGI usage.
"""
import base64
import logging
import os
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from onelogin.saml2.auth import OneLogin_Saml2_Auth
from onelogin.saml2.settings import OneLogin_Saml2_Settings

from database import get_database

logger = logging.getLogger(__name__)


# ─── Exceptions ──────────────────────────────────────────────────────────────

class SAMLConfigError(Exception):
    """SAML configuration is missing or invalid."""


class SAMLValidationError(Exception):
    """An ACS/SLO SAML message failed validation (signature, audience,
    timestamp, or replay check)."""


class SAMLProvisionError(Exception):
    """A validated assertion could not be provisioned into a local user."""


# ─── Config ──────────────────────────────────────────────────────────────────

def _maybe_b64_decode(value: Optional[str]) -> Optional[str]:
    """Certs/keys are documented (user_setup) as base64-encoded PEM blocks —
    a common way to store multi-line PEM text in a single-line env var.
    Accept either the already-decoded PEM text or the base64 wrapper."""
    if not value:
        return value
    stripped = value.strip()
    if "BEGIN CERTIFICATE" in stripped or "PRIVATE KEY" in stripped:
        return stripped
    try:
        decoded = base64.b64decode(stripped, validate=True).decode("utf-8")
        return decoded
    except Exception:
        return stripped


@dataclass
class SAMLConfig:
    entity_id: str
    acs_url: str
    slo_url: str
    idp_entity_id: str
    idp_sso_url: str
    idp_slo_url: str = ""
    idp_x509_cert: str = ""
    sp_x509_cert: str = ""
    sp_private_key: str = ""
    attribute_email: str = "email"
    attribute_name: str = "name"
    attribute_groups: str = "groups"

    @classmethod
    def from_env(cls) -> "SAMLConfig":
        entity_id = os.getenv("SAML_ENTITY_ID", "")
        acs_url = os.getenv("SAML_ACS_URL", "")
        idp_entity_id = os.getenv("SAML_IDP_ENTITY_ID", "")
        idp_sso_url = os.getenv("SAML_IDP_SSO_URL", "")
        if not entity_id or not acs_url or not idp_entity_id or not idp_sso_url:
            raise SAMLConfigError(
                "SAML is not configured: SAML_ENTITY_ID, SAML_ACS_URL, "
                "SAML_IDP_ENTITY_ID, and SAML_IDP_SSO_URL are required "
                "(set env vars, or configure via POST /api/admin/sso/saml/config)."
            )
        return cls(
            entity_id=entity_id,
            acs_url=acs_url,
            slo_url=os.getenv("SAML_SLO_URL", ""),
            idp_entity_id=idp_entity_id,
            idp_sso_url=idp_sso_url,
            idp_slo_url=os.getenv("SAML_IDP_SLO_URL", ""),
            idp_x509_cert=_maybe_b64_decode(os.getenv("SAML_IDP_X509_CERT")) or "",
            sp_x509_cert=_maybe_b64_decode(os.getenv("SAML_SP_X509_CERT")) or "",
            sp_private_key=_maybe_b64_decode(os.getenv("SAML_SP_PRIVATE_KEY")) or "",
        )

    @classmethod
    def from_dict(cls, d: dict) -> "SAMLConfig":
        return cls(
            entity_id=d.get("entity_id", ""),
            acs_url=d.get("acs_url", ""),
            slo_url=d.get("slo_url") or "",
            idp_entity_id=d.get("idp_entity_id", ""),
            idp_sso_url=d.get("idp_sso_url", ""),
            idp_slo_url=d.get("idp_slo_url") or "",
            idp_x509_cert=_maybe_b64_decode(d.get("idp_x509_cert")) or "",
            sp_x509_cert=_maybe_b64_decode(d.get("sp_x509_cert")) or "",
            sp_private_key=_maybe_b64_decode(d.get("sp_private_key")) or "",
            attribute_email=d.get("attribute_email") or "email",
            attribute_name=d.get("attribute_name") or "name",
            attribute_groups=d.get("attribute_groups") or "groups",
        )


async def get_saml_config(tenant_id: Optional[str] = None) -> SAMLConfig:
    """Resolve SAML config: an admin-saved MongoDB document takes precedence
    over environment variables (mirrors ldap_service.get_ldap_config).
    `tenant_id=None` is the platform-wide default config; a tenant-scoped
    lookup that finds nothing falls back to the platform default, then env."""
    db = get_database()
    doc = await db.saml_configs.find_one({"tenant_id": tenant_id})
    if not doc and tenant_id is not None:
        doc = await db.saml_configs.find_one({"tenant_id": None})
    if doc:
        sp_private_key = ""
        if doc.get("sp_private_key_encrypted"):
            from encryption_service import get_encryption_service
            sp_private_key = get_encryption_service().decrypt(doc["sp_private_key_encrypted"])
        return SAMLConfig.from_dict({**doc, "sp_private_key": sp_private_key})
    return SAMLConfig.from_env()


def _build_settings_dict(config: SAMLConfig) -> dict:
    """Translate SAMLConfig into the python3-saml settings dict. Requests
    are signed only when an SP private key is configured; assertions are
    always required to be signed by the IdP (T-64-13/T-64-18)."""
    return {
        "strict": True,
        "debug": False,
        "sp": {
            "entityId": config.entity_id,
            "assertionConsumerService": {
                "url": config.acs_url,
                "binding": "urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST",
            },
            "singleLogoutService": {
                "url": config.slo_url or config.acs_url,
                "binding": "urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect",
            },
            "NameIDFormat": "urn:oasis:names:tc:SAML:1.1:nameid-format:emailAddress",
            "x509cert": config.sp_x509_cert,
            "privateKey": config.sp_private_key,
        },
        "idp": {
            "entityId": config.idp_entity_id,
            "singleSignOnService": {
                "url": config.idp_sso_url,
                "binding": "urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect",
            },
            "singleLogoutService": {
                "url": config.idp_slo_url or config.idp_sso_url,
                "binding": "urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect",
            },
            "x509cert": config.idp_x509_cert,
        },
        "security": {
            "authnRequestsSigned": bool(config.sp_private_key and config.sp_x509_cert),
            "logoutRequestSigned": bool(config.sp_private_key and config.sp_x509_cert),
            "logoutResponseSigned": bool(config.sp_private_key and config.sp_x509_cert),
            "wantAssertionsSigned": True,
            "wantMessagesSigned": False,
            "wantNameIdEncrypted": False,
            "requestedAuthnContext": False,
        },
    }


async def _build_request_data(request) -> dict:
    """Build the request-data dict python3-saml needs from a FastAPI Request."""
    form: dict = {}
    if request.method == "POST":
        try:
            form = dict(await request.form())
        except Exception:
            form = {}
    url = request.url
    return {
        "https": "on" if url.scheme == "https" else "off",
        "http_host": url.hostname or "",
        "server_port": str(url.port or (443 if url.scheme == "https" else 80)),
        "script_name": url.path,
        "get_data": dict(request.query_params),
        "post_data": form,
    }


# ─── Login-state (InResponseTo correlation) + replay cache ────────────────────
# Both are short-lived MongoDB TTL collections, matching the pattern already
# used by sso_endpoints.py's sso_state collection and ldap's group-mapping store.

_LOGIN_STATE_TTL_SECONDS = 300  # 5 minutes — long enough for an IdP redirect round trip
_REPLAY_CACHE_TTL_SECONDS = 3600  # 1 hour — longer than any reasonable assertion clock skew

_saml_indexes_created = False


async def _saml_raw_db():
    """Return the raw (non-tenant-isolated) db handle for the TTL collections
    below — these are keyed by opaque tokens/assertion IDs, not tenant data."""
    global _saml_indexes_created
    db = get_database()
    raw = db._db
    if not _saml_indexes_created:
        await raw.saml_login_states.create_index("expires_at", expireAfterSeconds=0)
        await raw.saml_processed_assertions.create_index("expires_at", expireAfterSeconds=0)
        _saml_indexes_created = True
    return raw


async def _store_login_state(token: str, request_id: str) -> None:
    """Store the AuthnRequest ID issued at SP-initiated login, keyed by an
    opaque token that is sent to the IdP as RelayState and echoed back on
    the ACS POST — this is what lets us correlate InResponseTo (T-64-13)."""
    raw = await _saml_raw_db()
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=_LOGIN_STATE_TTL_SECONDS)
    await raw.saml_login_states.insert_one({"_id": token, "request_id": request_id, "expires_at": expires_at})


async def _pop_login_state(token: Optional[str]) -> Optional[str]:
    """Consume and return the stored request_id for a RelayState token, or
    None for an unsolicited (IdP-initiated) response — no InResponseTo check
    is performed in that case, matching the SAML spec."""
    if not token:
        return None
    raw = await _saml_raw_db()
    doc = await raw.saml_login_states.find_one_and_delete({"_id": token})
    return doc.get("request_id") if doc else None


async def _check_replay(assertion_id: Optional[str]) -> bool:
    """Returns True if this is the first time this assertion ID has been
    seen (not a replay). Uses an insert-with-unique-_id race-free check."""
    if not assertion_id:
        return True  # nothing to key on — signature/timestamp checks still apply
    raw = await _saml_raw_db()
    from pymongo.errors import DuplicateKeyError
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=_REPLAY_CACHE_TTL_SECONDS)
    try:
        await raw.saml_processed_assertions.insert_one({"_id": assertion_id, "expires_at": expires_at})
        return True
    except DuplicateKeyError:
        return False


# ─── Authenticator ──────────────────────────────────────────────────────────

class SAMLAuthenticator:
    """SP metadata, SP-initiated login, ACS validation, and SLO handling for
    a single resolved SAMLConfig."""

    def __init__(self, config: SAMLConfig):
        self.config = config
        self._settings_dict = _build_settings_dict(config)

    def _auth(self, request_data: dict) -> OneLogin_Saml2_Auth:
        return OneLogin_Saml2_Auth(request_data, old_settings=self._settings_dict)

    def metadata(self) -> tuple[str, list]:
        """Return (metadata_xml, validation_errors)."""
        settings = OneLogin_Saml2_Settings(self._settings_dict, sp_validation_only=True)
        metadata_xml = settings.get_sp_metadata()
        errors = settings.validate_metadata(metadata_xml)
        return metadata_xml, errors

    async def build_login_url(self, request_data: dict) -> str:
        """SP-initiated SSO: build the AuthnRequest, store its ID keyed by an
        opaque RelayState token (for InResponseTo correlation at the ACS),
        and return the IdP redirect URL."""
        auth = self._auth(request_data)
        token = secrets.token_urlsafe(24)
        url = auth.login(return_to=token)
        request_id = auth.get_last_request_id()
        await _store_login_state(token, request_id)
        return url

    async def process_acs(self, request_data: dict) -> dict:
        """Validate an IdP Response (signature, audience, timestamps, and —
        for SP-initiated flows — InResponseTo), then check the independent
        assertion-ID replay cache. Returns nameid/attributes/session info.
        Raises SAMLValidationError on any failure (T-64-13)."""
        auth = self._auth(request_data)
        relay_state = (request_data.get("post_data") or {}).get("RelayState")
        request_id = await _pop_login_state(relay_state)

        try:
            auth.process_response(request_id=request_id)
        except Exception as exc:
            raise SAMLValidationError(f"Could not process SAML response: {exc}") from exc

        errors = auth.get_errors()
        if errors:
            reason = auth.get_last_error_reason()
            raise SAMLValidationError(f"SAML response invalid: {errors} ({reason})")
        if not auth.is_authenticated():
            raise SAMLValidationError("SAML response did not authenticate")

        assertion_id = auth.get_last_assertion_id()
        if not await _check_replay(assertion_id):
            raise SAMLValidationError("SAML assertion replay detected (assertion already processed)")

        return {
            "nameid": auth.get_nameid(),
            "attributes": auth.get_attributes(),
            "session_index": auth.get_session_index(),
        }

    def process_slo(self, request_data: dict) -> Optional[str]:
        """Handle an IdP-sent LogoutRequest or LogoutResponse. Returns a
        redirect URL when a response must be sent back to the IdP, else None."""
        auth = self._auth(request_data)
        redirect_url = auth.process_slo(keep_local_session=False)
        errors = auth.get_errors()
        if errors:
            raise SAMLValidationError(f"SLO invalid: {errors} ({auth.get_last_error_reason()})")
        return redirect_url


# ─── Full authenticate -> provision -> mint-JWT flow ───────────────────────────

async def is_saml_sourced_user(email: str, tenant_id: Optional[str] = None) -> bool:
    """True if the given user's record has source="saml" — used to block
    local password changes for SAML-sourced users (Pitfall 4 / T-64-17)."""
    db = get_database()
    query: dict = {"email": email}
    if tenant_id:
        query["tenantId"] = tenant_id
    user = await db.users.find_one(query, {"source": 1})
    return bool(user and user.get("source") == "saml")


async def authenticate_saml(request_data: dict, tenant_id: Optional[str] = None) -> dict:
    """ACS validate -> provision -> mint JWT.

    Token minting delegates to authentication_service.create_access_token /
    create_refresh_token (imported, not duplicated) per this plan's
    instruction to keep authentication_service.py untouched (64-06 owns it
    in the same wave for the two-phase MFA rewrite).

    `tenant_id` is the caller's known tenant, if any. The public ACS route
    passes None; this function then resolves a target tenant from an
    existing local user record's tenantId, else raises SAMLProvisionError —
    same pattern as ldap_service.authenticate_ldap (no LDAP_DEFAULT_TENANT_ID
    equivalent for SAML in this plan's scope; pre-provision the user via
    POST /api/users, or extend this later with a SAML_DEFAULT_TENANT_ID).
    """
    from saml_mapping import SAMLGroupMapper, SAMLUserProvisioner

    config = await get_saml_config(tenant_id)
    authenticator = SAMLAuthenticator(config)
    result = await authenticator.process_acs(request_data)

    provisioner = SAMLUserProvisioner(config)
    mapped = provisioner.extract_attributes(result["nameid"], result["attributes"])
    if not mapped.get("email"):
        raise SAMLProvisionError("SAML assertion did not contain a usable email/NameID")

    db = get_database()
    existing = await db.users.find_one({"email": mapped["email"]})
    target_tenant_id = tenant_id or (existing.get("tenantId") if existing else None)
    if not target_tenant_id:
        raise SAMLProvisionError(
            f"SAML user '{mapped['email']}' authenticated but has no existing local "
            "account and no tenant could be determined. Pre-create the user via "
            "POST /api/users with the matching tenantId."
        )

    group_mapper = SAMLGroupMapper()
    role = await group_mapper.resolve_role(mapped.get("groups") or [], target_tenant_id)
    user_doc = await provisioner.provision_user(mapped, target_tenant_id, role=role)

    from authentication_service import create_access_token, create_refresh_token
    token_payload = {
        "sub": user_doc["email"],
        "role": user_doc.get("role", "itam_viewer"),
        "tenant_id": target_tenant_id,
    }
    access_token = create_access_token(data=token_payload)
    refresh_token = create_refresh_token(data={"sub": user_doc["email"]})
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "success": True,
        "email": user_doc["email"],
        "role": user_doc.get("role", "itam_viewer"),
        "tenant_id": target_tenant_id,
    }

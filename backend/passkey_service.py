import os
import time
import webauthn
import secrets
from typing import Optional, Dict, Any, Tuple
from datetime import datetime, timezone

# Module-level constants and in-memory challenge store
_webauthn_challenges: Dict[Tuple[str, str], Tuple[bytes, float]] = {}
_CHALLENGE_EXPIRY_SECONDS = 300

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

def store_challenge(user_key: str, challenge_type: str, challenge: bytes) -> None:
    """Store a challenge keyed by (user_key, challenge_type) with TTL."""
    expiry = time.time() + _CHALLENGE_EXPIRY_SECONDS
    _webauthn_challenges[(user_key, challenge_type)] = (challenge, expiry)

def consume_challenge(user_key: str, challenge_type: str) -> Optional[bytes]:
    """Atomically read and invalidate a challenge if not expired."""
    pair = (user_key, challenge_type)
    entry = _webauthn_challenges.pop(pair, None)
    if not entry:
        return None
    challenge, expiry = entry
    if time.time() > expiry:
        return None
    return challenge

def _get_rp_id() -> str:
    platform_url = os.getenv("PLATFORM_URL", "")
    if platform_url:
        return platform_url.replace("https://", "").replace("http://", "").strip("/")
    return "localhost"

def _get_origin() -> str:
    platform_url = os.getenv("PLATFORM_URL", "")
    if platform_url:
        return platform_url.rstrip("/")
    return "http://localhost:3000"

RP_ID = _get_rp_id()
ORIGIN = _get_origin()

async def build_registration_options(user_id: str, username: str, display_name: str) -> dict:
    """Generate public key credential creation options."""
    user_id_bytes = user_id.encode("utf-8")
    challenge = secrets.token_bytes(32)
    store_challenge(user_id, "registration", challenge)
    options = webauthn.generate_registration_options(
        rp_id=RP_ID,
        rp_name="Enterprise Omni-Agent AI Platform",
        user_id=user_id_bytes,
        user_name=username,
        user_display_name=display_name,
        challenge=challenge,
        pubkey_cred_params=[
            webauthn.PublicKeyCredentialParameters(
                type="public-key",
                alg=-7,  # ES256
            ),
        ],
        authenticator_selection=webauthn.AuthenticatorSelectionCriteria(
            user_verification="preferred",
            resident_key="preferred",
        ),
    )
    return options

async def verify_and_store_registration(user_id: str, credential_response: dict, db, users_collection, tenant_id: str) -> dict:
    """Verify the registration response and persist the credential."""
    expected_challenge = consume_challenge(user_id, "registration")
    if not expected_challenge:
        raise ValueError("Challenge expired or missing")

    verification = webauthn.verify_registration_response(
        credential=credential_response,
        expected_challenge=expected_challenge,
        expected_origin=ORIGIN,
        expected_rp_id=RP_ID,
    )

    credential_id = verification.credential_data.credential_id
    public_key = verification.credential_data.public_key
    sign_count = verification.credential_data.sign_count

    cred_doc = {
        "credential_id": credential_id.hex(),
        "public_key": public_key.hex(),
        "sign_count": sign_count,
        "transports": credential_response.get("response", {}).get("transports", []),
        "created_at": _now_iso(),
        "last_used_at": None,
    }
    from database import mongodb
    await mongodb.db.users.update_one(
        {"id": user_id},
        {"$push": {"webauthn_credentials": cred_doc}},
    )
    return cred_doc

async def build_authentication_options(user_key: str) -> dict:
    """Generate public key credential request options for authentication."""
    challenge = secrets.token_bytes(32)
    store_challenge(user_key, "authentication", challenge)
    options = webauthn.generate_authentication_options(
        rp_id=RP_ID,
        challenge=challenge,
        user_verification="preferred",
    )
    return options

async def verify_authentication(user_key: str, credential_response: dict, db, users_collection) -> dict:
    """Verify the authentication response and update sign count."""
    expected_challenge = consume_challenge(user_key, "authentication")
    if not expected_challenge:
        raise ValueError("Challenge expired or missing")
    cred_id_hex = credential_response.get("id") or credential_response.get("rawId")
    if not cred_id_hex:
        raise ValueError("Missing credential id in response")
    from database import mongodb
    user_doc = await mongodb.db.users.find_one(
        {"webauthn_credentials.credential_id": cred_id_hex},
        {"id": 1, "webauthn_credentials": 1, "tenantId": 1},
    )
    if not user_doc:
        raise ValueError("Credential not found")
    stored_cred_obj = next(
        (c for c in user_doc.get("webauthn_credentials", []) if c.get("credential_id") == cred_id_hex),
        None,
    )
    if not stored_cred_obj:
        raise ValueError("Credential not found")

    verification = webauthn.verify_authentication_response(
        credential=credential_response,
        expected_challenge=expected_challenge,
        expected_origin=ORIGIN,
        expected_rp_id=RP_ID,
        credential_public_key=bytes.fromhex(stored_cred_obj["public_key"]),
        credential_current_sign_count=stored_cred_obj.get("sign_count", 0),
    )

    new_sign_count = verification.new_sign_count
    await mongodb.db.users.update_one(
        {"id": user_doc["id"], "webauthn_credentials.credential_id": cred_id_hex},
        {
            "$set": {
                "webauthn_credentials.$.sign_count": new_sign_count,
                "webauthn_credentials.$.last_used_at": _now_iso(),
            }
        },
    )
    return {"user_id": user_doc["id"], "tenant_id": user_doc.get("tenantId")}

import base64
import hashlib
import logging
import os
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Depends
from database import get_database
from security_service import get_security_service
from authentication_service import get_current_user, SECRET_KEY
from auth_types import TokenData
from rbac_utils import is_super_admin

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api")


@router.post("/security/generate-keypair")
async def generate_signing_keypair(
    current_user: TokenData = Depends(get_current_user),
):
    """
    Generate RSA key pair for patch signing.
    Admin-only. Returns public key + the private key once in the response.
    Only the AES-256-GCM encrypted private key is persisted; the plaintext is never stored.
    """
    if not is_super_admin(getattr(current_user, "role", "")):
        raise HTTPException(status_code=403, detail="Admin privileges required to generate signing keys")

    try:
        security_service = get_security_service()
        private_key_pem, public_key_pem = security_service.generate_rsa_keypair(key_size=2048)

        db = get_database()
        key_id = f"key-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}-{os.urandom(4).hex()}"

        wrap_key = security_service.generate_encryption_key()
        encrypted_priv, nonce = security_service.encrypt_payload(private_key_pem, wrap_key)

        # Derive a persistent storage key from the server JWT secret + key_id
        # so the wrap_key itself is never written to the database.
        storage_wrap = hashlib.sha256(f"{SECRET_KEY}:{key_id}".encode()).digest()
        encrypted_wrap, wrap_nonce = security_service.encrypt_payload(wrap_key, storage_wrap)

        await db.signing_keys.insert_one({
            "id": key_id,
            "public_key": public_key_pem.decode(),
            "private_key_encrypted": base64.b64encode(encrypted_priv).decode(),
            "private_key_nonce": base64.b64encode(nonce).decode(),
            "wrap_key_encrypted": base64.b64encode(encrypted_wrap).decode(),
            "wrap_key_nonce": base64.b64encode(wrap_nonce).decode(),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "created_by": getattr(current_user, "username", "unknown"),
            "key_size": 2048,
            "algorithm": "RSA",
        })

        await security_service.audit_security_event(
            db=db,
            event_type="signing_key_generated",
            details={
                "key_id": key_id,
                "algorithm": "RSA-2048",
                "created_by": getattr(current_user, "username", "unknown"),
            },
            severity="Info",
        )

        return {
            "success": True,
            "key_id": key_id,
            "public_key": public_key_pem.decode(),
            "private_key": private_key_pem.decode(),
            "message": (
                "Private key returned once. Store it securely — "
                "it cannot be recovered from the server without the master secret."
            ),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error generating keypair: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error")

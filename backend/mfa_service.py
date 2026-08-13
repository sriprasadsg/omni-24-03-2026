"""
MFA Service — TOTP (RFC 6238) + Backup Codes
----------------------------------------------
Supports:
  - Google Authenticator, Authy, Microsoft Authenticator (TOTP compatible)
  - 8 x 8-digit one-time backup recovery codes (bcrypt hashed — same convention
    as password/API-key storage, see auth_utils.hash_password)
  - Two-phase login: password -> mfa_session_token -> full JWT
  - AES-256 encryption of TOTP secrets at rest (via encryption_service),
    no plaintext-equivalent fallback (Pitfall 2)
  - MongoDB TTL-backed MFA session tokens — not in-memory (Pitfall 1)
"""

import pyotp
import qrcode
import io
import base64
import secrets
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional
from database import get_database

# Fail fast: no try/except around this import. If encryption_service is
# unavailable, mfa_service must not silently degrade to a base64
# plaintext-equivalent fallback (RESEARCH.md Pitfall 2 / threat T-64-24).
from encryption_service import get_encryption_service

APP_NAME = "Enterprise Omni-Agent Platform"
MFA_SESSION_TTL_SECONDS = 300  # 5 minutes for the intermediate MFA session token


# ─── Encryption Helpers ─────────────────────────────────────────────────────

def _encrypt_secret(secret: str) -> str:
    """AES-256 (Fernet) encrypt via the shared encryption_service. No fallback."""
    return get_encryption_service().encrypt(secret)


def _decrypt_secret(ciphertext: str) -> str:
    """AES-256 (Fernet) decrypt via the shared encryption_service. No fallback."""
    return get_encryption_service().decrypt(ciphertext)


def verify_encryption_service() -> None:
    """
    Startup/health-check helper: raises if encryption_service is unavailable
    or fails a round-trip encrypt/decrypt check. Call this during app startup
    (or from an ops health endpoint) to catch a missing/broken encryption key
    before any TOTP secret is ever written with it.
    In production, encryption_service itself already refuses to start without
    PAYMENT_ENCRYPTION_KEY set; in dev it falls back to an ephemeral key
    (documented limitation — MFA secrets encrypted with it are unreadable
    after a restart, matching the existing JWT_SECRET_KEY dev behavior).
    """
    probe = "mfa-encryption-health-check"
    svc = get_encryption_service()
    round_tripped = svc.decrypt(svc.encrypt(probe))
    if round_tripped != probe:
        raise RuntimeError("encryption_service round-trip check failed — MFA secrets would be unrecoverable")


def _hash_backup_code(code: str) -> str:
    """
    Bcrypt-hash a backup code for storage (auth_utils.hash_password — same
    convention as password/API-key hashing elsewhere in this codebase).
    One-way hashing is intentionally used instead of reversible encryption:
    backup codes are only ever compared, never redisplayed, so a hash is both
    sufficient and strictly safer than a symmetric-key-recoverable ciphertext.
    """
    from auth_utils import hash_password
    return hash_password(code.strip())


def _verify_backup_code(code: str, code_hash: str) -> bool:
    from auth_utils import verify_password
    return verify_password(code.strip(), code_hash)


# ─── TOTP Setup ───────────────────────────────────────────────────────────────

def generate_totp_secret() -> str:
    """Generate a new random-base32 TOTP secret."""
    return pyotp.random_base32()


def get_totp_provisioning_uri(email: str, secret: str) -> str:
    """Return an otpauth:// URI for QR code generation."""
    totp = pyotp.TOTP(secret)
    return totp.provisioning_uri(name=email, issuer_name=APP_NAME)


def generate_qr_base64(uri: str) -> str:
    """Render the OTP URI as a base64-encoded PNG QR code."""
    try:
        qr = qrcode.QRCode(version=1, box_size=10, border=4)
        qr.add_data(uri)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        buffer = io.BytesIO()
        img.save(buffer, format="PNG")
        return base64.b64encode(buffer.getvalue()).decode()
    except Exception:
        return ""  # Frontend falls back to showing the raw URI


def verify_totp_code(secret: str, code: str) -> bool:
    """Verify a 6-digit TOTP code with +/-1 window tolerance (90s validity)."""
    totp = pyotp.TOTP(secret)
    return totp.verify(code, valid_window=1)


# ─── Backup Codes ─────────────────────────────────────────────────────────────

def generate_backup_codes(count: int = 8) -> list[str]:
    """Generate one-time 8-digit backup recovery codes."""
    return [str(secrets.randbelow(100_000_000)).zfill(8) for _ in range(count)]


async def use_backup_code(email: str, code: str) -> bool:
    """
    Verify and consume a backup code.
    Returns True if the code was valid and not yet used.
    """
    db = get_database()
    user = await db.users.find_one({"email": email})
    if not user or not user.get("mfa", {}).get("enabled"):
        return False

    stored_hashes = user.get("mfa", {}).get("backup_codes_hashed", [])
    for code_hash in stored_hashes:
        if _verify_backup_code(code, code_hash):
            new_hashes = [h for h in stored_hashes if h != code_hash]
            await db.users.update_one(
                {"email": email},
                {"$set": {
                    "mfa.backup_codes_hashed": new_hashes,
                    "mfa.last_used_at": datetime.now(timezone.utc).isoformat(),
                }}
            )
            return True
    return False


# ─── MFA Enrollment ───────────────────────────────────────────────────────────

async def enroll_mfa(email: str, totp_code: str, password: Optional[str] = None) -> dict:
    """
    Called after the user scans the QR code and enters their first TOTP code.
    Activates MFA on the account and returns 8 backup codes.

    If MFA is already enabled on the account, this is a re-enrollment (e.g. a
    lost/stolen authenticator) rather than initial setup, and requires the
    same password confirmation as disable_mfa/regenerate_backup_codes
    (T-64-26) — otherwise a stolen/XSS'd JWT alone could silently replace an
    already-active TOTP secret and backup codes with attacker-controlled ones.
    """
    db = get_database()
    user = await db.users.find_one({"email": email})
    if not user:
        return {"success": False, "error": "User not found"}

    if user.get("mfa", {}).get("enabled"):
        stored_hash = user.get("password") or user.get("hashed_password")
        if not stored_hash:
            return {"success": False, "error": "Account has no password set"}
        if not password:
            return {"success": False, "error": "Password confirmation required to re-enroll MFA"}
        from auth_utils import verify_password
        if not verify_password(password, stored_hash):
            return {"success": False, "error": "Invalid password"}

    pending = user.get("mfa", {}).get("pending_secret")
    if not pending:
        return {"success": False, "error": "No pending MFA setup. Call /mfa/setup first."}

    secret = _decrypt_secret(pending)
    if not verify_totp_code(secret, totp_code):
        return {"success": False, "error": "Invalid TOTP code"}

    backup_codes = generate_backup_codes()
    backup_hashes = [_hash_backup_code(c) for c in backup_codes]

    await db.users.update_one(
        {"email": email},
        {"$set": {
            "mfa.enabled": True,
            "mfa.secret_encrypted": pending,
            "mfa.backup_codes_hashed": backup_hashes,
            "mfa.enrolled_at": datetime.now(timezone.utc).isoformat(),
            "mfa.pending_secret": None,
            "mfa.last_used_at": None,
        }}
    )
    return {"success": True, "backup_codes": backup_codes}


async def disable_mfa(email: str, password: str) -> dict:
    """
    Disable MFA after verifying the account password (not a TOTP code — a
    security tightening over the prior TOTP-confirmation flow: a lost/stolen
    authenticator app should not be sufficient to turn MFA off, see
    threat T-64-26). Clears MFA fields and revokes any in-flight MFA sessions
    for this account.
    """
    db = get_database()
    user = await db.users.find_one({"email": email})
    if not user or not user.get("mfa", {}).get("enabled"):
        return {"success": False, "error": "MFA is not enabled"}

    stored_hash = user.get("password") or user.get("hashed_password")
    if not stored_hash:
        return {"success": False, "error": "Account has no password set"}

    from auth_utils import verify_password
    if not verify_password(password, stored_hash):
        return {"success": False, "error": "Invalid password"}

    await db.users.update_one(
        {"email": email},
        {"$set": {
            "mfa.enabled": False,
            "mfa.secret_encrypted": None,
            "mfa.backup_codes_hashed": [],
            "mfa.disabled_at": datetime.now(timezone.utc).isoformat(),
        }}
    )
    await _revoke_all_mfa_sessions(email)
    return {"success": True}


async def regenerate_backup_codes(email: str, password: str) -> dict:
    """Invalidate existing backup codes and issue a fresh set (password-confirmed, T-64-25)."""
    db = get_database()
    user = await db.users.find_one({"email": email})
    if not user or not user.get("mfa", {}).get("enabled"):
        return {"success": False, "error": "MFA is not enabled"}

    stored_hash = user.get("password") or user.get("hashed_password")
    if not stored_hash:
        return {"success": False, "error": "Account has no password set"}

    from auth_utils import verify_password
    if not verify_password(password, stored_hash):
        return {"success": False, "error": "Invalid password"}

    backup_codes = generate_backup_codes()
    backup_hashes = [_hash_backup_code(c) for c in backup_codes]
    await db.users.update_one(
        {"email": email},
        {"$set": {"mfa.backup_codes_hashed": backup_hashes}}
    )
    return {"success": True, "backup_codes": backup_codes}


async def get_mfa_status(email: str) -> dict:
    db = get_database()
    user = await db.users.find_one({"email": email})
    if not user:
        return {
            "enabled": False,
            "enrolled_at": None,
            "backup_codes_remaining": 0,
            "has_backup_codes": False,
            "last_used": None,
        }
    mfa = user.get("mfa", {})
    backup_remaining = len(mfa.get("backup_codes_hashed", []))
    return {
        "enabled": mfa.get("enabled", False),
        "enrolled_at": mfa.get("enrolled_at"),
        "backup_codes_remaining": backup_remaining,
        "has_backup_codes": backup_remaining > 0,
        "last_used": mfa.get("last_used_at"),
    }


# ─── MFA Session Tokens (two-factor login flow) ───────────────────────────────
# Persisted in a MongoDB TTL collection (mfa_sessions), not an in-memory dict
# (RESEARCH.md Pitfall 1 / threat T-64-23) — survives server restarts across
# workers and expires automatically via the `expires_at` TTL index, following
# the same lazy-index-creation pattern used by sso_endpoints._sso_col() and
# saml_service._saml_raw_db().

_mfa_index_created = False


def _as_utc(dt: datetime) -> datetime:
    """Motor/pymongo return naive UTC datetimes by default (client is not
    constructed with tz_aware=True) — normalize before comparison."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


async def _mfa_sessions_col():
    """Return the mfa_sessions collection, ensuring its TTL index exists."""
    global _mfa_index_created
    db = get_database()
    col = db._db.mfa_sessions
    if not _mfa_index_created:
        await col.create_index("expires_at", expireAfterSeconds=0)
        _mfa_index_created = True
    return col


async def _revoke_all_mfa_sessions(email: str) -> None:
    """Delete any pending MFA session tokens for this account (e.g. on disable)."""
    col = await _mfa_sessions_col()
    await col.delete_many({"email": email})


async def create_mfa_session(email: str) -> str:
    """
    Create a short-lived session token (5 min) returned after password check
    when the account has MFA enabled. The frontend then submits this + TOTP
    to /mfa/verify to receive the full JWT.
    """
    col = await _mfa_sessions_col()
    token = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    await col.insert_one({
        "_id": token,
        "email": email,
        "created_at": now,
        "expires_at": now + timedelta(seconds=MFA_SESSION_TTL_SECONDS),
    })
    return token


async def validate_mfa_session(session_token: str) -> Optional[str]:
    """
    Validate an MFA session token without consuming it (used by the backup-code
    path, which needs to retry against the same session on a wrong code).
    Returns the associated email if valid, None otherwise. Expired tokens found
    before the TTL sweep removes them are explicitly rejected and deleted.
    """
    col = await _mfa_sessions_col()
    doc = await col.find_one({"_id": session_token})
    if not doc:
        return None
    expires_at = doc.get("expires_at")
    if not expires_at or _as_utc(expires_at) < datetime.now(timezone.utc):
        await col.delete_one({"_id": session_token})
        return None
    return doc.get("email")


async def consume_mfa_session(session_token: str) -> None:
    """Delete the session token (e.g. after a successful backup-code verification)."""
    col = await _mfa_sessions_col()
    await col.delete_one({"_id": session_token})


async def cleanup_expired_sessions() -> int:
    """
    Manually purge expired MFA sessions. Normally handled automatically by the
    mfa_sessions TTL index (expires_at, expireAfterSeconds=0); MongoDB's TTL
    background sweep runs on ~60s intervals rather than immediately at expiry,
    so this is provided as an explicit/testable fallback, not required for
    correctness (validate_mfa_session/verify_mfa_token both reject expired
    documents on read regardless of whether the sweep has run yet).
    """
    col = await _mfa_sessions_col()
    now = datetime.now(timezone.utc)
    result = await col.delete_many({"expires_at": {"$lt": now}})
    return result.deleted_count


async def verify_mfa_token(session_token: str, code: str) -> dict:
    """
    Complete the MFA step: validate + single-use-consume the session, then
    verify the TOTP code. The session is deleted via find_one_and_delete on
    the first attempt regardless of whether the code turns out to be valid —
    this is the "single-use consumption" mitigation for T-64-23 (a session
    token cannot be replayed or brute-forced across multiple TOTP guesses;
    a wrong code requires the user to restart login and obtain a fresh
    session token from /api/auth/login).
    Returns { success, email } or { success: False, error }.
    """
    col = await _mfa_sessions_col()
    doc = await col.find_one_and_delete({"_id": session_token})
    if not doc:
        return {"success": False, "error": "MFA session expired or invalid"}

    expires_at = doc.get("expires_at")
    if not expires_at or _as_utc(expires_at) < datetime.now(timezone.utc):
        return {"success": False, "error": "MFA session expired or invalid"}

    email = doc["email"]
    db = get_database()
    user = await db.users.find_one({"email": email})
    if not user or not user.get("mfa", {}).get("enabled"):
        return {"success": False, "error": "MFA not configured for this account"}

    secret = _decrypt_secret(user["mfa"]["secret_encrypted"])
    if verify_totp_code(secret, code):
        await db.users.update_one(
            {"email": email},
            {"$set": {"mfa.last_used_at": datetime.now(timezone.utc).isoformat()}}
        )
        return {"success": True, "email": email}

    return {"success": False, "error": "Invalid TOTP code"}

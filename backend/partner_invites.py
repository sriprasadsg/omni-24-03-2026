"""Invite a person into an organization with a seven-day, single-use password-set link (Phase 87).

The invited person is stored first as an Active user whose password hash nobody knows. The link
lives in ``password_reset_tokens`` so the existing ``POST /api/auth/reset-password/confirm`` sets
the password and consumes the row; ``invites`` keeps only the SHA-256 of the link's secret so the
public status route can say valid / expired / used / invalid without the row itself.

The secret is emailed and nothing else: it is never returned from ``invite`` or ``resend``, never
logged, and the inviter (a partner or the Super Admin) cannot read it back. The token row carries
no creation-time field on purpose: the collection's one-hour TTL index keys on that field, so
adding it would delete a seven-day invite after an hour.

Every query names its collection on the raw handle; a user's email is unique across all
organizations, so the clash check cannot go through the tenant-scoped wrapper.
"""
import hashlib
import html
import logging
import os
import re
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from pymongo.errors import DuplicateKeyError

from auth_utils import hash_password
from partner_pool import PartnerError, _raw

logger = logging.getLogger(__name__)

INVITE_DAYS = 7
ROLE_KINDS = ("customer_admin", "partner_admin", "partner_viewer")
MAX_TOKEN_LENGTH = 512
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_CLASH_MESSAGE = "That email address can't be used. Use a different one."


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _unavailable() -> PartnerError:
    """The one refusal for every clash: it never says whether or where the address is used."""
    return PartnerError(409, "email_unavailable", _CLASH_MESSAGE)


def normalize_email(email: Any) -> str:
    address = email.strip().lower() if isinstance(email, str) else ""
    if len(address) > 254 or not _EMAIL.match(address):
        raise PartnerError(422, "invalid_email", "Enter a valid email address.")
    return address


async def email_in_use(db, email: str) -> bool:
    """True when any user of any organization holds this address, ignoring case."""
    pattern = {"$regex": f"^{re.escape(email.strip())}$", "$options": "i"}
    return await _raw(db).users.find_one({"email": pattern}, {"_id": 1}) is not None


async def issue_invite(db, *, email: str, tenant_id: str, organization_name: str, role_kind: str,
                       invited_by: str, now: Optional[datetime] = None) -> str:
    """Store a fresh link for ``email`` and return its secret; the caller may only email it."""
    now = now or _now()
    expires = now + timedelta(days=INVITE_DAYS)
    token = secrets.token_urlsafe(32)
    raw = _raw(db)
    await raw.password_reset_tokens.insert_one(
        {"token": token, "email": email, "expires_at": expires.isoformat(), "invite": True})
    await raw.invites.insert_one({
        "id": f"invite-{uuid.uuid4()}", "tokenHash": _hash(token), "email": email, "tenantId": tenant_id,
        "organizationName": organization_name, "roleKind": role_kind, "invitedBy": invited_by,
        "createdAt": now.isoformat(), "expiresAt": expires.isoformat(),
    })
    return token


async def send_invite_email(*, email: str, name: str, organization_name: str, token: str,
                            tenant_id: str) -> bool:
    """Email the link; False (nothing sent) without a configured link base or mail server."""
    base = os.getenv("FRONTEND_URL", "").strip().rstrip("/")
    if not base.startswith(("http://", "https://")):
        logger.warning("[Invite] FRONTEND_URL is not set to an http(s) address; no invite email sent")
        return False
    try:
        from database import get_database
        from email_service import email_service
        from auth_password_reset_endpoints import _resolve_smtp_config

        smtp = await _resolve_smtp_config(get_database(), tenant_id)
        if not smtp:
            logger.warning("[Invite] No usable mail configuration for tenant %s; no invite email sent",
                           tenant_id)
            return False
        link = f"{base}/accept-invite?token={token}"
        body_text = (
            f"Hello {name},\n\n"
            f"You have been invited to {organization_name} on Omni-Agent AI.\n\n"
            f"Set your password with this link:\n{link}\n\n"
            f"The link works for {INVITE_DAYS} days and can be used once.\n\n"
            "If you did not expect this invitation, ignore this email.\n"
        )
        body_html = (
            "<p>Hello {name},</p><p>You have been invited to <strong>{org}</strong> on Omni-Agent AI.</p>"
            '<p><a href="{link}">Set your password</a></p><p style="word-break:break-all">{link}</p>'
            "<p>The link works for {days} days and can be used once.</p>"
            "<p>If you did not expect this invitation, ignore this email.</p>"
        ).format(name=html.escape(name), org=html.escape(organization_name),
                 link=html.escape(link, quote=True), days=INVITE_DAYS)
        result = await email_service.send_email(
            smtp_config=smtp, to_email=email, subject="You're invited to Omni-Agent AI",
            body_text=body_text, body_html=body_html)
        sent = bool(result and result.get("success"))
        if not sent:
            logger.warning("[Invite] The mail server refused the invite email for tenant %s", tenant_id)
        return sent
    except Exception as exc:
        logger.warning("[Invite] Invite email failed for tenant %s (%s)", tenant_id, type(exc).__name__)
        return False


async def invite(db, *, tenant_id: str, organization_name: str, email: str, name: str, role: str,
                 role_kind: str, invited_by: str) -> Dict[str, Any]:
    """Create the person and issue their link. Returns the person and whether the email went out,
    never the link."""
    address = normalize_email(email)
    if role_kind not in ROLE_KINDS:
        raise PartnerError(422, "invalid_role_kind", "Choose a valid role.")
    if await email_in_use(db, address):
        raise _unavailable()
    now = _now().isoformat()
    user_id = f"user-{uuid.uuid4()}"
    try:
        await _raw(db).users.insert_one({
            "id": user_id, "email": address, "full_name": name, "name": name, "role": role,
            "tenantId": tenant_id, "status": "Active",
            "hashed_password": hash_password(secrets.token_urlsafe(48)),
            "invitedAt": now, "invitedBy": invited_by, "createdAt": now, "updatedAt": now,
        })
    except DuplicateKeyError:
        raise _unavailable()
    try:
        token = await issue_invite(db, email=address, tenant_id=tenant_id, organization_name=organization_name,
                                   role_kind=role_kind, invited_by=invited_by)
    except Exception:
        # Without its link the person can never sign in or be invited again (WR-03), so they go too.
        await _raw(db).users.delete_one({"id": user_id})
        raise
    sent = await send_invite_email(email=address, name=name, organization_name=organization_name,
                                   token=token, tenant_id=tenant_id)
    return {"user": {"id": user_id, "name": name, "email": address, "role": role}, "emailSent": sent}


def _expired(row: Dict[str, Any], now: datetime) -> bool:
    try:
        expires = datetime.fromisoformat(row["expires_at"])
    except (KeyError, TypeError, ValueError):
        return True
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    return now > expires


async def invite_state(db, token: Any, now: Optional[datetime] = None) -> Dict[str, Any]:
    """Classify a link for the public accept-invite page; the answer never carries the token."""
    if not isinstance(token, str) or not 1 <= len(token) <= MAX_TOKEN_LENGTH:
        return {"state": "invalid"}
    raw = _raw(db)
    record = await raw.invites.find_one({"tokenHash": _hash(token)})
    if not record or record.get("supersededAt"):
        return {"state": "invalid"}
    row = await raw.password_reset_tokens.find_one({"token": token})
    if not row:
        return {"state": "used"}
    if _expired(row, now or _now()):
        return {"state": "expired"}
    return {"state": "valid", "organizationName": record.get("organizationName"),
            "email": record.get("email"), "roleKind": record.get("roleKind")}


async def member_status(db, email: str, now: Optional[datetime] = None) -> str:
    """``invited`` while the link is open, ``invite_expired`` after it, ``active`` once used (or
    when the person was never invited)."""
    row = await _raw(db).password_reset_tokens.find_one({"email": email.strip().lower(), "invite": True})
    if not row:
        return "active"
    return "invite_expired" if _expired(row, now or _now()) else "invited"


async def resend(db, *, user: Dict[str, Any], organization_name: str, role_kind: str,
                 invited_by: str) -> bool:
    """Replace the person's link with a new seven-day one. Refused once they have set a password."""
    address = normalize_email(user.get("email"))
    if await member_status(db, address) == "active":
        raise PartnerError(409, "already_active", "This person has already set a password.")
    raw = _raw(db)
    await raw.invites.update_many({"email": address, "supersededAt": {"$exists": False}},
                                  {"$set": {"supersededAt": _now().isoformat()}})
    await raw.password_reset_tokens.delete_many({"email": address, "invite": True})
    tenant_id = user.get("tenantId") or user.get("tenant_id")
    name = user.get("name") or user.get("full_name") or address
    token = await issue_invite(db, email=address, tenant_id=tenant_id, organization_name=organization_name,
                               role_kind=role_kind, invited_by=invited_by)
    return await send_invite_email(email=address, name=name, organization_name=organization_name,
                                   token=token, tenant_id=tenant_id)

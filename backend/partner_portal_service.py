"""The partner's side of the channel (Phase 87): create a customer from the pool, read the overview.

The partner is always the document ``partner_endpoints.current_partner`` loaded from the verified
token; nothing here takes a partner id from a request. An increase claims the pool first and a failed
insert gives the claim back (see ``partner_pool`` for the invariant). Raw handle, explicit filters.
"""
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, Optional

from pymongo.errors import DuplicateKeyError

import licensing
import partner_invites
import partner_pool
import rbac_defaults
import tenant_docs
import tenant_features
from partner_pool import PartnerError, _raw
from partner_store import audit, customer_rows, find_partner, name_taken, pool_view

logger = logging.getLogger(__name__)

NAME_UNAVAILABLE = "That name isn't available."
EXPIRED_CREATE = "Your seat pool has expired. You can't create customers."
EXPIRED_HAND_OUT = "Your seat pool has expired. You can't hand out seats."
CUSTOMER_ADMIN_ROLE = "Tenant Admin"


def _actor_email(actor: Any) -> str:
    return getattr(actor, "username", None) or "system"


async def _remove_failed_customer(db, partner_id: str, customer_id: str, seats: int, address: str) -> None:
    """Undo a creation whose invite failed: the customer, whatever the invite stored for it, the seats."""
    raw = _raw(db)
    await raw.tenants.delete_one({"id": customer_id, "partnerId": partner_id})
    await raw.users.delete_many({"tenantId": customer_id})
    await raw.invites.delete_many({"tenantId": customer_id})
    await raw.password_reset_tokens.delete_many({"email": address, "invite": True})
    await partner_pool.release(db, partner_id, seats)


async def _row_of(db, partner_doc: Dict[str, Any], customer_id: str) -> Dict[str, Any]:
    for row in await customer_rows(db, partner_doc):
        if row["id"] == customer_id:
            return row
    raise PartnerError(404, "not_found", "Customer not found")


def _ceiling(partner_doc: Dict[str, Any]) -> list:
    return [s for s in (partner_doc.get("partner") or {}).get("screenCeiling") or [] if isinstance(s, str)]


def _allowed(partner_doc: Dict[str, Any]) -> set:
    """What a partner may switch on: its ceiling (every switch when it is ``all``) plus the start screens."""
    ceiling = _ceiling(partner_doc)
    base = set(tenant_features.SWITCHABLE) if "all" in ceiling else set(ceiling)
    return base | set(tenant_features.START_FEATURES)


def _label(screen: str) -> str:
    return tenant_features.SWITCH_LABELS.get(screen, screen)


def _final_screens(partner_doc: Dict[str, Any], submitted: Iterable[str], current: Iterable[str]) -> list:
    """The screen list to store (D-10, D-19): the submitted order de-duplicated, then the screens the
    customer already has outside the ceiling, then any missing start screen. Refuses ``all``, unknown
    strings, a screen outside the ceiling and a switch whose parent is missing."""
    allowed = _allowed(partner_doc)
    kept = [s for s in dict.fromkeys(current) if s not in allowed]
    known = set(tenant_features.SWITCHABLE) | set(tenant_features.START_FEATURES) | set(kept)
    known.discard(tenant_features.ALL_FEATURES)
    wanted = list(dict.fromkeys(submitted))
    for value in wanted:
        if not isinstance(value, str) or value not in known:
            raise PartnerError(422, "invalid_screen", f"'{value}' is not a screen that can be sold.")
    for value in wanted:
        if value not in allowed and value not in kept:
            raise PartnerError(422, "screen_outside_ceiling", f"{_label(value)} is not one of the screens you can sell.",
                               screen=value)
    final = list(dict.fromkeys([*wanted, *kept, *tenant_features.START_FEATURES]))
    for value in final:
        parent = tenant_features.SWITCH_PARENTS.get(value)
        if value not in kept and parent is not None and parent not in final:
            raise PartnerError(422, "missing_parent", f"{_label(value)} needs {_label(parent)}.", screen=value, parent=parent)
    return final


async def create_customer(db, partner_doc: Dict[str, Any], *, name: str, seats: int,
                          enabled_features: Optional[Iterable[str]], admin_name: str, admin_email: str,
                          actor: Any) -> Dict[str, Any]:
    """Create one customer organization with ``seats`` claimed from the pool and invite its first admin
    (D-09); returns ``{"customer": D-01 row, "emailSent": bool}`` and never a link or token.

    Every refusal that needs no write comes first (expired pool, bad or used email, name); then the pool is
    claimed and the customer stored; if the invite then fails the customer is deleted and the seats returned."""
    partner_id = partner_doc["id"]
    name = name.strip()
    if partner_pool.pool_expired(partner_doc):
        raise PartnerError(409, "pool_expired", EXPIRED_CREATE)
    address = partner_invites.normalize_email(admin_email)
    if await partner_invites.email_in_use(db, address):
        raise partner_invites._unavailable()
    if await name_taken(db, name):
        raise PartnerError(409, "name_unavailable", NAME_UNAVAILABLE)
    features = _final_screens(partner_doc, enabled_features or [], current=[])
    if not await partner_pool.claim(db, partner_id, seats, require_active=True):
        free = await partner_pool.free_seats(db, partner_id)
        raise PartnerError(409, "pool_full", f"Only {free} seats are free in your pool.", free=free)
    doc = tenant_docs.build_tenant_doc(name, max_agents=seats, enabled_features=features, partner_id=partner_id)
    try:
        await _raw(db).tenants.insert_one(dict(doc))
    except Exception as exc:
        await partner_pool.release(db, partner_id, seats)
        if isinstance(exc, DuplicateKeyError):  # the name was taken after name_taken looked (WR-02)
            raise PartnerError(409, "name_unavailable", NAME_UNAVAILABLE)
        raise
    try:
        invited = await partner_invites.invite(
            db, tenant_id=doc["id"], organization_name=name, email=address, name=admin_name.strip(),
            role=CUSTOMER_ADMIN_ROLE, role_kind="customer_admin", invited_by=_actor_email(actor))
    except Exception:
        await _remove_failed_customer(db, partner_id, doc["id"], seats, address)
        raise
    await tenant_docs.ensure_tenant_extras(_raw(db), doc["id"])
    await audit("partner.customer_created", actor=actor, partner_id=partner_id,
                customerId=doc["id"], customerName=name, seats=seats)
    await audit("partner.invite_sent", actor=actor, partner_id=partner_id, customerId=doc["id"],
                inviteeEmail=address, roleKind="customer_admin", emailSent=bool(invited.get("emailSent")))
    return {"customer": await _row_of(db, partner_doc, doc["id"]), "emailSent": bool(invited.get("emailSent"))}


async def change_seats(db, partner_doc: Dict[str, Any], customer_id: str, seats: int, actor: Any) -> Dict[str, Any]:
    """Set a customer's seats (D-06): never below the seats in use, a raise only within the free seats and
    never after the pool expired (D-08; giving seats back stays allowed). Returns the row and the pool."""
    partner_id = partner_doc["id"]
    customer = await _raw(db).tenants.find_one({"id": customer_id, "partnerId": partner_id}, {"_id": 0})
    if customer is None:
        raise PartnerError(404, "not_found", "Customer not found")
    if seats > licensing.license_of(customer)["maxAgents"] and partner_pool.pool_expired(partner_doc):
        raise PartnerError(409, "pool_expired", EXPIRED_HAND_OUT)
    moved = await partner_pool.change_allotment(db, customer_id, seats, partner_id=partner_id,
                                                enforce_used_floor=True, require_active=True)
    if moved["before"] != moved["after"]:
        await audit("partner.allotment_changed", actor=actor, partner_id=partner_id, customerId=customer_id,
                    before=moved["before"], after=moved["after"])
    fresh = await find_partner(db, partner_id) or partner_doc
    return {"customer": await _row_of(db, fresh, customer_id), "pool": pool_view(fresh)}


async def overview(db, partner_doc: Dict[str, Any], role: str) -> Dict[str, Any]:
    """The portal's whole read: pool, ceiling and the D-01 customer rows."""
    ceiling = [s for s in (partner_doc.get("partner") or {}).get("screenCeiling") or [] if isinstance(s, str)]
    return {
        "partner": {"name": partner_doc.get("name")},
        "role": role,
        "pool": pool_view(partner_doc),
        "ceiling": ceiling,
        "unrestricted": "all" in ceiling,
        "customers": await customer_rows(db, partner_doc),
    }


def _features_view(partner_doc: Dict[str, Any], enabled: Iterable[str]) -> Dict[str, Any]:
    allowed = _allowed(partner_doc)
    enabled = [s for s in enabled if isinstance(s, str)]
    ceiling = _ceiling(partner_doc)
    return {"enabledFeatures": enabled, "ceiling": ceiling, "unrestricted": "all" in ceiling,
            "kept": [s for s in enabled if s not in allowed]}


async def _own_customer(db, partner_doc: Dict[str, Any], customer_id: str) -> Dict[str, Any]:
    customer = await _raw(db).tenants.find_one({"id": customer_id, "partnerId": partner_doc["id"]},
                                               {"_id": 0, "id": 1, "enabledFeatures": 1})
    if customer is None:
        raise PartnerError(404, "not_found", "Customer not found")
    return customer


async def customer_features(db, partner_doc: Dict[str, Any], customer_id: str) -> Dict[str, Any]:
    """The customer's screens, the partner's ceiling, and the screens kept beyond it (D-10, D-19)."""
    customer = await _own_customer(db, partner_doc, customer_id)
    return _features_view(partner_doc, customer.get("enabledFeatures") or [])


async def set_customer_features(db, partner_doc: Dict[str, Any], customer_id: str, features: Iterable[str],
                                actor: Any) -> Dict[str, Any]:
    """Store the customer's screens within the ceiling. The write is a compare-and-set on the list that was
    read, so a Super Admin change made meanwhile is not lost (409 ``changed``)."""
    partner_id = partner_doc["id"]
    customer = await _own_customer(db, partner_doc, customer_id)
    before = customer.get("enabledFeatures")
    current = [s for s in before or [] if isinstance(s, str)]
    final = _final_screens(partner_doc, features, current)
    guard = {"enabledFeatures": before} if before is not None else {"enabledFeatures": {"$exists": False}}
    res = await _raw(db).tenants.update_one(
        {"id": customer_id, "partnerId": partner_id, **guard},
        {"$set": {"enabledFeatures": final, "updatedAt": datetime.now(timezone.utc).isoformat()}})
    if res.matched_count != 1:
        raise PartnerError(409, "changed", "The screens changed while you were saving. Try again.")
    await audit("partner.customer_screens_changed", actor=actor, partner_id=partner_id, customerId=customer_id,
                added=[s for s in final if s not in current], removed=[s for s in current if s not in final])
    return _features_view(partner_doc, final)


# --- the partner's own team (D-17) ----------------------------------------------------------------

_STAFF_ROLES = (rbac_defaults.PARTNER_ADMIN_KEY, rbac_defaults.PARTNER_VIEWER_KEY)


def _staff_role(user: Dict[str, Any]) -> Optional[str]:
    key = rbac_defaults.canonical_key(rbac_defaults.normalize_role(user.get("role")))
    return key if key in _STAFF_ROLES else None


async def _member(db, user: Dict[str, Any]) -> Dict[str, Any]:
    email = user.get("email") or ""
    return {"id": user.get("id"), "name": user.get("full_name") or user.get("name") or email, "email": email,
            "role": _staff_role(user) or user.get("role"), "status": await partner_invites.member_status(db, email)}


async def team(db, partner_doc: Dict[str, Any]) -> Dict[str, Any]:
    """The partner's own staff (people whose organization is the partner), never a customer's users."""
    users = await _raw(db).users.find(
        {"tenantId": partner_doc["id"]}, {"_id": 0, "id": 1, "email": 1, "name": 1, "full_name": 1, "role": 1},
    ).to_list(length=None)
    members = [await _member(db, user) for user in users]
    members.sort(key=lambda m: (str(m["name"]).casefold(), str(m["email"]).casefold()))
    return {"members": members}


async def invite_colleague(db, partner_doc: Dict[str, Any], *, name: str, email: str, role: str,
                           actor: Any) -> Dict[str, Any]:
    """Invite a partner_admin or partner_viewer into this partner; returns ``{member, emailSent}``, no link."""
    if role not in _STAFF_ROLES:
        raise PartnerError(422, "invalid_role", "Choose Partner Admin or Partner Viewer.")
    invited = await partner_invites.invite(
        db, tenant_id=partner_doc["id"], organization_name=partner_doc.get("name") or "", email=email,
        name=name.strip(), role=role, role_kind=role, invited_by=_actor_email(actor))
    user = invited["user"]
    await audit("partner.invite_sent", actor=actor, partner_id=partner_doc["id"], inviteeEmail=user["email"],
                roleKind=role, emailSent=bool(invited.get("emailSent")))
    member = {**user, "status": await partner_invites.member_status(db, user["email"])}
    return {"member": member, "emailSent": bool(invited.get("emailSent"))}


async def resend_colleague(db, partner_doc: Dict[str, Any], user_id: str, actor: Any) -> Dict[str, Any]:
    """Send a new seven-day link to a colleague who has not set a password; only inside this partner."""
    user = await _raw(db).users.find_one({"id": user_id, "tenantId": partner_doc["id"]}, {"_id": 0})
    role = _staff_role(user) if user else None
    if user is None or role is None:
        raise PartnerError(404, "not_found", "Team member not found")
    sent = await partner_invites.resend(
        db, user=user, organization_name=partner_doc.get("name") or "", role_kind=role, invited_by=_actor_email(actor))
    await audit("partner.invite_sent", actor=actor, partner_id=partner_doc["id"], inviteeEmail=user.get("email"),
                roleKind=role, emailSent=bool(sent), resent=True)
    return {"member": await _member(db, user), "emailSent": bool(sent)}

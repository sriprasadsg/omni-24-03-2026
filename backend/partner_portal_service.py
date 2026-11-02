"""The partner's side of the channel (Phase 87): create a customer from the pool, read the overview.

The partner is always the document ``partner_endpoints.current_partner`` loaded from the verified
token; nothing here takes a partner id from a request. An increase claims the pool first and a failed
insert gives the claim back (see ``partner_pool`` for the invariant). Raw handle, explicit filters.
"""
import logging
from typing import Any, Dict, Iterable, Optional

import licensing
import partner_invites
import partner_pool
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
    if not await partner_pool.claim(db, partner_id, seats, require_active=True):
        free = await partner_pool.free_seats(db, partner_id)
        raise PartnerError(409, "pool_full", f"Only {free} seats are free in your pool.", free=free)
    features = list(tenant_features.START_FEATURES) if enabled_features is None else list(enabled_features)
    doc = tenant_docs.build_tenant_doc(name, max_agents=seats, enabled_features=features, partner_id=partner_id)
    try:
        await _raw(db).tenants.insert_one(dict(doc))
    except Exception:
        await partner_pool.release(db, partner_id, seats)
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

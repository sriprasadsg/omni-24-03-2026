"""The Super Admin's side of the partner channel (Phase 87): appoint and list partners.

Raw handle and explicit filters throughout (``tenants`` is exempt from the tenant wrapper). A partner
is its own organization marked ``type: "partner"`` (D-13) with no seats of its own: ``license.maxAgents``
is stored as 0 so the licensing defaults never invent seats for it.
"""
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional

from pymongo.errors import DuplicateKeyError

import authentication_service
import licensing
import partner_invites
import partner_pool
import plan_service
import rbac_defaults
import tenant_features
from partner_pool import PartnerError, _raw
from partner_store import (PARTNER_TYPE, PLAN_CEILING_DEFAULT, audit, customer_rows, find_partner, name_taken,
                           partner_summary, plan_ceiling)

ALL_SCREENS = "all"
_NAME_UNAVAILABLE = "That name isn't available."


def validate_ceiling(values: Iterable[str]) -> List[str]:
    """The screen ceiling (D-10): switchable screens or features, or the single value ``all``."""
    cleaned = list(dict.fromkeys(values or []))
    for value in cleaned:
        if value != ALL_SCREENS and value not in tenant_features.SWITCHABLE:
            raise PartnerError(422, "invalid_screen", f"'{value}' is not a screen that can be sold.")
    if ALL_SCREENS in cleaned and len(cleaned) > 1:
        raise PartnerError(422, "invalid_screen", "'all' cannot be combined with individual screens.")
    return cleaned


def validate_plan_ceiling(values: Iterable[str]) -> List[str]:
    """The plans a partner may sell (D-13): canonical plan keys, de-duplicated in order. An empty list is
    allowed and means the partner changes no customer's plan."""
    cleaned: List[str] = []
    for value in values or []:
        key = plan_service.normalize_plan(value)
        if key is None:
            raise PartnerError(422, "invalid_plan", f"'{str(value)[:40]}' is not a plan.")
        if key not in cleaned:
            cleaned.append(key)
    return cleaned


def _utc_iso(value: Optional[datetime]) -> Optional[str]:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()


def _actor_email(actor: Any) -> str:
    if isinstance(actor, dict):
        return str(actor.get("email") or "system")
    return getattr(actor, "username", None) or "system"


async def _remove_half_appointed(db, partner_id: str, address: str) -> None:
    """Undo a failed appointment: the new organization and whatever the invite stored for it."""
    raw = _raw(db)
    await raw.tenants.delete_one({"id": partner_id, "type": PARTNER_TYPE})
    await raw.users.delete_many({"tenantId": partner_id})
    await raw.invites.delete_many({"tenantId": partner_id})
    await raw.password_reset_tokens.delete_many({"email": address, "invite": True})


async def appoint(db, *, name: str, pool_size: int, expires_at: Optional[datetime],
                  screen_ceiling: Iterable[str], admin_name: str, admin_email: str,
                  actor: Any, plan_ceiling: Optional[Iterable[str]] = None) -> Dict[str, Any]:
    """Create the partner organization and invite its first admin; returns ``{partner, emailSent}``.
    Every refusal (name, ceiling, email) comes before the first write."""
    name = name.strip()
    admin_name = admin_name.strip()
    ceiling = validate_ceiling(screen_ceiling)
    plans = validate_plan_ceiling(PLAN_CEILING_DEFAULT if plan_ceiling is None else plan_ceiling)
    address = partner_invites.normalize_email(admin_email)
    if await name_taken(db, name):
        raise PartnerError(409, "name_unavailable", _NAME_UNAVAILABLE)
    if await partner_invites.email_in_use(db, address):
        raise partner_invites._unavailable()
    now = datetime.now(timezone.utc).isoformat()
    doc = {
        "id": f"partner_{uuid.uuid4().hex[:12]}",
        "name": name,
        "type": PARTNER_TYPE,
        "partner": {
            "poolSize": pool_size,
            "allocated": 0,
            "expiresAt": _utc_iso(expires_at),
            "screenCeiling": ceiling,
            "planCeiling": plans,
            "status": "active",
        },
        "license": {"maxAgents": 0, "seatsUsed": 0, "inactiveReclaimDays": licensing.DEFAULT_RECLAIM_DAYS},
        "maxAgents": 0,
        "enabledFeatures": [],
        "emailConfig": {},
        "createdAt": now,
        "updatedAt": now,
    }
    try:
        await _raw(db).tenants.insert_one(dict(doc))
    except DuplicateKeyError:  # the name was taken after name_taken looked (WR-02); nothing is written yet
        raise PartnerError(409, "name_unavailable", _NAME_UNAVAILABLE)
    try:
        invited = await partner_invites.invite(
            db, tenant_id=doc["id"], organization_name=name, email=address, name=admin_name,
            role=rbac_defaults.PARTNER_ADMIN_KEY, role_kind="partner_admin", invited_by=_actor_email(actor))
    except Exception:
        await _remove_half_appointed(db, doc["id"], address)
        raise
    await audit("partner.appointed", actor=actor, partner_id=doc["id"], platform=True,
                poolSize=pool_size, expiresAt=doc["partner"]["expiresAt"], ceilingSize=len(ceiling),
                adminEmail=address)
    return {"partner": partner_summary(doc, 0), "emailSent": bool(invited.get("emailSent"))}


async def _summary_of(db, partner_id: str) -> Dict[str, Any]:
    raw = _raw(db)
    doc = await raw.tenants.find_one({"id": partner_id, "type": PARTNER_TYPE}, {"_id": 0})
    if doc is None:
        raise PartnerError(404, "not_found", "Partner not found")
    return partner_summary(doc, await raw.tenants.count_documents({"partnerId": partner_id}))


async def update_partner(db, partner_id: str, *, changes: Dict[str, Any], actor: Any) -> Dict[str, Any]:
    """Apply only the fields the caller sent: name, poolSize (never below what is handed out, D-07),
    expiresAt (``None`` clears it, D-08), screenCeiling (D-10) and planCeiling (D-13). Everything is validated, and the
    pool resize (the one step that can be refused by the data) runs, before any other field is written.
    A customer's screens are never touched (D-19). Returns the new summary."""
    raw = _raw(db)
    doc = await raw.tenants.find_one({"id": partner_id, "type": PARTNER_TYPE}, {"_id": 0})
    if doc is None:
        raise PartnerError(404, "not_found", "Partner not found")
    pool = doc.get("partner") or {}
    sets: Dict[str, Any] = {}
    events: List[tuple] = []
    if "name" in changes:
        name = str(changes["name"] or "").strip()
        if not name:
            raise PartnerError(422, "invalid_name", "Enter a name.")
        if name != doc.get("name"):
            if await name_taken(db, name, exclude_id=partner_id):
                raise PartnerError(409, "name_unavailable", _NAME_UNAVAILABLE)
            sets["name"] = name
            events.append(("partner.renamed", doc.get("name"), name))
    if "screenCeiling" in changes:
        ceiling = validate_ceiling(changes["screenCeiling"])
        before = [s for s in pool.get("screenCeiling") or [] if isinstance(s, str)]
        if ceiling != before:
            sets["partner.screenCeiling"] = ceiling
            events.append(("partner.ceiling_changed", before, ceiling))
    if "planCeiling" in changes:
        plans = validate_plan_ceiling(changes["planCeiling"])
        before_plans = plan_ceiling(doc)
        if plans != before_plans:
            sets["partner.planCeiling"] = plans
            events.append(("partner.plan_ceiling_changed", before_plans, plans))
    if "expiresAt" in changes:
        expiry = _utc_iso(changes["expiresAt"])
        if expiry != pool.get("expiresAt"):
            sets["partner.expiresAt"] = expiry
            events.append(("partner.expiry_changed", pool.get("expiresAt"), expiry))
    # The name is the one write the unique index can refuse (WR-02), so it goes first; a pool resize
    # refused after it puts the old name back, so a refusal never leaves half an update.
    renamed = sets.pop("name", None)
    if renamed is not None:
        try:
            await raw.tenants.update_one({"id": partner_id, "type": PARTNER_TYPE}, {"$set": {"name": renamed}})
        except DuplicateKeyError:
            raise PartnerError(409, "name_unavailable", _NAME_UNAVAILABLE)
    if "poolSize" in changes and changes["poolSize"] != pool.get("poolSize"):
        try:
            await partner_pool.set_pool_size(db, partner_id, changes["poolSize"])
        except Exception:
            if renamed is not None:
                await raw.tenants.update_one({"id": partner_id, "type": PARTNER_TYPE}, {"$set": {"name": doc.get("name")}})
            raise
        events.append(("partner.pool_changed", pool.get("poolSize"), changes["poolSize"]))
    if renamed is not None:
        sets["name"] = renamed
    if sets:
        sets["updatedAt"] = datetime.now(timezone.utc).isoformat()
        await raw.tenants.update_one({"id": partner_id, "type": PARTNER_TYPE}, {"$set": sets})
    for action, before, after in events:
        await audit(action, actor=actor, partner_id=partner_id, platform=True, before=before, after=after)
    return await _summary_of(db, partner_id)


_SIGN_OUT_FAILED = "Couldn't sign this partner's users out. Try again."


async def suspend(db, partner_id: str, actor: Any) -> Dict[str, Any]:
    """Lock a partner (D-15): its status flips to suspended and every one of its users is signed out.
    Only the partner's own document and its users are read or written; customers, their seats and
    their agents are never touched. Repeating it records nothing new but signs the users out again,
    so a retry after a failed sign-out finishes the job."""
    raw = _raw(db)
    now = datetime.now(timezone.utc).isoformat()
    res = await raw.tenants.update_one(
        {"id": partner_id, "type": PARTNER_TYPE, "partner.status": {"$ne": "suspended"}},
        {"$set": {"partner.status": "suspended", "partner.suspendedAt": now,
                  "partner.suspendedBy": _actor_email(actor), "updatedAt": now}})
    if res.matched_count == 0 and await raw.tenants.find_one({"id": partner_id, "type": PARTNER_TYPE}, {"_id": 1}) is None:
        raise PartnerError(404, "not_found", "Partner not found")
    if res.matched_count == 1:
        await audit("partner.suspended", actor=actor, partner_id=partner_id, platform=True,
                    before="active", after="suspended")
    failed = False
    async for user in raw.users.find({"tenantId": partner_id}, {"_id": 0, "email": 1}):
        try:
            await authentication_service.revoke_user_sessions(user.get("email"), "partner suspended")
        except Exception:
            failed = True
    if failed:
        # The status is already suspended, so the chokepoint refuses these users either way.
        raise PartnerError(503, "sign_out_failed", _SIGN_OUT_FAILED)
    return await _summary_of(db, partner_id)


async def reinstate(db, partner_id: str, actor: Any) -> Dict[str, Any]:
    """Lift a suspension: status active again, the suspension stamp removed. Nothing else changes."""
    raw = _raw(db)
    res = await raw.tenants.update_one(
        {"id": partner_id, "type": PARTNER_TYPE, "partner.status": "suspended"},
        {"$set": {"partner.status": "active", "updatedAt": datetime.now(timezone.utc).isoformat()},
         "$unset": {"partner.suspendedAt": "", "partner.suspendedBy": ""}})
    if res.matched_count == 1:
        await audit("partner.reinstated", actor=actor, partner_id=partner_id, platform=True,
                    before="suspended", after="active")
    return await _summary_of(db, partner_id)


async def list_partners(db) -> List[Dict[str, Any]]:
    """Every partner with its pool and customer count, ordered by name then id."""
    raw = _raw(db)
    partners = await raw.tenants.find({"type": PARTNER_TYPE}, {"_id": 0}).to_list(length=None)
    counts: Dict[str, int] = {}
    async for row in raw.tenants.aggregate([
        {"$match": {"partnerId": {"$type": "string"}}},
        {"$group": {"_id": "$partnerId", "count": {"$sum": 1}}},
    ]):
        counts[row["_id"]] = row["count"]
    out = [partner_summary(p, counts.get(p["id"], 0)) for p in partners]
    out.sort(key=lambda s: (str(s["name"] or "").casefold(), s["id"]))
    return out


async def partner_customers(db, partner_id: str) -> List[Dict[str, Any]]:
    """The partner's customers as the D-01 rows; a missing partner (or a customer's id) is a 404."""
    partner = await find_partner(db, partner_id)
    if partner is None:
        raise PartnerError(404, "not_found", "Partner not found")
    return await customer_rows(db, partner)


async def direct_customers(db) -> List[Dict[str, Any]]:
    """Organizations that belong to no partner (never a partner organization or the platform), by name."""
    docs = await _raw(db).tenants.find(
        {"partnerId": {"$exists": False}, "type": {"$ne": PARTNER_TYPE}, "id": {"$ne": "platform-admin"}},
        {"_id": 0, "id": 1, "name": 1, "license": 1, "maxAgents": 1},
    ).to_list(length=None)
    rows = [{"id": d["id"], "name": d.get("name"), "seatsAssigned": licensing.license_of(d)["maxAgents"]}
            for d in docs if d.get("id")]
    rows.sort(key=lambda r: (str(r["name"] or "").casefold(), r["id"]))
    return rows


async def move(db, customer_id: str, target_partner_id: Optional[str], actor: Any) -> Dict[str, Any]:
    """Move a customer to another partner's pool, or to direct (``None``), keeping its seats (D-11, D-18).
    The pool arithmetic is partner_pool's one atomic path; this adds the audit under the platform and
    each partner involved."""
    customer = await _raw(db).tenants.find_one({"id": customer_id, "type": {"$ne": PARTNER_TYPE}}, {"_id": 0, "name": 1})
    moved = await partner_pool.move_customer(db, customer_id, target_partner_id)
    involved = [pid for pid in (moved["from"], moved["to"]) if pid]
    for index, pid in enumerate(involved):
        await audit("partner.customer_moved", actor=actor, partner_id=pid, platform=index == 0,
                    customerId=customer_id, customerName=(customer or {}).get("name"), seats=moved["seats"],
                    **{"from": moved["from"], "to": moved["to"]})
    return {"id": customer_id, "name": (customer or {}).get("name"), "partnerId": target_partner_id}

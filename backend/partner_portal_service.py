"""The partner's side of the channel (Phase 87): create a customer from the pool, read the overview.

The partner is always the document ``partner_endpoints.current_partner`` loaded from the verified
token; nothing here takes a partner id from a request. An increase claims the pool first and a failed
insert gives the claim back (see ``partner_pool`` for the invariant). Raw handle, explicit filters.
"""
import logging
from typing import Any, Dict, Iterable, Optional

import partner_pool
import tenant_docs
import tenant_features
from partner_pool import PartnerError, _raw
from partner_store import audit, customer_rows, name_taken, pool_view

logger = logging.getLogger(__name__)

NAME_UNAVAILABLE = "That name isn't available."


async def create_customer(db, partner_doc: Dict[str, Any], *, name: str, seats: int,
                          enabled_features: Optional[Iterable[str]], actor: Any) -> Dict[str, Any]:
    """Create one customer organization with ``seats`` claimed from the pool; returns its D-01 row."""
    partner_id = partner_doc["id"]
    name = name.strip()
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
    await tenant_docs.ensure_tenant_extras(_raw(db), doc["id"])
    await audit("partner.customer_created", actor=actor, partner_id=partner_id,
                customerId=doc["id"], customerName=name, seats=seats)
    for row in await customer_rows(db, partner_doc):
        if row["id"] == doc["id"]:
            return row
    raise RuntimeError("created customer not found")  # pragma: no cover - the insert above just succeeded


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

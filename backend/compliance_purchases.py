"""Per-tenant compliance framework purchases.

The Super Admin prices every compliance framework in Service Pricing Configuration
(category "Compliance", at least $5.00 per tenant per month) and ticks, per tenant, the
frameworks that tenant purchased (``tenants.purchasedFrameworks``). A tenant's users see
only those frameworks, plus any framework the tenant created itself; each purchased
framework is a monthly line on the tenant's invoice at its configured price.

Every function takes the raw (unwrapped) Motor database: the framework catalogue, the
price list and the tenant record are platform data, read with explicit ids.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

PLATFORM_TENANT_ID = "platform-admin"
CATEGORY = "Compliance"
UNIT = "per_tenant_per_month"
MIN_PRICE = 5.00
# The generic compliance entries the per-framework prices replace (never billed).
LEGACY_PRICE_IDS = frozenset({"price-compliance", "price-soc2", "price-pci-dss",
                              "compliance_soc2", "compliance_iso27001"})


def price_id(framework_id: str) -> str:
    return f"compliance-{framework_id}"


def is_framework_price(entry: Dict[str, Any]) -> bool:
    return bool(entry.get("frameworkId")) or entry.get("category") == CATEGORY


def check_price(entry: Dict[str, Any]) -> None:
    """ValueError unless the price is a number >= 0, and >= $5.00 for a compliance entry."""
    try:
        price = float(entry.get("price"))
    except (TypeError, ValueError):
        raise ValueError("price must be a number")
    if price != price or price < 0:  # NaN or negative
        raise ValueError("price must be a non-negative number")
    if is_framework_price(entry) and price < MIN_PRICE:
        raise ValueError(f"compliance framework prices must be at least ${MIN_PRICE:.2f} per tenant per month")


def default_price_entry(framework: Dict[str, Any]) -> Dict[str, Any]:
    name = framework.get("name") or framework["id"]
    return {"id": price_id(framework["id"]), "frameworkId": framework["id"], "name": name,
            "category": CATEGORY, "unit": UNIT, "price": MIN_PRICE,
            "description": f"{name} compliance framework, billed monthly per tenant."}


async def catalogue_frameworks(raw_db) -> List[Dict[str, Any]]:
    """The platform's framework catalogue (frameworks no tenant owns), id and name only."""
    return await raw_db.compliance_frameworks.find(
        {"tenantId": {"$in": [None, ""]}}, {"_id": 0, "id": 1, "name": 1}).to_list(length=1000)


async def framework_prices(raw_db) -> Dict[str, Dict[str, Any]]:
    """``{framework id: price entry}`` for every catalogue framework; a framework without a
    stored entry gets the $5.00 default."""
    stored = {doc["frameworkId"]: doc async for doc in raw_db.service_pricing.find(
        {"frameworkId": {"$type": "string"}}, {"_id": 0})}
    return {fw["id"]: stored.get(fw["id"]) or default_price_entry(fw)
            for fw in await catalogue_frameworks(raw_db)}


async def purchased(raw_db, tenant_id: Optional[str]) -> List[str]:
    """The tenant's purchased framework ids; none for no tenant or no list."""
    if not tenant_id:
        return []
    doc = await raw_db.tenants.find_one({"id": tenant_id}, {"_id": 0, "purchasedFrameworks": 1})
    ids = (doc or {}).get("purchasedFrameworks")
    return [i for i in ids if isinstance(i, str)] if isinstance(ids, list) else []


async def visible_filter(raw_db, tenant_id: Optional[str]) -> Optional[Dict[str, Any]]:
    """The extra framework filter for a request in ``tenant_id``'s context.

    None (no restriction) for the platform context and for work with no tenant context
    (startup seeding, background jobs); otherwise the purchased catalogue frameworks plus
    the tenant's own. A failed tenant lookup propagates, so the read fails rather than
    showing everything.
    """
    if not tenant_id or tenant_id == PLATFORM_TENANT_ID:
        return None
    return {"$or": [{"id": {"$in": await purchased(raw_db, tenant_id)}}, {"tenantId": tenant_id}]}


async def validate_purchase(raw_db, framework_ids: List[str]) -> List[str]:
    """De-duplicated ids, each an existing catalogue framework; ValueError names the unknown."""
    ids = list(dict.fromkeys(i for i in framework_ids if isinstance(i, str) and i))
    known = {fw["id"] for fw in await catalogue_frameworks(raw_db)}
    unknown = [i for i in ids if i not in known]
    if unknown:
        raise ValueError(f"unknown compliance framework(s): {', '.join(unknown[:10])}")
    return ids


async def invoice_lines(raw_db, tenant_id: str) -> List[Dict[str, Any]]:
    """One monthly line per purchased framework, at its configured price."""
    prices = await framework_prices(raw_db)
    lines = []
    for fid in await purchased(raw_db, tenant_id):
        entry = prices.get(fid)
        if entry is None:
            continue  # framework removed from the catalogue since it was purchased
        price = round(float(entry["price"]), 2)
        lines.append({"description": f"Compliance framework: {entry['name']} (monthly)",
                      "frameworkId": fid, "quantity": 1, "unit_price": price, "amount": price})
    return lines

"""Asset finance-field strip (Phase 76 D-04, D-10).

Asset reads stay open to ``view:assets``, but purchase, warranty and depreciation
fields are only returned to callers who hold ``view:itam`` (or its ``manage:itam`` twin,
D-03). The strip always builds new dicts: the ``@cached`` layer can hand the same stored
object to later requests, so a caller's response must never be edited in place.

``finance_filtered`` sits *outside* ``@cached``. The cache keeps the full document under
its per-user key and the strip runs on every request, so a role edit changes what a
caller sees immediately instead of after the cache TTL.
"""
from __future__ import annotations

import functools
from typing import Any, Awaitable, Callable, Dict, Iterable, List

from rbac_utils import verify_permission

# Stored purchase/finance/warranty keys (itam_models.Asset, AssetPurchaseUpdate) plus the
# computed names the finance and reporting services use, so a document that carries a
# derived value is stripped too.
ASSET_FINANCE_FIELDS = frozenset({
    "purchaseCostCents", "purchaseDate", "poNumber", "purchase_order_id", "supplierId",
    "warrantyMonths", "warranty_expiry_date", "warrantyAlertSentAt", "warrantyExpiresAt",
    "warrantyStatus", "salvage_value", "salvageValueCents", "useful_life_years",
    "usefulLifeYears", "bookValueCents", "currentBookValueCents",
})


async def can_view_finance(user: Any) -> bool:
    """True when the caller holds view:itam or manage:itam (super admin passes both)."""
    return await verify_permission(user, "view:itam") or await verify_permission(user, "manage:itam")


def strip_finance(doc: Any) -> Any:
    """Copy of *doc* without finance keys; anything that is not a dict comes back unchanged."""
    if not isinstance(doc, dict):
        return doc
    return {k: v for k, v in doc.items() if k not in ASSET_FINANCE_FIELDS}


def strip_finance_many(docs: Iterable[Any]) -> List[Any]:
    """New list of stripped copies."""
    return [strip_finance(d) for d in docs]


def strip_payload(payload: Any) -> Any:
    """Strip a list, a paginated ``{"items": [...]}`` page or a single document."""
    if isinstance(payload, list):
        return strip_finance_many(payload)
    if isinstance(payload, dict) and isinstance(payload.get("items"), list):
        page: Dict[str, Any] = dict(payload)
        page["items"] = strip_finance_many(payload["items"])
        return page
    return strip_finance(payload)


def finance_filtered(handler: Callable[..., Awaitable[Any]]) -> Callable[..., Awaitable[Any]]:
    """Route decorator: strip finance keys unless the handler's ``current_user`` may see them."""
    @functools.wraps(handler)
    async def wrapper(*args, **kwargs):
        payload = await handler(*args, **kwargs)
        if await can_view_finance(kwargs.get("current_user")):
            return payload
        return strip_payload(payload)

    return wrapper

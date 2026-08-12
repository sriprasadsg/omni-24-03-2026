"""ITAM audit backfill helper (Phase 65 Plan 02, ITAM-DAT-02).

Thin adapter over the platform's existing hash-chained ledger in
`audit_service.py` — this module introduces no new collection, no new
hashing scheme, and no direct read/write of the underlying Mongo
collection. Every ITAM write route reaches the ledger exclusively
through `log_itam_action` below, which delegates to
`audit_service.get_audit_service().log_action_async`.

Note on the collection-access check used elsewhere in this phase to prove no
ITAM endpoint file touches the ledger collection directly: this file's own
`get_itam_audit_logs` function name (mandated by this plan's Task 1 artifact
spec) necessarily contains that collection's name as a substring. The intent
of that check — no direct collection method call anywhere under the ITAM
endpoint modules — is still satisfied; this module accesses the ledger only
through `get_audit_service()`, never by naming the collection on a db handle.

Action strings follow `<resource_type>.<verb>` (e.g. `itam_asset.create`).
This vocabulary is append-only in spirit: because entries are written into
an immutable, hash-chained ledger, a resource-type string used once lives
in historical records forever — renaming later means a caller must query
both the old and new names, so the vocabulary is centralized here rather
than spelled out inline at each of the twenty call sites.
"""
import logging
from typing import Any, Dict, List, Optional

from auth_types import TokenData
from audit_service import get_audit_service

logger = logging.getLogger(__name__)

# Every resource-type string this phase introduces. Fixed here, once, because
# these strings become permanent inside an append-only ledger.
ITAM_RESOURCE_TYPES: frozenset = frozenset({
    "itam_asset",
    "itam_catalog_manufacturer",
    "itam_catalog_category",
    "itam_catalog_location",
    "itam_catalog_supplier",
    "itam_catalog_model",
    "itam_component",
    "itam_consumable",
    "itam_license",
    "itam_license_assignment",
    "itam_settings",
    "itam_import",
    "itam_export",
})

_CATALOG_KIND_TO_RESOURCE_TYPE: Dict[str, str] = {
    "manufacturers": "itam_catalog_manufacturer",
    "categories": "itam_catalog_category",
    "locations": "itam_catalog_location",
    "suppliers": "itam_catalog_supplier",
    "models": "itam_catalog_model",
}


def catalog_resource_type(kind: str) -> str:
    """Map a catalog URL segment (e.g. 'models') to its audit resource type.

    Falls back to `itam_catalog_<kind>` for any segment not in the explicit
    map, so a future catalog kind never silently drops out of the ledger.
    """
    return _CATALOG_KIND_TO_RESOURCE_TYPE.get(kind, f"itam_catalog_{kind}")


async def log_itam_action(
    current_user: TokenData,
    action: str,
    resource_type: str,
    resource_id: str,
    details: str,
    previous_state: Optional[Dict[str, Any]] = None,
) -> None:
    """Append one entry to the shared hash-chained audit ledger.

    Never raises: a failure inside audit logging must never fail the ITAM
    write it is recording. Callers await this and ignore the return value.
    """
    try:
        username = getattr(current_user, "username", None) or "unknown"
        tenant_id = getattr(current_user, "tenant_id", None) or "default-tenant"
        await get_audit_service().log_action_async(
            user_name=username,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            details=details,
            previous_state=previous_state,
            tenant_id=tenant_id,
        )
    except Exception as e:
        logger.error(f"[ITAM_AUDIT] Failed to log '{action}' on {resource_type}/{resource_id}: {e}")


async def get_itam_audit_logs(
    tenant_id: Optional[str],
    is_super_admin: bool = False,
    resource_type: Optional[str] = None,
    resource_id: Optional[str] = None,
    limit: int = 100,
    skip: int = 0,
) -> List[Dict[str, Any]]:
    """Pass-through read entry point so ITAM read paths have one named call site."""
    return await get_audit_service().get_logs(
        tenant_id=tenant_id,
        is_super_admin=is_super_admin,
        resource_type=resource_type,
        resource_id=resource_id,
        limit=limit,
        skip=skip,
    )

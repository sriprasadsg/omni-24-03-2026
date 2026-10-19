"""SAML attribute extraction, user provisioning, and group->role mapping
(ITAM-USR-04). Split out of saml_service.py up front per the plan's
<module_budget> to keep both files under the CLAUDE.md 500-line cap —
mirrors the ldap_service.py LDAPUserSyncer / LDAPGroupMapper split.
"""
import logging
from datetime import datetime, timezone
from typing import Optional

from pymongo.errors import DuplicateKeyError

from database import get_database

logger = logging.getLogger(__name__)


def _is_super_admin_tier(role: Optional[str]) -> bool:
    """True when ``role`` normalizes to the super-admin tier (decided by name, never by permissions)."""
    from rbac_service import RBACService
    import rbac_defaults
    return RBACService._normalize_role(role or "") == rbac_defaults.SUPER_ADMIN_KEY


class SAMLMappingError(Exception):
    """Attribute mapping or group-mapping configuration is invalid."""


class SAMLUserProvisioner:
    """Extracts ITAM user fields from a validated SAML assertion and
    upserts into MongoDB with source="saml" (Pitfall 4 / T-64-17)."""

    def __init__(self, config):
        self.config = config

    def extract_attributes(self, nameid: Optional[str], attributes: dict) -> dict:
        """Map SAML NameID/attributes onto ITAM user fields using the
        configurable attribute names in SAMLConfig. Falls back to NameID
        for email when it looks like an email address (common IdP default:
        NameIDFormat=emailAddress)."""
        def _first(attr_name: str) -> Optional[str]:
            vals = attributes.get(attr_name) or []
            return vals[0] if vals else None

        email = _first(self.config.attribute_email)
        if not email and nameid and "@" in nameid:
            email = nameid
        name = _first(self.config.attribute_name) or email
        groups = attributes.get(self.config.attribute_groups) or []
        return {
            "nameid": nameid,
            "email": email,
            "full_name": name,
            "groups": list(groups),
        }

    async def provision_user(self, mapped: dict, tenant_id: str, role: Optional[str] = None,
                              default_role: str = "itam_viewer") -> dict:
        """Upsert a single mapped SAML user into MongoDB with source="saml".

        `role` should only be passed when a group mapping actually resolved
        one — on update, an existing user's role is left untouched when
        `role` is None (mirrors ldap_service.LDAPUserSyncer.sync_user's
        role-clobber guard), so a re-login never silently downgrades an
        admin-assigned elevated role back to the default.
        """
        if role:
            from rbac_service import RBACService
            import rbac_defaults
            if RBACService._normalize_role(role) == rbac_defaults.SUPER_ADMIN_KEY:
                # D-22 apply time: a directory group can never grant the super-admin tier.
                logger.warning(
                    "SAML mapping resolved %s to super-admin-tier role %r in tenant %s; "
                    "refusing it and keeping the existing or default role",
                    mapped["email"], role, tenant_id,
                )
                role = None
        db = get_database()
        now = datetime.now(timezone.utc).isoformat()
        existing = await db.users.find_one({"email": mapped["email"], "tenantId": tenant_id})
        if role and existing and _is_super_admin_tier(existing.get("role")):
            # A directory mapping may not replace the role of a platform super-admin account.
            logger.warning(
                "SAML mapping resolved %s to role %r but the existing account is super-admin-tier; "
                "keeping its role", mapped["email"], role,
            )
            role = None
        doc = {
            "email": mapped["email"],
            "full_name": mapped["full_name"],
            "tenantId": tenant_id,
            "source": "saml",
            "saml_nameid": mapped.get("nameid"),
            "saml_groups": mapped.get("groups", []),
            "updatedAt": now,
        }
        if existing:
            if role:
                doc["role"] = role
            if doc.get("role", existing.get("role", default_role)) != existing.get("role"):
                # Revoke BEFORE the write: if the cutoff cannot be stored the role is not
                # changed, so a demotion never persists while the old session survives (WR-05).
                from authentication_service import revoke_user_sessions
                await revoke_user_sessions(doc["email"], "saml role change")
            # Never touch status on an existing account: a directory sign-in
            # must not undo an admin's disable.
            await db.users.update_one({"_id": existing["_id"]}, {"$set": doc})
            doc["_id"] = existing["_id"]
            doc["role"] = doc.get("role", existing.get("role", default_role))
            doc["status"] = existing.get("status", "Active")
        else:
            doc["status"] = "Active"
            doc["role"] = role or default_role
            doc["createdAt"] = now
            # DB-F09 (2026-08-25 audit): users.email has a *global* unique
            # index (database.py), but this lookup is tenant-scoped, so a
            # brand-new user for this tenant can still collide with an
            # existing user of the same email under a different tenant.
            # Left unhandled, this surfaced as a raw pymongo
            # DuplicateKeyError propagating out of a live SAML login.
            try:
                result = await db.users.insert_one(doc)
            except DuplicateKeyError:
                raise SAMLMappingError(
                    f"Could not provision SAML user '{mapped['email']}' for this tenant: "
                    "this email is already registered. Contact your administrator."
                )
            doc["_id"] = result.inserted_id
        return doc


class SAMLGroupMapper:
    """Maps SAML group-attribute values to ITAM roles via an admin-managed
    `saml_group_mappings` collection (mirrors LDAPGroupMapper)."""

    async def resolve_role(self, group_values: list, tenant_id: Optional[str] = None) -> Optional[str]:
        """Given the group attribute values from a validated assertion,
        return the highest-priority mapped ITAM role, or None if no mapping
        matches (existing admin-assigned roles are then left untouched)."""
        if not group_values:
            return None
        db = get_database()
        query: dict = {"group_value": {"$in": group_values}}
        if tenant_id:
            query["tenant_id"] = tenant_id
        mappings = await db.saml_group_mappings.find(query).sort("priority", 1).to_list(100)
        if mappings:
            return mappings[0].get("role")
        return None

    @staticmethod
    async def list_mappings(tenant_id: Optional[str] = None) -> list:
        db = get_database()
        query: dict = {"tenant_id": tenant_id} if tenant_id else {}
        docs = await db.saml_group_mappings.find(query).to_list(200)
        for d in docs:
            d["_id"] = str(d["_id"])
        return docs

    @staticmethod
    async def upsert_mapping(group_value: str, role: str, tenant_id: Optional[str] = None,
                              priority: int = 100) -> dict:
        from rbac_service import RBACService
        import rbac_defaults
        normalized = RBACService._normalize_role(role)
        if normalized not in rbac_defaults.builtin_role_keys():
            # 77 D-04: a custom role of this mapping's own tenant, stored under its canonical name.
            if not tenant_id:
                raise SAMLMappingError(f"'{role}' is not a valid ITAM role")
            from role_contents import find_custom_role
            try:
                custom = await find_custom_role(get_database(), tenant_id, name=role)
            except Exception as exc:  # fail closed: an unverifiable role is never stored
                logger.warning("Role store error while validating mapping role %r: %s", role, exc)
                raise SAMLMappingError(f"'{role}' is not a valid ITAM role")
            if custom is None:
                raise SAMLMappingError(f"'{role}' is not a valid ITAM role")
            role = custom["name"]

        db = get_database()
        doc = {"group_value": group_value, "role": role, "tenant_id": tenant_id, "priority": priority}
        result = await db.saml_group_mappings.update_one(
            {"group_value": group_value, "tenant_id": tenant_id},
            {"$set": doc},
            upsert=True,
        )
        doc["_id"] = str(result.upserted_id) if getattr(result, "upserted_id", None) else None
        return doc

    @staticmethod
    async def get_mapping(mapping_id: str) -> Optional[dict]:
        from bson import ObjectId
        db = get_database()
        return await db.saml_group_mappings.find_one({"_id": ObjectId(mapping_id)})

    @staticmethod
    async def delete_mapping(mapping_id: str) -> bool:
        from bson import ObjectId
        db = get_database()
        result = await db.saml_group_mappings.delete_one({"_id": ObjectId(mapping_id)})
        return result.deleted_count > 0

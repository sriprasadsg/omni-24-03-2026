"""SCIM 2.0 Groups and the roles they give (scim_service holds tokens, filters and Users).

A group is a ``scim_groups`` document of one organization: displayName, externalId and member user ids. Roles come
from the organization's directory group mappings, the same ``saml_group_mappings`` SAML uses: a mapping whose
group_value equals a group's displayName or externalId offers its role, the lowest priority number winning.
Whenever a user's groups change their role is worked out again: the mapped role, or ``viewer`` when no mapping
matches and the directory gave the current role. directory_role_guard decides whether it may be written (a role
an admin raised by hand, or a higher-privileged local account, is kept), a mapping to a super-admin, platform or
partner role is never applied, and a change ends the user's sessions before it is written.
"""
import re
import uuid
from typing import Any, Dict, List, Optional, Set

import directory_role_guard
import rbac_defaults
from scim_service import (DEFAULT_ROLE, GROUP_SCHEMA, ScimError, audit, ci_equals, is_super, list_response, now_iso,
                          page_args, parse_filter, raw_db)

GROUP_FILTERS = {"displayname": "displayName", "externalid": "externalId", "id": "id"}
MAX_MEMBERS = 5000
MEMBER_PATH = re.compile(r'^members\[value eq "([^"]+)"\]$', re.I)


def group_resource(doc: Dict[str, Any], names: Dict[str, str], base: str, members: bool = True) -> Dict[str, Any]:
    out = {"schemas": [GROUP_SCHEMA], "id": doc["id"], "displayName": doc.get("displayName"),
           "externalId": doc.get("externalId"),
           "meta": {"resourceType": "Group", "created": doc.get("createdAt"), "lastModified": doc.get("updatedAt"),
                    "location": f"{base}/Groups/{doc['id']}"}}
    if members:
        out["members"] = [{"value": m, "display": names.get(m), "$ref": f"{base}/Users/{m}"} for m in doc.get("members", [])]
    return out


async def _names(db, tenant: str, ids: List[str]) -> Dict[str, str]:
    if not ids:
        return {}
    rows = await raw_db(db).users.find({"tenantId": tenant, "id": {"$in": list(ids)}}, {"_id": 0, "id": 1, "name": 1, "email": 1}).to_list(len(ids))
    return {r["id"]: r.get("name") or r.get("email") for r in rows}


async def _members(db, tenant: str, value: Any) -> List[str]:
    """Member ids from a SCIM members value, each a live (not SCIM-deleted) user of the organization."""
    if value is None:
        return []
    items = value if isinstance(value, list) else [value]
    ids = list(dict.fromkeys(str(m.get("value") if isinstance(m, dict) else m) for m in items if m))
    if len(ids) > MAX_MEMBERS:
        raise ScimError(400, f"A group holds at most {MAX_MEMBERS} members", "invalidValue")
    found = await raw_db(db).users.find({"tenantId": tenant, "id": {"$in": ids}, "scimDeleted": {"$ne": True}},
                                        {"_id": 0, "id": 1, "role": 1}).to_list(len(ids) or 1)
    known = {u["id"] for u in found if not is_super(u.get("role"))}
    missing = [i for i in ids if i not in known]
    if missing:
        raise ScimError(400, f"Unknown member {missing[0]}", "invalidValue")
    return ids


async def load_group(db, tenant: str, group_id: str) -> Dict[str, Any]:
    doc = await raw_db(db).scim_groups.find_one({"tenantId": tenant, "id": group_id}, {"_id": 0})
    if not doc:
        raise ScimError(404, "Group not found")
    return doc


async def get_group(db, tenant: str, group_id: str, base: str, members: bool = True) -> Dict[str, Any]:
    doc = await load_group(db, tenant, group_id)
    return group_resource(doc, await _names(db, tenant, doc.get("members", [])), base, members)


async def list_groups(db, tenant: str, filt: Optional[str], start: Optional[int], count: Optional[int], base: str,
                      members: bool = True) -> Dict[str, Any]:
    start, count = page_args(start, count)
    query: Dict[str, Any] = {"tenantId": tenant}
    parsed = parse_filter(filt, GROUP_FILTERS)
    if parsed:
        field, value = parsed
        query[field] = ci_equals(str(value)) if field == "displayName" else str(value)
    raw = raw_db(db)
    total = await raw.scim_groups.count_documents(query)
    docs = await raw.scim_groups.find(query, {"_id": 0}).sort("createdAt", 1).skip(start - 1).limit(count).to_list(count)
    names = await _names(db, tenant, sorted({m for d in docs for m in d.get("members", [])})) if members else {}
    return list_response([group_resource(d, names, base, members) for d in docs], total, start)


async def _name_free(db, tenant: str, name: str, group_id: Optional[str]) -> None:
    if await raw_db(db).scim_groups.find_one({"tenantId": tenant, "displayName": ci_equals(name), "id": {"$ne": group_id}}, {"_id": 1}):
        raise ScimError(409, f"A group named {name} already exists", "uniqueness")


def _display(body: Dict[str, Any]) -> str:
    name = str(body.get("displayName") or "").strip()[:200]
    if not name:
        raise ScimError(400, "displayName is required", "invalidValue")
    return name


async def create_group(db, tenant: str, body: Dict[str, Any], actor: str, base: str) -> Dict[str, Any]:
    name = _display(body)
    await _name_free(db, tenant, name, None)
    members = await _members(db, tenant, body.get("members"))
    doc = {"id": f"grp-{uuid.uuid4().hex[:16]}", "tenantId": tenant, "displayName": name,
           "externalId": str(body.get("externalId") or "")[:200] or None, "members": members,
           "createdAt": now_iso(), "updatedAt": now_iso()}
    await raw_db(db).scim_groups.insert_one(dict(doc))
    await audit(db, "scim.group.create", tenant, actor, resourceId=doc["id"], target=name, members=len(members))
    await recompute_roles(db, tenant, members, actor)
    return await get_group(db, tenant, doc["id"], base)


async def _write(db, tenant: str, doc: Dict[str, Any], changes: Dict[str, Any], actor: str, action: str) -> None:
    before = set(doc.get("members", []))
    await raw_db(db).scim_groups.update_one({"tenantId": tenant, "id": doc["id"]}, {"$set": {**changes, "updatedAt": now_iso()}})
    after = set(changes.get("members", doc.get("members", [])))
    await audit(db, action, tenant, actor, resourceId=doc["id"], target=changes.get("displayName", doc.get("displayName")),
                added=len(after - before), removed=len(before - after))
    touched = (before ^ after) if "members" in changes else set()
    if "displayName" in changes or "externalId" in changes:
        touched |= after  # a rename can match a different mapping
    await recompute_roles(db, tenant, touched, actor)


async def replace_group(db, tenant: str, group_id: str, body: Dict[str, Any], actor: str, base: str) -> Dict[str, Any]:
    doc = await load_group(db, tenant, group_id)
    name = _display(body)
    if name.lower() != str(doc.get("displayName") or "").lower():
        await _name_free(db, tenant, name, group_id)
    changes = {"displayName": name, "externalId": str(body.get("externalId") or "")[:200] or None,
               "members": await _members(db, tenant, body.get("members"))}
    await _write(db, tenant, doc, changes, actor, "scim.group.replace")
    return await get_group(db, tenant, group_id, base)


async def patch_group(db, tenant: str, group_id: str, body: Dict[str, Any], actor: str, base: str) -> Optional[Dict[str, Any]]:
    """PATCH /Groups/{id}: add/remove/replace members, replace displayName or externalId."""
    doc = await load_group(db, tenant, group_id)
    ops = body.get("Operations")
    if not isinstance(ops, list) or not ops:
        raise ScimError(400, "Operations must be a non-empty list", "invalidSyntax")
    members: List[str] = list(doc.get("members", []))
    changes: Dict[str, Any] = {}
    for op in ops:
        kind = str((op or {}).get("op") or "").lower()
        path, value = (op.get("path") or "").strip(), op.get("value")
        single = MEMBER_PATH.match(path)
        if kind not in ("add", "replace", "remove"):
            raise ScimError(400, f"Unsupported op {op.get('op') if isinstance(op, dict) else op!r}", "invalidSyntax")
        if path.lower() == "members" or single or (not path and kind == "add" and isinstance(value, list)):
            if kind == "remove":
                drop = {single.group(1)} if single else ({str(m.get("value")) for m in value if isinstance(m, dict)}
                                                         if isinstance(value, list) else set(members))
                members = [m for m in members if m not in drop]
            else:
                new = await _members(db, tenant, value)
                members = new if kind == "replace" else list(dict.fromkeys(members + new))
            changes["members"] = members
        elif path.lower() in ("displayname", "externalid") or (not path and isinstance(value, dict)):
            items = {path: value} if path else value
            for key, item in items.items():
                if key.lower() == "displayname":
                    name = _display({"displayName": item})
                    await _name_free(db, tenant, name, group_id)
                    changes["displayName"] = name
                elif key.lower() == "externalid":
                    changes["externalId"] = (str(item or "")[:200] or None) if kind != "remove" else None
                elif key.lower() == "members":
                    changes["members"] = members = await _members(db, tenant, item)
        else:
            raise ScimError(400, f"Unsupported path {path!r}", "invalidPath")
    if len(members) > MAX_MEMBERS:
        raise ScimError(400, f"A group holds at most {MAX_MEMBERS} members", "invalidValue")
    if changes:
        await _write(db, tenant, doc, changes, actor, "scim.group.patch")
    return await get_group(db, tenant, group_id, base)


async def delete_group(db, tenant: str, group_id: str, actor: str) -> None:
    doc = await load_group(db, tenant, group_id)
    await raw_db(db).scim_groups.delete_one({"tenantId": tenant, "id": group_id})
    await audit(db, "scim.group.delete", tenant, actor, resourceId=group_id, target=doc.get("displayName"))
    await recompute_roles(db, tenant, doc.get("members", []), actor)


# ── Roles from groups ───────────────────────────────────────────────────────


def _mappable(role: Optional[str]) -> bool:
    return bool(role) and not is_super(role) and not rbac_defaults.is_platform_role(role) \
        and not rbac_defaults.is_partner_role(role)


async def mapped_role(db, tenant: str, values: List[str]) -> Optional[str]:
    """The role the organization's group mappings give these group names/ids, or None."""
    if not values:
        return None
    raw = raw_db(db)
    maps = await raw.saml_group_mappings.find({"tenant_id": tenant, "group_value": {"$in": values}}).sort("priority", 1).to_list(100)
    for mapping in maps:
        if _mappable(mapping.get("role")) and await directory_role_guard.mapping_still_assignable(raw, mapping, tenant, "scim"):
            return mapping["role"]
    return None


async def recompute_roles(db, tenant: str, user_ids: Set[str] | List[str], actor: str) -> None:
    raw = raw_db(db)
    for uid in sorted(set(user_ids)):
        user = await raw.users.find_one({"tenantId": tenant, "id": uid}, {"_id": 0})
        if not user or is_super(user.get("role")) or user.get("scimDeleted"):
            continue
        groups = await raw.scim_groups.find({"tenantId": tenant, "members": uid}, {"_id": 0, "displayName": 1, "externalId": 1}).to_list(500)
        offered = await mapped_role(db, tenant, [v for g in groups for v in (g.get("displayName"), g.get("externalId")) if v])
        owns = user.get(directory_role_guard.DIRECTORY_ROLE_FIELD) == user.get("role") or (
            directory_role_guard.DIRECTORY_ROLE_FIELD not in user and user.get("source") == "scim")
        if offered is None and owns:
            offered = DEFAULT_ROLE
        role = await directory_role_guard.role_to_apply(raw, user, offered, tenant, "scim")
        changes = {**directory_role_guard.directory_role_update(user, offered, "scim")}
        if role and role != user.get("role"):
            from authentication_service import revoke_user_sessions
            await revoke_user_sessions(user.get("email"), "scim role change")  # before the write (WR-05)
            changes["role"] = role
            await audit(db, "scim.user.role", tenant, actor, resourceId=uid, target=user.get("email"),
                        before=user.get("role"), after=role)
        if changes:
            await raw.users.update_one({"tenantId": tenant, "id": uid}, {"$set": {**changes, "updatedAt": now_iso()}})

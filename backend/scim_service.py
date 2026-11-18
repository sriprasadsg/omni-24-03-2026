"""SCIM 2.0 provisioning (RFC 7643/7644) for one organization at a time: tokens, filters and Users.

An organization's admin creates a bearer token (``scim_tokens`` keeps only its SHA-256); the identity provider
(Entra ID, Okta) calls /api/scim/v2 with it, and every read and write is scoped to that token's tenant with an
explicit ``tenantId`` filter on the raw collections (the request has no session, so no tenant context).

Users are the platform's ``users`` documents. userName is the sign-in email (or emails[primary] when userName is
not an email); a new user gets a random unusable password (sign-in is SAML/OIDC) and the role ``viewer`` until a
group mapping gives one (scim_groups). Deprovisioning never deletes: ``active: false`` sets status Inactive and
ends the user's sessions; DELETE does the same and marks the record ``scimDeleted`` so SCIM answers 404 for it,
while the account stays for the audit trail (a later POST of the same userName revives it). SCIM never touches a
super-admin-tier account, never disables the organization's last active admin, and records every change in the
audit ledger.
"""
import hashlib
import re
import secrets
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import audit_ledger
import rbac_defaults

USER_SCHEMA = "urn:ietf:params:scim:schemas:core:2.0:User"
GROUP_SCHEMA = "urn:ietf:params:scim:schemas:core:2.0:Group"
LIST_SCHEMA = "urn:ietf:params:scim:api:messages:2.0:ListResponse"
PATCH_SCHEMA = "urn:ietf:params:scim:api:messages:2.0:PatchOp"
ERROR_SCHEMA = "urn:ietf:params:scim:api:messages:2.0:Error"
DEFAULT_ROLE = "viewer"
TOKEN_PREFIX = "omni_scim_"
MAX_TOKENS = 5
MAX_COUNT = 200
ADMIN_ROLES = ("tenant_admin", "admin")
EMAIL = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,190}\.[^@\s]{2,63}$")
FILTER = re.compile(r'^\s*([A-Za-z][\w.\[\]" ]*?)\s+eq\s+(?:"((?:[^"\\]|\\.)*)"|(true|false))\s*$', re.I)


class ScimError(Exception):
    def __init__(self, status: int, detail: str, scim_type: Optional[str] = None):
        super().__init__(detail)
        self.status, self.detail, self.scim_type = status, detail, scim_type

    def body(self) -> Dict[str, Any]:
        return {"schemas": [ERROR_SCHEMA], "status": str(self.status), "detail": self.detail,
                **({"scimType": self.scim_type} if self.scim_type else {})}


def raw_db(db):
    return getattr(db, "_db", db)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def is_super(role: Any) -> bool:
    return rbac_defaults.normalize_role(role or "") == rbac_defaults.SUPER_ADMIN_KEY


async def audit(db, action: str, tenant: str, actor: str, **fields: Any) -> None:
    await audit_ledger.event(action, tenant, actor={"email": actor, "role": "scim", "tenantId": tenant},
                             db=raw_db(db), resourceType="scim", **fields)


# ── Tokens ──────────────────────────────────────────────────────────────────


def _digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


async def create_token(db, tenant: str, who: str, label: Optional[str]) -> Dict[str, Any]:
    """A new token for the organization; the token itself is returned once and never stored."""
    raw = raw_db(db)
    if await raw.scim_tokens.count_documents({"tenantId": tenant, "revokedAt": None}) >= MAX_TOKENS:
        raise ScimError(409, f"An organization holds at most {MAX_TOKENS} active SCIM tokens; revoke one first")
    token = TOKEN_PREFIX + secrets.token_urlsafe(32)
    doc = {"id": f"scimtok-{uuid.uuid4().hex[:12]}", "tenantId": tenant, "hash": _digest(token),
           "prefix": token[:len(TOKEN_PREFIX) + 6], "label": (label or "").strip()[:80] or None,
           "createdBy": who, "createdAt": now_iso(), "lastUsedAt": None, "revokedAt": None}
    await raw.scim_tokens.insert_one(dict(doc))
    doc.pop("hash")
    return {**doc, "token": token}


async def list_tokens(db, tenant: str) -> List[Dict[str, Any]]:
    return await raw_db(db).scim_tokens.find({"tenantId": tenant}, {"_id": 0, "hash": 0}).sort("createdAt", -1).to_list(50)


async def revoke_token(db, tenant: str, token_id: str, who: str) -> None:
    result = await raw_db(db).scim_tokens.update_one({"id": token_id, "tenantId": tenant, "revokedAt": None},
                                                     {"$set": {"revokedAt": now_iso(), "revokedBy": who}})
    if result.matched_count == 0:
        raise ScimError(404, "Token not found or already revoked")


async def token_record(db, token: str) -> Optional[Dict[str, Any]]:
    """The active token's record for a presented bearer value, else None (lastUsedAt kept to the minute)."""
    if not token.startswith(TOKEN_PREFIX) or len(token) > 200:
        return None
    raw = raw_db(db)
    rec = await raw.scim_tokens.find_one({"hash": _digest(token), "revokedAt": None}, {"_id": 0, "hash": 0})
    if not rec or not rec.get("tenantId") or rec["tenantId"] == rbac_defaults.PLATFORM_TENANT_ID:
        return None
    stamp = now_iso()
    if (rec.get("lastUsedAt") or "")[:16] != stamp[:16]:
        await raw.scim_tokens.update_one({"id": rec["id"]}, {"$set": {"lastUsedAt": stamp}})
    return rec


async def ensure_indexes(db) -> None:
    raw = raw_db(db)
    await raw.scim_tokens.create_index("hash", unique=True, name="scim_token_hash")
    await raw.scim_groups.create_index([("tenantId", 1), ("id", 1)], unique=True, name="scim_group_id")
    await raw.scim_groups.create_index([("tenantId", 1), ("members", 1)], name="scim_group_members")


# ── Filters and paging ──────────────────────────────────────────────────────


def parse_filter(text: Optional[str], allowed: Dict[str, str]) -> Optional[Tuple[str, Any]]:
    """('stored field', value) for `attr eq "value"` on an allowed attribute; None without a filter."""
    if not text:
        return None
    m = FILTER.match(text)
    if not m:
        raise ScimError(400, "Only `attribute eq \"value\"` filters are supported", "invalidFilter")
    attr = re.sub(r"\s+", "", m.group(1)).lower()
    if attr not in allowed:
        raise ScimError(400, f"Filtering on {m.group(1).strip()} is not supported", "invalidFilter")
    value = m.group(2).replace('\\"', '"') if m.group(2) is not None else m.group(3).lower() == "true"
    return allowed[attr], value


def page_args(start: Optional[int], count: Optional[int]) -> Tuple[int, int]:
    return max(1, start or 1), max(0, min(MAX_COUNT, 100 if count is None else count))


def list_response(resources: List[Dict[str, Any]], total: int, start: int) -> Dict[str, Any]:
    return {"schemas": [LIST_SCHEMA], "totalResults": total, "startIndex": start,
            "itemsPerPage": len(resources), "Resources": resources}


def as_bool(value: Any) -> bool:
    """SCIM booleans; Entra ID sends "True"/"False" strings in PATCH."""
    if isinstance(value, bool):
        return value
    if isinstance(value, str) and value.strip().lower() in ("true", "false"):
        return value.strip().lower() == "true"
    raise ScimError(400, f"Expected a boolean, got {value!r}", "invalidValue")


def ci_equals(value: str) -> Dict[str, Any]:
    return {"$regex": f"^{re.escape(value)}$", "$options": "i"}


# ── Users ───────────────────────────────────────────────────────────────────

USER_FILTERS = {"username": "email", "externalid": "scimExternalId", "id": "id", "emails.value": "email",
                'emails[type eq "work"].value': "email", "active": "active"}


def _active(doc: Dict[str, Any]) -> bool:
    return str(doc.get("status") or "Active").lower() == "active"


def user_resource(doc: Dict[str, Any], groups: List[Dict[str, Any]], base: str) -> Dict[str, Any]:
    name = doc.get("scimName") or {}
    return {
        "schemas": [USER_SCHEMA], "id": doc["id"], "externalId": doc.get("scimExternalId"),
        "userName": doc.get("scimUserName") or doc.get("email"),
        "name": {k: v for k, v in {"givenName": name.get("givenName"), "familyName": name.get("familyName"),
                                     "formatted": name.get("formatted") or doc.get("name")}.items() if v},
        "displayName": doc.get("name") or doc.get("email"),
        "emails": [{"value": doc.get("email"), "type": "work", "primary": True}],
        "active": _active(doc),
        "groups": [{"value": g["id"], "display": g.get("displayName"), "$ref": f"{base}/Groups/{g['id']}"} for g in groups],
        "meta": {"resourceType": "User", "created": doc.get("createdAt") or doc.get("created_at"),
                 "lastModified": doc.get("updatedAt") or doc.get("createdAt"), "location": f"{base}/Users/{doc['id']}"},
    }


def _email_of(body: Dict[str, Any]) -> Tuple[str, str]:
    """(email, userName as given) from a User body; userName when it is an email, else the primary email."""
    user_name = str(body.get("userName") or "").strip()
    if not user_name:
        raise ScimError(400, "userName is required", "invalidValue")
    email = user_name if EMAIL.match(user_name) else None
    if not email:
        emails = body.get("emails") if isinstance(body.get("emails"), list) else []
        primary = [e for e in emails if isinstance(e, dict) and e.get("primary")] or [e for e in emails if isinstance(e, dict)]
        candidate = str((primary[0] if primary else {}).get("value") or "").strip()
        email = candidate if EMAIL.match(candidate) else None
    if not email:
        raise ScimError(400, "userName or the primary email must be an email address", "invalidValue")
    return email.lower(), user_name[:254]


def _names(body: Dict[str, Any], email: str) -> Dict[str, Any]:
    name = body.get("name") if isinstance(body.get("name"), dict) else {}
    parts = {k: str(name.get(k) or "").strip()[:120] or None for k in ("givenName", "familyName", "formatted")}
    display = str(body.get("displayName") or "").strip()[:200] or parts["formatted"] \
        or " ".join(p for p in (parts["givenName"], parts["familyName"]) if p) or email
    return {"scimName": parts, "name": display}


async def _groups_of(db, tenant: str, user_id: str) -> List[Dict[str, Any]]:
    return await raw_db(db).scim_groups.find({"tenantId": tenant, "members": user_id},
                                             {"_id": 0, "id": 1, "displayName": 1}).to_list(500)


async def load_user(db, tenant: str, user_id: str) -> Dict[str, Any]:
    doc = await raw_db(db).users.find_one({"id": user_id, "tenantId": tenant, "scimDeleted": {"$ne": True}}, {"_id": 0})
    if not doc or is_super(doc.get("role")):
        raise ScimError(404, "User not found")
    return doc


async def get_user(db, tenant: str, user_id: str, base: str) -> Dict[str, Any]:
    doc = await load_user(db, tenant, user_id)
    return user_resource(doc, await _groups_of(db, tenant, user_id), base)


async def list_users(db, tenant: str, filt: Optional[str], start: Optional[int], count: Optional[int], base: str) -> Dict[str, Any]:
    start, count = page_args(start, count)
    query: Dict[str, Any] = {"tenantId": tenant, "scimDeleted": {"$ne": True},
                             "role": {"$nin": ["Super Admin", "super_admin", "superadmin"]}}
    parsed = parse_filter(filt, USER_FILTERS)
    if parsed:
        field, value = parsed
        if field == "active":
            query["status"] = "Active" if value else {"$ne": "Active"}
        elif field == "email":
            query["$or"] = [{"email": ci_equals(str(value))}, {"scimUserName": ci_equals(str(value))}]
        else:
            query[field] = str(value)
    raw = raw_db(db)
    total = await raw.users.count_documents(query)
    docs = await raw.users.find(query, {"_id": 0}).sort("createdAt", 1).skip(start - 1).limit(count).to_list(count)
    return list_response([user_resource(d, await _groups_of(db, tenant, d["id"]), base) for d in docs], total, start)


async def _assert_can_disable(db, tenant: str, doc: Dict[str, Any]) -> None:
    if rbac_defaults.normalize_role(doc.get("role")) not in ADMIN_ROLES or not _active(doc):
        return
    others = await raw_db(db).users.count_documents({"tenantId": tenant, "id": {"$ne": doc["id"]}, "status": "Active",
                                                     "role": {"$in": ["Tenant Admin", "tenant_admin", "admin", "Admin"]}})
    if others == 0:
        raise ScimError(400, "This is the organization's last active administrator; SCIM cannot disable it", "mutability")


async def _set_status(db, tenant: str, doc: Dict[str, Any], active: bool, actor: str) -> Dict[str, Any]:
    """The status change to write; a deactivation ends the user's sessions first."""
    if active == _active(doc):
        return {}
    if not active:
        await _assert_can_disable(db, tenant, doc)
        from authentication_service import revoke_user_sessions
        await revoke_user_sessions(doc.get("email"), "scim deprovisioning")
    await audit(db, "scim.user.activate" if active else "scim.user.deactivate", tenant, actor, resourceId=doc["id"],
                target=doc.get("email"))
    return {"status": "Active" if active else "Inactive"}


async def _email_free(db, tenant: str, email: str, user_id: Optional[str]) -> None:
    other = await raw_db(db).users.find_one({"email": ci_equals(email), "id": {"$ne": user_id}},
                                            {"_id": 0, "tenantId": 1, "scimDeleted": 1})
    if other:
        where = "in this organization" if other.get("tenantId") == tenant else "in another organization"
        raise ScimError(409, f"{email} is already registered {where}", "uniqueness")


async def create_user(db, tenant: str, body: Dict[str, Any], actor: str, base: str) -> Dict[str, Any]:
    """POST /Users: a new user, or the revival of one SCIM deleted (same email, same organization)."""
    import bcrypt
    email, user_name = _email_of(body)
    active = as_bool(body.get("active", True))
    raw = raw_db(db)
    revived = await raw.users.find_one({"email": ci_equals(email), "tenantId": tenant, "scimDeleted": True}, {"_id": 0})
    fields = {"scimUserName": user_name, "scimExternalId": str(body.get("externalId") or "")[:200] or None,
              **_names(body, email), "updatedAt": now_iso()}
    if revived and not is_super(revived.get("role")):
        fields.update(status="Active" if active else "Inactive", source="scim")
        await raw.users.update_one({"id": revived["id"], "tenantId": tenant}, {"$set": fields, "$unset": {"scimDeleted": ""}})
        await audit(db, "scim.user.revive", tenant, actor, resourceId=revived["id"], target=email)
        return await get_user(db, tenant, revived["id"], base)
    await _email_free(db, tenant, email, None)
    doc = {"id": f"user-{uuid.uuid4()}", "email": email, "username": email.split("@")[0], "tenantId": tenant,
           "role": DEFAULT_ROLE, "directoryRole": DEFAULT_ROLE, "status": "Active" if active else "Inactive",
           "password": bcrypt.hashpw(secrets.token_bytes(32), bcrypt.gensalt()).decode(), "source": "scim",
           "created_via": "scim", "createdAt": now_iso(), **fields}
    await raw.users.insert_one(dict(doc))
    await audit(db, "scim.user.create", tenant, actor, resourceId=doc["id"], target=email, role=DEFAULT_ROLE)
    return await get_user(db, tenant, doc["id"], base)


async def replace_user(db, tenant: str, user_id: str, body: Dict[str, Any], actor: str, base: str) -> Dict[str, Any]:
    """PUT /Users/{id}: userName, names, externalId and active as given."""
    doc = await load_user(db, tenant, user_id)
    email, user_name = _email_of(body)
    if email != str(doc.get("email") or "").lower():
        await _email_free(db, tenant, email, user_id)
    changes = {"email": email, "scimUserName": user_name, "scimExternalId": str(body.get("externalId") or "")[:200] or None,
               **_names(body, email), **await _set_status(db, tenant, doc, as_bool(body.get("active", True)), actor),
               "updatedAt": now_iso()}
    await raw_db(db).users.update_one({"id": user_id, "tenantId": tenant}, {"$set": changes})
    await audit(db, "scim.user.replace", tenant, actor, resourceId=user_id, target=email)
    return await get_user(db, tenant, user_id, base)


def _patch_value(path: str, value: Any, current: Dict[str, Any]) -> Dict[str, Any]:
    """One PATCH path onto a User body (unknown attributes, e.g. enterprise extensions, are ignored)."""
    p = re.sub(r"\s+", "", path).lower()
    body = dict(current)
    if p == "active":
        body["active"] = value
    elif p == "username":
        body["userName"] = value
    elif p == "externalid":
        body["externalId"] = value
    elif p == "displayname":
        body["displayName"] = value
    elif p.startswith("name.") and p[5:] in ("givenname", "familyname", "formatted"):
        key = {"givenname": "givenName", "familyname": "familyName", "formatted": "formatted"}[p[5:]]
        body["name"] = {**(body.get("name") or {}), key: value}
    elif p == "name" and isinstance(value, dict):
        body["name"] = {**(body.get("name") or {}), **value}
    elif p in ('emails[typeeq"work"].value', "emails.value", 'emails[primaryeqtrue].value'):
        body["emails"] = [{"value": value, "type": "work", "primary": True}]
    elif p == "emails" and isinstance(value, list):
        body["emails"] = value
    return body


async def patch_user(db, tenant: str, user_id: str, body: Dict[str, Any], actor: str, base: str) -> Dict[str, Any]:
    """PATCH /Users/{id}: add/replace/remove on the supported attributes, then the same writes as PUT."""
    doc = await load_user(db, tenant, user_id)
    current = user_resource(doc, [], base)
    current = {k: current[k] for k in ("userName", "externalId", "displayName", "name", "emails", "active")}
    ops = body.get("Operations")
    if not isinstance(ops, list) or not ops:
        raise ScimError(400, "Operations must be a non-empty list", "invalidSyntax")
    for op in ops:
        kind = str((op or {}).get("op") or "").lower()
        if kind not in ("add", "replace", "remove"):
            raise ScimError(400, f"Unsupported op {op.get('op') if isinstance(op, dict) else op!r}", "invalidSyntax")
        path, value = op.get("path"), op.get("value")
        if kind == "remove":
            if not path or re.sub(r"\s+", "", path).lower() in ("active", "username", "emails"):
                raise ScimError(400, f"{path or 'That attribute'} cannot be removed", "mutability")
            current = _patch_value(path, None, current)
        elif path:
            current = _patch_value(path, value, current)
        elif isinstance(value, dict):
            for key, item in value.items():
                current = _patch_value(key, item, current)
        else:
            raise ScimError(400, "An op without a path needs an object value", "invalidSyntax")
    return await replace_user(db, tenant, user_id, current, actor, base)


async def delete_user(db, tenant: str, user_id: str, actor: str) -> None:
    """DELETE /Users/{id}: disabled and marked scimDeleted (never removed), out of every SCIM group."""
    doc = await load_user(db, tenant, user_id)
    changes = await _set_status(db, tenant, doc, False, actor)
    raw = raw_db(db)
    await raw.users.update_one({"id": user_id, "tenantId": tenant},
                               {"$set": {**changes, "scimDeleted": True, "updatedAt": now_iso()}})
    await raw.scim_groups.update_many({"tenantId": tenant, "members": user_id}, {"$pull": {"members": user_id}})
    await audit(db, "scim.user.delete", tenant, actor, resourceId=user_id, target=doc.get("email"))

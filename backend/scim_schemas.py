"""SCIM 2.0 discovery documents (RFC 7643 §6-7): the User and Group schemas with the attributes this server keeps,
and their resource types, so a client (an identity provider, or a checker such as scim2-tester) learns which
attributes exist and which are required. Only attributes scim_service / scim_groups read or return are listed.
Also the attributes / excludedAttributes projection (RFC 7644 §3.9) applied to the resources the routes return.
"""
from typing import Any, Dict, List, Optional

from scim_service import GROUP_SCHEMA, USER_SCHEMA

SCHEMA_SCHEMA = "urn:ietf:params:scim:schemas:core:2.0:Schema"
RESOURCE_TYPE_SCHEMA = "urn:ietf:params:scim:schemas:core:2.0:ResourceType"


def _attr(name: str, type_: str = "string", *, required: bool = False, multi: bool = False, mutability: str = "readWrite",
          uniqueness: str = "none", returned: str = "default", sub: Optional[List[Dict[str, Any]]] = None, **extra: Any) -> Dict[str, Any]:
    out = {"name": name, "type": type_, "multiValued": multi, "required": required, "caseExact": False,
           "mutability": mutability, "returned": returned, "uniqueness": uniqueness, "description": extra.pop("description", name), **extra}
    if sub:
        out["subAttributes"] = sub
    return out


_REF = [_attr("value", mutability="immutable"), _attr("$ref", "reference", mutability="immutable", referenceTypes=["User", "Group"]),
        _attr("display", mutability="immutable")]
SCHEMAS = {
    USER_SCHEMA: {"name": "User", "description": "An Omni-Agent user of this organization", "attributes": [
        _attr("userName", required=True, uniqueness="server", description="The sign-in email (or emails[primary] when not an email)"),
        _attr("name", "complex", sub=[_attr("formatted"), _attr("givenName"), _attr("familyName")]),
        _attr("displayName"),
        _attr("emails", "complex", multi=True, sub=[_attr("value"), _attr("type", canonicalValues=["work"]), _attr("primary", "boolean")]),
        _attr("active", "boolean", description="false sets the user Inactive and ends their sessions"),
        _attr("groups", "complex", multi=True, mutability="readOnly", sub=_REF, description="Groups the user belongs to"),
    ]},
    GROUP_SCHEMA: {"name": "Group", "description": "A group of this organization's users, mapped to a role", "attributes": [
        _attr("displayName", required=True, uniqueness="server"),
        _attr("members", "complex", multi=True, sub=_REF),
    ]},
}


def schema(schema_id: str, base: str) -> Optional[Dict[str, Any]]:
    s = SCHEMAS.get(schema_id)
    return None if s is None else {"schemas": [SCHEMA_SCHEMA], "id": schema_id, **s,
                                   "meta": {"resourceType": "Schema", "location": f"{base}/Schemas/{schema_id}"}}


def resource_type(name: str, base: str) -> Optional[Dict[str, Any]]:
    sid = {"User": USER_SCHEMA, "Group": GROUP_SCHEMA}.get(name)
    return None if sid is None else {"schemas": [RESOURCE_TYPE_SCHEMA], "id": name, "name": name, "endpoint": f"/{name}s",
                                     "description": SCHEMAS[sid]["description"], "schema": sid, "schemaExtensions": [],
                                     "meta": {"resourceType": "ResourceType", "location": f"{base}/ResourceTypes/{name}"}}


# ── attributes / excludedAttributes (RFC 7644 §3.9) ─────────────────────────

ALWAYS = ("schemas", "id", "meta")


def _paths(value: Any) -> List[str]:
    """The parameter as lower-case attribute paths: a comma list (query string) or a list (.search body). The core
    schema's URN prefix is dropped, so urn:...:User:userName is userName."""
    items = value.split(",") if isinstance(value, str) else value if isinstance(value, list) else []
    out = []
    for item in items[:50]:
        path = str(item).strip()
        for urn in SCHEMAS:
            if path.lower().startswith(urn.lower() + ":"):
                path = path[len(urn) + 1:]
        if path:
            out.append(path.lower())
    return out


def returns(attr: str, attributes: Any, excluded: Any) -> bool:
    """Whether a response with these parameters carries a top-level attribute (to skip the work of one it drops)."""
    wanted = _paths(attributes)
    if wanted:
        return any(p.split(".")[0] == attr.lower() for p in wanted)
    return attr.lower() not in _paths(excluded)


def _subset(value: Any, subs: set, drop: bool) -> Any:
    def one(item: Any) -> Any:
        return {k: v for k, v in item.items() if (k.lower() in subs) != drop} if isinstance(item, dict) else item
    return [one(v) for v in value] if isinstance(value, list) else one(value)


def project(resource: Dict[str, Any], attributes: Any = None, excluded: Any = None) -> Dict[str, Any]:
    """Only the attributes asked for, or all but the excluded ones (attributes wins when both are given); schemas,
    id and meta always stay, and a sub-attribute path (name.givenName) narrows its complex attribute."""
    wanted, dropped = _paths(attributes), _paths(excluded)
    keys = {k.lower(): k for k in resource}
    if wanted:
        whole: set = set()
        subs: Dict[str, set] = {}
        for p in wanted:
            top, _, sub = p.partition(".")
            if sub:
                subs.setdefault(top, set()).add(sub)
            else:
                whole.add(top)
        out = {k: v for k, v in resource.items() if k in ALWAYS}
        for top in whole | set(subs):
            key = keys.get(top)
            if key and key not in out:
                out[key] = resource[key] if top in whole else _subset(resource[key], subs[top], drop=False)
        return out
    out = dict(resource)
    for p in dropped:
        top, _, sub = p.partition(".")
        key = keys.get(top)
        if key in out and key not in ALWAYS:
            if sub:
                out[key] = _subset(out[key], {sub}, drop=True)
            else:
                out.pop(key)
    return out


def project_response(out: Dict[str, Any], attributes: Any = None, excluded: Any = None) -> Dict[str, Any]:
    """project() on one resource, or on each resource of a ListResponse."""
    if not _paths(attributes) and not _paths(excluded):
        return out
    if "Resources" in out:
        return {**out, "Resources": [project(r, attributes, excluded) for r in out["Resources"]]}
    return project(out, attributes, excluded)

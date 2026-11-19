"""SCIM 2.0 discovery documents (RFC 7643 §6-7): the User and Group schemas with the attributes this server keeps,
and their resource types, so a client (an identity provider, or a checker such as scim2-tester) learns which
attributes exist and which are required. Only attributes scim_service / scim_groups read or return are listed.
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

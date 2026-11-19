"""SCIM 2.0 provisioning (scim_service, scim_groups, scim_endpoints, migration 043). protects/fails_when/no_claim per
test; real MongoDB and the real SCIM router. Requests follow what Entra ID's provisioning service sends (userName
filter before create, PATCH with "False" strings, members[value eq ...] removal).
"""
import importlib
import os
import sys

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import database
import scim_endpoints
import scim_service
from tests._mongo_test_db import mongo_db  # noqa: F401  (fixture)

BASE = "/api/scim/v2"
UPN = "anna.berg@contoso.example"


def _user_body(user_name=UPN, external="11111111-aaaa", active=True):
    return {"schemas": [scim_service.USER_SCHEMA], "userName": user_name, "externalId": external, "active": active,
            "name": {"givenName": "Anna", "familyName": "Berg"}, "displayName": "Anna Berg",
            "emails": [{"value": user_name, "type": "work", "primary": True}]}


def _patch(*ops):
    return {"schemas": [scim_service.PATCH_SCHEMA], "Operations": list(ops)}


@pytest_asyncio.fixture
async def env(mongo_db, monkeypatch):  # noqa: F811
    monkeypatch.setattr(database.mongodb, "db", mongo_db)
    monkeypatch.setattr(scim_endpoints, "get_database", lambda: database.TenantIsolatedDatabase(mongo_db))
    await scim_service.ensure_indexes(mongo_db)
    await mongo_db.users.insert_many([
        {"id": "user-admin-a", "email": "admin@a.example", "name": "A Admin", "role": "Tenant Admin", "tenantId": "t-a", "status": "Active"},
        {"id": "user-b", "email": "bob@b.example", "name": "Bob", "role": "viewer", "tenantId": "t-b", "status": "Active"},
        {"id": "user-root", "email": "root@a.example", "name": "Root", "role": "Super Admin", "tenantId": "t-a", "status": "Active"},
    ])
    tokens = {t: (await scim_service.create_token(mongo_db, t, f"admin@{t}", "Entra"))["token"] for t in ("t-a", "t-b")}
    app = FastAPI()
    app.include_router(scim_endpoints.router)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="https://omni.example") as ac:
        yield ac, mongo_db, tokens


def _h(token):
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/scim+json"}


@pytest.mark.asyncio
async def test_entra_user_lifecycle_creates_finds_deprovisions_and_revives(env):
    """protects=create with a random unusable password and role viewer, find by userName, PATCH active "False"
    (Entra's string) disables and ends sessions, DELETE disables and hides but never removes, a new POST revives
    the same account; fails_when=deprovisioning deletes a user, leaves sessions alive, or a deleted user still
    answers; no_claim=Okta's own validator"""
    ac, db, tokens = env
    h = _h(tokens["t-a"])
    assert (await ac.get(f"{BASE}/Users", params={"filter": f'userName eq "{UPN}"'}, headers=h)).json()["totalResults"] == 0
    made = await ac.post(f"{BASE}/Users", json=_user_body(), headers=h)
    assert made.status_code == 201 and made.headers["content-type"].startswith("application/scim+json")
    user = made.json()
    assert user["userName"] == UPN and user["active"] is True and user["meta"]["location"].startswith("https://omni.example/api/scim/v2/Users/")
    stored = await db.users.find_one({"id": user["id"]})
    assert stored["tenantId"] == "t-a" and stored["role"] == "viewer" and stored["password"].startswith("$2") and stored["source"] == "scim"
    found = (await ac.get(f"{BASE}/Users", params={"filter": f'userName eq "{UPN.upper()}"'}, headers=h)).json()
    assert found["totalResults"] == 1 and found["Resources"][0]["id"] == user["id"]

    off = await ac.patch(f"{BASE}/Users/{user['id']}", json=_patch({"op": "Replace", "path": "active", "value": "False"}), headers=h)
    assert off.status_code == 200 and off.json()["active"] is False
    assert (await db.users.find_one({"id": user["id"]}))["status"] == "Inactive"
    assert await db.revoked_tokens.find_one({"type": "user_cutoff", "reason": "scim deprovisioning"})
    on = await ac.patch(f"{BASE}/Users/{user['id']}", json=_patch({"op": "replace", "value": {"active": True, "displayName": "Anna B."}}), headers=h)
    assert on.json()["active"] is True and on.json()["displayName"] == "Anna B."

    assert (await ac.delete(f"{BASE}/Users/{user['id']}", headers=h)).status_code == 204
    assert (await ac.get(f"{BASE}/Users/{user['id']}", headers=h)).status_code == 404
    kept = await db.users.find_one({"id": user["id"]})
    assert kept["scimDeleted"] is True and kept["status"] == "Inactive"
    again = await ac.post(f"{BASE}/Users", json=_user_body(), headers=h)
    assert again.status_code == 201 and again.json()["id"] == user["id"] and again.json()["active"] is True
    assert await db.audit_logs.count_documents({"action": {"$regex": "^scim.user"}}) >= 5


@pytest.mark.asyncio
async def test_a_token_reaches_only_its_own_organization(env):
    """protects=the token names the tenant: another tenant's users are absent from lists and filters, and their ids
    answer 404 to read, change and delete; a revoked or made-up token gets 401; fails_when=Entra for one customer
    can read or disable another customer's users; no_claim=-"""
    ac, db, tokens = env
    a, b = _h(tokens["t-a"]), _h(tokens["t-b"])
    assert (await ac.get(f"{BASE}/Users", params={"filter": 'userName eq "bob@b.example"'}, headers=a)).json()["totalResults"] == 0
    assert [r["id"] for r in (await ac.get(f"{BASE}/Users", headers=b)).json()["Resources"]] == ["user-b"]
    for method, body in (("get", None), ("patch", _patch({"op": "replace", "path": "active", "value": False})), ("delete", None)):
        r = await getattr(ac, method)(f"{BASE}/Users/user-b", headers=a, **({"json": body} if body else {}))
        assert r.status_code == 404, method
    assert (await db.users.find_one({"id": "user-b"}))["status"] == "Active"
    clash = await ac.post(f"{BASE}/Users", json=_user_body("bob@b.example"), headers=a)
    assert clash.status_code == 409 and clash.json()["scimType"] == "uniqueness" and "another organization" in clash.json()["detail"]
    tok = await db.scim_tokens.find_one({"tenantId": "t-a"})
    await scim_service.revoke_token(db, "t-a", tok["id"], "admin@t-a")
    assert (await ac.get(f"{BASE}/Users", headers=a)).status_code == 401
    for bad in ("Bearer omni_scim_madeup", "Bearer " + tokens["t-b"][:-1] + "x", "Basic abc", ""):
        assert (await ac.get(f"{BASE}/ServiceProviderConfig", headers={"Authorization": bad})).status_code == 401


@pytest.mark.asyncio
async def test_scim_cannot_touch_super_admins_or_disable_the_last_admin(env):
    """protects=a super-admin-tier account is invisible to SCIM, and the organization's last active admin cannot be
    disabled or deleted through it; fails_when=an identity provider locks an organization out; no_claim=-"""
    ac, db, tokens = env
    h = _h(tokens["t-a"])
    listed = {r["id"] for r in (await ac.get(f"{BASE}/Users", headers=h)).json()["Resources"]}
    assert listed == {"user-admin-a"}
    assert (await ac.get(f"{BASE}/Users/user-root", headers=h)).status_code == 404
    refused = await ac.patch(f"{BASE}/Users/user-admin-a", json=_patch({"op": "Replace", "path": "active", "value": "False"}), headers=h)
    assert refused.status_code == 400 and refused.json()["scimType"] == "mutability"
    assert (await ac.delete(f"{BASE}/Users/user-admin-a", headers=h)).status_code == 400
    assert (await db.users.find_one({"id": "user-admin-a"}))["status"] == "Active"


@pytest.mark.asyncio
async def test_groups_give_mapped_roles_and_take_them_back(env):
    """protects=a group whose name or externalId has a mapping gives its role (sessions ended first), removing the
    member returns a directory-given role to viewer, a mapping to the super-admin tier never applies, and an
    admin's hand-raised role is kept; fails_when=SCIM escalates to super admin or demotes a local admin; no_claim=-"""
    ac, db, tokens = env
    h = _h(tokens["t-a"])
    await db.saml_group_mappings.insert_many([
        {"tenant_id": "t-a", "group_value": "aad-group-ops", "role": "security_analyst", "priority": 10},
        {"tenant_id": "t-a", "group_value": "Root Group", "role": "super_admin", "priority": 1}])
    anna = (await ac.post(f"{BASE}/Users", json=_user_body(), headers=h)).json()["id"]
    grp = await ac.post(f"{BASE}/Groups", json={"schemas": [scim_service.GROUP_SCHEMA], "displayName": "SecOps",
                                                "externalId": "aad-group-ops", "members": [{"value": anna}]}, headers=h)
    assert grp.status_code == 201 and grp.json()["members"][0]["display"] == "Anna Berg"
    assert (await db.users.find_one({"id": anna}))["role"] == "security_analyst"
    assert await db.revoked_tokens.find_one({"reason": "scim role change"})
    assert (await ac.get(f"{BASE}/Users/{anna}", headers=h)).json()["groups"][0]["display"] == "SecOps"

    gid = grp.json()["id"]
    removed = await ac.patch(f"{BASE}/Groups/{gid}", json=_patch({"op": "Remove", "path": f'members[value eq "{anna}"]'}), headers=h)
    assert removed.status_code == 200 and removed.json()["members"] == []
    assert (await db.users.find_one({"id": anna}))["role"] == "viewer"

    root = await ac.post(f"{BASE}/Groups", json={"displayName": "Root Group", "members": [{"value": anna}]}, headers=h)
    assert root.status_code == 201 and (await db.users.find_one({"id": anna}))["role"] == "viewer"

    await db.users.update_one({"id": anna}, {"$set": {"role": "tenant_admin"}})  # an admin raised her by hand
    await ac.patch(f"{BASE}/Groups/{gid}", json=_patch({"op": "add", "path": "members", "value": [{"value": anna}]}), headers=h)
    assert (await db.users.find_one({"id": anna}))["role"] == "tenant_admin"
    assert (await ac.delete(f"{BASE}/Groups/{root.json()['id']}", headers=h)).status_code == 204
    assert (await ac.get(f"{BASE}/Groups/{root.json()['id']}", headers=h)).status_code == 404


@pytest.mark.asyncio
async def test_filters_paging_discovery_and_bad_requests_answer_in_scim_form(env):
    """protects=ListResponse paging, displayName filters, excludedAttributes=members, discovery behind the token, and
    SCIM error bodies for unsupported filters, bad JSON, unknown members and duplicate names; fails_when=Entra's
    connection test or a retry gets a 500; no_claim=bulk, sort and etags (advertised as unsupported)"""
    ac, db, tokens = env
    h = _h(tokens["t-a"])
    for n in range(3):
        assert (await ac.post(f"{BASE}/Users", json=_user_body(f"u{n}@contoso.example", f"ext-{n}"), headers=h)).status_code == 201
    page = (await ac.get(f"{BASE}/Users", params={"startIndex": 2, "count": 2}, headers=h)).json()
    assert (page["totalResults"], page["startIndex"], page["itemsPerPage"]) == (4, 2, 2)
    assert (await ac.get(f"{BASE}/Users", params={"filter": 'externalId eq "ext-1"'}, headers=h)).json()["Resources"][0]["userName"] == "u1@contoso.example"
    bad = await ac.get(f"{BASE}/Users", params={"filter": 'title co "x"'}, headers=h)
    assert bad.status_code == 400 and bad.json()["scimType"] == "invalidFilter" and bad.json()["schemas"] == [scim_service.ERROR_SCHEMA]
    await ac.post(f"{BASE}/Groups", json={"displayName": "Finance"}, headers=h)
    dup = await ac.post(f"{BASE}/Groups", json={"displayName": "finance"}, headers=h)
    assert dup.status_code == 409 and dup.json()["scimType"] == "uniqueness"
    lean = (await ac.get(f"{BASE}/Groups", params={"filter": 'displayName eq "Finance"', "excludedAttributes": "members"}, headers=h)).json()
    assert lean["totalResults"] == 1 and "members" not in lean["Resources"][0]
    ghost = await ac.post(f"{BASE}/Groups", json={"displayName": "X", "members": [{"value": "user-b"}]}, headers=h)
    assert ghost.status_code == 400 and "Unknown member" in ghost.json()["detail"]
    junk = await ac.post(f"{BASE}/Users", content=b"{nope", headers=h)
    assert junk.status_code == 400 and junk.json()["scimType"] == "invalidSyntax"
    notmail = await ac.post(f"{BASE}/Users", json={"userName": "anna", "emails": []}, headers=h)
    assert notmail.status_code == 400
    cfg = await ac.get(f"{BASE}/ServiceProviderConfig", headers=h)
    assert cfg.json()["patch"]["supported"] is True and cfg.json()["bulk"]["supported"] is False
    assert (await ac.get(f"{BASE}/ResourceTypes", headers=h)).json()["totalResults"] == 2


@pytest.mark.asyncio
async def test_discovery_describes_the_attributes_and_unknown_paths_answer_in_scim_form(env):
    """protects=/Schemas and /Schemas/{id} list each attribute with its type and whether it is required (userName for
    User, displayName for Group), /ResourceTypes/{id} answers, discovery refuses writes with 405, and an unknown id
    or path is a 404 with a SCIM error body, all behind the token; fails_when=a client (scim2-tester, an identity
    provider) cannot learn that userName is required, or gets FastAPI's {"detail"} instead of a SCIM error;
    no_claim=attributes=/excludedAttributes= projection on Users (not supported yet)"""
    ac, _, tokens = env
    h = _h(tokens["t-a"])
    listed = (await ac.get(f"{BASE}/Schemas", headers=h)).json()
    assert listed["totalResults"] == 2 and {r["name"] for r in listed["Resources"]} == {"User", "Group"}
    user = (await ac.get(f"{BASE}/Schemas/{scim_service.USER_SCHEMA}", headers=h)).json()
    attrs = {a["name"]: a for a in user["attributes"]}
    assert attrs["userName"]["required"] is True and attrs["userName"]["uniqueness"] == "server"
    assert attrs["groups"]["mutability"] == "readOnly" and {a["name"] for a in attrs["name"]["subAttributes"]} == {"formatted", "givenName", "familyName"}
    assert user["meta"]["location"].endswith(f"/Schemas/{scim_service.USER_SCHEMA}")
    group = (await ac.get(f"{BASE}/Schemas/{scim_service.GROUP_SCHEMA}", headers=h)).json()
    assert [a["name"] for a in group["attributes"] if a["required"]] == ["displayName"]
    rt = (await ac.get(f"{BASE}/ResourceTypes/Group", headers=h)).json()
    assert (rt["endpoint"], rt["schema"]) == ("/Groups", scim_service.GROUP_SCHEMA)
    for method, path in (("GET", "/Schemas/urn:nope"), ("GET", "/ResourceTypes/Device"), ("GET", "/Devices"), ("DELETE", "/Nope/1")):
        r = await ac.request(method, f"{BASE}{path}", headers=h)
        assert r.status_code == 404 and r.json()["schemas"] == [scim_service.ERROR_SCHEMA], path
    for method, path in (("POST", "/Schemas"), ("PUT", f"/Schemas/{scim_service.USER_SCHEMA}"), ("PATCH", "/ResourceTypes/User"),
                         ("DELETE", "/ServiceProviderConfig")):
        r = await ac.request(method, f"{BASE}{path}", headers=h)
        assert r.status_code == 405 and r.json()["status"] == "405", path
    assert (await ac.get(f"{BASE}/Schemas/{scim_service.USER_SCHEMA}")).status_code == 401
    assert (await ac.get(f"{BASE}/Devices")).status_code == 401


@pytest.mark.asyncio
async def test_tokens_are_stored_hashed_capped_and_migration_043_runs_twice(mongo_db):  # noqa: F811
    """protects=only a SHA-256 of a token is kept, at most 5 active per organization, and the migration's indexes
    (unique hash) apply twice; fails_when=a database read reveals a usable token; no_claim=-"""
    migration = importlib.import_module("migrations.043_scim")
    await migration.up(mongo_db)
    await migration.up(mongo_db)
    made = [await scim_service.create_token(mongo_db, "t-x", "a@x", None) for _ in range(5)]
    with pytest.raises(scim_service.ScimError, match="at most 5"):
        await scim_service.create_token(mongo_db, "t-x", "a@x", None)
    stored = await mongo_db.scim_tokens.find_one({"id": made[0]["id"]})
    assert made[0]["token"] not in str(stored) and len(stored["hash"]) == 64 and "token" not in stored
    assert (await scim_service.token_record(mongo_db, made[0]["token"]))["tenantId"] == "t-x"
    assert (await mongo_db.scim_tokens.index_information())["scim_token_hash"]["unique"]
    assert await scim_service.token_record(mongo_db, "omni_scim_" + "a" * 43) is None


@pytest_asyncio.fixture
async def admin_client(mongo_db, monkeypatch):  # noqa: F811
    """The token routes behind the real middleware, session tokens and permission checks."""
    import rbac_utils
    from tenant_middleware import TenantMiddleware
    monkeypatch.setattr(database.mongodb, "db", mongo_db)
    monkeypatch.setattr(scim_endpoints, "get_database", lambda: database.TenantIsolatedDatabase(mongo_db))
    monkeypatch.setattr(rbac_utils, "get_database", lambda: database.TenantIsolatedDatabase(mongo_db))
    await mongo_db.tenants.insert_one({"id": "t-a", "name": "Tenant A"})
    app = FastAPI()
    app.add_middleware(TenantMiddleware)
    app.include_router(scim_endpoints.admin_router)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as ac:
        yield ac, mongo_db


def _bearer(role, tenant):
    from authentication_service import create_access_token
    return {"Authorization": "Bearer " + create_access_token({"sub": f"{role}@{tenant}", "role": role, "tenant_id": tenant,
                                                              "mfa_verified": True})}


@pytest.mark.asyncio
async def test_admins_create_list_and_revoke_tokens_for_their_organization_only(admin_client):
    """protects=an organization's admin gets a token once (the list never shows it), revokes it, a viewer is refused,
    and a Super Admin who is not viewing a tenant gets 400 instead of a platform-wide token; fails_when=a token
    value is readable later or lands on the platform scope; no_claim=the UI"""
    ac, db = admin_client
    made = await ac.post("/api/admin/sso/scim/tokens", json={"label": "Entra"}, headers=_bearer("admin", "t-a"))
    assert made.status_code == 200, made.text
    assert made.json()["token"].startswith("omni_scim_") and made.json()["basePath"] == "/api/scim/v2"
    listed = await ac.get("/api/admin/sso/scim/tokens", headers=_bearer("admin", "t-a"))
    assert listed.status_code == 200 and made.json()["token"] not in listed.text and listed.json()["items"][0]["label"] == "Entra"
    assert (await db.scim_tokens.find_one({"id": made.json()["id"]}))["tenantId"] == "t-a"
    assert (await ac.post("/api/admin/sso/scim/tokens", json={}, headers=_bearer("viewer", "t-a"))).status_code == 403
    owner = await ac.post("/api/admin/sso/scim/tokens", json={}, headers=_bearer("Super Admin", "platform-admin"))
    assert owner.status_code == 400 and "Select a tenant" in owner.text
    gone = await ac.delete(f"/api/admin/sso/scim/tokens/{made.json()['id']}", headers=_bearer("admin", "t-a"))
    assert gone.status_code == 200 and await scim_service.token_record(db, made.json()["token"]) is None
    assert (await ac.delete(f"/api/admin/sso/scim/tokens/{made.json()['id']}", headers=_bearer("admin", "t-a"))).status_code == 404

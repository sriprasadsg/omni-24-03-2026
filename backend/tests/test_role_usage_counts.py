"""77 WR-05: who still holds a custom role is counted by the store, not by a capped scan.

Runs ``role_contents.role_usage`` against a throwaway database on the test MongoDB
(MONGO_TEST_URL), so the regex the count sends is checked with the server's own matching.
Skips when no server is reachable.
"""
from types import SimpleNamespace

import pytest

import rbac_defaults
import role_contents
from tests._mongo_test_db import mongo_db  # noqa: F401  (fixture)

SPELLINGS = ["Help Desk", "help-desk", "HELP_DESK", "  help desk ", "help desk", "helpdesk", "help  desk",
             "Help Desk 2", "xhelp desk", "help.desk", None]


def _user(i, role, tenant="t1"):
    return {"id": f"u{i}", "email": f"u{i}@t.test", "full_name": f"User {i}", "role": role, "tenantId": tenant}


@pytest.mark.asyncio
async def test_a_holder_past_the_first_5000_users_still_counts(mongo_db):  # noqa: F811
    await mongo_db.users.insert_many([_user(i, "viewer") for i in range(5000)])
    await mongo_db.users.insert_one(_user(5000, "help desk"))
    holders, listed, _mappings, _ = await role_contents.role_usage(SimpleNamespace(_db=mongo_db), "t1", "Help Desk")
    assert holders == 1
    assert listed == [{"name": "User 5000", "email": "u5000@t.test"}]


@pytest.mark.asyncio
async def test_a_mapping_past_the_first_5000_still_counts(mongo_db):  # noqa: F811
    await mongo_db.ldap_group_mappings.insert_many(
        [{"group_dn": f"cn=g{i}", "role": "viewer", "tenant_id": "t1"} for i in range(5000)])
    await mongo_db.ldap_group_mappings.insert_one({"group_dn": "cn=desk", "role": "Help-Desk", "tenant_id": "t1"})
    _holders, _, mappings, listed = await role_contents.role_usage(SimpleNamespace(_db=mongo_db), "t1", "Help Desk")
    assert mappings == 1 and listed == [{"group": "cn=desk", "source": "LDAP"}]


@pytest.mark.asyncio
async def test_the_count_matches_normalize_role_for_every_spelling(mongo_db):  # noqa: F811
    await mongo_db.users.insert_many([_user(i, role) for i, role in enumerate(SPELLINGS)])
    await mongo_db.users.insert_one(_user(99, "Help Desk", tenant="t2"))
    await mongo_db.saml_group_mappings.insert_many(
        [{"group_value": f"g{i}", "role": role, "tenant_id": "t1"} for i, role in enumerate(SPELLINGS)])
    expected = sum(1 for role in SPELLINGS if rbac_defaults.normalize_role(role) == "help_desk")
    assert expected == 5
    holders, listed, mappings, _ = await role_contents.role_usage(SimpleNamespace(_db=mongo_db), "t1", "Help Desk")
    assert holders == expected and mappings == expected
    assert all(u["email"] != "u99@t.test" for u in listed)


@pytest.mark.asyncio
async def test_the_listing_is_capped_and_the_counts_are_not(mongo_db):  # noqa: F811
    await mongo_db.users.insert_many([_user(i, "Help Desk") for i in range(role_contents.MAX_LISTED + 10)])
    holders, listed, _, _ = await role_contents.role_usage(SimpleNamespace(_db=mongo_db), "t1", "Help Desk")
    assert holders == role_contents.MAX_LISTED + 10 and len(listed) == role_contents.MAX_LISTED


def test_the_name_pattern_escapes_regex_characters():
    import re
    pattern = re.compile(role_contents.role_name_pattern("ops.team_a"), re.IGNORECASE)
    assert pattern.search("Ops.Team A") and pattern.search("ops.team-a")
    assert not pattern.search("opsxteam a")

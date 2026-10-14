"""Spec C4: allowlist, OS/group sub-limits, limited-use install keys and license expiry,
against a real MongoDB (skips without one).

Value: protects=each control holds a new machine Pending with its own reason (not_allowlisted,
sublimit:os:<class>, sublimit:group:<id>, key_exhausted, license_expired) while machines that
pass enroll and agents already enrolled keep working; install keys are claimed atomically,
shown once and revocable; the Legacy key keeps old installers enrolling until revoked; the CSV
import reports bad rows and stays fast; only a super admin changes any of it;
fails_when=a control is skipped, a key overshoots its cap under concurrency, a revoked or
replaced key still enrolls, a running agent is cut off by expiry or revocation, or a tenant
admin edits controls; no_claim=the HTTP layer and JWT handling (endpoint functions are called
with a TokenData; limiters off), sub-limit races (documented as non-atomic), WS delivery.
"""
import asyncio
import contextlib
import importlib
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from starlette.requests import Request
from starlette.responses import Response

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import agent_allowlist
import agent_download_endpoints as dl
import agent_group_endpoints as groups
import agent_heartbeat_endpoints as hb
import agent_registry_endpoints as reg
import enrollment_keys
import license_rules
import licensing
import pending_agents
import tenant_endpoints as te
import tenant_enrollment_endpoints as tee
from auth_types import TokenData
from tests._mongo_test_db import mongo_db  # noqa: F401  (fixture)

T = "tenant-a"
REG_KEY = "reg_0123456789abcdef0123"
SUPER = TokenData(username="root@example.com", role="Super Admin", tenant_id="platform-admin", mfa_verified=True)
ADMIN_A = TokenData(username="admin@a.example", role="Tenant Admin", tenant_id=T, mfa_verified=True)
NOW = datetime.now(timezone.utc)


@pytest.fixture(autouse=True)
def _fresh_status_cache():
    pending_agents._status_cache.clear()
    yield


async def _setup(db, max_agents=50, **license_extra):
    await db.tenants.insert_one({"id": T, "name": "Acme", "registrationKey": REG_KEY,
                                 "license": {"maxAgents": max_agents, "seatsUsed": 0, "inactiveReclaimDays": 30,
                                             **license_extra}})
    await importlib.import_module("migrations.013_enrollment_controls").up(db)


def _hw(serial, os_family="windows", os_name="Windows 11 Pro", device="laptop"):
    return {"serialNumber": serial, "osFamily": os_family, "osName": os_name, "deviceType": device,
            "macAddresses": []}


def _request():
    return Request({"type": "http", "method": "POST", "path": "/api/agents/register", "headers": [],
                    "client": ("203.0.113.7", 5555)})


@contextlib.contextmanager
def _register_patches(db):
    stub = MagicMock()
    stub.finops_service.recalculate_tenant_costs = AsyncMock()
    with patch.object(reg, "get_database", return_value=db), patch.object(reg.limiter, "enabled", False), \
            patch.object(reg, "invalidate_cache"), patch.dict(sys.modules, {"finops_service": stub}):
        yield


async def _register_unpatched(hostname, key=REG_KEY, hardware=None, **body):
    payload = {"registrationKey": key, "hostname": hostname, "platform": "Windows", "version": "2.1.13",
               "supportsPending": True, **body}
    if hardware is not None:
        payload["hardware"] = hardware
    response = Response()
    try:
        out = await reg.register_agent(_request(), response, payload, background_tasks=MagicMock())
    except HTTPException as exc:
        return exc.status_code, exc.detail
    return response.status_code, out


async def _register(db, hostname, key=REG_KEY, hardware=None, **body):
    """(status, body) of POST /api/agents/register; (status, detail) when refused."""
    with _register_patches(db):
        return await _register_unpatched(hostname, key, hardware, **body)


async def _status(db, hostname):
    agent = await db.agents.find_one({"hostname": hostname})
    return agent["status"], agent.get("pendingReason")


# ── allowlist ─────────────────────────────────────────────────────────────────

async def test_allowlist_enforce_admits_listed_machines_only(mongo_db):
    """AC1. protects=enforce mode admits a listed serial (case-insensitively) and holds an
    unlisted one Pending not_allowlisted; fails_when=enforcement is skipped or over-matches."""
    await _setup(mongo_db, allowlistMode="enforce")
    await agent_allowlist.add(mongo_db, T, agent_allowlist.normalize_entry(serial="PF3ABC12"), "root")
    assert (await _register(mongo_db, "listed", hardware=_hw("pf3abc12")))[0] == 200
    code, out = await _register(mongo_db, "unlisted", hardware=_hw("ZZ999999"))
    assert code == 202 and out["pendingReason"] == "not_allowlisted"
    assert await _status(mongo_db, "unlisted") == ("Pending", "not_allowlisted")
    code, _ = await _register(mongo_db, "no-identity")  # an agent that reports no hardware cannot be matched
    assert code == 202


async def test_csv_import_of_ten_thousand_rows_is_fast_and_reports_bad_rows(mongo_db):
    """AC2. protects=10,000 rows import in under 10 s; a bad MAC, a repeated value and an empty
    row are reported by line and skipped; re-importing reports every row as already listed;
    fails_when=one bad row aborts the import or the import is slow."""
    await _setup(mongo_db)
    lines = ["serial,uuid,mac,note"] + [f"SN{i:06d}X,,,laptop {i}" for i in range(9_997)]
    lines += ["SNBADMAC1,,zz:zz:zz:zz:zz:zz,", "SN000001X,,,dup", ",,,", "SNOK0002,,3c:52:82:00:00:02,"]
    text = "\n".join(lines)
    started = time.perf_counter()
    out = await agent_allowlist.import_csv(mongo_db, T, text, "root")
    elapsed = time.perf_counter() - started
    assert elapsed < 10, elapsed
    assert out["imported"] == 9_998
    errors = {e["row"]: e["error"] for e in out["errors"]}
    assert "invalid macAddress" in errors[9_999] and "duplicate of row 3" in errors[10_000]
    assert await mongo_db.agent_allowlist.count_documents({"tenantId": T}) == 9_998
    again = await agent_allowlist.import_csv(mongo_db, T, "SN000005X,,,\nSNNEW001,,,", "root")
    assert again["imported"] == 1 and again["errors"] == [{"row": 1, "error": "already on the allowlist"}]
    with pytest.raises(agent_allowlist.EntryError):
        agent_allowlist.parse_csv("\n".join(f"S{i:07d}Q" for i in range(10_001)))


# ── sub-limits ────────────────────────────────────────────────────────────────

async def test_windows_server_sublimit_holds_the_second_server_only(mongo_db):
    """AC3. protects=os:windows_server max 1 with one server enrolled holds a second server
    Pending sublimit:os:windows_server while a workstation still enrolls; servers are told apart
    by OS name even as VMs; fails_when=the class is misread or the sub-limit ignored."""
    await _setup(mongo_db, subLimits=[{"key": "os:windows_server", "max": 1}])
    server_hw = _hw("SRV00001", os_name="Windows Server 2022 Datacenter", device="virtual_machine")
    assert (await _register(mongo_db, "srv-1", hardware=server_hw))[0] == 200
    code, out = await _register(mongo_db, "srv-2", hardware=dict(server_hw, serialNumber="SRV00002"))
    assert code == 202 and out["pendingReason"] == "sublimit:os:windows_server"
    assert (await _register(mongo_db, "laptop-1", hardware=_hw("LT000001")))[0] == 200
    assert license_rules.os_class({"osFamily": "linux"}) == "linux"
    assert license_rules.os_class(None, "Darwin") == "macos"
    assert license_rules.os_class({"osFamily": "windows", "deviceType": "server"}) == "windows_server"


async def test_group_sublimit_blocks_joining_and_key_default_group(mongo_db):
    """protects=a full group refuses new members (409) and holds a machine enrolling with a key
    whose default group is full; with room, the machine joins that group; fails_when=the group
    overfills or the key's group is ignored."""
    await _setup(mongo_db)
    await mongo_db.agent_groups.insert_one({"id": "g-1", "tenantId": T, "name": "Finance"})
    await licensing.update_license(mongo_db, T, sub_limits=[{"key": "group:g-1", "max": 1}])
    key = await enrollment_keys.create(mongo_db, T, "finance laptops", "root", default_group_id="g-1")
    code, out = await _register(mongo_db, "fin-1", key=key["key"], hardware=_hw("FIN00001"))
    assert code == 200
    assert await mongo_db.agent_group_members.count_documents({"group_id": "g-1", "agent_id": out["agentId"]}) == 1
    code, out = await _register(mongo_db, "fin-2", key=key["key"], hardware=_hw("FIN00002"))
    assert code == 202 and out["pendingReason"] == "sublimit:group:g-1"
    other = await _register(mongo_db, "ops-1", hardware=_hw("OPS00001"))
    with patch.object(groups, "get_database", return_value=mongo_db):
        with pytest.raises(HTTPException) as exc:
            await groups.add_members("g-1", groups.MembersUpdate(agent_ids=[other[1]["agentId"]]),
                                     current_user=SimpleNamespace(tenant_id=T, email="a@a"))
    assert exc.value.status_code == 409
    # Approving the held agent is an override: it joins its key's group.
    await pending_agents.approve(mongo_db, out["agentId"], "root")
    assert await mongo_db.agent_group_members.count_documents({"group_id": "g-1", "agent_id": out["agentId"]}) == 1


# ── install keys ──────────────────────────────────────────────────────────────

async def test_key_with_three_uses_admits_three_of_five_concurrent_installs(mongo_db):
    """AC4. protects=maxUses 3 under 5 concurrent installs -> exactly 3 enroll and 2 are Pending
    key_exhausted, the key showing 3 uses; fails_when=the use claim is not atomic."""
    await _setup(mongo_db)
    key = await enrollment_keys.create(mongo_db, T, "batch", "root", max_uses=3)
    with _register_patches(mongo_db):  # one patch scope: per-call scopes would unwind under the others
        results = await asyncio.gather(*(_register_unpatched(f"pc-{i}", key=key["key"], hardware=_hw(f"SN{i:05d}Q"))
                                         for i in range(5)))
    codes = sorted(code for code, _ in results)
    assert codes == [200, 200, 200, 202, 202], results
    assert {out["pendingReason"] for code, out in results if code == 202} == {"key_exhausted"}
    assert (await mongo_db.enrollment_keys.find_one({"id": key["id"]}))["uses"] == 3
    assert (await mongo_db.tenants.find_one({"id": T}))["license"]["seatsUsed"] == 3


async def test_legacy_key_enrolls_until_revoked_and_running_agents_carry_on(mongo_db):
    """AC5. protects=after migration 013 the tenant key is a Legacy key that enrolls; once revoked
    a new machine is Pending key_exhausted while an enrolled agent still re-enrolls with its secret
    and heartbeats; a replaced tenant key stops being a key at all; fails_when=revocation cuts off
    running agents or does not stop new ones."""
    await _setup(mongo_db)
    legacy = await mongo_db.enrollment_keys.find_one({"tenantId": T, "legacy": True})
    assert legacy and legacy["maxUses"] is None and legacy["keyHash"] == enrollment_keys.hash_key(REG_KEY)
    code, enrolled = await _register(mongo_db, "old-pc", hardware=_hw("OLD00001"))
    assert code == 200
    await enrollment_keys.revoke(mongo_db, T, legacy["id"], "root")
    code, out = await _register(mongo_db, "new-pc", hardware=_hw("NEW00001"))
    assert code == 202 and out["pendingReason"] == "key_exhausted"
    code, again = await _register(mongo_db, "old-pc", hardware=_hw("OLD00001"), agentSecret=enrolled["agentSecret"])
    assert code == 200 and again["token"]
    assert await _heartbeat_ok(mongo_db, enrolled["agentId"])
    await mongo_db.tenants.update_one({"id": T}, {"$set": {"registrationKey": "reg_replaced_0000000000"}})
    assert (await _register(mongo_db, "another", hardware=_hw("ANO00001")))[0] == 404


async def _heartbeat_ok(db, agent_id):
    tenant = await db.tenants.find_one({"id": T})
    response = Response()
    with patch.object(hb, "get_database", return_value=db), patch.object(hb.agent_limiter, "enabled", False), \
            patch.object(hb, "heartbeat_uninstall_protection", AsyncMock(return_value=None)):
        out = await hb.report_heartbeat(Request({"type": "http", "method": "POST", "headers": [],
                                                 "path": f"/api/agents/{agent_id}/heartbeat", "client": ("10.0.0.1", 1)}),
                                        response, agent_id, MagicMock(), {"hostname": "old-pc", "supportsPending": True},
                                        tenant)
    return response.status_code == 200 and out.get("success") is True


async def test_install_key_is_shown_once_and_managed_by_super_admin_only(mongo_db):
    """protects=the plaintext key comes back only from create, never from list; only a super admin
    creates or revokes keys while a tenant admin reads its own; fails_when=the key or its hash leaks
    or a tenant admin mints keys."""
    await _setup(mongo_db)
    with patch.object(tee, "mongodb", SimpleNamespace(db=mongo_db)), patch("audit_service.get_audit_service",
                                                                           return_value=MagicMock(log_action_async=AsyncMock())):
        created = await tee.create_enrollment_key(T, tee.KeyCreate(name="lab", maxUses=2), current_user=SUPER)
        assert created["key"].startswith("ek_") and created["prefix"] == created["key"][:8]
        listed = await tee.get_enrollment_keys(T, current_user=ADMIN_A)
        assert all("key" not in k and "keyHash" not in k for k in listed["keys"])
        assert {k["name"] for k in listed["keys"]} == {"lab", enrollment_keys.LEGACY_KEY_NAME}
        for call in (lambda: tee.create_enrollment_key(T, tee.KeyCreate(name="x"), current_user=ADMIN_A),
                     lambda: tee.revoke_enrollment_key(T, created["id"], current_user=ADMIN_A)):
            with pytest.raises(HTTPException) as exc:
                await call()
            assert exc.value.status_code == 403
        revoked = await tee.revoke_enrollment_key(T, created["id"], current_user=SUPER)
        assert revoked["revokedAt"] and "keyHash" not in revoked
        with pytest.raises(HTTPException) as exc:
            await tee.create_enrollment_key(T, tee.KeyCreate(name="old", expiresAt=NOW - timedelta(days=1)),
                                            current_user=SUPER)
        assert exc.value.status_code == 422


async def test_installer_download_can_ship_a_chosen_install_key(mongo_db):
    """protects=a download token may carry one of the tenant's usable install keys, which the
    installer then ships instead of the registration key; another tenant's or a revoked key is
    refused; fails_when=installers can only ever carry the tenant key or carry a foreign one."""
    await _setup(mongo_db)
    good = await enrollment_keys.create(mongo_db, T, "lab", "root", max_uses=5)
    bad = await enrollment_keys.create(mongo_db, T, "dead", "root")
    await enrollment_keys.revoke(mongo_db, T, bad["id"], "root")
    await mongo_db.tenants.insert_one({"id": "tenant-b", "name": "B", "registrationKey": "reg_b_000000000000000"})
    foreign = await enrollment_keys.create(mongo_db, "tenant-b", "b", "root")
    with patch.object(dl, "mongodb", SimpleNamespace(db=mongo_db)), patch.object(dl, "_check_agent_limit", AsyncMock()):
        for key in (bad["key"], foreign["key"], "ek_not_a_key"):
            with pytest.raises(HTTPException) as exc:
                await dl.create_download_token(T, {"enrollmentKey": key}, current_user=SUPER)
            assert exc.value.status_code == 422
        token = (await dl.create_download_token(T, {"enrollmentKey": good["key"]}, current_user=SUPER))["token"]
        role, _, install_key = await dl._auth_from_token(T, token)
        assert install_key == good["key"]
        assert await dl._get_tenant(T, install_key) == ("Acme", good["key"])
        assert await dl._get_tenant(T) == ("Acme", REG_KEY)


# ── expiry ────────────────────────────────────────────────────────────────────

async def test_expired_license_holds_new_machines_but_not_running_agents(mongo_db):
    """AC6. protects=after expiresAt a new machine is Pending license_expired while an enrolled
    agent's heartbeat is still 200; fails_when=expiry is ignored or suspends running agents."""
    await _setup(mongo_db)
    code, enrolled = await _register(mongo_db, "old-pc", hardware=_hw("OLD00001"))
    assert code == 200
    await licensing.update_license(mongo_db, T, expires_at=(NOW - timedelta(minutes=1)).isoformat())
    code, out = await _register(mongo_db, "new-pc", hardware=_hw("NEW00001"))
    assert code == 202 and out["pendingReason"] == "license_expired"
    assert await _heartbeat_ok(mongo_db, enrolled["agentId"])


async def test_expiry_reminders_go_out_once_per_threshold(mongo_db):
    """protects=30/7/1-day reminders reach the platform and tenant feeds once each, with the
    real days left, and a new expiry date re-arms them; fails_when=reminders repeat or are skipped."""
    await _setup(mongo_db)
    await licensing.update_license(mongo_db, T, expires_at=(NOW + timedelta(days=20)).isoformat())
    assert await license_rules.send_expiry_reminders(mongo_db, NOW) == 1
    assert await license_rules.send_expiry_reminders(mongo_db, NOW) == 0
    assert await license_rules.send_expiry_reminders(mongo_db, NOW + timedelta(days=14)) == 1   # 6 days left
    assert await license_rules.send_expiry_reminders(mongo_db, NOW + timedelta(days=19, hours=12)) == 1
    platform = await mongo_db.notifications.find({"tenantId": "platform-admin"}).sort("sent_at", 1).to_list(10)
    assert [n["metadata"]["daysLeft"] for n in platform] == [20, 6, 1]
    assert await mongo_db.notifications.count_documents({"tenantId": T, "metadata.audience": "tenant_admins"}) == 3
    await licensing.update_license(mongo_db, T, expires_at=(NOW + timedelta(days=3)).isoformat())
    assert await license_rules.send_expiry_reminders(mongo_db, NOW) == 1


# ── license PATCH ─────────────────────────────────────────────────────────────

async def test_license_patch_sets_validates_and_clears_controls(mongo_db):
    """protects=a super admin sets allowlist mode, sub-limits and expiry (and clears expiry with
    null); unknown keys or groups are 422; a tenant admin gets 403; fails_when=bad controls are
    stored or a tenant admin edits its own license."""
    await _setup(mongo_db)
    await mongo_db.agent_groups.insert_one({"id": "g-1", "tenantId": T, "name": "Finance"})
    audit = MagicMock(log_action_async=AsyncMock())
    with patch.object(te, "mongodb", SimpleNamespace(db=mongo_db)), patch("audit_service.get_audit_service", return_value=audit):
        out = await te.update_tenant_license(T, te.LicenseUpdate(
            allowlistMode="enforce", subLimits=[{"key": "os:linux", "max": 3}, {"key": "group:g-1", "max": 2}],
            expiresAt=NOW + timedelta(days=90)), current_user=SUPER)
        assert out["allowlistMode"] == "enforce" and len(out["subLimits"]) == 2 and out["expiresAt"]
        assert "allowlistMode" in audit.log_action_async.call_args.kwargs["details"]
        cleared = await te.update_tenant_license(T, te.LicenseUpdate(expiresAt=None), current_user=SUPER)
        assert cleared["expiresAt"] is None and cleared["allowlistMode"] == "enforce"
        for bad in ([{"key": "os:solaris", "max": 1}], [{"key": "group:nope", "max": 1}],
                    [{"key": "os:linux", "max": 1}, {"key": "os:linux", "max": 2}]):
            with pytest.raises(HTTPException) as exc:
                await te.update_tenant_license(T, te.LicenseUpdate(subLimits=bad), current_user=SUPER)
            assert exc.value.status_code == 422, bad
        with pytest.raises(HTTPException) as exc:
            await te.update_tenant_license(T, te.LicenseUpdate(allowlistMode="off"), current_user=ADMIN_A)
        assert exc.value.status_code == 403


async def test_allowlist_api_rejects_bad_entries_and_tenant_admin_writes(mongo_db):
    """protects=the allowlist API validates values (422), refuses duplicates (409) and lets a tenant
    admin read but not write; fails_when=junk is stored or a tenant admin edits its allowlist."""
    await _setup(mongo_db)
    with patch.object(tee, "mongodb", SimpleNamespace(db=mongo_db)), patch("audit_service.get_audit_service",
                                                                           return_value=MagicMock(log_action_async=AsyncMock())):
        doc = await tee.add_allowlist_entry(T, tee.AllowlistEntry(serialNumber="pf3abc12", note="CFO laptop"),
                                            current_user=SUPER)
        assert doc["serialNumber"] == "PF3ABC12"
        for body, code in ((tee.AllowlistEntry(serialNumber="PF3ABC12"), 409),
                           (tee.AllowlistEntry(macAddress="02:42:ac:11:00:02"), 422),
                           (tee.AllowlistEntry(serialNumber="To Be Filled By O.E.M."), 422),
                           (tee.AllowlistEntry(note="nothing else"), 422)):
            with pytest.raises(HTTPException) as exc:
                await tee.add_allowlist_entry(T, body, current_user=SUPER)
            assert exc.value.status_code == code, body
        assert (await tee.get_allowlist(T, 0, 200, current_user=ADMIN_A))["total"] == 1
        with pytest.raises(HTTPException) as exc:
            await tee.add_allowlist_entry(T, tee.AllowlistEntry(serialNumber="XYZ12345"), current_user=ADMIN_A)
        assert exc.value.status_code == 403
        with pytest.raises(HTTPException) as exc:
            await tee.get_allowlist("tenant-b", 0, 200, current_user=ADMIN_A)
        assert exc.value.status_code == 403

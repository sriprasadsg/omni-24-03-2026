"""The automatic quarantine decision, protected system files and playbook routing in the sweep
(Phase 83, plan 83-11, RESP-01 / RESP-03 / D-05 / D-28 / GATE-04). Real MongoDB (skips without one)
through the throwaway database of tests/_mongo_test_db.py. The full sweep tick is the system under test.

Value: protects=a file two different sources agree on is moved automatically (path and hash only), a hash
with no known location stays a suggestion because there is nothing to move, a protected operating-system
file waits for a person on both sides, and a tenant playbook can raise a block or a quarantine to a card
and never lower anything;
fails_when=a protected file is quarantined without a card, allow_protected is sent anywhere but from that
card, a hash with no path is dispatched, a playbook lowers a class, or a dormant host gets a row;
no_claim=a real agent or a real file system (the instruction is only written, never sent anywhere).
"""
import os
import sys
from datetime import datetime, timedelta, timezone

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from autonomous_ops import ledger, protected, protected_paths, signals, sweep
from tests._mongo_test_db import mongo_db  # noqa: F401  (fixture)
from tests.autonomy_support import seed_feed_ioc, seed_native_verdict, seed_response_agent, seed_tenant

SHA = "d" * 64
PATH = "/tmp/evil.bin"
NOW = datetime(2026, 10, 31, 12, 0, tzinfo=timezone.utc)
MIN = timedelta(minutes=1)
ACT_KEY = f"t1|sweep|quarantine_file|a1|{SHA}"


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("AUTONOMOUS_REMEDIATION_DRY_RUN", "false")
    protected.cache_clear()


async def _world(db, *, shadow=False, tokens=("block_ip_ttl", "quarantine_file"), platform="Linux", two_signal=None,
                 level="undoable_auto", last_seen=NOW):
    await ledger.ensure_indexes(db)
    await signals.ensure_indexes(db)
    await seed_tenant(db, "t1", shadow=shadow, level=level)
    await seed_response_agent(db, "t1", "a1", hostname="host-a1", tokens=list(tokens), platform=platform,
                              last_seen=last_seen)
    if two_signal is not None:
        await db.autonomy_settings.update_one({"tenantId": "t1"}, {"$set": {"response": {"twoSignal": two_signal}}})


async def _flag(db, path=PATH, *, second=True, kind="file", at=NOW):
    """The native scan flags the file (with its path) and, when ``second``, MalwareBazaar lists its hash."""
    await seed_native_verdict(db, "t1", "host-a1", kind=kind, target=path if kind == "file" else SHA, sha256=SHA,
                              created_at=at - 5 * MIN)
    if second:
        await seed_feed_ioc(db, ioc_type="hash", value=SHA, feed="malwarebazaar", updated_at=at)


async def _tick(db, at=NOW):
    await db.agents.update_one({"id": "a1"}, {"$set": {"lastSeen": at.isoformat()}})
    return await sweep.tick(db, now=at)


async def _rows(db, command="quarantine_file"):
    flt = {"tenantId": "t1", "kind": {"$ne": "control"}, "command": command}
    return [r async for r in db.autonomy_actions.find(flt, {"_id": 0}).sort("createdAt", 1)]


async def _instructions(db):
    return [d async for d in db.agent_instructions.find({"tenantId": "t1"}, {"_id": 0})]


# ------------------------------------------------------------------ the automatic quarantine

async def test_two_sources_and_a_known_path_make_one_automatic_quarantine(mongo_db):
    await _world(mongo_db)
    await _flag(mongo_db)
    await _tick(mongo_db)
    (row,) = await _rows(mongo_db)
    assert row["state"] == "dispatching" and row["autoDispatched"] is True and row["dedupeKey"] == ACT_KEY
    assert row["params"] == {"path": PATH, "sha256": SHA}               # no allow_protected, no other key
    assert row["target"] == PATH                                         # the row shows the file, not the agent id
    assert row["targets"] == ["a1"] and row["reasonText"].startswith("Two sources agree:")
    assert row["reason"]["inputs"]["origins"] == ["feed:malwarebazaar", "native"]
    assert row["reason"]["inputs"]["incidentId"].startswith("INC-")
    (doc,) = await _instructions(mongo_db)
    assert doc["type"] == "quarantine_file" and doc["autonomy"]["actionId"] == row["id"]
    assert doc["triggered_by"] == "autonomous_ops"


async def test_a_second_tick_decides_the_same_file_only_once(mongo_db):
    await _world(mongo_db)
    await _flag(mongo_db)
    for i in range(3):
        await _tick(mongo_db, NOW + i * MIN)
    assert len(await _rows(mongo_db)) == 1 and len(await _instructions(mongo_db)) == 1


async def test_with_the_rule_off_one_source_and_a_path_quarantine_and_say_so(mongo_db):
    await _world(mongo_db, two_signal=False)
    await _flag(mongo_db, second=False)
    await _tick(mongo_db)
    (row,) = await _rows(mongo_db)
    assert row["state"] == "dispatching" and row["reasonText"].startswith("This organization's two-source rule is off")


async def test_one_source_alone_stays_a_suggestion_with_the_path(mongo_db):
    await _world(mongo_db)
    await _flag(mongo_db, second=False)
    await _tick(mongo_db)
    (row,) = await _rows(mongo_db)
    assert row["state"] == "suggested" and row["params"] == {"path": PATH, "sha256": SHA}
    assert await _instructions(mongo_db) == []


async def test_a_corroborated_hash_with_no_path_on_the_host_stays_a_suggestion(mongo_db):
    await _world(mongo_db)
    await _flag(mongo_db, kind="hash")
    await _tick(mongo_db)
    (row,) = await _rows(mongo_db)
    assert row["state"] == "suggested" and "path" not in row["params"] and row["params"]["sha256"] == SHA
    assert row["dedupeKey"] == f"t1|sweep-suggest|quarantine_file|a1|{SHA}"
    assert "nothing to move" in row["reasonText"] and row["reasonText"].startswith("Two sources agree:")
    assert await _instructions(mongo_db) == []


async def test_the_suggestion_becomes_the_action_when_the_path_becomes_known(mongo_db):
    await _world(mongo_db)
    await _flag(mongo_db, kind="hash")
    await _tick(mongo_db)
    await seed_native_verdict(mongo_db, "t1", "host-a1", kind="file", target=PATH, sha256=SHA,
                              created_at=NOW + 5 * MIN)
    await _tick(mongo_db, NOW + 10 * MIN)
    states = sorted(r["state"] for r in await _rows(mongo_db))
    assert states == ["dispatching", "expired"]
    assert len(await _instructions(mongo_db)) == 1


async def test_in_shadow_the_decision_is_a_simulation_and_nothing_is_written(mongo_db):
    await _world(mongo_db, shadow=True)
    await _flag(mongo_db)
    await _tick(mongo_db)
    (row,) = await _rows(mongo_db)
    assert row["state"] == "shadow" and row["wouldHave"] == "allow_auto" and await _instructions(mongo_db) == []


@pytest.mark.parametrize("tokens,last_seen", [(("block_ip_ttl",), NOW), (("quarantine_file",), NOW - timedelta(hours=2))])
async def test_a_host_that_cannot_quarantine_right_now_gets_no_row(mongo_db, tokens, last_seen):
    await _world(mongo_db, tokens=tokens, last_seen=last_seen)
    await _flag(mongo_db)
    await sweep.tick(mongo_db, now=NOW)
    assert await _rows(mongo_db) == [] and await _instructions(mongo_db) == []


# ------------------------------------------------------------------ protected system files (D-28)

@pytest.mark.parametrize("platform,path", [("Linux", "/usr/bin/ls"), ("Windows", "C:/WINDOWS/System32/Evil.exe")])
async def test_a_protected_system_file_becomes_a_card_that_carries_allow_protected(mongo_db, platform, path):
    await _world(mongo_db, platform=platform)
    await _flag(mongo_db, path)
    await _tick(mongo_db)
    (row,) = await _rows(mongo_db)
    assert row["state"] == "awaiting_approval" and row["reasonCode"] == "playbook_raised"
    assert row["params"] == {"path": path, "sha256": SHA, "allow_protected": True}
    assert row["reasonText"].startswith("This is a protected system file, so it isn't moved automatically.")
    assert "Two sources agree" in row["reasonText"]
    assert row["reason"]["inputs"]["protectedPath"] is True and row["reason"]["inputs"]["incidentId"]
    assert await _instructions(mongo_db) == []


async def test_approving_the_protected_card_sends_allow_protected_and_nothing_else_does(mongo_db):
    from autonomous_ops import approvals
    await _world(mongo_db)
    await _flag(mongo_db, "/usr/bin/ls")
    await _tick(mongo_db)
    (card,) = await _rows(mongo_db)
    # The dormancy re-check at approval time reads the real clock: the host reports in now, the card is still fresh.
    now = datetime.now(timezone.utc)
    await mongo_db.agents.update_one({"id": "a1"}, {"$set": {"lastSeen": now.isoformat()}})
    await mongo_db.autonomy_actions.update_one({"id": card["id"]}, {"$set": {"approval.expiresAt": now + 10 * MIN}})
    out = await approvals.approve(mongo_db, "t1", card["id"],
                                  approver={"username": "alice", "display": "Alice", "tier": "tenant"})
    assert out["status"] == "dispatched", out
    (doc,) = await _instructions(mongo_db)
    assert doc["type"] == "quarantine_file" and doc["payload"].get("allow_protected") is True


async def test_an_ordinary_file_never_carries_allow_protected(mongo_db):
    await _world(mongo_db)
    await _flag(mongo_db, "/home/user/Downloads/x.bin")
    await _tick(mongo_db)
    (row,) = await _rows(mongo_db)
    assert "allow_protected" not in row["params"]


# ------------------------------------------------------------------ the protected-path check itself

@pytest.mark.parametrize("platform,path,expected", [
    ("Linux", "/usr/bin/ls", True), ("Linux", "/usr/sbin/sshd", True), ("Linux", "/bin/sh", True),
    ("Linux", "/sbin/init", True), ("Linux", "/boot/vmlinuz", True), ("Linux", "/etc/passwd", True),
    ("Linux", "/var/lib/omni-agent/quarantine/x", True), ("Linux", "/opt/omni-agent/bin/agent", True),
    ("Linux", "/bin", True),
    ("Linux", "/tmp/../usr/bin/x", True), ("Linux", "//usr//bin//x", True), ("Linux", "/usr/./bin/x", True),
    ("Linux", "/etcetera/x", False), ("Linux", "/usr/binary/x", False), ("Linux", "/home/u/usr/bin/x", False),
    ("Linux", "/tmp/evil.bin", False), ("Linux", "usr/bin/x", True), ("Linux", "", True),
    ("Windows", "C:\\Windows\\System32\\cmd.exe", True), ("Windows", "c:/windows/system32/x.dll", True),
    ("Windows", "C:/WINDOWS/SysWOW64/x.exe", True), ("Windows", "D:\\Windows\\WinSxS\\x", True),
    ("Windows", "C:\\Program Files\\OmniAgentRust\\agent.exe", True),
    ("Windows", "C:\\ProgramData\\OmniAgent\\q\\x", True),
    ("Windows", "C:\\Windows\\Temp\\..\\System32\\x.exe", True),
    ("Windows", "C:\\Windows\\System32.\\x.exe", True), ("Windows", "\\\\?\\C:\\Windows\\System32\\x.exe", True),
    ("Windows", "C:\\Windows\\System3\\x.exe", False), ("Windows", "C:\\Users\\u\\Downloads\\x.exe", False),
    ("Windows", "C:\\Windows\\Temp\\x.exe", False),
    (None, "/usr/bin/ls", True), (None, "C:\\Windows\\System32\\x.exe", True), (None, "/tmp/x", False),
    ("Linux", None, True), ("Linux", 5, True),
])
def test_is_protected(platform, path, expected):
    assert protected_paths.is_protected(path, platform) is expected


def test_the_lists_are_the_contracts_so_the_agent_and_the_backend_cannot_drift():
    from autonomous_ops import agent_support
    windows, linux = protected_paths._lists()
    assert windows == agent_support.CONTRACT["protectedPaths"]["windows"]
    assert linux == agent_support.CONTRACT["protectedPaths"]["linux"]
    for needed in ("windows\\system32", "windows\\syswow64", "windows\\winsxs"):
        assert needed in windows
    for needed in ("/usr/bin/", "/usr/sbin/", "/bin/", "/sbin/", "/boot/"):
        assert needed in linux


# ------------------------------------------------------------------ playbooks may raise a class, never lower it (GATE-04)

async def _tenant_playbook(db, name, action, params, **step):
    await db.remediation_playbooks.insert_one({
        "id": f"op-{name}", "name": name, "finding_class": "nscan", "source": "operator", "tenantId": "t1",
        "steps": [{"action": action, "params": params, **step}], "rollback": []})


async def test_a_tenant_playbook_that_raises_quarantine_file_makes_the_automatic_path_a_card(mongo_db):
    await _world(mongo_db)
    await _tenant_playbook(mongo_db, "quarantine_file", "quarantine_file",
                           {"path": "{{finding.resource_id}}", "sha256": "{{finding.details.sha256}}"},
                           gate_class="approve")
    await _flag(mongo_db)
    await _tick(mongo_db)
    (row,) = await _rows(mongo_db)
    assert row["state"] == "awaiting_approval" and row["reasonCode"] == "playbook_raised"
    assert "allow_protected" not in row["params"] and await _instructions(mongo_db) == []


async def test_a_tenant_playbook_that_raises_block_ip_makes_the_automatic_block_a_card(mongo_db):
    await _world(mongo_db)
    await _tenant_playbook(mongo_db, "block_ip", "block_ip", {"ip_address": "{{finding.resource_id}}"},
                           gate_class="approve")
    ip = "45.33.32.156"
    await seed_native_verdict(mongo_db, "t1", "host-a1", kind="ip", target=ip, created_at=NOW - 5 * MIN)
    await seed_feed_ioc(mongo_db, ioc_type="url", value=f"http://{ip}/x", source_ip=ip, feed="urlhaus", updated_at=NOW)
    await _tick(mongo_db)
    (row,) = await _rows(mongo_db, "block_ip")
    assert row["state"] == "awaiting_approval" and row["reasonCode"] == "playbook_raised"


async def test_a_tenant_playbook_cannot_lower_an_approval_action(mongo_db):
    from autonomous_ops import registry
    assert registry.playbook_raises([{"action": "isolate_host", "gate_class": "auto"}]) is False
    assert registry.effective_class(registry.resolve("isolate_host"), playbook_raise=False) == "approve"


async def test_a_playbook_that_says_auto_changes_nothing(mongo_db):
    await _world(mongo_db)
    await _tenant_playbook(mongo_db, "quarantine_file", "quarantine_file",
                           {"path": "{{finding.resource_id}}", "sha256": "{{finding.details.sha256}}"},
                           gate_class="auto", destructive=True)
    await _flag(mongo_db)
    await _tick(mongo_db)
    (row,) = await _rows(mongo_db)
    assert row["state"] == "dispatching"


# ------------------------------------------------------------------ the sweep reads the playbook, nothing more

def test_the_sweep_selects_a_playbook_and_checks_protected_paths_and_stays_small():
    import inspect
    from autonomous_ops import sweep_security
    source = inspect.getsource(sweep_security)
    assert "select_playbook" in source and "playbook_raises" in source and "is_protected" in source
    assert len(source.splitlines()) < 500

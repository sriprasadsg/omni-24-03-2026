"""Autonomous Ops gate (Phase 81, plan 81-01): the one decision function, the write-ahead
decision ledger and the audit mirror. Real MongoDB (skips without one) through the
throwaway database of tests/_mongo_test_db.py; nothing touches the live database.

Value: protects=an eligible tenant's request is decided once, recorded in autonomy_actions
BEFORE anything is dispatched, mirrored into the hash-chained audit ledger and listed under
the right bucket; a tenant without the Autonomous Ops screen tick is Off and leaves no row,
no audit event; a ledger that cannot be written refuses the decision and dispatches nothing;
fails_when=a decision is returned without a row, an unticked tenant leaves a trace, an
instruction is written in shadow mode or without a ledger row, or the audit chain breaks;
no_claim=the remaining GATE-03 steps (stop, level, never-touch, caps, dedupe), which
test_autonomous_ops_gate_order.py (plan 81-11) enumerates.
"""
import contextlib
import itertools
import os
import sys
from unittest.mock import AsyncMock, patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import audit_ledger
from autonomous_ops import gate, ledger, protected, registry, settings
from tests._mongo_test_db import mongo_db  # noqa: F401  (fixture)
from tests.autonomy_support import seed_agent, seed_platform_stop, seed_tenant

IP = "203.0.113.7"


def _block_ip(tenant_id, agent_id="a1", ip=IP):
    return gate.ActionRequest(tenant_id=tenant_id, kind="security", origin="test", actions=["block_ip"],
                              targets=[agent_id], params={"ip_address": ip},
                              dedupe_key=f"{tenant_id}|block_ip|{ip}",
                              reason={"ruleId": "playbook:block_ip", "inputs": {"ip": ip}})


@pytest.fixture(autouse=True)
def _default_master(monkeypatch):
    monkeypatch.delenv("AUTONOMOUS_REMEDIATION_DRY_RUN", raising=False)  # unset = shadow on


async def test_tracer_shadow_decision_is_written_ahead_and_listed(mongo_db):
    """Tracer. protects=GATE-03 / GATE-07 / GATE-09: the decision exists as one shadow row,
    nothing is dispatched, the audit chain holds the matching event and the list shows it."""
    await ledger.ensure_indexes(mongo_db)
    await seed_tenant(mongo_db, "t1")
    await seed_agent(mongo_db, "t1", "a1", hostname="h1", ip="10.1.1.5")

    decision = await gate.decide(mongo_db, _block_ip("t1"))

    assert (decision.outcome, decision.state, decision.would_have) == ("allow_auto", "shadow", "allow_auto")
    assert decision.recorded is True and decision.shadow is True and decision.action_id
    rows = await mongo_db.autonomy_actions.find({"tenantId": "t1"}).to_list(10)
    assert [r["id"] for r in rows] == [decision.action_id]
    assert rows[0]["state"] == "shadow" and rows[0]["wouldHave"] == "allow_auto"
    stored = await ledger.get(mongo_db, "t1", decision.action_id)
    assert stored["createdAt"].tzinfo is not None
    assert await mongo_db.agent_instructions.count_documents({}) == 0
    assert await mongo_db.response_tasks.count_documents({}) == 0

    report = await audit_ledger.verify("t1", db=mongo_db)
    assert report["valid"] and report["total_records"] >= 1
    event = await mongo_db.audit_logs.find_one({"tenantId": "t1", "action": "autonomous_ops.shadow"})
    assert event and event["resourceId"] == decision.action_id

    sim = await ledger.list_actions(mongo_db, "t1", bucket="simulation")
    assert [i["id"] for i in sim["items"]][:1] == [decision.action_id]
    done = await ledger.list_actions(mongo_db, "t1", bucket="done")
    assert done["items"] == [] and done["nextCursor"] is None


async def test_unticked_tenant_is_off_and_unrecorded(mongo_db):
    """protects=D-23 / GATE-02: no tick = Off; refused not_enabled, and no row, no audit event."""
    await ledger.ensure_indexes(mongo_db)
    await seed_tenant(mongo_db, "t2", ticked=False)

    decision = await gate.decide(mongo_db, _block_ip("t2"))

    assert (decision.outcome, decision.reason, decision.recorded) == ("refuse", "not_enabled", False)
    assert decision.action_id is None
    assert await mongo_db.autonomy_actions.count_documents({"tenantId": "t2"}) == 0
    assert await mongo_db.audit_logs.count_documents({"tenantId": "t2"}) == 0


async def test_platform_tenant_is_always_off(mongo_db):
    """protects=D-04: platform-admin is Off whatever it is ticked or stored as."""
    await ledger.ensure_indexes(mongo_db)
    await seed_tenant(mongo_db, "platform-admin")

    decision = await gate.decide(mongo_db, _block_ip("platform-admin"))

    assert (decision.outcome, decision.reason, decision.recorded) == ("refuse", "platform_tenant", False)
    assert await mongo_db.autonomy_actions.count_documents({}) == 0
    assert await mongo_db.audit_logs.count_documents({}) == 0


async def test_class_step_escalates_approve_actions_and_refuses_unregistered(mongo_db):
    """protects=GATE-04: an approve action never decides allow_auto (it needs approval), and a
    name outside the registry, an undo-only name or a probe is refused unregistered_action."""
    await ledger.ensure_indexes(mongo_db)
    await seed_tenant(mongo_db, "t1", shadow=False)
    await seed_agent(mongo_db, "t1", "a1", ip="198.51.100.11")
    mongo_db_shadow_off = {"master_shadow": False}

    iso = gate.ActionRequest(tenant_id="t1", kind="security", origin="test", actions=["isolate_host"],
                             targets=["a1"], params={}, dedupe_key="t1|isolate|a1")
    d = await gate.decide(mongo_db, iso, **mongo_db_shadow_off)
    assert (d.outcome, d.state, d.reason) == ("needs_approval", "awaiting_approval", "class_approve")
    row = await ledger.get(mongo_db, "t1", d.action_id)
    assert row["approval"]["expiresAt"] - row["createdAt"] == gate.APPROVAL_TTL

    raised = gate.ActionRequest(tenant_id="t1", kind="security", origin="test", actions=["block_ip"],
                                targets=["a1"], params={"ip_address": IP}, dedupe_key="t1|raised",
                                playbook_raise=True)
    d = await gate.decide(mongo_db, raised, **mongo_db_shadow_off)
    assert (d.outcome, d.reason) == ("needs_approval", "playbook_raised")

    for name in ("rm_rf", "unblock_ip", "scan_file"):
        bad = gate.ActionRequest(tenant_id="t1", kind="security", origin="test", actions=[name],
                                 targets=["a1"], params={}, dedupe_key=f"t1|{name}")
        d = await gate.decide(mongo_db, bad, **mongo_db_shadow_off)
        assert (d.outcome, d.reason) == ("refuse", "unregistered_action"), name

    auto = await gate.decide(mongo_db, _block_ip("t1"), **mongo_db_shadow_off)
    assert (auto.outcome, auto.state) == ("allow_auto", "dispatching")
    row = await ledger.get(mongo_db, "t1", auto.action_id)
    assert row["autoDispatched"] is True and row["state"] == "dispatching"

    sug = await gate.suggest(mongo_db, _block_ip("t1", ip="203.0.113.9"), **mongo_db_shadow_off)
    assert (sug.outcome, sug.state) == ("suggest", "suggested")


async def test_a_ledger_that_cannot_be_written_refuses_the_decision(mongo_db):
    """protects=GATE-07: when the insert raises, decide refuses ledger_unavailable and no
    instruction or response task is written."""
    await seed_tenant(mongo_db, "t1", shadow=False)
    await seed_agent(mongo_db, "t1", "a1", ip="198.51.100.11")

    class _Broken:
        async def insert_one(self, *_a, **_k):
            raise RuntimeError("disk full")

    with patch.object(ledger, "_actions", lambda _db: _Broken()):
        decision = await gate.decide(mongo_db, _block_ip("t1"), master_shadow=False)

    assert (decision.outcome, decision.reason, decision.recorded) == ("refuse", "ledger_unavailable", False)
    assert await mongo_db.agent_instructions.count_documents({}) == 0
    assert await mongo_db.response_tasks.count_documents({}) == 0


# ---------------------------------------------------------------- plan 81-11, Task 1 (tracer)

def _own_address() -> str:
    """An address of one of this host's own interfaces, as the never-touch list sees it."""
    import socket

    import psutil
    for addrs in psutil.net_if_addrs().values():
        for item in addrs:
            if item.family == socket.AF_INET and not item.address.startswith("127."):
                return item.address
    return "127.0.0.1"


async def test_tracer_own_address_is_refused_protected_target_at_every_level(mongo_db):
    """Tracer. protects=GATE-08 / PROH-81-03: a block_ip aimed at the backend's own address is
    refused protected_target through gate.decide, recorded with the plain-words reason, even at
    Suggest, and writes no instruction."""
    from autonomous_ops import messages
    await ledger.ensure_indexes(mongo_db)
    own = _own_address()
    for tenant, level in (("t1", "undoable_auto"), ("t2", "suggest")):
        await seed_tenant(mongo_db, tenant, level=level, shadow=False)
        await seed_agent(mongo_db, tenant, f"{tenant}-a1", ip="198.51.100.11" if tenant == "t1" else "198.51.100.12")
        d = await gate.decide(mongo_db, _block_ip(tenant, agent_id=f"{tenant}-a1", ip=own), master_shadow=False)
        assert (d.outcome, d.state, d.reason, d.recorded) == ("refuse", "refused", "protected_target", True), tenant
        rows = await mongo_db.autonomy_actions.find({"tenantId": tenant}).to_list(5)
        assert len(rows) == 1 and rows[0]["state"] == "refused" and rows[0]["reasonCode"] == "protected_target"
        assert rows[0]["reasonText"] == messages.REASON_TEXT["protected_target"]
    assert await mongo_db.agent_instructions.count_documents({}) == 0
    assert await mongo_db.response_tasks.count_documents({}) == 0


async def test_platform_agent_address_other_tenant_target_and_empty_targets_are_refused(mongo_db):
    """protects=GATE-08 / D-17: a block_ip for the address of a platform-admin agent is
    protected_target; a target agent of another tenant (or none) is cross_tenant_target; an
    empty target list is no_target."""
    await ledger.ensure_indexes(mongo_db)
    await seed_tenant(mongo_db, "t1", shadow=False)
    await seed_agent(mongo_db, "t1", "a1", ip="198.51.100.11")
    await seed_agent(mongo_db, "t9", "b1", ip="198.51.100.19")
    await seed_agent(mongo_db, "platform-admin", "pa1", ip="198.51.100.77")
    kw = {"master_shadow": False}

    d = await gate.decide(mongo_db, _block_ip("t1", ip="198.51.100.77"), **kw)
    assert (d.outcome, d.reason) == ("refuse", "protected_target")
    for target in ("b1", "pa1", "ghost"):
        d = await gate.decide(mongo_db, _block_ip("t1", agent_id=target), **kw)
        assert (d.outcome, d.reason) == ("refuse", "cross_tenant_target"), target
    empty = _block_ip("t1")
    empty.targets = []
    d = await gate.decide(mongo_db, empty, **kw)
    assert (d.outcome, d.reason) == ("refuse", "no_target")
    assert await mongo_db.agent_instructions.count_documents({}) == 0


def test_messages_cover_every_reason_code_and_every_registry_command():
    """protects=ACTV-01 / ACTV-08: every code decide can record has plain words, every command
    has a label, and no user-visible text uses a banned term."""
    import re

    from autonomous_ops import messages, registry
    assert set(messages.REASON_TEXT) >= set(gate.REASON_CODES)
    assert set(messages.ACTION_LABELS) >= set(registry.commands())
    assert messages.PLATFORM_ADMIN_DISPLAY == "Platform administrator"
    assert messages.simulation_result("block 203.0.113.7") == \
        "Nothing was done. This is what would have happened: block 203.0.113.7."
    texts = [*messages.ACTION_LABELS.values(), *messages.CLASS_LINES.values(), *messages.CONTROL_LABELS.values(),
             *messages.REASON_TEXT.values(), *[t for pair in messages.NOTICES.values() for t in pair]]
    banned = re.compile(r"\b(ASI|AGI)\b|autopilot|fully[ -]autonomous|roll(ed|ing)?[ -]?back", re.IGNORECASE)
    assert [t for t in texts if banned.search(t)] == []


# ---------------------------------------------------------------- plan 81-11, Task 2: the enumeration

_RANK = {"allow_auto": 0, "needs_approval": 1, "suggest": 2}
_STATE = {"allow_auto": "dispatching", "needs_approval": "awaiting_approval", "suggest": "suggested"}
_UNRECORDED = {"no_tenant", "platform_tenant", "not_enabled", "level_off", "duplicate",
               "suppressed_by_undo", "ledger_unavailable"}


def _oracle(pstop, elig, tstop, level, cls, prot, nt, shadow):
    """The expected (outcome, state, reason, recorded), written from the GATE-03 table and
    deliberately not sharing code with gate.py. shadow is master | tenant | off."""
    platform, unreadable = elig == "platform", elig in ("settings_bad", "features_bad")
    eff = "off" if elig in ("platform", "unticked") else "suggest" if unreadable else level
    # a tenant whose tenant document cannot be read has no settings: shadow on, stop not seen
    tenant_shadow = True if elig == "features_bad" else shadow == "tenant"
    stopped = tstop and elig != "features_bad"

    def refuse(code):
        return "refuse", "refused", code, code not in _UNRECORDED and eff != "off"

    if pstop != "off":
        return refuse("platform_stop")
    if platform:
        return refuse("platform_tenant")
    if elig == "unticked":
        return refuse("not_enabled")
    if stopped:
        return refuse("tenant_stop")
    if eff == "off":
        return refuse("level_off")
    soft = [("suggest", "settings_unreadable")] if unreadable else []
    soft += [("suggest", "level_suggest")] if eff == "suggest" else []
    soft += {"approve": [("needs_approval", "class_approve")],
             "raised": [("needs_approval", "playbook_raised")]}.get(cls, [])
    if nt == 0:
        return refuse("no_target")
    if prot:
        return refuse("protected_target")
    soft += [("needs_approval", "blast_radius")] if nt == 2 else []
    best = ("allow_auto", "class_auto")
    for outcome, code in soft:
        if _RANK[outcome] > _RANK[best[0]]:
            best = (outcome, code)
    state = "shadow" if shadow == "master" or tenant_shadow else _STATE[best[0]]
    return best[0], state, best[1], True


_DESTRUCTIVE_ONLY = [{"action": "block_ip", "params": {"ip_address": "x"}, "destructive": True}]
_RAISED = [{"action": "block_ip", "params": {"ip_address": "x"}, "gate_class": "approve"}]
_CLASSES = {  # name -> (action, steps the playbook would carry)
    "auto": ("block_ip", [{"action": "block_ip"}]), "approve": ("isolate_host", None),
    "raised": ("block_ip", _RAISED), "destructive": ("block_ip", _DESTRUCTIVE_ONLY)}


class _Tenants:
    async def find_one(self, *_a, **_k):
        raise RuntimeError("tenants collection unavailable")


class _FlakyDb:
    """The real database, except that the tenant document cannot be read."""

    def __init__(self, db):
        self._db, self.tenants = db, _Tenants()

    def __getattr__(self, name):
        return getattr(self._db, name)

    def __getitem__(self, name):
        return self._db[name]


async def _seed_world(db):
    """4 eligibility kinds x 3 levels x 2 stop x 2 shadow-flag tenants, each with three agents:
    a1, a2 (unprotected) and pa (recorded address 127.0.0.1, which is never touched)."""
    n = itertools.count(1)
    for kind, level, stop, tflag in itertools.product(("ticked", "unticked", "settings_bad", "features_bad"),
                                                      ("off", "suggest", "undoable_auto"), (False, True),
                                                      (False, True)):
        name = f"e-{kind}-{level}-{int(stop)}-{int(tflag)}"
        await seed_tenant(db, name, level=level, shadow=tflag, ticked=kind != "unticked",
                          stop={"active": True, "scope": "tenant"} if stop else None)
        if kind == "settings_bad":
            await db.autonomy_settings.update_one({"tenantId": name}, {"$set": {"level": "bogus"}})
        for agent, ip in (("a1", f"198.51.100.{next(n)}"), ("a2", f"198.51.100.{next(n)}"), ("pa", "127.0.0.1")):
            await seed_agent(db, name, f"{name}-{agent}", ip=ip)
    await seed_agent(db, "platform-admin", "platform-admin-a1", ip="198.51.100.250")


def _enum_request(tenant, cls, prot, nt, key):
    action, steps = _CLASSES[cls]
    targets = [f"{tenant}-pa" if prot else f"{tenant}-a1", f"{tenant}-a2"][:nt]
    params = {"ip_address": "127.0.0.1" if prot else IP} if action == "block_ip" else {}
    return gate.ActionRequest(tenant_id=tenant, kind="security", origin="enum", actions=[action], targets=targets,
                              params=params, dedupe_key=key,
                              playbook_raise=registry.playbook_raises(steps) if steps else False)


async def test_every_combination_of_inputs_matches_the_oracle(mongo_db):
    """protects=GATE-02/03/04/08/09, D-17, D-23: platform stop x eligibility x tenant stop x
    level x class x protected x targets x shadow equals the independent oracle; no combination
    writes an instruction; an Off tenant leaves no row; the destructive-only class equals plain
    auto; the master flag only turns a dispatching outcome into a simulation."""
    await ledger.ensure_indexes(mongo_db)
    await protected.ensure_indexes(mongo_db)
    protected.cache_clear()
    await _seed_world(mongo_db)
    flaky, seen, checked = _FlakyDb(mongo_db), {}, 0
    for pstop in ("off", "on", "unreadable"):
        await mongo_db.system_settings.delete_many({})
        if pstop == "on":
            await seed_platform_stop(mongo_db)
        with patch.object(settings, "platform_stop", AsyncMock(side_effect=RuntimeError("down"))) \
                if pstop == "unreadable" else contextlib.nullcontext():
            for elig, tstop, level, cls, prot, nt, shadow in itertools.product(
                    ("ticked", "unticked", "settings_bad", "features_bad", "platform"), (False, True),
                    ("off", "suggest", "undoable_auto"), tuple(_CLASSES), (False, True), (0, 1, 2),
                    ("master", "tenant", "off")):
                tflag = shadow == "tenant"
                tenant = ("platform-admin" if elig == "platform"
                          else f"e-{'ticked' if elig == 'features_bad' else elig}-{level}-{int(tstop)}-{int(tflag)}")
                if elig == "platform":
                    await seed_tenant(mongo_db, tenant, level=level, shadow=tflag,
                                      stop={"active": True, "scope": "tenant"} if tstop else None)
                req = _enum_request(tenant, cls, prot, nt, f"k{checked}")
                d = await gate.decide(flaky if elig == "features_bad" else mongo_db, req,
                                      master_shadow=shadow == "master")
                want = _oracle(pstop, elig, tstop, level, cls, prot, nt, shadow)
                got = (d.outcome, d.state, d.reason, d.recorded)
                assert got == want, (pstop, elig, tstop, level, cls, prot, nt, shadow)
                rows = await mongo_db.autonomy_actions.find({}, {"state": 1}).to_list(5)
                assert len(rows) == (1 if want[3] else 0), (pstop, elig, tstop, level, cls, prot, nt, shadow)
                if rows:
                    await mongo_db.autonomy_actions.delete_many({})
                assert await mongo_db.agent_instructions.estimated_document_count() == 0
                assert await mongo_db.response_tasks.estimated_document_count() == 0
                seen[(pstop, elig, tstop, level, cls, prot, nt, shadow)] = got
                checked += 1
    assert checked == 3 * 5 * 2 * 3 * 4 * 2 * 3 * 3 and checked >= 1000
    assert await mongo_db.audit_logs.count_documents({"tenantId": {"$regex": "^e-unticked-|^platform-admin$"}}) == 0
    assert {v[0] for v in seen.values()} == {"refuse", "suggest", "needs_approval", "allow_auto"}
    assert {v[1] for v in seen.values()} == {"refused", "shadow", "suggested", "awaiting_approval", "dispatching"}
    for key, got in seen.items():
        if key[4] == "destructive":
            assert got == seen[key[:4] + ("auto",) + key[5:]], key
        if key[7] == "master" and got[0] != "refuse":
            peer = seen[key[:7] + ("off",)]
            assert (got[0], got[2]) == (peer[0], peer[2]) and got[1] == "shadow", key


async def test_vendored_block_ip_playbook_stays_automatic_through_decide(mongo_db):
    """protects=GATE-04 / GATE-03: a request built from the shipped block_ip playbook (whose
    step carries destructive true) for an eligible tenant at undoable_auto, both shadow layers
    off, one unprotected target is allow_auto and dispatching; a gate_class approve step on the
    same playbook makes it needs_approval playbook_raised."""
    from remediation_playbook_service import load_default_playbooks
    await ledger.ensure_indexes(mongo_db)
    await seed_tenant(mongo_db, "t1", shadow=False)
    await seed_agent(mongo_db, "t1", "a1", ip="198.51.100.11")
    playbook = next(p for p in load_default_playbooks() if p["name"] == "block_ip")
    assert playbook["steps"][0].get("destructive") is True
    request = gate.ActionRequest(tenant_id="t1", kind="security", origin="playbook", actions=["block_ip"],
                                 targets=["a1"], params={"ip_address": IP}, dedupe_key="t1|vendored",
                                 playbook="block_ip", playbook_raise=registry.playbook_raises(playbook["steps"]))
    d = await gate.decide(mongo_db, request, master_shadow=False)
    assert (d.outcome, d.state, d.reason) == ("allow_auto", "dispatching", "class_auto")
    assert (await ledger.get(mongo_db, "t1", d.action_id))["autoDispatched"] is True

    steps = [dict(playbook["steps"][0], gate_class="approve")]
    raised = gate.ActionRequest(**{**request.__dict__, "dedupe_key": "t1|vendored-raised",
                                   "playbook_raise": registry.playbook_raises(steps)})
    d = await gate.decide(mongo_db, raised, master_shadow=False)
    assert (d.outcome, d.state, d.reason) == ("needs_approval", "awaiting_approval", "playbook_raised")


# ---------------------------------------------------------------- plan 81-17, Task 1 (tracer): WR-03

_MASTER = "AUTONOMOUS_REMEDIATION_DRY_RUN"


@pytest.mark.parametrize("value,expected", [
    (None, True), ("", True), ("true", True), ("TRUE", True), ("true ", True), ("1", True),
    ("yes", True), ("on", True), ("y", True), ("enabled", True), ("garbage", True),
    ("false", False), (" FALSE ", False), ("0", False), ("no", False), ("off", False), ("Off", False),
])
def test_master_shadow_is_off_only_for_an_explicit_off_word(monkeypatch, value, expected):
    """protects=GATE-09 (WR-03) / D-02: only 0, false, no, off (stripped, any case) turn the
    deployment shadow master off; unset, empty and every unrecognised value keep shadow on."""
    if value is None:
        monkeypatch.delenv(_MASTER, raising=False)
    else:
        monkeypatch.setenv(_MASTER, value)
    assert settings.master_shadow() is expected


async def test_unrecognised_master_value_records_a_shadow_row_end_to_end(mongo_db, monkeypatch):
    """protects=GATE-09 / T-81-62: tenant flag off, variable 'enabled' -> gate.decide (no
    override) records shadow with deployment as the source and writes no instruction; with
    'false' the same request is dispatching."""
    await ledger.ensure_indexes(mongo_db)
    await seed_tenant(mongo_db, "t1", shadow=False)
    await seed_agent(mongo_db, "t1", "a1", hostname="h1", ip="10.1.1.5")

    monkeypatch.setenv(_MASTER, "enabled")
    d = await gate.decide(mongo_db, _block_ip("t1"))
    assert (d.outcome, d.state) == ("allow_auto", "shadow") and d.recorded
    row = await ledger.get(mongo_db, "t1", d.action_id)
    assert {"check": "shadow", "result": "shadow", "code": "deployment"} in row["trace"]
    assert await mongo_db.agent_instructions.count_documents({}) == 0

    monkeypatch.setenv(_MASTER, "false")
    live = await gate.decide(mongo_db, _block_ip("t1", ip="203.0.113.9"))
    assert (live.outcome, live.state) == ("allow_auto", "dispatching")

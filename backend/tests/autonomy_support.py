"""Shared fixtures for the Autonomous Ops tests (Phase 81).

Real-database helpers (use with ``tests._mongo_test_db.mongo_db``): ``seed_tenant``,
``seed_agent``, ``seed_platform_stop``. For older MagicMock-database tests that must keep
exercising their own logic once the gate sits in front of it: ``FakeLedger`` (an in-memory
stand-in for the ledger functions) and ``permissive_gate`` (patches the gate and its stop
reads so a request decides the way the test asks, with nothing written to a database).

Plans 81-04 to 81-09 import this module and must not modify it; only 81-08 and 81-15 may extend
it (81-08 added ``agent_that_completes``: a stand-in agent for the remediation tests; 81-15 made
``permissive_gate`` record the decided steps/rollback and stub the never-touch read, because
``gate.execute`` now binds every dispatch to the decided row).
"""
import uuid
from contextlib import ExitStack
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

from autonomous_ops import PLATFORM_TENANT_ID, SCREEN_PERMISSION, TERMINAL_STATES


async def seed_tenant(db, tenant_id, *, level="undoable_auto", max_level="undoable_auto", shadow=True,
                      ticked=True, stop=None, name=None):
    """A tenant document (with the Autonomous Ops screen ticked or not) and its settings."""
    features = ["view:overview"] + ([SCREEN_PERMISSION] if ticked else [])
    await db.tenants.replace_one({"id": tenant_id},
                                 {"id": tenant_id, "name": name or tenant_id.upper(), "enabledFeatures": features},
                                 upsert=True)
    await db.autonomy_settings.replace_one(
        {"tenantId": tenant_id},
        {"tenantId": tenant_id, "level": level, "maxLevel": max_level, "shadow": shadow, "stop": stop,
         "breaker": None, "updatedAt": datetime.now(timezone.utc), "updatedBy": "test"},
        upsert=True)


async def seed_agent(db, tenant_id, agent_id, *, hostname=None, ip=None):
    """An enrolled agent of ``tenant_id``."""
    await db.agents.replace_one(
        {"id": agent_id},
        {"id": agent_id, "tenantId": tenant_id, "hostname": hostname or f"host-{agent_id}",
         "ipAddress": ip or "10.9.9.9", "status": "Online"}, upsert=True)


async def seed_platform_stop(db, active=True, by="Super Admin"):
    """The platform-wide stop document (system_settings, type autonomous_ops)."""
    stop = {"active": active, "scope": "platform", "pressedBy": {"username": by, "display": by},
            "pressedByTier": "platform", "pressedAt": datetime.now(timezone.utc), "reason": None}
    await db.system_settings.update_one({"type": "autonomous_ops"}, {"$set": {"type": "autonomous_ops", "stop": stop}},
                                        upsert=True)


class FakeLedger:
    """In-memory stand-in for the ledger functions, keyed by row id."""

    def __init__(self):
        self.rows = {}

    async def create_intent(self, db, row):
        doc = dict(row)
        doc.setdefault("id", "AO-" + uuid.uuid4().hex)
        now = datetime.now(timezone.utc)
        doc.setdefault("createdAt", now)
        doc.setdefault("updatedAt", now)
        self.rows[doc["id"]] = doc
        return dict(doc)

    async def transition(self, db, tenant_id, action_id, from_states, to_state, *, actor=None, where=None, **fields):
        row = self.rows.get(action_id)
        if row is None or row.get("tenantId") != tenant_id or row.get("state") not in tuple(from_states):
            return None
        row.update({"state": to_state, "updatedAt": datetime.now(timezone.utc), **fields})
        if to_state in TERMINAL_STATES:
            row.setdefault("finishedAt", row["updatedAt"])
        return dict(row)

    async def get(self, db, tenant_id, action_id):
        row = self.rows.get(action_id)
        return dict(row) if row and row.get("tenantId") == tenant_id else None

    async def record_control(self, db, tenant_id, event, *, scope, actor, reason):
        return await self.create_intent(db, {"tenantId": tenant_id, "kind": "control", "state": "recorded",
                                             "scope": scope, "controlEvent": event, "actor": actor,
                                             "reasonText": reason})


def permissive_gate(outcome="allow_auto", shadow=False):
    """Patch the gate so every request decides as ``outcome`` (state ``shadow`` when
    ``shadow``), record the row in a ``FakeLedger`` (returned as ``.ledger`` on the stack), and
    report no stop and a ticked tenant. Returns an entered ``ExitStack``: use it as
    ``with permissive_gate(...) as stack:`` or call ``stack.close()`` to undo the patches."""
    from autonomous_ops import dispatch_check, gate, protected, settings
    fake = FakeLedger()
    states = {"allow_auto": "dispatching", "needs_approval": "awaiting_approval", "suggest": "suggested"}

    async def decide(db, req, **kwargs):
        state = "shadow" if shadow else states.get(outcome, "refused")
        row = await fake.create_intent(db, {
            "tenantId": req.tenant_id, "kind": req.kind, "origin": req.origin, "actions": list(req.actions),
            "command": req.actions[0] if req.actions else None, "targets": list(req.targets), "params": req.params,
            "state": state, "shadow": shadow, "wouldHave": outcome if shadow else None, "dedupeKey": req.dedupe_key,
            "autoDispatched": state == "dispatching", "instructionIds": [],
            "steps": dispatch_check.plan_of(dispatch_check.request_steps(req)),
            "rollback": dispatch_check.plan_of(dispatch_check.request_rollback(req))})
        return gate.Decision(outcome=outcome, state=state, reason="test", action_id=row["id"], shadow=shadow,
                             would_have=outcome if shadow else None, trace=[], recorded=True)

    async def load(db, tenant_id):
        return settings.TenantSettings(tenant_id=tenant_id, eligible=tenant_id != PLATFORM_TENANT_ID)

    stack = ExitStack()
    stack.ledger = fake
    stack.enter_context(patch.object(gate, "decide", decide))
    for name in ("create_intent", "transition", "get", "record_control"):
        stack.enter_context(patch.object(gate.ledger, name, getattr(fake, name)))
    stack.enter_context(patch.object(settings, "platform_stop", AsyncMock(return_value=None)))
    stack.enter_context(patch.object(settings, "load", load))
    # A MagicMock database cannot serve the never-touch list; the real check is proven against a
    # real database in test_autonomous_ops_dispatch_binding.py.
    stack.enter_context(patch.object(protected, "check", AsyncMock(return_value=None)))
    return stack


def agent_that_completes(verdict="Clean"):
    """Patch ``AutonomousRemediationService._poll_task_status`` so the "agent" completes every
    instruction the moment it is polled: the instruction's status becomes SUCCESS and, for a
    scan_* probe, a fresh security_scan_results row with ``verdict`` appears (what a real agent
    reports). Reads and writes the real (throwaway) database the instruction was written to,
    so nothing here reaches a live system. Use as a context manager."""
    from unittest.mock import patch
    from autonomous_ops.scope import raw
    from autonomous_remediation_service import AutonomousRemediationService

    async def poll(self, db, task_id, timeout_sec, interval_sec, tenant_id=None):
        handle = raw(db)
        doc = await handle.agent_instructions.find_one({"id": task_id})
        await handle.agent_instructions.update_one({"id": task_id}, {"$set": {"status": "SUCCESS"}})
        if doc and str(doc.get("type", "")).startswith("scan_"):
            params = doc.get("payload") or {}
            await handle.security_scan_results.insert_one({
                "tenantId": doc.get("tenantId"), "target": params.get("path") or params.get("target"),
                "verdict": verdict, "created_at": (datetime.now(timezone.utc) + timedelta(seconds=5)).isoformat()})
        return "SUCCESS"

    return patch.object(AutonomousRemediationService, "_poll_task_status", poll)

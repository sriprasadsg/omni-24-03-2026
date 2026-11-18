"""AI triage of SOC alerts (soc_triage): what is sent to the local model, what is kept from its answer.

Each test states its card: protects=<observable>; fails_when=<wrong result it rejects>;
no_claim=<what green does not prove>. Real MongoDB via tests/_mongo_test_db.py; the model is replaced.
"""
import asyncio
import json
import os
import sys
from datetime import datetime, timezone

import pytest
import pytest_asyncio

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import database
import soc_service
import soc_triage
from tenant_context import reset_tenant_id, set_tenant_id
from tests._mongo_test_db import mongo_db  # noqa: F401  (fixture)

ANSWER = json.dumps({"summary": "A YARA rule matched a build artifact.", "likely_cause": "Developer build output.",
                     "seriousness": "LOW", "why": ["Path is a cargo target folder."],
                     "next_steps": ["close_false_positive", "rm -rf /", "investigate", "close_false_positive"]})


def _alert(**kw):
    doc = {"id": "al1", "tenantId": "t1", "agent_id": "ag1", "type": "runtime_security", "severity": "critical",
           "title": "YARA match on bob@corp.test", "status": "open", "created_at": datetime.now(timezone.utc).isoformat(),
           "description": "Executable '/home/bob/proj/target/debug/omni' and 'C:\\Users\\Alice Smith\\x.exe' matched (MITRE: T1003.001)"}
    doc.update(kw)
    return doc


def test_prompt_keeps_the_facts_and_drops_user_names():
    """protects=the model gets type, severity, details and techniques but no user names or e-mail addresses;
    fails_when=personal data leaves the alert; no_claim=the guardrail's own patterns"""
    prompt = soc_triage.prompt_for(soc_service.view(_alert()), "Linux")
    assert "Runtime threat" in prompt and "critical" in prompt and "T1003.001 LSASS Memory" in prompt and "Linux" in prompt
    assert "bob" not in prompt and "Alice" not in prompt and "corp.test" not in prompt
    assert "/home/<user>/proj" in prompt and "C:\\Users\\<user>\\x.exe" in prompt


def test_parse_keeps_only_known_steps_and_values():
    """protects=only the console's own step ids survive, once each, and seriousness is one of four words;
    fails_when=model text becomes a step (or a command); no_claim=-"""
    out = soc_triage.parse("Sure! " + ANSWER)
    assert out["nextSteps"] == ["close_false_positive", "investigate"]
    assert out["seriousness"] == "low" and out["why"] == "Path is a cargo target folder."
    with pytest.raises(soc_triage.TriageError):
        soc_triage.parse("no json here")
    assert soc_triage.parse(json.dumps({"summary": "Something happened here.", "seriousness": "apocalyptic"}))["seriousness"] is None


@pytest_asyncio.fixture
async def db(mongo_db, monkeypatch):  # noqa: F811
    monkeypatch.setattr(database.mongodb, "db", mongo_db)
    token = set_tenant_id("t1")
    try:
        yield mongo_db
    finally:
        reset_tenant_id(token)


@pytest.mark.asyncio
async def test_triage_is_stored_on_the_alert_and_stays_in_scope(db, monkeypatch):
    """protects=the answer is stored as aiTriage with the model and who asked; another tenant's alert is
    not found; an unreachable model says so; fails_when=triage leaks across tenants or fails silently;
    no_claim=the model's judgement"""
    sent = []

    async def fake(prompt):
        sent.append(prompt)
        return ANSWER
    monkeypatch.setattr(soc_triage, "_generate", fake)
    await db.security_alerts.insert_many([_alert(), _alert(id="other", tenantId="t2")])
    out = await soc_triage.triage("t1", "al1", "ana@t1.test")
    stored = (await db.security_alerts.find_one({"id": "al1"}))["aiTriage"]
    assert stored == out and out["by"] == "ana@t1.test" and out["model"] == soc_triage.MODEL and len(sent) == 1
    assert soc_service.view(await db.security_alerts.find_one({"id": "al1"}))["aiTriage"]["summary"].startswith("A YARA")
    with pytest.raises(soc_triage.TriageError) as other:
        await soc_triage.triage("t1", "other", "ana@t1.test")
    assert other.value.status == 404

    async def down(prompt):
        raise soc_triage.httpx.ConnectError("refused")
    monkeypatch.setattr(soc_triage, "_generate", down)
    with pytest.raises(soc_triage.TriageError) as unavailable:
        await soc_triage.triage("t1", "al1", "ana@t1.test")
    assert unavailable.value.status == 503


@pytest.mark.asyncio
async def test_only_new_critical_alerts_are_triaged_automatically(db, monkeypatch):
    """protects=a new critical alert is triaged in the background, a high one is not, and the switch turns
    it off; fails_when=every alert queues a 25-second model call; no_claim=-"""
    calls = []

    async def fake(scope, alert_id, who):
        calls.append((scope, alert_id, who))
    monkeypatch.setattr(soc_triage, "triage", fake)
    soc_triage.schedule_auto({"id": "c1", "tenantId": "t1", "severity": "critical"})
    soc_triage.schedule_auto({"id": "h1", "tenantId": "t1", "severity": "high"})
    monkeypatch.setenv("SOC_AUTO_TRIAGE", "0")
    soc_triage.schedule_auto({"id": "c2", "tenantId": "t1", "severity": "critical"})
    await asyncio.sleep(0.05)
    assert calls == [("t1", "c1", "automatic (critical alert)")]

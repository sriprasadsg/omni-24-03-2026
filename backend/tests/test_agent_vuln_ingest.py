"""
Tests for Phase 51 Plan 03 (VULN-01/03) — `agent_vuln_ingest_service`:
extract the agent's vuln-capability findings from the heartbeat payload and
upsert them (tenant-scoped, deduped, enriched) into the `vulnerabilities`
collection the dashboard reads.

Hermetic — a tiny in-memory fake collection with upsert semantics stands in for
Mongo (no real DB, no network). Covers: (a) a new CVE finding is upserted with
the VULN-03 fields + tenant/agent + first_seen/last_seen; (b) re-ingesting the
same (agentId, cve_id, affected_path) updates last_seen without duplicating;
(c) findings are tenant-scoped; (d) an ingest error is swallowed by the
non-blocking heartbeat wrapper (the heartbeat never fails on a vuln error).
"""
import os
import sys

import pytest

_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

import agent_vuln_ingest_service


class _FakeColl:
    def __init__(self):
        self.docs = []

    async def update_one(self, flt, update, upsert=False):
        for d in self.docs:
            if all(d.get(k) == v for k, v in flt.items()):
                d.update(update.get("$set", {}))
                return
        if upsert:
            doc = dict(flt)
            doc.update(update.get("$setOnInsert", {}))
            doc.update(update.get("$set", {}))
            self.docs.append(doc)


class _FakeDB:
    def __init__(self):
        self.vulnerabilities = _FakeColl()


def _cve_finding():
    return {
        "type": "cve",
        "cve_id": "CVE-2022-0778",
        "cvss": 7.5,
        "severity": "HIGH",
        "affected_path": "OpenSSL",
        "remediation_hint": "Upgrade OpenSSL to >=1.1.1n",
        "playbook_ref": "patch_package",
        "detail": "OpenSSL 1.0.1",
    }


@pytest.mark.asyncio
async def test_new_cve_finding_upserted_with_fields():
    db = _FakeDB()
    await agent_vuln_ingest_service.ingest_findings(db, "tenant-a", "agent-1", [_cve_finding()])
    assert len(db.vulnerabilities.docs) == 1
    doc = db.vulnerabilities.docs[0]
    assert doc["tenantId"] == "tenant-a"
    assert doc["agentId"] == "agent-1"
    assert doc["cve_id"] == "CVE-2022-0778"
    assert doc["cvss"] == 7.5
    assert doc["affected_path"] == "OpenSSL"
    assert doc["remediation_hint"] == "Upgrade OpenSSL to >=1.1.1n"
    assert doc["playbook_ref"] == "patch_package"
    assert doc["severity"] == "High"  # normalized title-case for the dashboard
    assert doc["cveId"] == "CVE-2022-0778"  # UI alias
    assert "first_seen" in doc and "last_seen" in doc


@pytest.mark.asyncio
async def test_reingest_dedups_and_updates_last_seen():
    db = _FakeDB()
    await agent_vuln_ingest_service.ingest_findings(db, "tenant-a", "agent-1", [_cve_finding()])
    first_seen = db.vulnerabilities.docs[0]["first_seen"]
    db.vulnerabilities.docs[0]["last_seen"] = "OLD"
    await agent_vuln_ingest_service.ingest_findings(db, "tenant-a", "agent-1", [_cve_finding()])
    assert len(db.vulnerabilities.docs) == 1  # no duplicate
    assert db.vulnerabilities.docs[0]["first_seen"] == first_seen  # setOnInsert not re-applied
    assert db.vulnerabilities.docs[0]["last_seen"] != "OLD"  # last_seen refreshed


@pytest.mark.asyncio
async def test_findings_are_tenant_scoped():
    db = _FakeDB()
    await agent_vuln_ingest_service.ingest_findings(db, "tenant-a", "agent-1", [_cve_finding()])
    await agent_vuln_ingest_service.ingest_findings(db, "tenant-b", "agent-1", [_cve_finding()])
    tenants = {d["tenantId"] for d in db.vulnerabilities.docs}
    assert tenants == {"tenant-a", "tenant-b"}
    assert len(db.vulnerabilities.docs) == 2  # same finding, different tenant → not merged


@pytest.mark.asyncio
async def test_two_misconfigs_same_path_not_collapsed():
    db = _FakeDB()
    findings = [
        {"type": "misconfig", "cve_id": None, "severity": "HIGH",
         "affected_path": "/etc/ssh/sshd_config", "remediation_hint": "h",
         "playbook_ref": "harden_ssh", "detail": "root login"},
        {"type": "misconfig", "cve_id": None, "severity": "MEDIUM",
         "affected_path": "/etc/ssh/sshd_config", "remediation_hint": "h",
         "playbook_ref": "harden_ssh", "detail": "weak ciphers"},
    ]
    await agent_vuln_ingest_service.ingest_findings(db, "tenant-a", "agent-1", findings)
    assert len(db.vulnerabilities.docs) == 2  # distinct detail → distinct docs


@pytest.mark.asyncio
async def test_heartbeat_wrapper_swallows_errors(monkeypatch):
    async def _boom(*a, **k):
        raise RuntimeError("db down")

    monkeypatch.setattr(agent_vuln_ingest_service, "ingest_findings", _boom)
    payload = {"meta": {"vulnerability_scanning": {"vulnerabilities": [_cve_finding()]}}}
    # Must NOT raise — the heartbeat is never failed by a vuln-ingest error.
    await agent_vuln_ingest_service.ingest_from_heartbeat(_FakeDB(), "tenant-a", "agent-1", payload)


@pytest.mark.asyncio
async def test_wrapper_extracts_from_confirmed_payload_path():
    db = _FakeDB()
    payload = {"meta": {"vulnerability_scanning": {"vulnerabilities": [_cve_finding()]}}}
    await agent_vuln_ingest_service.ingest_from_heartbeat(db, "tenant-a", "agent-1", payload)
    assert len(db.vulnerabilities.docs) == 1
    # Missing/empty path degrades to a no-op, never an error.
    await agent_vuln_ingest_service.ingest_from_heartbeat(db, "tenant-a", "agent-1", {"meta": {}})
    assert len(db.vulnerabilities.docs) == 1

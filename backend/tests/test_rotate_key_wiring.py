import pytest
import os
import sys

# Bootstrap sys.path to backend
_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

from remediation_playbook_service import load_default_playbooks, select_playbook
from autonomous_remediation_service import _render_step_params, RemediationFinding
from agent_vuln_ingest_service import ingest_findings

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

@pytest.mark.asyncio
async def test_rotate_key_wiring():
    db = _FakeDB()
    finding_dict = {
        "type": "misconfig",
        "cve_id": None,
        "severity": "HIGH",
        "affected_path": "/home/user/.ssh/authorized_keys",
        "fingerprint": "SHA256:1234567890abcdef",
        "remediation_hint": "Rotate weak key",
        "playbook_ref": "rotate_key",
        "detail": "Weak RSA key"
    }

    # Task 1: Ingest finding
    await ingest_findings(db, "tenant-a", "agent-1", [finding_dict])
    assert len(db.vulnerabilities.docs) == 1
    doc = db.vulnerabilities.docs[0]
    assert doc.get("fingerprint") == "SHA256:1234567890abcdef"

    # Task 2: Build RemediationFinding
    finding = RemediationFinding(
        finding_id=doc["id"] if "id" in doc else "1",
        finding_type="vuln",
        severity="high",
        tenant_id="tenant-a",
        agent_id="agent-1",
        resource_id=None,
        details=doc
    )

    # Task 3: Test select_playbook()
    playbooks = load_default_playbooks()
    playbook = select_playbook(finding, playbooks)
    assert playbook is not None
    assert playbook["name"] == "rotate_key"

    # Task 4: Test _render_step_params
    params = playbook["steps"][0]["params"]
    rendered = _render_step_params(params, finding)
    assert rendered["fingerprint"] == "SHA256:1234567890abcdef"
    assert rendered["authorized_keys_path"] == "/home/user/.ssh/authorized_keys"

    # Task 5: Test rollback params
    rollback_params = playbook["rollback"][0]["params"]
    rendered_rollback = _render_step_params(rollback_params, finding)
    assert rendered_rollback["authorized_keys_path"] == "/home/user/.ssh/authorized_keys"

    # Task 6 (plan 64-04): rollback step dispatches to the arm that actually
    # exists — action: rotate_key_rollback with only authorized_keys_path,
    # never the old restore_file/backup_path shape that could never resolve.
    rollback_step = playbook["rollback"][0]
    assert rollback_step["action"] == "rotate_key_rollback"
    assert set(rollback_step["params"].keys()) == {"authorized_keys_path"}

"""
Rust heartbeat evidence parity tests (RUST-01, RUST-02, RUST-03).
Unit tests mock the DB; live mode: python3 backend/tests/test_rust_heartbeat_parity.py
"""
import os, sys, time, traceback

BASE_URL = os.environ.get("BACKEND_URL", "http://localhost:5000")
MONGO_URI = os.environ.get("MONGODB_URI") or os.environ.get("MONGO_URI", "mongodb://localhost:27017")
DB_NAME = os.environ.get("MONGO_DB_NAME", "omni_platform")
TEST_AGENT_ID = "TEST-RUST-PARITY-001"
TEST_HOSTNAME = "test-rust-parity-host"
TEST_ASSET_ID = f"asset-{TEST_HOSTNAME}"

# ---------------------------------------------------------------------------
# Payload — all 12 Rust compliance check names
# ---------------------------------------------------------------------------
_CHECKS = [
    ("Windows Firewall Profiles",       "Pass",    "All profiles enabled"),
    ("Windows Defender Antivirus",      "Pass",    "Enabled and updated"),
    ("BitLocker Encryption",            "Warning", "Not enabled on C:"),
    ("User Access Control",             "Pass",    "UAC enabled"),
    ("Remote Desktop Service",          "Pass",    "RDP disabled"),
    ("SMBv1 Protocol Disabled",         "Pass",    "SMBv1 disabled"),
    ("Password Policy (Min Length)",    "Pass",    "MinLen:10"),
    ("Audit Logging Policy",            "Pass",    "Audit policies configured"),
    ("Windows Update Service",          "Pass",    "wuauserv Running"),
    ("PowerShell Script Block Logging", "Warning", "Not configured"),
    ("WinRM Status",                    "Pass",    "WinRM not running (expected)"),
    ("Secure Boot",                     "Pass",    "Secure Boot enabled"),
]
RUST_HEARTBEAT_PAYLOAD = {
    "status": "Online", "platform": "Windows",
    "version": "2.0.0-rust", "hostname": TEST_HOSTNAME,
    "meta": {
        "agent_type": "rust",
        "compliance_enforcement": {
            "compliance_checks": [
                {"check": c, "status": s, "details": d} for c, s, d in _CHECKS
            ]
        },
    },
}
# Representative check→control mappings for RUST-03 verification
CHECK_TO_CONTROL = {
    "Windows Firewall Profiles":       "A.8.22",
    "Windows Defender Antivirus":      "A.8.7",
    "BitLocker Encryption":            "A.8.1",
    "User Access Control":             "A.5.15",
    "Password Policy (Min Length)":    "CC6.1",
    "Audit Logging Policy":            "CC9.2",
    "Windows Update Service":          "CC7.3",
    "PowerShell Script Block Logging": "DE.CM-1",
    "Secure Boot":                     "CC7.2",
}

# ---------------------------------------------------------------------------
# Shared mock-DB factory
# ---------------------------------------------------------------------------
def _mock_db():
    from unittest.mock import AsyncMock, MagicMock
    col = MagicMock()
    col.update_one = AsyncMock()
    col.find_one = AsyncMock(return_value=None)
    db = MagicMock()
    db.asset_compliance = col
    db.assets = MagicMock()
    db.assets.find_one = AsyncMock(return_value=None)
    db.agents = MagicMock()
    db.agents.find_one = AsyncMock(return_value=None)
    return db


def _run_processor(db):
    """Run process_automated_evidence with the Rust payload against db."""
    import asyncio
    from unittest.mock import patch
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
    from compliance_evidence_processor import process_automated_evidence
    with patch("compliance_evidence_processor.set_tenant_id"), \
         patch("compliance_evidence_processor.get_tenant_id", return_value=None):
        compliance_data = RUST_HEARTBEAT_PAYLOAD["meta"]["compliance_enforcement"]
        asyncio.run(process_automated_evidence(TEST_HOSTNAME, compliance_data, db, agent_type="rust"))

# ---------------------------------------------------------------------------
# pytest unit tests
# ---------------------------------------------------------------------------

def test_rust01_processor_is_importable():
    """RUST-01: process_automated_evidence importable from compliance_evidence_processor."""
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
    from compliance_evidence_processor import process_automated_evidence
    assert callable(process_automated_evidence)


def test_rust02_and_rust03_db_calls():
    """RUST-02 + RUST-03: agent_type=rust in $set AND $push evidence; all 9 control IDs written."""
    db = _mock_db()
    _run_processor(db)

    assert db.asset_compliance.update_one.call_count > 0, "update_one not called"

    filters_seen = set()
    for c in db.asset_compliance.update_one.call_args_list:
        args, _ = c
        if not args:
            continue
        # RUST-02a: every $set must carry agent_type=rust
        if len(args) >= 2 and "$set" in args[1]:
            assert args[1]["$set"].get("agent_type") == "rust", (
                f"$set missing agent_type=rust: {args[1]['$set']}"
            )
        # RUST-02b: every $push evidence record must also carry agent_type=rust
        if len(args) >= 2 and "$push" in args[1]:
            pushed_ev = args[1]["$push"].get("evidence", {})
            assert pushed_ev.get("agent_type") == "rust", (
                f"$push.evidence missing agent_type=rust: {pushed_ev}"
            )
        # Collect control IDs for RUST-03
        if isinstance(args[0], dict) and "controlId" in args[0]:
            filters_seen.add(args[0]["controlId"])

    print("[RUST-02] agent_type=rust in all $set and $push.evidence calls: PASS")

    missing = [ctrl for ctrl in CHECK_TO_CONTROL.values() if ctrl not in filters_seen]
    assert not missing, f"[RUST-03] Missing control IDs: {missing}"
    print("[RUST-03] All 9 representative control IDs present: PASS")

def test_rust04_instruction_result_compliance_nesting():
    """RUST-04: report_instruction_result:
    (a) processes compliance_checks nested inside result.result (Rust agent format),
    (b) also accepts flat top-level compliance_checks (Python agent format),
    (c) resolves the actual Windows hostname via agent doc lookup (UUID URL → hostname).
    """
    import sys
    import os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

    from unittest.mock import AsyncMock, MagicMock, patch
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    import agent_tasks_endpoints as mod

    received: list = []  # (hostname, payload, fallback_tenant_id)

    async def _fake_process_evidence(hostname, payload, db, fallback_tenant_id=None, **kw):
        received.append({"hostname": hostname, "payload": payload, "tid": fallback_tenant_id})

    # Agent doc: UUID id but "DESKTOP-WIN" hostname (simulates real Rust agent registration)
    AGENT_UUID = "agent-uuid-001"
    WIN_HOSTNAME = "DESKTOP-WIN"
    agent_doc = {"id": AGENT_UUID, "hostname": WIN_HOSTNAME, "tenantId": "t1"}

    db = MagicMock()
    db.agent_instructions = MagicMock()
    db.agent_instructions.update_one = AsyncMock()
    db.agents = MagicMock()
    db.agents.find_one = AsyncMock(return_value=agent_doc)
    db.compliance_remediation_tasks = MagicMock()
    db.compliance_remediation_tasks.find = MagicMock()
    db.compliance_remediation_tasks.find.return_value.to_list = AsyncMock(return_value=[])

    tenant = {"id": "t1"}
    app = FastAPI()
    app.include_router(mod.router)
    app.dependency_overrides[mod.verify_agent_key] = lambda: tenant

    # (a) Rust agent nested format — URL param is UUID, hostname resolved from DB
    nested_body = {
        "instruction_id": "i1",
        "task_id": "tid1",
        "type": "run_compliance_check",
        "status": "success",
        "result": {
            "compliance_checks": [
                {"check": "Windows Firewall Profiles", "status": "Pass", "details": "OK"}
            ]
        },
    }

    with patch("agent_tasks_endpoints.get_database", return_value=db), \
         patch("compliance_endpoints.process_automated_evidence", side_effect=_fake_process_evidence):
        with TestClient(app) as client:
            resp = client.post(f"/api/agents/{AGENT_UUID}/instructions/result", json=nested_body)

    assert resp.status_code == 200
    assert len(received) == 1, "process_automated_evidence must be called (nested format)"
    assert received[0]["hostname"] == WIN_HOSTNAME, (
        f"Must use Windows hostname '{WIN_HOSTNAME}', not agent UUID. Got: {received[0]['hostname']}"
    )
    assert "compliance_checks" in received[0]["payload"]
    assert received[0]["tid"] == "t1", "fallback_tenant_id must be populated from _tenant"

    # (b) Flat top-level format — agent doc returns None (hostname same as URL param)
    received.clear()
    db.agents.find_one = AsyncMock(return_value=None)
    flat_body = {
        "instruction_id": "i2",
        "task_id": "tid2",
        "type": "run_compliance_check",
        "status": "success",
        "compliance_checks": [
            {"check": "BitLocker Encryption", "status": "Warning", "details": "Off"}
        ],
    }
    with patch("agent_tasks_endpoints.get_database", return_value=db), \
         patch("compliance_endpoints.process_automated_evidence", side_effect=_fake_process_evidence):
        with TestClient(app) as client:
            resp = client.post("/api/agents/test-host/instructions/result", json=flat_body)

    assert resp.status_code == 200
    assert len(received) == 1, "process_automated_evidence must be called (flat format)"
    assert received[0]["hostname"] == "test-host", "fallback to URL param when agent not in DB"
    assert "compliance_checks" in received[0]["payload"]


# ---------------------------------------------------------------------------
# Live-backend mode
# ---------------------------------------------------------------------------
def _cleanup(db):
    db.asset_compliance.delete_many({"assetId": TEST_ASSET_ID})
    db.agents.delete_many({"id": TEST_AGENT_ID})
    db.assets.delete_many({"id": TEST_ASSET_ID})


def main():
    import requests
    import pymongo

    client = pymongo.MongoClient(MONGO_URI)
    db = client[DB_NAME]
    _cleanup(db)

    # Register agent (409 = already exists)
    resp = requests.post(
        f"{BASE_URL}/api/agents/register",
        json={"agent_id": TEST_AGENT_ID, "hostname": TEST_HOSTNAME,
              "platform": "Windows", "version": "2.0.0-rust",
              "agent_type": "rust", "tenantId": "test-tenant"},
        timeout=10,
    )
    if resp.status_code not in (200, 201, 409):
        raise RuntimeError(f"Registration failed: {resp.status_code} {resp.text}")
    token = resp.json().get("api_key") or (
        db.agents.find_one({"id": TEST_AGENT_ID}) or {}
    ).get("api_key")
    if not token:
        raise RuntimeError("Could not obtain agent token")

    hb = requests.post(
        f"{BASE_URL}/api/agents/{TEST_AGENT_ID}/heartbeat",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json=RUST_HEARTBEAT_PAYLOAD, timeout=10,
    )
    assert hb.status_code == 200, f"Heartbeat failed: {hb.status_code} {hb.text}"
    assert hb.json().get("success") is True
    print(f"[RUST-01] Heartbeat POST returned {hb.status_code}: PASS")

    deadline = time.monotonic() + 10
    records = []
    while time.monotonic() < deadline:
        records = list(db.asset_compliance.find({"assetId": TEST_ASSET_ID}))
        if records:
            break
        time.sleep(0.25)
    assert records, "No asset_compliance records found within 10 seconds"
    for doc in records:
        assert doc.get("agent_type") == "rust", f"Missing doc-level agent_type: {doc.get('controlId')}"
        assert any(e.get("agent_type") == "rust" for e in doc.get("evidence", [])), (
            f"No evidence entry with agent_type=rust: {doc.get('controlId')}"
        )
    print(f"[RUST-02] agent_type: rust present in all {len(records)} records: PASS")

    for check_name, ctrl in CHECK_TO_CONTROL.items():
        rec = db.asset_compliance.find_one({"assetId": TEST_ASSET_ID, "controlId": ctrl})
        print(f"  {ctrl} ({check_name}): {'FOUND' if rec else 'MISSING'}")
        assert rec is not None, f"Missing mapping: {check_name} -> {ctrl}"
    print("[RUST-03] All representative control mappings present: PASS")

    print("=== RUST AGENT EVIDENCE PARITY: ALL CHECKS PASSED ===")
    print("RUST-01: heartbeat endpoint accepted payload and called process_automated_evidence")
    print("RUST-02: agent_type=rust preserved in asset_compliance documents and evidence records")
    print("RUST-03: all 9 verified control IDs found in asset_compliance")
    _cleanup(db)


if __name__ == "__main__":
    try:
        main()
        sys.exit(0)
    except Exception:
        traceback.print_exc()
        sys.exit(1)

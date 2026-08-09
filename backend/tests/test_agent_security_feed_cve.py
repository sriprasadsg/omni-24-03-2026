"""Phase 51 Plan 01 (VULN-02) — cve_feed table in the signed bundle."""
import os
import sqlite3
import sys
import tempfile

import pytest

_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)


@pytest.fixture()
def svc(monkeypatch, tmp_path):
    monkeypatch.setenv("AGENT_FEED_SIGNING_KEY_PATH", str(tmp_path / "k.key"))
    import importlib
    import agent_security_feed_service as s
    importlib.reload(s)
    return s


def _tables_and_rows(data):
    with tempfile.NamedTemporaryFile(suffix=".db") as f:
        f.write(data); f.flush()
        con = sqlite3.connect(f.name)
        tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        cve = list(con.execute("SELECT package, version_range, cve_id, cvss, severity, remediation_hint, playbook_ref FROM cve_feed"))
        con.close()
    return tables, cve


def test_cve_feed_present_and_seeded(svc):
    tables, cve = _tables_and_rows(svc.build_bundle())
    # cve_feed + all Phase-50 tables intact
    assert {"cve_feed", "hash_sigs", "yara_rules", "url_feed", "ip_feed", "manifest"} <= tables
    assert len(cve) >= 14
    cves = {r[2] for r in cve}
    assert "CVE-2021-44228" in cves  # log4j
    assert "CVE-2022-0778" in cves   # openssl
    # every row has the required enrichment
    for pkg, vr, cid, cvss, sev, hint, pb in cve:
        assert pkg and vr and cid and sev and hint and pb
        assert isinstance(cvss, (int, float))


def test_bundle_still_signs(svc):
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    data = svc.build_bundle()
    Ed25519PublicKey.from_public_bytes(svc.get_public_key()).verify(svc.sign_bundle(data), data)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

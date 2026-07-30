"""
Tests for Phase 50 Plan 01 (Native Security Scanning, NSCAN-02/03) —
agent_security_feed_service: build + ed25519-sign a SQLite feed bundle
(hash_sigs/yara_rules/url_feed/ip_feed/manifest incl. EICAR), and
agent_security_feed_endpoints: GET /api/agents/security/feed-bundle (versioned).

Hermetic — ephemeral signing key in a tmp path, no real Mongo, no network.
"""
import os
import sqlite3
import sys
import tempfile

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

# EICAR test-file SHA256 (safe standard AV test artifact — not real malware).
EICAR_SHA256 = "275a021bbfb6489e54d471899f7db9d1663fc695ec2fe2a2c4538aabf651fd0f"


@pytest.fixture()
def feed_key(monkeypatch, tmp_path):
    """Point the signing service at an ephemeral key path."""
    key_path = tmp_path / "feed_signing.key"
    monkeypatch.setenv("AGENT_FEED_SIGNING_KEY_PATH", str(key_path))
    import importlib
    import agent_security_feed_service as s
    importlib.reload(s)  # re-read the env-driven key path
    return s


def test_build_bundle_has_tables_and_eicar(feed_key):
    s = feed_key
    data = s.build_bundle()
    assert isinstance(data, (bytes, bytearray)) and len(data) > 0
    with tempfile.NamedTemporaryFile(suffix=".db") as f:
        f.write(data)
        f.flush()
        con = sqlite3.connect(f.name)
        tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert {"hash_sigs", "yara_rules", "url_feed", "ip_feed", "manifest"} <= tables
        hashes = {r[0] for r in con.execute("SELECT sha256 FROM hash_sigs")}
        assert EICAR_SHA256 in hashes
        con.close()


def test_sign_verifies_and_tamper_fails(feed_key):
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    from cryptography.exceptions import InvalidSignature
    s = feed_key
    data = s.build_bundle()
    sig = s.sign_bundle(data)
    pub = Ed25519PublicKey.from_public_bytes(s.get_public_key())
    pub.verify(sig, data)  # valid → no raise
    with pytest.raises(InvalidSignature):
        pub.verify(sig, data + b"x")  # tampered


def test_public_key_is_32_bytes_and_private_not_exposed(feed_key):
    s = feed_key
    assert len(s.get_public_key()) == 32
    # No API returns the private key bytes.
    assert not hasattr(s, "get_private_key")


def test_endpoint_serves_bundle_and_version_noop(feed_key, monkeypatch):
    import agent_security_feed_endpoints as ep
    from agent_auth import verify_agent_key

    app = FastAPI()
    app.include_router(ep.router)
    app.dependency_overrides[verify_agent_key] = lambda: {"tenant_id": "t1"}
    client = TestClient(app)

    r = client.get("/api/agents/security/feed-bundle")
    assert r.status_code == 200
    version = r.headers.get("X-Feed-Version")
    assert version

    # Already-current → no-op (no body re-send).
    r2 = client.get(f"/api/agents/security/feed-bundle?have={version}")
    assert r2.status_code in (200, 304)
    if r2.status_code == 200:
        assert r2.json().get("updated") is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

"""Regression tests for path traversal in update_endpoints.py (2026-08-25 audit).

_resolve_servable_path joined the attacker-controlled {filename} path
parameter straight into BINARY_STORAGE_PATH with no containment check, so
/download/{filename} or /checksum/{filename} could be used to read any file
readable by the backend process (e.g. ../../.env, ../../../etc/passwd).
"""
import sys, os, hashlib
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from fastapi import FastAPI
from starlette.testclient import TestClient
import update_endpoints as ue


def _client():
    app = FastAPI(); app.include_router(ue.router)
    return TestClient(app, raise_server_exceptions=False)


def test_resolve_servable_path_rejects_dotdot_traversal(tmp_path, monkeypatch):
    monkeypatch.setattr(ue, "BINARY_STORAGE_PATH", str(tmp_path))
    secret = tmp_path.parent / "secret.txt"
    secret.write_text("top-secret")

    target_path, _ = ue._resolve_servable_path("../secret.txt")
    assert target_path == ""


def test_resolve_servable_path_rejects_embedded_slash(tmp_path, monkeypatch):
    monkeypatch.setattr(ue, "BINARY_STORAGE_PATH", str(tmp_path))
    target_path, _ = ue._resolve_servable_path("sub/../../secret.txt")
    assert target_path == ""


def test_resolve_servable_path_still_serves_legitimate_file(tmp_path, monkeypatch):
    monkeypatch.setattr(ue, "BINARY_STORAGE_PATH", str(tmp_path))
    content = b"legit-binary"
    (tmp_path / "omni-agent.exe").write_bytes(content)

    target_path, filename = ue._resolve_servable_path("omni-agent.exe")
    assert filename == "omni-agent.exe"
    assert os.path.realpath(target_path) == os.path.realpath(str(tmp_path / "omni-agent.exe"))


def test_download_endpoint_rejects_traversal_via_encoded_slash(tmp_path, monkeypatch):
    monkeypatch.setattr(ue, "BINARY_STORAGE_PATH", str(tmp_path))
    secret = tmp_path.parent / "backend_secret.env"
    secret.write_text("SECRET_KEY=should-not-leak")

    c = _client()
    r = c.get("/api/agent-updates/download/..%2Fbackend_secret.env")
    assert r.status_code in (404, 400)
    assert b"should-not-leak" not in r.content


def test_checksum_endpoint_rejects_traversal_via_encoded_slash(tmp_path, monkeypatch):
    monkeypatch.setattr(ue, "BINARY_STORAGE_PATH", str(tmp_path))
    secret = tmp_path.parent / "backend_secret.env"
    secret.write_text("SECRET_KEY=should-not-leak")
    real_hash = hashlib.sha256(secret.read_bytes()).hexdigest()

    c = _client()
    r = c.get("/api/agent-updates/checksum/..%2Fbackend_secret.env")
    assert r.status_code in (404, 400)
    if r.status_code == 200:
        assert r.json()["sha256"] != real_hash

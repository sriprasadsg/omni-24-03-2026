"""Tests for phase-23 WR-05 — checksum endpoint for agent binaries/scripts.

Verifies /api/agent-updates/checksum/{filename} serves a SHA-256 that matches
the file /api/agent-updates/download/{filename} actually serves, since the two
endpoints must never drift (a checksum computed from a different file than the
one downloaded would defeat the whole point of client-side verification).
"""
import sys, os, hashlib
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from fastapi import FastAPI
from starlette.testclient import TestClient
import update_endpoints as ue


def _client():
    app = FastAPI(); app.include_router(ue.router)
    return TestClient(app, raise_server_exceptions=False)


def test_checksum_matches_actual_binary_content(tmp_path, monkeypatch):
    monkeypatch.setattr(ue, "BINARY_STORAGE_PATH", str(tmp_path))
    content = b"fake-omni-agent-binary-bytes"
    (tmp_path / "omni-agent.exe").write_bytes(content)

    c = _client()
    r = c.get("/api/agent-updates/checksum/omni-agent.exe")
    assert r.status_code == 200
    body = r.json()
    assert body["filename"] == "omni-agent.exe"
    assert body["algorithm"] == "sha256"
    assert body["sha256"] == hashlib.sha256(content).hexdigest()


def test_checksum_matches_versioned_fallback_file(tmp_path, monkeypatch):
    monkeypatch.setattr(ue, "BINARY_STORAGE_PATH", str(tmp_path))
    content = b"versioned-binary-content"
    (tmp_path / "omni-agent-1.2.3-windows.exe").write_bytes(content)

    c = _client()
    r = c.get("/api/agent-updates/checksum/omni-agent.exe")
    assert r.status_code == 200
    body = r.json()
    assert body["filename"] == "omni-agent-1.2.3-windows.exe"
    assert body["sha256"] == hashlib.sha256(content).hexdigest()


def test_checksum_missing_file_returns_404(tmp_path, monkeypatch):
    monkeypatch.setattr(ue, "BINARY_STORAGE_PATH", str(tmp_path))
    c = _client()
    r = c.get("/api/agent-updates/checksum/does-not-exist.bin")
    assert r.status_code == 404


def test_checksum_collect_evidence_script_resolves_canonical_file(monkeypatch, tmp_path):
    canonical = tmp_path / "Collect-Evidence.ps1"
    canonical.write_text("# fake collector script\n")
    monkeypatch.setattr(ue, "AGENT_COLLECT_PS1", str(canonical))

    c = _client()
    r = c.get("/api/agent-updates/checksum/Collect-Evidence.ps1")
    assert r.status_code == 200
    body = r.json()
    assert body["filename"] == "Collect-Evidence.ps1"
    assert body["sha256"] == hashlib.sha256(canonical.read_bytes()).hexdigest()


def test_download_and_checksum_resolve_the_same_file(tmp_path, monkeypatch):
    """The checksum must be computed over exactly what /download would serve."""
    monkeypatch.setattr(ue, "BINARY_STORAGE_PATH", str(tmp_path))
    content = b"content-must-match-between-both-endpoints"
    (tmp_path / "omni-agent.exe").write_bytes(content)

    c = _client()
    dl = c.get("/api/agent-updates/download/omni-agent.exe")
    assert dl.status_code == 200
    assert dl.content == content

    cs = c.get("/api/agent-updates/checksum/omni-agent.exe")
    assert cs.status_code == 200
    assert cs.json()["sha256"] == hashlib.sha256(dl.content).hexdigest()

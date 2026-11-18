"""A server certificate change reaches every agent before the switch, and only the agents that need it.

Value: protects=agents keep connecting across a certificate change (they get the new list over the pinned
connection, test the next certificate, and Platform health shows who is not ready); fails_when=an agent that
already trusts the list is sent it every beat, an agent missing it is not sent it, readiness counts an agent
as ready before it trusts and has tested the next certificate, or installers keep shipping only the old
certificate during a change; no_claim=that a given agent's TLS stack accepts the certificate (the agent's own
probe answers that).
"""
import asyncio
import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import agent_tls_trust as m  # noqa: E402


def _cert(tmp_path, name):
    path = tmp_path / f"{name}.crt"
    subprocess.run(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-keyout", os.devnull, "-out", str(path),
                    "-days", "30", "-subj", f"/CN={name}", "-addext", "subjectAltName=IP:10.0.0.4"],
                   check=True, capture_output=True)
    return path.read_text()


@pytest.fixture
def rollover(tmp_path, monkeypatch):
    old, new = _cert(tmp_path, "old"), _cert(tmp_path, "new")
    trust, state, served = tmp_path / "agent-trust.pem", tmp_path / "rollover.json", tmp_path / "omni.crt"
    served.write_text(old)
    monkeypatch.setattr(m, "TRUST_FILE", trust)
    monkeypatch.setattr(m, "STATE_FILE", state)
    monkeypatch.setattr(m, "SERVED_CERT_FILE", served)
    m._cache.update(key=None, value=None)

    def publish(certs, phase="prepared", probe_port=8443):
        trust.write_text("".join(certs))
        state.write_text(json.dumps({"phase": phase, "next": [m.fingerprint(new)], "probePort": probe_port}))
        st = os.stat(trust)
        os.utime(trust, (st.st_atime, st.st_mtime + 1))  # a new mtime, as a later write would have
        m._cache.update(key=None, value=None)

    yield {"old": old, "new": new, "fp_old": m.fingerprint(old), "fp_new": m.fingerprint(new), "publish": publish}
    m._cache.update(key=None, value=None)


def test_nothing_is_sent_while_no_change_is_published(rollover):
    assert m.current() is None
    assert m.heartbeat_reply({"tls_trust": [rollover["fp_old"]]}) == {}


def test_an_agent_missing_the_list_gets_it_with_the_probe_ask(rollover):
    rollover["publish"]([rollover["old"], rollover["new"]])
    reply = m.heartbeat_reply({"tls_trust": [rollover["fp_old"]]})["serverTrust"]
    assert m.split_pem(reply["certs"]) == m.split_pem(rollover["old"] + rollover["new"])
    assert (reply["next"], reply["probePort"]) == ([rollover["fp_new"]], 8443)


def test_an_agent_that_trusts_the_list_and_tested_the_next_certificate_gets_nothing(rollover):
    rollover["publish"]([rollover["old"], rollover["new"]])
    both = [rollover["fp_old"], rollover["fp_new"]]
    assert "serverTrust" in m.heartbeat_reply({"tls_trust": both}), "it still has to test the next certificate"
    probed = {"fingerprints": [rollover["fp_new"]], "ok": False, "error": "could not connect"}
    assert m.heartbeat_reply({"tls_trust": list(reversed(both)), "tls_probe": probed}) == {}


def test_older_and_unpinned_agents_are_not_sent_a_list_they_cannot_use(rollover):
    rollover["publish"]([rollover["old"], rollover["new"]])
    assert m.heartbeat_reply({"version": "2.1.21"}) == {}
    assert m.heartbeat_reply({"tls_trust": []}) == {}


def test_after_the_switch_no_probe_is_asked(rollover):
    rollover["publish"]([rollover["old"], rollover["new"]], phase="switched")
    reply = m.heartbeat_reply({"tls_trust": [rollover["fp_old"]]})["serverTrust"]
    assert "probePort" not in reply and "next" not in reply


def test_reported_values_are_checked_before_they_are_stored():
    fields = m.agent_fields({"tls_trust": ["AB" * 32, "not-a-fingerprint", 7],
                             "tls_probe": {"ok": "yes", "fingerprints": ["cd" * 32, "x"], "error": "e" * 900, "status": "200"}})
    assert fields["tlsTrust"] == ["ab" * 32]
    assert fields["tlsProbe"]["ok"] is False and fields["tlsProbe"]["fingerprints"] == ["cd" * 32]
    assert len(fields["tlsProbe"]["error"]) == 300 and fields["tlsProbe"]["status"] is None
    assert m.agent_fields({"hostname": "x"}) == {}


class _Cursor:
    def __init__(self, rows):
        self.rows = rows

    async def to_list(self, length):
        return self.rows[:length]


class _Agents:
    def __init__(self, rows):
        self.rows = rows

    def find(self, *_args):
        return _Cursor(self.rows)


class _Db:
    def __init__(self, rows):
        self.agents = _Agents(rows)


def test_readiness_counts_active_agents_and_says_why_the_others_wait(rollover):
    rollover["publish"]([rollover["old"], rollover["new"]])
    now = datetime.now(timezone.utc)
    seen = now.isoformat()
    both = [rollover["fp_old"], rollover["fp_new"]]
    ok = {"fingerprints": [rollover["fp_new"]], "ok": True}
    rows = [
        {"hostname": "ready", "lastSeen": seen, "tlsTrust": both, "tlsProbe": ok},
        {"hostname": "old-version", "lastSeen": seen},
        {"hostname": "unpinned", "lastSeen": seen, "tlsTrust": []},
        {"hostname": "waiting", "lastSeen": seen, "tlsTrust": [rollover["fp_old"]]},
        {"hostname": "untested", "lastSeen": seen, "tlsTrust": both},
        {"hostname": "refused", "lastSeen": seen, "tlsTrust": both,
         "tlsProbe": {"fingerprints": [rollover["fp_new"]], "ok": False, "error": "certificate: not standards compliant"}},
        {"hostname": "gone", "lastSeen": (now - timedelta(days=30)).isoformat()},
    ]
    out = asyncio.run(m.readiness(_Db(rows), now))
    assert out["phase"] == "prepared" and out["served"]["fingerprint"] == rollover["fp_old"]
    assert out["counts"] == {"active": 6, "ready": 1, "update_agent": 1, "not_pinned": 1, "waiting": 1,
                             "probe_pending": 1, "probe_failed": 1}
    by_host = {a["hostname"]: a for a in out["notReady"]}
    assert set(by_host) == {"old-version", "unpinned", "waiting", "untested", "refused"}
    assert "not standards compliant" in by_host["refused"]["detail"]


def test_installers_ship_the_whole_list_while_a_change_is_published(rollover, tmp_path, monkeypatch):
    import agent_installer_builders as builders
    cert_file = tmp_path / "omni.crt"
    monkeypatch.setenv("AGENT_CA_CERT_FILE", str(cert_file))
    assert builders.agent_ca_cert_pem().strip() == rollover["old"].strip()
    rollover["publish"]([rollover["old"], rollover["new"]])
    assert m.split_pem(builders.agent_ca_cert_pem()) == m.split_pem(rollover["old"] + rollover["new"])
    monkeypatch.delenv("AGENT_CA_CERT_FILE")
    assert builders.agent_ca_cert_pem() is None, "a deployment that pins nothing keeps pinning nothing"

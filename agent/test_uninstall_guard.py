"""
uninstall_guard: the agent checks uninstall codes against the hash the platform
sent, and stores new hashes from heartbeat responses.

VECTOR is shared with the Rust agent's unit test (omni-agent-rs/src/uninstall.rs)
and matches backend agent_uninstall_endpoints.hash_code.
"""
import hashlib
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

import uninstall_guard as ug

VECTOR = {
    "code": "abcd-efgh-jkmn",
    "salt": "00112233445566778899aabbccddeeff",
    "iterations": 1000,
    "hash": "b85f55c4887a7b5fc80a3669c0758177811c0bcb45b2a70583f91311b1529372",
}


def _cfg():
    return {ug.KEY: {"version": 1, "salt": VECTOR["salt"], "iterations": VECTOR["iterations"], "hash": VECTOR["hash"]}}


def test_shared_vector_matches_pbkdf2():
    digest = hashlib.pbkdf2_hmac("sha256", b"ABCDEFGHJKMN", bytes.fromhex(VECTOR["salt"]), VECTOR["iterations"]).hex()
    assert digest == VECTOR["hash"]


def test_verify_accepts_the_code_in_any_format():
    for typed in ("ABCD-EFGH-JKMN", "abcd efgh jkmn", "ABCDEFGHJKMN"):
        assert ug.verify(_cfg(), typed) is True
    assert ug.verify_exit_code(_cfg(), "ABCD-EFGH-JKMN") == ug.EXIT_VALID


def test_verify_rejects_a_wrong_or_missing_code():
    assert ug.verify(_cfg(), "ABCD-EFGH-JKMP") is False
    assert ug.verify(_cfg(), "") is False
    assert ug.verify_exit_code(_cfg(), "nope") == ug.EXIT_INVALID


def test_unprotected_agent_is_reported_as_such():
    assert ug.verify({}, "anything") is None
    assert ug.verify_exit_code({}, "anything") == ug.EXIT_UNPROTECTED


def test_heartbeat_response_updates_config_only_on_change():
    saved = []
    cfg = {}
    body = {"success": True, ug.KEY: {"version": 2, "salt": "aa", "iterations": 5, "hash": "bb", "extra": "ignored"}}
    ug.update_from_heartbeat(cfg, body, saved.append)
    ug.update_from_heartbeat(cfg, body, saved.append)
    assert cfg[ug.KEY] == {"version": 2, "salt": "aa", "iterations": 5, "hash": "bb"}
    assert len(saved) == 1


def test_heartbeat_without_protection_leaves_config_alone():
    saved = []
    ug.update_from_heartbeat({}, {"success": True}, saved.append)
    ug.update_from_heartbeat({}, None, saved.append)
    assert saved == []

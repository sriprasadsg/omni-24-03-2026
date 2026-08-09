"""
Tests for WebRTC call signaling relay in websocket_manager.py.

Focus: routing to the right user session and — critically — tenant isolation
(a call signal must never be bridged across tenants).
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import asyncio
import pytest
from unittest.mock import AsyncMock, patch

import websocket_manager as wm


def _reset_state():
    wm.user_sessions.clear()
    wm.user_tenants.clear()


@pytest.fixture(autouse=True)
def clean_state():
    _reset_state()
    yield
    _reset_state()


def _run(coro):
    return asyncio.run(coro)


def test_offer_relayed_to_same_tenant_target():
    wm.user_sessions.update({"alice@t1": "sid-alice", "bob@t1": "sid-bob"})
    wm.user_tenants.update({"alice@t1": "t1", "bob@t1": "t1"})

    with patch.object(wm.sio, "emit", new=AsyncMock()) as emit:
        _run(wm._relay_call_signal(
            "sid-alice",
            {"to": "bob@t1", "call_id": "c1", "sdp": {"type": "offer"}},
            "webrtc_offer",
        ))

    emit.assert_awaited_once()
    args, kwargs = emit.await_args
    assert args[0] == "webrtc_offer"
    assert args[1]["from"] == "alice@t1"     # sender stamped
    assert args[1]["to"] == "bob@t1"
    assert kwargs["room"] == "sid-bob"       # routed to callee's sid


def test_cross_tenant_signal_is_dropped():
    wm.user_sessions.update({"alice@t1": "sid-alice", "mallory@t2": "sid-mallory"})
    wm.user_tenants.update({"alice@t1": "t1", "mallory@t2": "t2"})

    with patch.object(wm.sio, "emit", new=AsyncMock()) as emit:
        _run(wm._relay_call_signal(
            "sid-alice",
            {"to": "mallory@t2", "call_id": "c1", "sdp": {"type": "offer"}},
            "webrtc_offer",
        ))

    emit.assert_not_awaited()   # never bridged across tenants


def test_offline_target_notifies_caller_unavailable():
    wm.user_sessions.update({"alice@t1": "sid-alice"})
    wm.user_tenants.update({"alice@t1": "t1", "bob@t1": "t1"})   # bob known but no session

    with patch.object(wm.sio, "emit", new=AsyncMock()) as emit:
        _run(wm._relay_call_signal(
            "sid-alice",
            {"to": "bob@t1", "call_id": "c1", "convo_id": "convo-9"},
            "webrtc_offer",
        ))

    emit.assert_awaited_once()
    args, kwargs = emit.await_args
    assert args[0] == "webrtc_unavailable"
    assert kwargs["room"] == "sid-alice"     # caller is told, not the target


def test_end_signal_to_offline_target_is_silent():
    wm.user_sessions.update({"alice@t1": "sid-alice"})
    wm.user_tenants.update({"alice@t1": "t1", "bob@t1": "t1"})

    with patch.object(wm.sio, "emit", new=AsyncMock()) as emit:
        _run(wm._relay_call_signal(
            "sid-alice",
            {"to": "bob@t1", "call_id": "c1"},
            "webrtc_call_end",
        ))

    # Terminal events don't emit 'unavailable' back to the caller.
    emit.assert_not_awaited()


def test_unknown_sender_sid_is_ignored():
    wm.user_sessions.update({"bob@t1": "sid-bob"})
    wm.user_tenants.update({"bob@t1": "t1"})

    with patch.object(wm.sio, "emit", new=AsyncMock()) as emit:
        _run(wm._relay_call_signal(
            "sid-ghost",   # not in user_sessions
            {"to": "bob@t1", "call_id": "c1"},
            "webrtc_offer",
        ))

    emit.assert_not_awaited()


def test_missing_target_is_ignored():
    wm.user_sessions.update({"alice@t1": "sid-alice"})
    wm.user_tenants.update({"alice@t1": "t1"})

    with patch.object(wm.sio, "emit", new=AsyncMock()) as emit:
        _run(wm._relay_call_signal("sid-alice", {"call_id": "c1"}, "webrtc_offer"))

    emit.assert_not_awaited()

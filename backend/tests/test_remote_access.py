"""
Comprehensive tests for the remote access subsystem:
  - remote_endpoints.py    — session REST CRUD
  - tunnel_endpoints.py    — WebSocket relay (user ↔ agent)
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import asyncio
import threading
import time
import uuid
from datetime import datetime, timezone
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import FastAPI
from fastapi.testclient import TestClient
from authentication_service import get_current_user
from auth_types import TokenData


# ─────────────────────────────────────────────────────────────────────────────
# Shared helpers
# ─────────────────────────────────────────────────────────────────────────────

def _col(**kw):
    col = MagicMock()
    col.find_one = AsyncMock(return_value=None)
    col.insert_one = AsyncMock(return_value=MagicMock(inserted_id="fake-id"))
    col.update_one = AsyncMock(return_value=MagicMock(matched_count=1))
    col.update_many = AsyncMock(return_value=MagicMock(modified_count=0))
    col.delete_one = AsyncMock()
    _cur = MagicMock()
    _cur.sort = MagicMock(return_value=_cur)
    _cur.limit = MagicMock(return_value=_cur)
    _cur.to_list = AsyncMock(return_value=[])
    col.find = MagicMock(return_value=_cur)
    col.count_documents = AsyncMock(return_value=0)
    for k, v in kw.items():
        setattr(col, k, v)
    return col


def _db():
    db = MagicMock()
    db.remote_sessions = _col()
    db.agent_instructions = _col()
    db.agents = _col()
    db.agent_commands = _col()
    db.tenants = _col()
    return db


def _user(role="super_admin", tenant_id="tenant-1"):
    return TokenData(username="tester@example.com", role=role,
                     tenant_id=tenant_id, mfa_verified=True)


def _app(router, user=None):
    app = FastAPI()
    app.include_router(router)
    if user is not None:
        app.dependency_overrides[get_current_user] = lambda: user
    return app


# ─────────────────────────────────────────────────────────────────────────────
# 1.  Remote Session REST  (remote_endpoints.py)
# ─────────────────────────────────────────────────────────────────────────────

class TestRemoteSessionEndpoints:

    @pytest.fixture(autouse=True)
    def setup(self):
        import remote_endpoints as mod
        self.mod = mod
        self.user = _user()
        self.db = _db()
        self.app = _app(mod.router, self.user)

    # ── start session ─────────────────────────────────────────────────────────

    def test_start_session_returns_session_id_and_ws_url(self):
        with patch("remote_endpoints.get_database", return_value=self.db):
            with TestClient(self.app) as c:
                r = c.post("/api/remote/session/start",
                           json={"agent_id": "agent-abc", "protocol": "ssh", "type": "shell"})
        assert r.status_code == 200
        body = r.json()
        assert "session_id" in body
        assert body["status"] == "pending"
        assert body["websocket_url"].startswith("/api/tunnel/")
        assert body["websocket_url"].endswith("/user")

    def test_start_session_missing_agent_id_returns_400(self):
        with patch("remote_endpoints.get_database", return_value=self.db):
            with TestClient(self.app) as c:
                r = c.post("/api/remote/session/start",
                           json={"protocol": "ssh", "type": "shell"})
        assert r.status_code == 400

    def test_start_session_instruction_carries_tenant_id(self):
        """Critical fix: instruction must have tenantId or agent polling query never matches."""
        captured = {}

        async def capture(doc):
            captured.update(doc)
            return MagicMock(inserted_id="instr-id")

        self.db.agent_instructions.insert_one = capture

        with patch("remote_endpoints.get_database", return_value=self.db):
            with TestClient(self.app) as c:
                c.post("/api/remote/session/start",
                       json={"agent_id": "agent-xyz", "protocol": "ssh", "type": "shell"})

        assert captured.get("tenantId") == "tenant-1", (
            "Instruction missing tenantId — agent polling query will never match"
        )
        assert captured.get("type") == "start_remote_session"
        assert captured.get("status") == "pending"

    def test_start_session_instruction_has_id_and_instruction_fields(self):
        """Instruction must have id (for result tracking) and instruction field (for Rust agent)."""
        captured = {}

        async def capture(doc):
            captured.update(doc)
            return MagicMock(inserted_id="instr-id")

        self.db.agent_instructions.insert_one = capture

        with patch("remote_endpoints.get_database", return_value=self.db):
            with TestClient(self.app) as c:
                c.post("/api/remote/session/start",
                       json={"agent_id": "agent-xyz", "protocol": "vnc", "type": "desktop"})

        assert captured.get("id"), "Instruction missing 'id' — result reporting update will never match"
        assert captured.get("instruction") == "start_remote_session", (
            "Missing 'instruction' field — Rust agent reads this for dispatch"
        )
        # Payload must include session_id and url so agent can start the stream
        payload = captured.get("payload", {})
        assert payload.get("session_id"), "Payload missing session_id"
        assert payload.get("url", "").startswith("ws"), "Payload url must be a ws(s):// URL"
        assert payload.get("type") == "desktop"

    def test_start_session_session_record_carries_tenant_id(self):
        """Session record must also carry tenantId for the tenant-scoped list endpoint."""
        captured = {}

        async def capture(doc):
            captured.update(doc)
            return MagicMock(inserted_id="sess-id")

        self.db.remote_sessions.insert_one = capture

        with patch("remote_endpoints.get_database", return_value=self.db):
            with TestClient(self.app) as c:
                c.post("/api/remote/session/start",
                       json={"agent_id": "agent-xyz", "protocol": "ssh", "type": "shell"})

        assert captured.get("tenantId") == "tenant-1"
        assert captured.get("status") == "pending"

    def test_start_session_agent_callback_url_is_websocket_url(self):
        """Agent callback URL must use ws:// or wss:// and include the tunnel path."""
        captured = {}

        async def capture(doc):
            captured.update(doc)
            return MagicMock(inserted_id="instr-id")

        self.db.agent_instructions.insert_one = capture

        with patch("remote_endpoints.get_database", return_value=self.db):
            with TestClient(self.app) as c:
                c.post("/api/remote/session/start",
                       json={"agent_id": "agent-xyz", "protocol": "ssh", "type": "shell"})

        url = captured.get("payload", {}).get("url", "")
        assert url.startswith("ws://") or url.startswith("wss://"), (
            f"Expected ws(s):// agent callback URL, got: '{url}'"
        )
        assert "/api/tunnel/" in url
        assert url.endswith("/agent")

    def test_start_session_desktop_protocol_stored(self):
        """VNC/desktop protocol is forwarded into the instruction payload."""
        captured = {}

        async def capture(doc):
            captured.update(doc)
            return MagicMock(inserted_id="instr-id")

        self.db.agent_instructions.insert_one = capture

        with patch("remote_endpoints.get_database", return_value=self.db):
            with TestClient(self.app) as c:
                c.post("/api/remote/session/start",
                       json={"agent_id": "agent-xyz", "protocol": "vnc", "type": "desktop"})

        payload = captured.get("payload", {})
        assert payload.get("protocol") == "vnc"
        assert payload.get("type") == "desktop"

    # ── list / active sessions ─────────────────────────────────────────────────

    def test_list_sessions_returns_200(self):
        with patch("remote_endpoints.get_database", return_value=self.db):
            with patch("rbac_utils.verify_permission", AsyncMock(return_value=True)):
                with TestClient(self.app) as c:
                    r = c.get("/api/remote")
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_active_sessions_returns_200(self):
        with patch("remote_endpoints.get_database", return_value=self.db):
            with patch("rbac_utils.verify_permission", AsyncMock(return_value=True)):
                with TestClient(self.app) as c:
                    r = c.get("/api/remote/sessions")
        assert r.status_code == 200

    def test_list_sessions_denied_without_permission(self):
        with patch("remote_endpoints.get_database", return_value=self.db):
            with patch("rbac_utils.verify_permission", AsyncMock(return_value=False)):
                # Replace super_admin with a role that has no view:remote_access
                self.app.dependency_overrides[get_current_user] = lambda: _user(role="viewer")
                with TestClient(self.app) as c:
                    r = c.get("/api/remote")
        assert r.status_code == 403


# ── Phase 74: control:remote_access is a distinct, non-implied permission ─────

class TestControlSessionPermission:

    @pytest.fixture(autouse=True)
    def setup(self):
        import remote_endpoints as mod
        self.mod = mod
        self.user = _user()
        self.db = _db()
        self.app = _app(mod.router, self.user)

    def test_control_permission_denied_yields_403_and_no_instruction(self):
        """A principal without control:remote_access gets 403 and no instruction."""
        with patch("remote_endpoints.get_database", return_value=self.db):
            with patch("rbac_utils.verify_permission", AsyncMock(return_value=False)):
                with TestClient(self.app) as c:
                    r = c.post("/api/remote/session/start",
                               json={"agent_id": "agent-abc", "protocol": "vnc", "type": "control"})
        assert r.status_code == 403
        assert r.json()["detail"] == "Missing required permission: control:remote_access"
        assert self.db.agent_instructions.insert_one.call_count == 0

    def test_control_permission_granted_yields_200_control_instruction(self):
        """A holder of control:remote_access gets a control-typed instruction."""
        captured = {}
        async def capture(doc):
            captured.update(doc)
            return MagicMock(inserted_id="instr-id")
        self.db.agent_instructions.insert_one = capture
        with patch("remote_endpoints.get_database", return_value=self.db):
            with patch("rbac_utils.verify_permission", AsyncMock(return_value=True)):
                with TestClient(self.app) as c:
                    r = c.post("/api/remote/session/start",
                               json={"agent_id": "agent-abc", "protocol": "vnc", "type": "control"})
        assert r.status_code == 200
        assert captured.get("payload", {}).get("type") == "control"

    def test_desktop_never_consults_control_permission(self):
        """desktop is independent of control:remote_access — denied control still gets 200 (D-06)."""
        async def _perm(_user, permission):
            return permission != "control:remote_access"
        with patch("remote_endpoints.get_database", return_value=self.db):
            with patch("rbac_utils.verify_permission", AsyncMock(side_effect=_perm)):
                with TestClient(self.app) as c:
                    r = c.post("/api/remote/session/start",
                               json={"agent_id": "agent-abc", "protocol": "vnc", "type": "desktop"})
        assert r.status_code == 200

    @pytest.mark.parametrize("session_type", ["shell", "desktop"])
    def test_non_control_session_requires_view_permission(self, session_type):
        """shell/desktop sessions need view:remote_access — 403 and no instruction without it."""
        async def _perm(_user, permission):
            return permission != "view:remote_access"
        with patch("remote_endpoints.get_database", return_value=self.db):
            with patch("rbac_utils.verify_permission", AsyncMock(side_effect=_perm)):
                with TestClient(self.app) as c:
                    r = c.post("/api/remote/session/start",
                               json={"agent_id": "agent-abc", "protocol": "ssh", "type": session_type})
        assert r.status_code == 403
        assert r.json()["detail"] == "Missing required permission: view:remote_access"
        assert self.db.agent_instructions.insert_one.call_count == 0


class TestControlSessionReaping:
    """The single-control-session guard must block only a session that is still
    alive, and reap a dead one (capture died while the browser held its socket)
    rather than wedge the agent with a permanent 409."""

    @pytest.fixture(autouse=True)
    def setup(self):
        import remote_endpoints as mod
        self.mod = mod
        self.db = _db()
        self.app = _app(mod.router, _user())

    def _start_control(self, existing, connected):
        self.db.remote_sessions.find_one = AsyncMock(return_value=existing)
        with patch("remote_endpoints.get_database", return_value=self.db):
            with patch("rbac_utils.verify_permission", AsyncMock(return_value=True)):
                with patch("remote_endpoints.is_session_connected", return_value=connected):
                    with patch("remote_endpoints.close_session", return_value=True):
                        with TestClient(self.app) as c:
                            return c.post("/api/remote/session/start",
                                          json={"agent_id": "agent-abc", "protocol": "vnc", "type": "control"})

    def test_live_control_session_blocks_with_409(self):
        existing = {"_id": 1, "session_id": "live-1", "created_at": "2000-01-01T00:00:00+00:00"}
        r = self._start_control(existing, connected=True)
        assert r.status_code == 409
        assert r.json()["detail"]["reason"] == "already_controlled"
        assert self.db.agent_instructions.insert_one.call_count == 0

    def test_recent_control_session_still_blocks_within_grace(self):
        """No live tunnel yet, but just created — the agent may still be dialing in."""
        now = datetime.now(timezone.utc).isoformat()
        r = self._start_control({"_id": 1, "session_id": "new-1", "created_at": now}, connected=False)
        assert r.status_code == 409

    def test_stale_control_session_is_reaped_and_new_one_starts(self):
        existing = {"_id": 1, "session_id": "dead-1", "created_at": "2000-01-01T00:00:00+00:00"}
        r = self._start_control(existing, connected=False)
        assert r.status_code == 200
        # The dead session was marked closed, and a fresh session + instruction created.
        closed = [c for c in self.db.remote_sessions.update_one.call_args_list
                  if c.args and c.args[0] == {"session_id": "dead-1"}
                  and c.args[1].get("$set", {}).get("status") == "closed"]
        assert closed, "stale control session was not reaped"
        assert self.db.agent_instructions.insert_one.call_count == 1


# ─────────────────────────────────────────────────────────────────────────────
# 2.  WebSocket Tunnel  (tunnel_endpoints.py)
# ─────────────────────────────────────────────────────────────────────────────

def _tunnel_db(session_tenant="tenant-1"):
    """
    Returns a (raw_db, tenant_isolated_db) pair for tunnel tests.
    raw_db  → patches tunnel_endpoints.mongodb.db (used by IDOR guards before accept())
    idb     → patches tunnel_endpoints.get_database (used by tenant_key validation + update_one)
    """
    raw_db = MagicMock()
    raw_db.remote_sessions.find_one = AsyncMock(
        return_value={"session_id": "any", "tenantId": session_tenant, "status": "pending",
                      "agent_id": "agent-1"}
    )
    # The session's target agent; the agent side authenticates against it.
    raw_db.agents.find_one = AsyncMock(return_value={"id": "agent-1", "tenantId": "tenant-1"})
    raw_db.tenants.find_one = AsyncMock(
        return_value={"id": "tenant-1", "registrationKey": "valid-reg-key"}
    )
    idb = _db()
    # idb.tenants needs to return a matching tenant for the agent tenant_key happy path
    idb.tenants.find_one = AsyncMock(
        return_value={"id": session_tenant, "registrationKey": "valid-reg-key"}
    )
    idb.remote_sessions.find_one = AsyncMock(
        return_value={"session_id": "any", "tenantId": session_tenant, "status": "pending"}
    )
    return raw_db, idb


def _patch_tunnel_db(session_tenant="tenant-1"):
    """Context-manager helper: patch both mongodb.db and get_database for tunnel tests."""
    from contextlib import ExitStack, contextmanager

    @contextmanager
    def _ctx():
        raw_db, idb = _tunnel_db(session_tenant)
        mock_mongodb = MagicMock()
        mock_mongodb.db = raw_db
        with ExitStack() as stack:
            stack.enter_context(patch("tunnel_endpoints.mongodb", mock_mongodb))
            stack.enter_context(patch("tunnel_endpoints.get_database", return_value=idb))
            yield raw_db

    return _ctx()


def _user_token(tenant_id="tenant-1"):
    """verify_token_async mock that returns a real TokenData: the session's
    agent for "agenttok", a tenant admin for anything else."""
    def verify(token, *args, **kwargs):
        if token == "agenttok":
            return TokenData(username="agent-1", role="agent", tenant_id="tenant-1")
        return TokenData(username="user@t1.com", role="admin", tenant_id=tenant_id, mfa_verified=True)
    return AsyncMock(side_effect=verify)


class TestTunnelWebSocket:

    @pytest.fixture(autouse=True)
    def setup(self):
        from tunnel_endpoints import register_tunnel_routes, _tunnels
        _tunnels.clear()
        self.app = FastAPI()
        register_tunnel_routes(self.app)
        yield
        _tunnels.clear()

    # ── authentication ────────────────────────────────────────────────────────

    def test_user_side_rejects_missing_token(self):
        """Connection with no token must be refused."""
        with patch("authentication_service.verify_token_async",
                   AsyncMock(side_effect=Exception("no token"))):
            with TestClient(self.app) as c:
                with pytest.raises(Exception):
                    with c.websocket_connect("/api/tunnel/no-auth-sess/user"):
                        pass

    def test_agent_side_rejects_neither_token_nor_tenant_key(self):
        """Agent with neither JWT nor X-Tenant-Key must be refused."""
        with patch("authentication_service.verify_token_async",
                   AsyncMock(side_effect=Exception("bad token"))):
            with _patch_tunnel_db():
                with TestClient(self.app) as c:
                    with pytest.raises(Exception):
                        with c.websocket_connect("/api/tunnel/no-auth-agent/agent"):
                            pass

    def test_user_token_is_verified_on_connect(self):
        """verify_token_async is called with the exact token from the query string."""
        verify_mock = _user_token()
        sid = "verify-test-" + uuid.uuid4().hex[:8]

        with patch("authentication_service.verify_token_async", verify_mock):
            with _patch_tunnel_db():
                with TestClient(self.app) as c:
                    with c.websocket_connect(f"/api/tunnel/{sid}/user?token=mytoken"):
                        pass

        # The browser side of a tunnel is user-only: agent tokens are refused.
        verify_mock.assert_called_once_with("mytoken", allow_agent=False)

    # ── IDOR guard (fix #2) ───────────────────────────────────────────────────

    def test_user_side_rejects_nonexistent_session(self):
        """User cannot connect to a session that doesn't exist in the DB."""
        raw_db, idb = _tunnel_db()
        raw_db.remote_sessions.find_one = AsyncMock(return_value=None)
        mock_mdb = MagicMock(); mock_mdb.db = raw_db

        with patch("authentication_service.verify_token_async", _user_token()):
            with patch("tunnel_endpoints.mongodb", mock_mdb):
                with patch("tunnel_endpoints.get_database", return_value=idb):
                    with TestClient(self.app) as c:
                        with pytest.raises(Exception):
                            with c.websocket_connect("/api/tunnel/ghost-session/user?token=tok"):
                                pass

    def test_user_side_rejects_cross_tenant_session(self):
        """Authenticated user cannot hijack a session belonging to another tenant."""
        with patch("authentication_service.verify_token_async", _user_token(tenant_id="tenant-1")):
            with _patch_tunnel_db(session_tenant="tenant-2"):
                with TestClient(self.app) as c:
                    with pytest.raises(Exception):
                        with c.websocket_connect("/api/tunnel/other-tenant-sess/user?token=tok"):
                            pass

    # ── tenant_key auth (fix #1) ──────────────────────────────────────────────

    def test_agent_side_rejects_tenant_key_from_query_param(self):
        """tenant_key in query string must NOT be accepted (logs leak)."""
        with patch("authentication_service.verify_token_async",
                   AsyncMock(side_effect=Exception("no jwt"))):
            with _patch_tunnel_db():
                with TestClient(self.app) as c:
                    with pytest.raises(Exception):
                        with c.websocket_connect(
                            "/api/tunnel/qs-key-sess/agent?tenant_key=valid-reg-key"
                        ):
                            pass

    def _agent_connect(self, url, headers=None):
        """'accepted', or the close code the agent side was refused with."""
        from starlette.websockets import WebSocketDisconnect
        with TestClient(self.app) as c:
            try:
                with c.websocket_connect(url, headers=headers or {}):
                    return "accepted"
            except WebSocketDisconnect as exc:
                return exc.code

    def test_agent_side_rejects_invalid_tenant_key_header(self):
        """X-Tenant-Key that does not match any stored registrationKey is rejected."""
        with patch("authentication_service.verify_token_async", AsyncMock(side_effect=Exception("no jwt"))):
            with _patch_tunnel_db() as raw_db:
                raw_db.tenants.find_one = AsyncMock(return_value=None)
                code = self._agent_connect("/api/tunnel/bad-key-sess/agent", {"X-Tenant-Key": "wrong-key"})
        assert code == 4401

    def test_agent_side_rejects_tenant_key_from_wrong_tenant(self):
        """A valid key of tenant-99 cannot serve a session for tenant-1's agent."""
        with patch("authentication_service.verify_token_async", AsyncMock(side_effect=Exception("no jwt"))):
            with _patch_tunnel_db() as raw_db:
                raw_db.tenants.find_one = AsyncMock(return_value={"id": "tenant-99"})
                code = self._agent_connect("/api/tunnel/wrong-tenant-sess/agent", {"X-Tenant-Key": "valid-reg-key"})
        assert code == 4401

    def test_agent_side_closes_the_session_on_disconnect(self):
        """When the agent tunnel drops, the session is marked closed — so desktop
        sessions don't pile up and a dead control session can't wedge the guard."""
        sid = f"close-on-drop-{uuid.uuid4().hex[:8]}"
        with patch("authentication_service.verify_token_async", AsyncMock(side_effect=Exception("no jwt"))):
            with _patch_tunnel_db() as raw_db:
                code = self._agent_connect(f"/api/tunnel/{sid}/agent", {"X-Tenant-Key": "valid-reg-key"})
                assert code == "accepted"
                # The finally runs on the server task just after the client closes.
                closed = False
                for _ in range(50):
                    calls = raw_db.remote_sessions.update_one.call_args_list
                    if any(c.args and c.args[0] == {"session_id": sid}
                           and c.args[1].get("$set", {}).get("status") == "closed" for c in calls):
                        closed = True
                        break
                    time.sleep(0.02)
                assert closed, "agent-side disconnect did not close the session"

    def test_agent_side_accepts_valid_tenant_key_from_header(self):
        """Agent with its tenant's X-Tenant-Key (header only) is accepted."""
        with patch("authentication_service.verify_token_async", AsyncMock(side_effect=Exception("no jwt"))):
            with _patch_tunnel_db():
                code = self._agent_connect(f"/api/tunnel/valid-tk-{uuid.uuid4().hex[:8]}/agent",
                                           {"X-Tenant-Key": "valid-reg-key"})
        assert code == "accepted"

    def test_agent_side_accepts_agent_key_for_a_super_admin_session(self):
        """Regression: a super admin's session is stamped "platform-admin", which
        no agent key matched, so remote desktop from a super admin always failed."""
        with patch("authentication_service.verify_token_async", AsyncMock(side_effect=Exception("no jwt"))):
            with _patch_tunnel_db(session_tenant="platform-admin"):
                code = self._agent_connect(f"/api/tunnel/sa-{uuid.uuid4().hex[:8]}/agent",
                                           {"X-Tenant-Key": "valid-reg-key"})
        assert code == "accepted"

    def test_agent_side_accepts_the_session_agents_token(self):
        with patch("authentication_service.verify_token_async", _user_token()):
            with _patch_tunnel_db(session_tenant="platform-admin"):
                code = self._agent_connect(f"/api/tunnel/tok-{uuid.uuid4().hex[:8]}/agent",
                                           {"Authorization": "Bearer agenttok"})
        assert code == "accepted"

    def test_agent_side_refuses_user_tokens(self):
        """Any valid JWT used to pass; a user must not take the agent side (it
        receives the operator's keystrokes and feeds the operator's screen)."""
        with patch("authentication_service.verify_token_async", _user_token()):
            with _patch_tunnel_db():
                code = self._agent_connect("/api/tunnel/user-as-agent/agent?token=usertok")
        assert code == 4401

    def test_agent_side_refuses_another_agents_token(self):
        other = AsyncMock(return_value=TokenData(username="agent-2", role="agent", tenant_id="tenant-1"))
        with patch("authentication_service.verify_token_async", other):
            with _patch_tunnel_db():
                code = self._agent_connect("/api/tunnel/other-agent/agent", {"Authorization": "Bearer t"})
        assert code == 4401

    def test_agent_side_refuses_an_unknown_session(self):
        with patch("authentication_service.verify_token_async", _user_token()):
            with _patch_tunnel_db() as raw_db:
                raw_db.remote_sessions.find_one = AsyncMock(return_value=None)
                code = self._agent_connect("/api/tunnel/ghost/agent", {"Authorization": "Bearer agenttok"})
        assert code == 4403

    # ── relay (bidirectional) ─────────────────────────────────────────────────

    def test_relay_user_to_agent(self):
        """Message sent by the user side arrives at the agent side."""
        sid = "u2a-" + uuid.uuid4().hex[:8]
        received = []
        agent_ready = threading.Event()
        agent_done = threading.Event()
        errors = []

        with patch("authentication_service.verify_token_async", _user_token()):
            with _patch_tunnel_db():
                with TestClient(self.app) as client:

                    def run_agent():
                        try:
                            with client.websocket_connect(
                                f"/api/tunnel/{sid}/agent?token=agenttok"
                            ) as ws:
                                agent_ready.set()
                                msg = ws.receive_text()
                                received.append(msg)
                        except Exception as exc:
                            errors.append(str(exc))
                        finally:
                            agent_done.set()

                    t = threading.Thread(target=run_agent, daemon=True)
                    t.start()
                    assert agent_ready.wait(timeout=3), "Agent did not connect in time"

                    with client.websocket_connect(
                        f"/api/tunnel/{sid}/user?token=tok"
                    ) as user_ws:
                        user_ws.send_text("ping from user")

                    assert agent_done.wait(timeout=3), "Agent did not finish in time"
                    t.join(timeout=2)

        assert not errors, f"Agent thread raised: {errors}"
        assert received == ["ping from user"]

    def test_relay_agent_to_user(self):
        """Message sent by the agent side arrives at the user side."""
        sid = "a2u-" + uuid.uuid4().hex[:8]
        received = []
        agent_ready = threading.Event()
        user_ready = threading.Event()
        errors = []

        with patch("authentication_service.verify_token_async", _user_token()):
            with _patch_tunnel_db():
                with TestClient(self.app) as client:

                    def run_agent():
                        try:
                            with client.websocket_connect(
                                f"/api/tunnel/{sid}/agent?token=agenttok"
                            ) as ws:
                                agent_ready.set()
                                user_ready.wait(timeout=3)
                                ws.send_text("response from agent")
                        except Exception as exc:
                            errors.append(str(exc))

                    t = threading.Thread(target=run_agent, daemon=True)
                    t.start()
                    assert agent_ready.wait(timeout=3), "Agent did not connect in time"

                    with client.websocket_connect(
                        f"/api/tunnel/{sid}/user?token=tok"
                    ) as user_ws:
                        user_ready.set()
                        msg = user_ws.receive_text()
                        received.append(msg)

                    t.join(timeout=2)

        assert not errors, f"Agent thread raised: {errors}"
        assert received == ["response from agent"]

    def test_disconnect_propagates_sentinel_to_partner(self):
        """When user disconnects, the sentinel unblocks the agent's send queue."""
        from tunnel_endpoints import _tunnels
        sid = "sentinel-" + uuid.uuid4().hex[:8]

        with patch("authentication_service.verify_token_async", _user_token()):
            with _patch_tunnel_db():
                with TestClient(self.app) as client:
                    with client.websocket_connect(
                        f"/api/tunnel/{sid}/user?token=tok"
                    ):
                        pass  # Disconnect immediately

        assert sid not in _tunnels  # Tunnel cleaned up after disconnect

    def test_recv_to_queue_breaks_on_websocket_disconnect(self):
        """WebSocketDisconnect in receive_text must break without calling receive_bytes."""
        from fastapi.websockets import WebSocketDisconnect
        from tunnel_endpoints import _recv_to_queue

        queue = asyncio.Queue()
        ws = MagicMock()
        ws.receive_text = AsyncMock(side_effect=WebSocketDisconnect(code=1000))
        ws.receive_bytes = AsyncMock()

        asyncio.run(_recv_to_queue(ws, queue))

        ws.receive_bytes.assert_not_called()
        assert queue.empty()

    # ── Phase 74: /user carries control frames, /viewer is receive-only ────────

    def test_relay_control_frame_arrives_byte_identical_at_agent(self):
        """JSON input frame sent via /user arrives byte-identical at /agent."""
        sid = "relay-frame-" + uuid.uuid4().hex[:8]
        frame = '{"type":"input","kind":"mousemove","x":0.45,"y":0.72}'
        received = []
        agent_ready = threading.Event()
        agent_done = threading.Event()
        errors = []

        with patch("authentication_service.verify_token_async", _user_token()):
            with _patch_tunnel_db():
                with TestClient(self.app) as client:

                    def run_agent():
                        try:
                            with client.websocket_connect(
                                f"/api/tunnel/{sid}/agent?token=agenttok"
                            ) as ws:
                                agent_ready.set()
                                msg = ws.receive_text()
                                received.append(msg)
                        except Exception as exc:
                            errors.append(str(exc))
                        finally:
                            agent_done.set()

                    t = threading.Thread(target=run_agent, daemon=True)
                    t.start()
                    assert agent_ready.wait(timeout=3), "Agent did not connect in time"

                    with client.websocket_connect(
                        f"/api/tunnel/{sid}/user?token=tok"
                    ) as user_ws:
                        user_ws.send_text(frame)

                    assert agent_done.wait(timeout=3), "Agent did not finish in time"
                    t.join(timeout=2)

        assert not errors, f"Agent thread raised: {errors}"
        assert received == [frame]

    def test_relay_viewer_frame_does_not_reach_agent(self):
        """Frame sent via /viewer is never forwarded to /agent (receive-only lock)."""
        sid = "viewer-no-leak-" + uuid.uuid4().hex[:8]
        frame = '{"type":"input","kind":"mousemove","x":0.45,"y":0.72}'
        marker = '{"type":"input","kind":"mousemove","x":0.9,"y":0.9}'
        received = []
        agent_ready = threading.Event()
        agent_done = threading.Event()
        errors = []

        with patch("authentication_service.verify_token_async", _user_token()):
            with _patch_tunnel_db():
                with TestClient(self.app) as client:

                    def run_agent():
                        try:
                            with client.websocket_connect(
                                f"/api/tunnel/{sid}/agent?token=agenttok"
                            ) as ws:
                                agent_ready.set()
                                # Block until something arrives, then exit. The
                                # marker (0.9) proves delivery; if the viewer frame
                                # (0.45) had leaked onto u2a it would have arrived
                                # first and interleaved.
                                msg = ws.receive_text()
                                received.append(msg)
                        except Exception as exc:
                            errors.append(str(exc))
                        finally:
                            agent_done.set()

                    t = threading.Thread(target=run_agent, daemon=True)
                    t.start()
                    assert agent_ready.wait(timeout=3), "Agent did not connect in time"

                    with client.websocket_connect(
                        f"/api/tunnel/{sid}/viewer?token=tok"
                    ) as viewer_ws:
                        viewer_ws.send_text(frame)

                    # Give any (incorrect) viewer->agent relay time to deliver.
                    agent_done.wait(timeout=0.0)  # must still be empty here
                    import time as _time
                    _time.sleep(0.4)

                    # Now deliver a marker via /user. Agent must receive exactly
                    # this — proving the viewer frame never interleaved.
                    with client.websocket_connect(
                        f"/api/tunnel/{sid}/user?token=tok"
                    ) as user_ws:
                        user_ws.send_text(marker)

                    assert agent_done.wait(timeout=3), "Agent did not finish in time"
                    t.join(timeout=2)

        assert not errors, f"Agent thread raised: {errors}"
        assert received == [marker], "Viewer frame must not reach the agent side"


# ─────────────────────────────────────────────────────────────────────────────
# 3.  Phase 74-02: Disconnect, Consent, Capabilities
# ─────────────────────────────────────────────────────────────────────────────

class TestSessionDisconnect:
    """POST /session/{id}/disconnect — admin force-kill, gated on control:remote_access."""

    @pytest.fixture(autouse=True)
    def setup(self):
        import remote_endpoints as mod
        self.mod = mod
        self.user = _user()
        self.db = _db()
        self.app = _app(mod.router, self.user)

    def test_disconnect_requires_control_permission(self):
        with patch("remote_endpoints.get_database", return_value=self.db):
            with patch("rbac_utils.verify_permission", AsyncMock(return_value=False)):
                with TestClient(self.app) as c:
                    r = c.post("/api/remote/session/abc/disconnect", json={"reason": "admin_disconnect"})
        assert r.status_code == 403

    def test_disconnect_404_on_missing_session(self):
        self.db.remote_sessions.find_one = AsyncMock(return_value=None)
        with patch("remote_endpoints.get_database", return_value=self.db):
            with patch("rbac_utils.verify_permission", AsyncMock(return_value=True)):
                with patch("tunnel_endpoints.close_session", return_value=False):
                    with TestClient(self.app) as c:
                        r = c.post("/api/remote/session/missing/disconnect", json={"reason": "admin_disconnect"})
        assert r.status_code == 404

    def test_disconnect_rejects_non_control_session(self):
        self.db.remote_sessions.find_one = AsyncMock(return_value={"session_id": "s1", "type": "shell"})
        with patch("remote_endpoints.get_database", return_value=self.db):
            with patch("rbac_utils.verify_permission", AsyncMock(return_value=True)):
                with TestClient(self.app) as c:
                    r = c.post("/api/remote/session/s1/disconnect", json={"reason": "admin_disconnect"})
        assert r.status_code == 400

    def test_disconnect_kills_tunnel_and_writes_audit(self):
        self.db.remote_sessions.find_one = AsyncMock(return_value={
            "session_id": "s1", "type": "control", "agent_id": "agent-1", "tenantId": "tenant-1"
        })
        self.db.remote_sessions.update_one = AsyncMock(return_value=MagicMock(matched_count=1))
        write_audit_called = {}
        async def capture_audit(db, tenant, record):
            write_audit_called["record"] = record
            return "audit-id"
        with patch("remote_endpoints.get_database", return_value=self.db):
            with patch("rbac_utils.verify_permission", AsyncMock(return_value=True)):
                with patch("tunnel_endpoints.close_session", return_value=True):
                    with patch("remote_endpoints.write_audit", capture_audit):
                        with TestClient(self.app) as c:
                            r = c.post("/api/remote/session/s1/disconnect", json={"reason": "admin_disconnect"})
        assert r.status_code == 200
        assert r.json()["status"] == "disconnected"
        assert write_audit_called["record"]["event"] == "session_end"
        assert write_audit_called["record"]["disconnect_reason"] == "admin_disconnect"
        assert write_audit_called["record"]["mode"] == "control"


class TestConsentReporting:
    """POST /session/{id}/consent — agent reports accept/decline/timeout, writes audit."""

    AGENT = TokenData(username="a1", role="agent", tenant_id="tenant-1")

    @pytest.fixture(autouse=True)
    def setup(self):
        import remote_endpoints as mod
        self.mod = mod
        self.db = _db()
        self.db._db = self.db  # the route reads sessions on the raw collection
        self.db.remote_sessions.find_one = AsyncMock(return_value={
            "session_id": "s1", "type": "control", "tenantId": "platform-admin", "agent_id": "a1"
        })

    def _post(self, principal, body, audit=None, closed=False):
        from authentication_service import get_current_user_or_agent
        app = FastAPI()
        app.include_router(self.mod.router)
        if principal is not None:
            app.dependency_overrides[get_current_user_or_agent] = lambda: principal
        async def capture_audit(db, tenant, record):
            if audit is not None:
                audit["record"] = record
            return "audit-id"
        with patch("remote_endpoints.get_database", return_value=self.db), \
             patch("remote_endpoints.close_session", return_value=closed), \
             patch("remote_endpoints.write_audit", capture_audit):
            with TestClient(app) as c:
                return c.post("/api/remote/session/s1/consent", json=body)

    def test_consent_rejects_invalid_decision(self):
        assert self._post(self.AGENT, {"decision": "maybe"}).status_code == 400

    def test_consent_requires_agent_auth(self):
        # No bearer token at all.
        assert self._post(None, {"decision": "accept"}).status_code == 401

    @pytest.mark.parametrize("principal,status", [
        (TokenData(username="op@tenant-1", role="Tenant Admin", tenant_id="tenant-1", mfa_verified=True), 401),
        (TokenData(username="a2", role="agent", tenant_id="tenant-1"), 403),
        (TokenData(username="a9", role="agent", tenant_id="tenant-2"), 403),
    ])
    def test_consent_refuses_user_tokens_and_other_agents(self, principal, status):
        """Only the session's own agent can record consent — not the requester,
        not another agent (a super admin's "platform-admin" session used to
        accept any tenant's agent)."""
        assert self._post(principal, {"decision": "accept"}).status_code == status
        self.db.remote_sessions.update_one.assert_not_called()

    def test_consent_accept_activates_session(self):
        r = self._post(self.AGENT, {"decision": "accept"})
        assert r.status_code == 200
        assert r.json()["decision"] == "accept"
        statuses = [c.args[1].get("$set", {}).get("status") for c in self.db.remote_sessions.update_one.call_args_list]
        assert "active" in statuses

    def test_consent_decline_closes_session(self):
        audit = {}
        r = self._post(self.AGENT, {"decision": "decline"}, audit=audit, closed=True)
        assert r.status_code == 200
        assert audit["record"]["consent_decision"] == "decline"
        assert audit["record"]["disconnect_reason"] == "consent_declined"
        assert audit["record"]["mode"] == "control"

    def test_view_session_consent_is_audited_as_view(self):
        """The agent prompts before a view-only stream too; that decision used to
        get a 400 here, so view-mode consent never reached the audit trail."""
        self.db.remote_sessions.find_one = AsyncMock(return_value={
            "session_id": "s1", "type": "desktop", "tenantId": "platform-admin", "agent_id": "a1"
        })
        audit = {}
        r = self._post(self.AGENT, {"decision": "accept"}, audit=audit)
        assert r.status_code == 200
        assert audit["record"]["mode"] == "view"
        assert audit["record"]["consent_decision"] == "accept"

    def test_shell_session_has_no_consent(self):
        self.db.remote_sessions.find_one = AsyncMock(return_value={
            "session_id": "s1", "type": "shell", "tenantId": "platform-admin", "agent_id": "a1"
        })
        assert self._post(self.AGENT, {"decision": "accept"}).status_code == 400
        self.db.remote_sessions.update_one.assert_not_called()


class TestAgentTunnelUrl:
    """The address agents are told to stream to must be the one they enrolled with."""

    def _resolve(self, monkeypatch, env, host="57.154.210.55"):
        import remote_endpoints as mod
        for k in ("PLATFORM_URL", "AGENT_CA_CERT_FILE", "BACKEND_WS_HOST", "BACKEND_WS_PORT", "BACKEND_HOST"):
            monkeypatch.delenv(k, raising=False)
        for k, v in env.items():
            monkeypatch.setenv(k, v)
        req = MagicMock()
        req.headers = {"host": host}
        req.url.scheme = "http"
        return mod._resolve_backend_ws_base(req)

    def test_stale_backend_ws_host_no_longer_wins_for_pinned_agents(self, monkeypatch):
        """Regression: BACKEND_WS_HOST left at the retired 192.168.10.70 sent every
        desktop session there over plain ws:// — no video."""
        base = self._resolve(monkeypatch, {"BACKEND_WS_HOST": "192.168.10.70",
                                           "AGENT_CA_CERT_FILE": "/etc/nginx/ssl/omni.crt"})
        assert base == "wss://57.154.210.55"

    def test_platform_url_matches_what_installers_ship(self, monkeypatch):
        base = self._resolve(monkeypatch, {"PLATFORM_URL": "https://omni.example.com/",
                                           "BACKEND_WS_HOST": "192.168.10.70"})
        assert base == "wss://omni.example.com"

    def test_legacy_plaintext_deployments_keep_backend_ws_host(self, monkeypatch):
        assert self._resolve(monkeypatch, {"BACKEND_WS_HOST": "10.0.0.5"}) == "ws://10.0.0.5:5000"


class TestRemoteCapabilities:
    """GET /capabilities — returns can_view / can_control booleans."""

    @pytest.fixture(autouse=True)
    def setup(self):
        import remote_endpoints as mod
        self.mod = mod
        self.user = _user()
        self.db = _db()
        self.app = _app(mod.router, self.user)

    def test_capabilities_returns_booleans(self):
        with patch("remote_endpoints.get_database", return_value=self.db):
            with patch("rbac_utils.verify_permission", AsyncMock(side_effect=[True, False])):
                with TestClient(self.app) as c:
                    r = c.get("/api/remote/capabilities")
        assert r.status_code == 200
        body = r.json()
        assert body["can_view"] is True
        assert body["can_control"] is False

    def test_capabilities_both_true_for_super_admin(self):
        with patch("remote_endpoints.get_database", return_value=self.db):
            with patch("rbac_utils.verify_permission", AsyncMock(return_value=True)):
                with TestClient(self.app) as c:
                    r = c.get("/api/remote/capabilities")
        assert r.status_code == 200
        body = r.json()
        assert body["can_view"] is True
        assert body["can_control"] is True



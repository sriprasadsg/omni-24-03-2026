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
import uuid
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
        return_value={"session_id": "any", "tenantId": session_tenant, "status": "pending"}
    )
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
    """verify_token_async mock that returns a real TokenData."""
    return AsyncMock(return_value=TokenData(
        username="user@t1.com", role="admin", tenant_id=tenant_id, mfa_verified=True
    ))


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

        verify_mock.assert_called_once_with("mytoken")

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

    def test_agent_side_rejects_invalid_tenant_key_header(self):
        """X-Tenant-Key that does not match any stored registrationKey is rejected."""
        raw_db, idb = _tunnel_db()
        # Agent-side uses get_database() (idb) for tenant lookup — patch that
        idb.tenants.find_one = AsyncMock(return_value=None)
        mock_mdb = MagicMock(); mock_mdb.db = raw_db

        with patch("authentication_service.verify_token_async",
                   AsyncMock(side_effect=Exception("no jwt"))):
            with patch("tunnel_endpoints.mongodb", mock_mdb):
                with patch("tunnel_endpoints.get_database", return_value=idb):
                    with TestClient(self.app) as c:
                        with pytest.raises(Exception):
                            with c.websocket_connect(
                                "/api/tunnel/bad-key-sess/agent",
                                headers={"X-Tenant-Key": "wrong-key"},
                            ):
                                pass

    def test_agent_side_rejects_tenant_key_from_wrong_tenant(self):
        """Valid tenant_key resolves to tenant-99, but session belongs to tenant-1 → rejected."""
        raw_db, idb = _tunnel_db(session_tenant="tenant-1")
        # Key resolves to tenant-99 but session.tenantId is tenant-1 → mismatch
        idb.tenants.find_one = AsyncMock(
            return_value={"id": "tenant-99", "registrationKey": "valid-reg-key"}
        )
        mock_mdb = MagicMock(); mock_mdb.db = raw_db

        with patch("authentication_service.verify_token_async",
                   AsyncMock(side_effect=Exception("no jwt"))):
            with patch("tunnel_endpoints.mongodb", mock_mdb):
                with patch("tunnel_endpoints.get_database", return_value=idb):
                    with TestClient(self.app) as c:
                        with pytest.raises(Exception):
                            with c.websocket_connect(
                                "/api/tunnel/wrong-tenant-sess/agent",
                                headers={"X-Tenant-Key": "valid-reg-key"},
                            ):
                                pass

    def test_agent_side_accepts_valid_tenant_key_from_header(self):
        """Agent with a matching X-Tenant-Key (header only) is accepted."""
        sid = "valid-tk-" + uuid.uuid4().hex[:8]

        with patch("authentication_service.verify_token_async",
                   AsyncMock(side_effect=Exception("no jwt"))):
            with _patch_tunnel_db():
                with TestClient(self.app) as c:
                    with c.websocket_connect(
                        f"/api/tunnel/{sid}/agent",
                        headers={"X-Tenant-Key": "valid-reg-key"},
                    ):
                        pass

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
                                f"/api/tunnel/{sid}/agent?token=tok"
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
                                f"/api/tunnel/{sid}/agent?token=tok"
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



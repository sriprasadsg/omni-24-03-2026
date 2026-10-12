"""WebSocket tunnel relay and remote shell endpoints.

Registers routes directly on the FastAPI app (not an APIRouter) because
FastAPI WebSocket handlers must be decorated on the app instance.
"""
import asyncio
import logging
import re
from typing import Any, Dict, Optional

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from database import get_database, mongodb

logger = logging.getLogger(__name__)

# Per-session queues: session_id -> {"u2a": Queue, "a2u": Queue}
_tunnels: dict = {}
# Sentinel placed into a queue to signal the partner side to stop draining
_SENTINEL = object()


_TUNNEL_INSTRUCTIONS = {"start_remote_session", "start_desktop_stream"}
_HOST_RE = re.compile(r"[A-Za-z0-9.\-]+(:\d{1,5})?|\[[0-9A-Fa-f:.]+\](:\d{1,5})?")
_SESSION_RE = re.compile(r"[A-Za-z0-9\-]{1,64}")


def agent_tunnel_url(request: Request, session_id: str) -> Optional[str]:
    """The tunnel URL on the address this agent just used to reach us.

    The URL stored when the session was created comes from server settings
    (PLATFORM_URL, BACKEND_WS_HOST). Left pointing at a retired host, they sent
    every remote desktop there and the viewer never got a frame. The poll that
    is collecting the instruction proves which address works for this agent.
    """
    host = (request.headers.get("host") or "").strip()
    if not _HOST_RE.fullmatch(host) or not _SESSION_RE.fullmatch(session_id or ""):
        return None
    proto = (request.headers.get("x-forwarded-proto") or "").strip().lower()
    if not proto:
        # nginx terminates TLS on :443 (its :80 only redirects) and marks the
        # requests it proxies with X-Real-IP; agents dialling the backend
        # directly (legacy http://host:5000) come in without it.
        proto = "https" if request.headers.get("x-real-ip") else request.url.scheme
    scheme = "wss" if proto == "https" else "ws"
    return f"{scheme}://{host}/api/tunnel/{session_id}/agent"


def deliverable_payload(instr: Dict[str, Any], request: Request) -> Dict[str, Any]:
    payload = dict(instr.get("payload") or {})
    kind = instr.get("instruction") or instr.get("type")
    if kind in _TUNNEL_INSTRUCTIONS and payload.get("session_id"):
        url = agent_tunnel_url(request, str(payload["session_id"]))
        if url:
            payload["url"] = url
    return payload


def _get_tunnel(session_id: str) -> dict:
    if session_id not in _tunnels:
        _tunnels[session_id] = {
            "u2a": asyncio.Queue(maxsize=512),
            "a2u": asyncio.Queue(maxsize=512),
        }
    return _tunnels[session_id]


def close_session(session_id: str) -> bool:
    """Out-of-band kill switch: push the stop sentinel into both tunnel
    queues so both WebSocket peers actually disconnect (D-10/D-11).

    A database-only status flip cannot end a live session — the connection
    state lives in `_tunnels` — so REST handlers call this seam, never
    `_tunnels` directly. Returns True when the session was live and is now
    shutting down; False for an unknown session id. Never pops `_tunnels`
    here: the per-side `finally` blocks own cleanup, and popping out from
    under a live handler is what `tunnel_viewer_side` already warns against.
    """
    tunnel = _tunnels.get(session_id)
    if tunnel is None:
        return False
    # Sentinel into both queues; a full queue must not starve the other.
    for qname in ("u2a", "a2u"):
        try:
            tunnel[qname].put_nowait(_SENTINEL)
        except asyncio.QueueFull:
            pass
    return True


def is_session_connected(session_id: str) -> bool:
    """Whether a live tunnel exists for this session (either peer connected).

    In-process truth for session liveness: the single-control-session guard in
    remote_endpoints uses it to tell a genuinely active session from a dead one
    whose browser tab merely kept its WebSocket open on the "ended" overlay.
    """
    return session_id in _tunnels


async def _recv_to_queue(websocket: WebSocket, queue: asyncio.Queue):
    """Read all incoming messages from a WebSocket and push them onto a queue."""
    try:
        while True:
            try:
                data = await websocket.receive_text()
            except WebSocketDisconnect:
                break
            except Exception:
                # Try binary frame as fallback (some agents send bytes)
                try:
                    raw = await websocket.receive_bytes()
                    data = raw.decode("utf-8", errors="replace")
                except Exception:
                    break
            try:
                await queue.put(data)
            except asyncio.QueueFull:
                pass
    except WebSocketDisconnect:
        pass


async def _queue_to_send(queue: asyncio.Queue, websocket: WebSocket):
    """Drain a queue and send each item to a WebSocket. Stops on _SENTINEL."""
    try:
        while True:
            msg = await queue.get()
            if msg is _SENTINEL:
                break
            await websocket.send_text(msg)
    except (WebSocketDisconnect, Exception):
        pass


def register_tunnel_routes(app: FastAPI) -> None:
    """Attach all WebSocket tunnel and remote-shell routes to the app."""

    @app.websocket("/api/ws/remote/{agent_id}")
    async def websocket_remote_shell(
        websocket: WebSocket,
        agent_id: str,  # noqa: ARG001 (reserved for future relay routing)
        token: str = "",
    ):
        """Remote shell relay. Requires a valid JWT passed as ?token= query parameter."""
        from authentication_service import verify_token_async

        if not token:
            token = websocket.query_params.get("token", "")
        try:
            await verify_token_async(token)
        except Exception:
            await websocket.close(code=4401)
            return

        await websocket.accept()
        try:
            while True:
                data = await websocket.receive_text()
                if "Shell Ready" in data:
                    await websocket.send_text("echo 'Hello from Backend'")
        except WebSocketDisconnect:
            pass

    @app.websocket("/api/tunnel/{session_id}/user")
    async def tunnel_user_side(
        websocket: WebSocket, session_id: str, token: str = ""
    ):
        """Browser-side endpoint for a remote terminal session."""
        from authentication_service import verify_token_async

        if not token:
            token = websocket.query_params.get("token", "")
        try:
            user = await verify_token_async(token, allow_agent=False)
        except Exception:
            await websocket.close(code=4401)
            return

        # IDOR guard: raw Motor db used here — TenantIsolatedDatabase cannot be used
        # before websocket.accept() because the tenant ContextVar is not populated yet.
        session = await mongodb.db.remote_sessions.find_one({"session_id": session_id})
        if not session:
            await websocket.close(code=4403)
            return
        user_tenant = getattr(user, "tenant_id", None)
        if user_tenant and user_tenant != "platform-admin" and session.get("tenantId") != user_tenant:
            await websocket.close(code=4403)
            return

        await websocket.accept()
        tunnel = _get_tunnel(session_id)

        db = get_database()
        await db.remote_sessions.update_one(
            {"session_id": session_id}, {"$set": {"status": "active"}}
        )

        t_recv = asyncio.create_task(_recv_to_queue(websocket, tunnel["u2a"]))
        t_send = asyncio.create_task(_queue_to_send(tunnel["a2u"], websocket))
        try:
            await asyncio.wait([t_recv, t_send], return_when=asyncio.FIRST_COMPLETED)
        finally:
            t_recv.cancel()
            t_send.cancel()
            # Unblock the agent side's _queue_to_send which is waiting on u2a
            try:
                tunnel["u2a"].put_nowait(_SENTINEL)
            except asyncio.QueueFull:
                pass
            _tunnels.pop(session_id, None)
            try:
                await db.remote_sessions.update_one(
                    {"session_id": session_id}, {"$set": {"status": "closed"}}
                )
            except Exception as e:
                logger.debug("Session close DB update failed (non-fatal): %s", e)

    @app.websocket("/api/tunnel/{session_id}/agent")
    async def tunnel_agent_side(
        websocket: WebSocket, session_id: str, token: str = ""
    ):
        """Agent-side endpoint — the agent connects here to relay shell I/O."""
        from authentication_service import verify_token_async, AGENT_ROLE

        if not token:
            token = websocket.query_params.get("token", "")
        auth = websocket.headers.get("Authorization", "")
        if not token and auth.startswith("Bearer "):
            token = auth[7:]
        # Only accept X-Tenant-Key from headers — query params leak into access logs
        tenant_key = websocket.headers.get("X-Tenant-Key", "")

        # This side serves the endpoint's screen or shell and receives the
        # operator's keystrokes, so only the agent the session targets may take
        # it. Raw Motor db (same reason as tunnel_user_side/tunnel_viewer_side):
        # no tenant context exists yet — this lookup is what establishes it.
        session = await mongodb.db.remote_sessions.find_one({"session_id": session_id})
        agent = None
        if session and session.get("agent_id"):
            agent = await mongodb.db.agents.find_one(
                {"id": session["agent_id"]}, {"_id": 0, "id": 1, "tenantId": 1}
            )
        if not agent:
            await websocket.close(code=4403)
            return

        authorized = False
        if token:
            # Any valid JWT, a user's included, used to be enough here.
            try:
                td = await verify_token_async(token)
                authorized = (td.role == AGENT_ROLE and td.username == agent["id"]
                              and td.tenant_id == agent.get("tenantId"))
            except Exception as e:
                logger.debug("Agent tunnel token verification failed: %s", e)

        if not authorized and tenant_key:
            # Legacy agents send their tenant's registration key. Compare it with
            # the AGENT's tenant: the session carries the caller's, which for a
            # super admin is "platform-admin" — no agent key ever matched it, so
            # remote desktop from a super admin always failed with 4401.
            tenant = await mongodb.db.tenants.find_one({"registrationKey": tenant_key}, {"_id": 0, "id": 1})
            authorized = bool(tenant) and tenant.get("id") == agent.get("tenantId")

        if not authorized:
            await websocket.close(code=4401)
            return

        await websocket.accept()
        tunnel = _get_tunnel(session_id)

        t_recv = asyncio.create_task(_recv_to_queue(websocket, tunnel["a2u"]))
        t_send = asyncio.create_task(_queue_to_send(tunnel["u2a"], websocket))
        try:
            await asyncio.wait([t_recv, t_send], return_when=asyncio.FIRST_COMPLETED)
        finally:
            t_recv.cancel()
            t_send.cancel()
            # Unblock the user side's _queue_to_send which is waiting on a2u
            try:
                tunnel["a2u"].put_nowait(_SENTINEL)
            except asyncio.QueueFull:
                pass
            _tunnels.pop(session_id, None)
            # The agent side is authoritative for whether the endpoint is
            # actually streaming: when it drops, the session is over even if the
            # browser kept its /viewer or /user socket open on the "ended"
            # overlay. The viewer and user finally-blocks alone left desktop
            # sessions "active" forever and let a dead control session wedge the
            # single-control-session guard, so close it here too. Raw db: no
            # tenant context exists in a socket handler.
            try:
                await mongodb.db.remote_sessions.update_one(
                    {"session_id": session_id}, {"$set": {"status": "closed"}}
                )
            except Exception as e:
                logger.debug("Agent-side session close DB update failed (non-fatal): %s", e)

    @app.websocket("/api/tunnel/{session_id}/viewer")
    async def tunnel_viewer_side(
        websocket: WebSocket, session_id: str, token: str = ""
    ):
        """Browser-side endpoint for a remote desktop viewer (receive-only)."""
        from authentication_service import verify_token_async

        if not token:
            token = websocket.query_params.get("token", "")
        try:
            user = await verify_token_async(token, allow_agent=False)
        except Exception:
            await websocket.close(code=4401)
            return

        # IDOR guard: raw Motor db (same reason as tunnel_user_side)
        session = await mongodb.db.remote_sessions.find_one({"session_id": session_id})
        if not session:
            await websocket.close(code=4403)
            return
        user_tenant = getattr(user, "tenant_id", None)
        if user_tenant and user_tenant != "platform-admin" and session.get("tenantId") != user_tenant:
            await websocket.close(code=4403)
            return

        await websocket.accept()
        tunnel = _get_tunnel(session_id)

        t_send = asyncio.create_task(_queue_to_send(tunnel["a2u"], websocket))
        try:
            t_recv = asyncio.create_task(_recv_to_queue(websocket, asyncio.Queue()))
            await asyncio.wait([t_recv, t_send], return_when=asyncio.FIRST_COMPLETED)
        finally:
            t_send.cancel()
            # Do NOT pop the tunnel here — the agent side owns cleanup.
            # Popping here would orphan the agent's a2u writes if the viewer
            # reconnects (e.g. browser refresh) while the agent is still streaming.

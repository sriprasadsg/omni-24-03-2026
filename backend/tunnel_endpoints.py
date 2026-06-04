"""WebSocket tunnel relay and remote shell endpoints.

Registers routes directly on the FastAPI app (not an APIRouter) because
FastAPI WebSocket handlers must be decorated on the app instance.
"""
import asyncio
import logging

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from database import get_database, mongodb

logger = logging.getLogger(__name__)

# Per-session queues: session_id -> {"u2a": Queue, "a2u": Queue}
_tunnels: dict = {}
# Sentinel placed into a queue to signal the partner side to stop draining
_SENTINEL = object()


def _get_tunnel(session_id: str) -> dict:
    if session_id not in _tunnels:
        _tunnels[session_id] = {
            "u2a": asyncio.Queue(maxsize=512),
            "a2u": asyncio.Queue(maxsize=512),
        }
    return _tunnels[session_id]


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
            user = await verify_token_async(token)
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
        from authentication_service import verify_token_async

        if not token:
            token = websocket.query_params.get("token", "")
        # Only accept X-Tenant-Key from headers — query params leak into access logs
        tenant_key = websocket.headers.get("X-Tenant-Key", "")

        jwt_valid = False
        if token:
            try:
                await verify_token_async(token)
                jwt_valid = True
            except Exception as e:
                logger.debug("Agent tunnel token verification failed: %s", e)

        # Validate tenant_key against the stored registrationKey and session tenantId
        tenant_key_valid = False
        if not jwt_valid and tenant_key:
            db = get_database()
            session = await db.remote_sessions.find_one({"session_id": session_id})
            tenant = await db.tenants.find_one({"registrationKey": tenant_key})
            if (tenant and session
                    and tenant.get("id") == session.get("tenantId")):
                tenant_key_valid = True

        if not jwt_valid and not tenant_key_valid:
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

    @app.websocket("/api/tunnel/{session_id}/viewer")
    async def tunnel_viewer_side(
        websocket: WebSocket, session_id: str, token: str = ""
    ):
        """Browser-side endpoint for a remote desktop viewer (receive-only)."""
        from authentication_service import verify_token_async

        if not token:
            token = websocket.query_params.get("token", "")
        try:
            user = await verify_token_async(token)
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
            _tunnels.pop(session_id, None)

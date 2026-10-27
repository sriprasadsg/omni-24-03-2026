"""Watchdog ingest (Phase 82, plan 82-01): /api/internal/watchdog.

The platform watchdog (a separate process on the server) calls these two routes from the same
machine. It reports a heartbeat, the latest status snapshot and its events; the backend answers
with the platform-wide stop and, from later plans, an outbox of pages to send and a test-alert
request. The backend never holds the on-call key and never restarts anything.

Authentication: a bearer token from the systemd credential ``omni-watchdog-token`` (read on every
call from $CREDENTIALS_DIRECTORY, never cached, never logged), compared in constant time. The client
must be on the loopback interface and the request must carry none of X-Forwarded-For, X-Real-IP or
Forwarded, so the routes are unreachable through nginx even though uvicorn listens on 0.0.0.0.
The routes sit outside every catalogue prefix and have no session or role check by design.
"""
import hmac
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from autonomous_ops import selfheal
from database import get_database

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/internal/watchdog", tags=["Watchdog (internal)"])

_CREDENTIAL = "omni-watchdog-token"
_LOOPBACK = frozenset({"127.0.0.1", "::1"})
_PROXY_HEADERS = ("x-forwarded-for", "x-real-ip", "forwarded")
MAX_BODY_BYTES = 256 * 1024


def _load_credential() -> Optional[str]:
    """The token from the systemd credential directory, or None while it is not provisioned."""
    directory = os.environ.get("CREDENTIALS_DIRECTORY")
    if not directory:
        return None
    try:
        with open(os.path.join(directory, _CREDENTIAL), encoding="utf-8") as handle:
            return handle.read().strip() or None
    except OSError:
        return None


async def _require_watchdog_token(request: Request) -> None:
    """403 for a non-loopback client or any proxy header, 503 while no token is provisioned,
    401 for a missing or wrong bearer token."""
    client = request.client
    if client is None or client.host not in _LOOPBACK or any(h in request.headers for h in _PROXY_HEADERS):
        raise HTTPException(status_code=403, detail="Not available from this address")
    token = _load_credential()
    if token is None:
        raise HTTPException(status_code=503, detail="The watchdog endpoint is not configured")
    sent = request.headers.get("authorization", "")
    if not hmac.compare_digest(sent.encode("utf-8"), f"Bearer {token}".encode("utf-8")):
        raise HTTPException(status_code=401, detail="Invalid credentials")


class SyncBody(BaseModel):
    """One watchdog run: v 1, the host, the status blocks and the events since the last accepted sync."""
    model_config = ConfigDict(extra="ignore")

    v: int = 1
    host: str = Field(max_length=selfheal.MAX_HOST)
    sentAt: Optional[str] = Field(None, max_length=64)
    services: Dict[str, Any] = Field(default_factory=dict, max_length=32)
    certs: List[Any] = Field(default_factory=list, max_length=32)
    disks: List[Any] = Field(default_factory=list, max_length=32)
    oncall: Optional[Dict[str, Any]] = None
    stop: Optional[Dict[str, Any]] = None
    events: List[Any] = Field(default_factory=list, max_length=selfheal.MAX_EVENTS)
    delivered: List[Any] = Field(default_factory=list, max_length=selfheal.MAX_EVENTS)


class ResultsBody(BaseModel):
    """The outcome of the tasks the last sync handed out (pages sent, a test alert); acted on by 82-07."""
    model_config = ConfigDict(extra="ignore")

    v: int = 1
    delivered: List[Any] = Field(default_factory=list, max_length=selfheal.MAX_EVENTS)
    testResult: Optional[Dict[str, Any]] = None


async def _read_limited(request: Request) -> bytes:
    """The request body, refused with 413 above 256 KB before anything is parsed."""
    declared = request.headers.get("content-length", "")
    if declared.isdigit() and int(declared) > MAX_BODY_BYTES:
        raise HTTPException(status_code=413, detail="Request body is too large")
    chunks, size = [], 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > MAX_BODY_BYTES:
            raise HTTPException(status_code=413, detail="Request body is too large")
        chunks.append(chunk)
    return b"".join(chunks)


async def _parse(request: Request, model):
    data = await _read_limited(request)
    try:
        return model.model_validate_json(data)
    except ValidationError as exc:
        problems = [{"loc": list(e["loc"]), "msg": e["msg"]} for e in exc.errors(include_input=False, include_url=False)]
        raise HTTPException(status_code=422, detail=problems) from exc


@router.post("/sync", summary="Watchdog heartbeat, status snapshot and events")
async def post_sync(request: Request, _auth: None = Depends(_require_watchdog_token)):
    """Stores the heartbeat and the snapshot, records each valid event once, and answers with the
    platform stop: ``{stop, acceptedEventIds, droppedEvents, outbox, testRequest}``. Body: ``SyncBody``
    (at most 50 events and 256 KB; an unknown event kind is dropped and counted, not stored)."""
    body: SyncBody = await _parse(request, SyncBody)
    now = datetime.now(timezone.utc)
    try:
        db = get_database()
        await selfheal.record_heartbeat(db, body.host, now)
        await selfheal.store_snapshot(db, body.model_dump(), now)
        accepted, dropped = await selfheal.ingest_events(db, body.events, body.host, now)
        return await selfheal.sync_response(db, accepted, dropped)
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("watchdog sync could not be served: %s", exc)
        raise HTTPException(status_code=503, detail="Platform health is temporarily unavailable") from exc


@router.post("/results", summary="Watchdog task results")
async def post_results(request: Request, _auth: None = Depends(_require_watchdog_token)):
    """Accepts the results of the tasks the last sync handed out (``ResultsBody``). Acted on by plan 82-07."""
    await _parse(request, ResultsBody)
    return {"ok": True}

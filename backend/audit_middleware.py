"""Audit every mutating API call (spec C5).

A pure ASGI middleware registered inside TenantMiddleware (so the tenant context is
set): for every /api/ POST, PUT, PATCH and DELETE it records one entry after the
response is sent, with the route template as the action ("PATCH
/api/tenants/{tenant_id}/license"), the catalogue that owns the path, the caller, the
status and outcome, IP, user agent, request id, duration and the top-level keys of a
JSON body. Body values are never stored. See audit_exempt for what is skipped.

The write happens after the last response byte is sent, so callers never wait on it,
and a failure only spools the entry (audit_ledger).
"""
import json
import logging
import time
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import audit_exempt
import audit_ledger

logger = logging.getLogger(__name__)

MUTATING = frozenset({"POST", "PUT", "PATCH", "DELETE"})
_BODY_KEYS_MAX_BYTES = 256 * 1024
_MANIFEST = Path(__file__).parent.parent / "shared" / "catalogue-access.json"


@lru_cache(maxsize=1)
def _catalogue_prefixes() -> List[Tuple[str, str]]:
    try:
        manifest = json.loads(_MANIFEST.read_text(encoding="utf-8"))
    except Exception:
        return []
    pairs = [(p.rstrip("/"), c["view"]) for c in manifest.get("catalogues", []) for p in c.get("routes", [])]
    return sorted(pairs, key=lambda x: -len(x[0]))


def catalogue_of(path: str) -> Optional[str]:
    for prefix, view in _catalogue_prefixes():
        if path == prefix or path.startswith(prefix + "/"):
            return view
    return None


def outcome_of(status: int) -> str:
    if status < 400:
        return "success"
    return "denied" if status in (401, 403) else "error"


def _header(scope, name: bytes) -> str:
    for key, value in scope.get("headers") or []:
        if key == name:
            return value.decode("latin-1")
    return ""


def actor_of(scope) -> Tuple[Optional[Dict[str, Any]], bool]:
    """(actor, is_agent) from the bearer token; (None, False) when there is none."""
    auth = _header(scope, b"authorization")
    if not auth.startswith("Bearer "):
        return None, False
    try:
        import jwt
        from authentication_service import ALGORITHM, SECRET_KEY, is_agent_payload
        payload = jwt.decode(auth[7:], SECRET_KEY, algorithms=[ALGORITHM], options={"verify_exp": False})
    except Exception:
        return {"userId": None, "email": None, "role": None, "tenantId": None, "tokenValid": False}, False
    if is_agent_payload(payload):
        return {"userId": payload.get("sub"), "role": "agent", "tenantId": payload.get("tenant_id")}, True
    return {"userId": payload.get("user_id") or payload.get("sub"), "email": payload.get("sub"),
            "role": payload.get("role"), "tenantId": payload.get("tenant_id"), "platformTier": None}, False


def body_keys(body: bytes, content_type: str) -> Optional[List[str]]:
    if not body or "json" not in content_type or len(body) > _BODY_KEYS_MAX_BYTES:
        return None
    try:
        data = json.loads(body)
    except Exception:
        return None
    return sorted(str(k) for k in data.keys())[:100] if isinstance(data, dict) else None


def resource_id_of(path_params: Dict[str, Any]) -> Optional[str]:
    for key in sorted(path_params, key=lambda k: (not k.endswith("id"), k)):
        return str(path_params[key])[:200]
    return None


class AuditMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        method = scope.get("method", "")
        path = scope.get("path", "")
        if scope["type"] != "http" or method not in MUTATING or not path.startswith("/api/"):
            return await self.app(scope, receive, send)

        actor, is_agent = actor_of(scope)
        agent_plane = is_agent or (actor is None and _header(scope, b"x-tenant-key"))
        if agent_plane and not path.startswith(audit_exempt.AGENT_PATHS_RECORDED[0]) \
                and not path.endswith(audit_exempt.AGENT_PATHS_RECORDED[1:]):
            return await self.app(scope, receive, send)

        body = bytearray()
        status = {"code": 500}
        started = time.perf_counter()
        receive_tap = receive
        try:
            length = int(_header(scope, b"content-length") or 0)
        except ValueError:
            length = 0
        if "json" in _header(scope, b"content-type") and 0 < length <= _BODY_KEYS_MAX_BYTES:
            # Small JSON bodies are read up front (routes that ignore their body would
            # otherwise never pass it through) and replayed to the app unchanged.
            more = True
            while more:
                message = await receive()
                if message["type"] != "http.request":
                    break
                body.extend(message.get("body", b""))
                more = message.get("more_body", False)
            replayed = {"done": False}

            async def receive_tap():
                if not replayed["done"]:
                    replayed["done"] = True
                    return {"type": "http.request", "body": bytes(body), "more_body": False}
                return await receive()

        async def send_tap(message):
            if message["type"] == "http.response.start":
                status["code"] = message["status"]
            await send(message)

        try:
            await self.app(scope, receive_tap, send_tap)
        finally:
            await self._record(scope, method, path, actor, bytes(body), status["code"],
                               (time.perf_counter() - started) * 1000)

    async def _record(self, scope, method, path, actor, body, status_code, duration_ms):
        try:
            route = scope.get("route")
            template = getattr(route, "path", None) or path
            if audit_exempt.exempt_reason(method, template):
                return
            from tenant_context import get_tenant_id
            tenant = get_tenant_id() or (actor or {}).get("tenantId")
            client = scope.get("client") or (None, None)
            entry = audit_ledger.build(
                f"{method} {template}", tenant, actor=actor or {"userId": None, "role": "anonymous"},
                outcome=outcome_of(status_code), catalogue=catalogue_of(path) or "unowned",
                resourceId=resource_id_of(scope.get("path_params") or {}), statusCode=status_code,
                ip=client[0], userAgent=_header(scope, b"user-agent")[:300] or None,
                requestId=_header(scope, b"x-request-id") or None, durationMs=round(duration_ms, 1),
                bodyKeys=body_keys(body, _header(scope, b"content-type")), source="request")
            await audit_ledger.record(entry)
        except Exception as exc:  # auditing must never break a request
            logger.error("Audit middleware failed for %s %s: %s", method, path, exc)

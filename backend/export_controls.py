"""Export controls for every route that hands tenant data out as a file.

Each signed-in user gets a daily export allowance (count and size, reset at 00:00 UTC);
every successful export is written to the audit ledger; and the user's exports in the last
10 minutes are checked for a bulk export, which opens a DLP incident (dlp_service).
Agent tokens and requests without a valid token pass through untouched, so the route
itself answers them (401/403).
"""
import json
import logging
import os
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from tenant_middleware import bearer_token

logger = logging.getLogger(__name__)

EXPORT_PATHS = re.compile(
    r"^/api/("
    r"reports/export"
    r"|audit-logs/export\.csv"
    r"|compliance/reports/(generate(/[a-z]+){0,2}|download/[^/]+)"
    r"|compliance/evidence/download/[^/]+"
    r"|itam/data/export"
    r"|itam/reports/((prebuilt|custom)/[^/]+/export|download/[^/]+)"
    r"|tickets/export/csv"
    r"|tickets/[^/]+/attachments/[^/]+/download"
    r"|soa/[^/]+/export"
    r"|mitre/navigator-export"
    r"|governance/documents/[^/]+/export-signed-pdf"
    r")$"
)
DAILY_EXPORTS = int(os.getenv("EXPORT_DAILY_LIMIT_PER_USER", "200"))
DAILY_BYTES = int(float(os.getenv("EXPORT_DAILY_MB_PER_USER", "500")) * 1024 * 1024)
_usage_index_ready = False


def _caller(scope) -> Optional[Dict[str, Any]]:
    """The signed-in user behind a bearer token; None for agents and missing/invalid tokens."""
    token = bearer_token(next((v.decode("latin-1") for k, v in scope.get("headers") or [] if k == b"authorization"), ""))
    if not token:
        return None
    try:
        import jwt
        from authentication_service import ALGORITHM, SECRET_KEY, is_agent_payload
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except Exception:
        return None
    if is_agent_payload(payload) or payload.get("type") == "refresh" or not payload.get("sub"):
        return None
    return {"email": payload["sub"], "role": payload.get("role"), "tenantId": payload.get("tenant_id")}


def _usage_key(who: Dict[str, Any], now: datetime) -> str:
    return f"{who.get('tenantId') or '-'}|{who['email'].lower()}|{now:%Y-%m-%d}"


def _raw_db():
    from database import get_database
    return get_database()._db


async def _usage(who: Dict[str, Any], now: datetime) -> Dict[str, Any]:
    return await _raw_db().export_usage.find_one({"_id": _usage_key(who, now)}) or {}


async def _add_usage(who: Dict[str, Any], now: datetime, size: int) -> None:
    global _usage_index_ready
    usage = _raw_db().export_usage
    if not _usage_index_ready:
        await usage.create_index("expiresAt", expireAfterSeconds=0)
        _usage_index_ready = True
    await usage.update_one(
        {"_id": _usage_key(who, now)},
        {"$inc": {"count": 1, "bytes": int(size)},
         "$setOnInsert": {"email": who["email"], "tenantId": who.get("tenantId"),
                          "expiresAt": now + timedelta(days=2)}},
        upsert=True,
    )


def _refusal(used: Dict[str, Any]) -> Optional[str]:
    if used.get("count", 0) >= DAILY_EXPORTS or used.get("bytes", 0) >= DAILY_BYTES:
        return (f"Daily export allowance reached ({DAILY_EXPORTS} exports or "
                f"{DAILY_BYTES // (1024 * 1024)} MB per user per day). It resets at 00:00 UTC.")
    return None


async def _record(who: Dict[str, Any], path: str, size: int, rows: Optional[int], now: datetime) -> None:
    await _add_usage(who, now, size)
    import audit_ledger
    import dlp_service
    await audit_ledger.event("data.export", who.get("tenantId") or "platform-admin",
                             actor={"email": who["email"], "role": who.get("role")},
                             path=path, bytes=size, rows=rows)
    if await dlp_service.check_bulk_export(who["email"], who.get("tenantId"), rows or 0, size, path):
        await dlp_service.open_bulk_export_incident(who["email"], who.get("tenantId"), path)


class ExportControlMiddleware:
    """Enforces the daily export allowance and records each export (see the module docstring)."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if (scope["type"] != "http" or scope.get("method") not in ("GET", "POST")
                or not EXPORT_PATHS.match(scope.get("path", ""))):
            return await self.app(scope, receive, send)
        who = _caller(scope)
        if who is None:
            return await self.app(scope, receive, send)

        now = datetime.now(timezone.utc)
        try:
            refusal = _refusal(await _usage(who, now))
        except Exception as exc:  # fail closed: the allowance cannot be checked
            logger.error("Export allowance lookup failed for %s: %s", who["email"], exc)
            refusal = "Exports are unavailable right now; try again shortly."
        if refusal:
            body = json.dumps({"detail": refusal}).encode()
            await send({"type": "http.response.start", "status": 429,
                        "headers": [(b"content-type", b"application/json"),
                                    (b"content-length", str(len(body)).encode())]})
            await send({"type": "http.response.body", "body": body})
            return

        seen = {"status": 0, "bytes": 0, "rows": None}

        async def counting_send(message):
            if message["type"] == "http.response.start":
                seen["status"] = message["status"]
                for k, v in message.get("headers") or []:
                    if k.lower() == b"x-export-rows" and v.isdigit():
                        seen["rows"] = int(v)
            elif message["type"] == "http.response.body":
                seen["bytes"] += len(message.get("body") or b"")
            await send(message)

        await self.app(scope, receive, counting_send)
        if 200 <= seen["status"] < 300:
            try:
                await _record(who, scope["path"], seen["bytes"], seen["rows"], now)
            except Exception as exc:  # the response is already sent; never fail it here
                logger.error("Recording export of %s by %s failed: %s", scope["path"], who["email"], exc)

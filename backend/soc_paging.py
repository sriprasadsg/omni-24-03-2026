"""Paging for critical alerts (Wave 3).

An organization sends its on-call a page through PagerDuty (Events API v2 routing key) or Opsgenie (API key), or a
post to a Microsoft Teams or Slack channel (webhook URL). Two things page:
  * a new alert at or above the paging severity (``minSeverity``, critical by default), as soon as it is recorded;
  * an open alert at or above ``breachSeverity`` still unacknowledged past its acknowledge target (soc_context SLA),
    found by the sweep that runs every minute.
Each alert pages once (``soc_pages``, unique per alert). Closing, archiving or merging the alert, by any path,
resolves the PagerDuty incident or closes the Opsgenie alert on the next sweep, and posts a "resolved" line to Teams
or Slack. Only alerts created after paging was switched on page, so an old backlog never does.

Settings live in ``soc_paging``, one row per organization: the key or webhook URL is encrypted at rest
(encryption_service) and never returned. On-call hours are a weekly window in the organization's time zone; outside
it nothing pages, and an alert still unacknowledged past its target pages once the window opens. At most
MAX_PER_HOUR pages per organization an hour; the rest are counted as suppressed.
"""
import asyncio
import logging
import re
import uuid
from datetime import datetime, time, timedelta, timezone
from typing import Any, Dict, List, Optional, Set, Tuple
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import httpx

from soc_alerts import SEVERITIES, TYPE_LABELS, status_of
from soc_service import parse_ts

logger = logging.getLogger(__name__)

PROVIDERS = ("pagerduty", "opsgenie", "teams", "slack")
PROVIDER_NAMES = {"pagerduty": "PagerDuty", "opsgenie": "Opsgenie", "teams": "Microsoft Teams", "slack": "Slack"}
PAGERDUTY_EVENTS = "https://events.pagerduty.com/v2/enqueue"
OPSGENIE = {"us": "https://api.opsgenie.com/v2/alerts", "eu": "https://api.eu.opsgenie.com/v2/alerts"}
PD_SEVERITY = {"critical": "critical", "high": "error", "medium": "warning", "low": "info", "info": "info"}
OG_PRIORITY = {"critical": "P1", "high": "P2", "medium": "P3", "low": "P4", "info": "P5"}
ROUTING_KEY = re.compile(r"^[A-Za-z0-9_-]{20,64}$")
GENIE_KEY = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
HHMM = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
MAX_PER_HOUR = 20
MAX_ATTEMPTS = 3
TIMEOUT = 15.0
ALWAYS = {"always": True}
_tasks: Set[asyncio.Task] = set()
_indexed: Set[str] = set()  # databases whose soc_pages indexes exist


class PagingError(ValueError):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def _raw(db):
    return getattr(db, "_db", db)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _client(**kw) -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=TIMEOUT, **kw)


def _rank(severity: Optional[str]) -> int:
    return SEVERITIES.index(severity) if severity in SEVERITIES else len(SEVERITIES)


def _on_call_hours(raw: Any) -> Dict[str, Any]:
    if raw is None or (isinstance(raw, dict) and raw.get("always") is True):
        return dict(ALWAYS)
    if not isinstance(raw, dict):
        raise PagingError("onCall must be {always: true} or a weekly window")
    try:
        ZoneInfo(str(raw.get("timezone") or ""))
    except (ZoneInfoNotFoundError, ValueError):
        raise PagingError("onCall.timezone must be an IANA time zone such as Europe/London")
    days = raw.get("days")
    if not isinstance(days, list) or not days or any(isinstance(d, bool) or d not in range(7) for d in days):
        raise PagingError("onCall.days must list weekdays 0 (Monday) to 6 (Sunday)")
    start, end = raw.get("start"), raw.get("end")
    if not (isinstance(start, str) and HHMM.match(start) and isinstance(end, str) and HHMM.match(end)) or start == end:
        raise PagingError("onCall.start and onCall.end must be different HH:MM times")
    return {"always": False, "timezone": raw["timezone"], "days": sorted(set(days)), "start": start, "end": end}


def on_call(hours: Dict[str, Any], now: datetime) -> bool:
    """Whether ``now`` falls in the weekly window; a window whose end is before its start runs past midnight and
    belongs to the day it starts on."""
    if not hours or hours.get("always"):
        return True
    local = now.astimezone(ZoneInfo(hours["timezone"]))
    start, end, t = time.fromisoformat(hours["start"]), time.fromisoformat(hours["end"]), local.time()
    if start < end:
        return local.weekday() in hours["days"] and start <= t < end
    return (t >= start and local.weekday() in hours["days"]) or (t < end and (local.weekday() - 1) % 7 in hours["days"])


async def save_config(db, tenant: str, body: Dict[str, Any], who: str) -> Dict[str, Any]:
    from encryption_service import get_encryption_service
    from webhook_url_validator import validate_webhook_url
    provider = body.get("provider")
    if provider not in PROVIDERS:
        raise PagingError(f"provider must be one of: {', '.join(PROVIDERS)}")
    severities = {k: body.get(k, d) for k, d in (("minSeverity", "critical"), ("breachSeverity", "high"))}
    if any(v not in ("critical", "high") for v in severities.values()):
        raise PagingError("minSeverity and breachSeverity must be critical or high")
    raw = _raw(db)
    existing = await raw.soc_paging.find_one({"tenantId": tenant}, {"_id": 0}) or {}
    secret = (body.get("secret") or "").strip()
    if not secret and existing.get("provider") != provider:
        raise PagingError(f"The {PROVIDER_NAMES[provider]} {'webhook URL' if provider in ('teams', 'slack') else 'key'} is required")
    doc = {"tenantId": tenant, "provider": provider, **severities, "enabled": bool(body.get("enabled", True)),
           "pageBreaches": bool(body.get("pageBreaches", True)), "onCall": _on_call_hours(body.get("onCall")),
           "region": "eu" if body.get("region") == "eu" else "us", "updatedBy": who, "updatedAt": _now().isoformat()}
    if secret:
        if provider == "pagerduty" and not ROUTING_KEY.match(secret):
            raise PagingError("A PagerDuty routing key is the 32-character integration key of an Events API v2 integration")
        if provider == "opsgenie" and not GENIE_KEY.match(secret):
            raise PagingError("An Opsgenie API key looks like 01234567-89ab-cdef-0123-456789abcdef")
        if provider in ("teams", "slack"):
            try:
                await validate_webhook_url(secret)
            except ValueError as exc:
                raise PagingError(f"Webhook URL refused: {exc}")
            doc["webhookHost"] = httpx.URL(secret).host
        doc["secret"] = get_encryption_service().encrypt(secret)
    if doc["enabled"] and not (existing.get("enabled") and existing.get("enabledAt")):
        doc["enabledAt"] = doc["updatedAt"]  # only alerts created from now on page
    await raw.soc_paging.update_one({"tenantId": tenant}, {"$set": doc}, upsert=True)
    return await get_config(db, tenant)


async def get_config(db, tenant: str) -> Dict[str, Any]:
    raw = _raw(db)
    cfg = await raw.soc_paging.find_one({"tenantId": tenant}, {"_id": 0, "secret": 0})
    if not cfg:
        return {"configured": False}
    pages = await raw.soc_pages.find({"tenantId": tenant}, {"_id": 0, "tenantId": 0}).sort("sentAt", -1).limit(10).to_list(10)
    return {"configured": True, **cfg, "recentPages": pages}


async def remove_config(db, tenant: str) -> None:
    if (await _raw(db).soc_paging.delete_one({"tenantId": tenant})).deleted_count == 0:
        raise PagingError("Paging is not set up", 404)


def _summary(alert: Dict[str, Any], reason: str) -> str:
    sev = (alert.get("severity") or "medium").upper()
    late = "Not acknowledged in time: " if reason == "ack_breach" else ""
    where = f" on {alert['hostname']}" if alert.get("hostname") else ""
    return f"[{sev}] {late}{alert.get('title') or TYPE_LABELS.get(alert.get('type'), 'Security alert')}{where}"


def _details(alert: Dict[str, Any], reason: str) -> Dict[str, Any]:
    return {"alertId": alert.get("id"), "type": TYPE_LABELS.get(alert.get("type"), alert.get("type")),
            "severity": alert.get("severity"), "endpoint": alert.get("hostname") or alert.get("agent_id"),
            "raised": alert.get("created_at"), "why": "acknowledge target missed" if reason == "ack_breach" else "new alert",
            "where": "Omni-Agent > Security > SOC console > Alert queue"}


def _chat_body(provider: str, title: str, lines: List[str]) -> Dict[str, Any]:
    if provider == "slack":
        return {"text": "\n".join([f"*{title}*", *lines])}
    card = {"$schema": "http://adaptivecards.io/schemas/adaptive-card.json", "type": "AdaptiveCard", "version": "1.4",
            "body": [{"type": "TextBlock", "text": title, "weight": "Bolder", "wrap": True},
                     *({"type": "TextBlock", "text": line, "wrap": True, "spacing": "None"} for line in lines)]}
    return {"type": "message", "attachments": [{"contentType": "application/vnd.microsoft.card.adaptive", "content": card}]}


async def _send(cfg: Dict[str, Any], action: str, alert: Dict[str, Any], reason: str, dedup: str) -> Tuple[bool, Optional[str]]:
    """Trigger or resolve one page at the provider: (accepted, error). Errors name the HTTP status, never the key."""
    from encryption_service import get_encryption_service
    secret = get_encryption_service().decrypt(cfg["secret"])
    provider = cfg["provider"]
    if provider == "pagerduty":
        url, headers = PAGERDUTY_EVENTS, {}
        body: Dict[str, Any] = {"routing_key": secret, "event_action": action, "dedup_key": dedup}
        if action == "trigger":
            body.update(client="Omni-Agent", payload={"summary": _summary(alert, reason)[:1024], "source": (
                alert.get("hostname") or "Omni-Agent")[:255], "severity": PD_SEVERITY.get(alert.get("severity"), "error"),
                "class": TYPE_LABELS.get(alert.get("type"), alert.get("type")), "custom_details": _details(alert, reason)})
    elif provider == "opsgenie":
        base, headers = OPSGENIE[cfg.get("region", "us")], {"Authorization": f"GenieKey {secret}"}
        if action == "trigger":
            url = base
            body = {"message": _summary(alert, reason)[:130], "alias": dedup, "source": "Omni-Agent",
                    "priority": OG_PRIORITY.get(alert.get("severity"), "P2"), "description": (alert.get("description") or "")[:15000],
                    "details": {k: str(v) for k, v in _details(alert, reason).items() if v is not None}}
        else:
            url, body = f"{base}/{dedup}/close?identifierType=alias", {"source": "Omni-Agent", "note": "Closed in Omni-Agent"}
    else:
        url, headers = secret, {}
        if action == "trigger":
            d = _details(alert, reason)
            body = _chat_body(provider, _summary(alert, reason), [
                f"Endpoint: {d['endpoint'] or 'none'} · raised {d['raised']}", f"Alert {d['alertId']}: {d['where']}"])
        else:
            res = status_of(alert)
            body = _chat_body(provider, f"Resolved: {alert.get('title') or 'Security alert'}",
                              [f"Closed in Omni-Agent ({res[1] or res[0]}). Alert {alert.get('id')}"])
    try:
        async with _client() as c:
            r = await c.post(url, json=body, headers=headers)
    except httpx.HTTPError as exc:
        return False, f"{PROVIDER_NAMES[provider]} could not be reached ({type(exc).__name__})"
    if 200 <= r.status_code < 300:
        return True, None
    hint = {400: "the event was refused", 401: "the key was refused", 403: "the key was refused",
            404: "the URL or alert was not found", 429: "rate limited"}.get(r.status_code, "an error")
    return False, f"{PROVIDER_NAMES[provider]} answered HTTP {r.status_code}: {hint}"


async def _ensure_index(raw) -> None:
    name = getattr(raw, "name", "")
    if name not in _indexed:
        await raw.soc_pages.create_index([("tenantId", 1), ("alertId", 1)], unique=True, name="soc_page_alert")
        await raw.soc_pages.create_index([("status", 1)], name="soc_page_status")
        _indexed.add(name)


async def page(db, alert_id: str, tenant: Optional[str], reason: str, force: bool = False) -> Dict[str, Any]:
    """Page one alert if the organization's settings say so; returns what happened ({"paged": bool, ...})."""
    raw = _raw(db)
    tenant = tenant or "platform-admin"
    cfg = await raw.soc_paging.find_one({"tenantId": tenant}, {"_id": 0})
    if not cfg or not cfg.get("secret") or not (cfg.get("enabled") or force):
        return {"paged": False, "why": "paging is off"}
    alert = await raw.security_alerts.find_one({"id": alert_id}, {"_id": 0})
    if not alert or (alert.get("tenantId") or "platform-admin") != tenant or status_of(alert)[0] in ("closed", "merged", "archived"):
        return {"paged": False, "why": "the alert is not active"}
    now = _now()
    if not force:
        limit = cfg["breachSeverity"] if reason == "ack_breach" else cfg["minSeverity"]
        created, since = parse_ts(alert.get("created_at")), parse_ts(cfg.get("enabledAt"))
        if _rank(alert.get("severity")) > _rank(limit) or not created or not since or created < since:
            return {"paged": False, "why": "below the paging severity or older than paging"}
        if not on_call(cfg.get("onCall") or ALWAYS, now):
            return {"paged": False, "why": "outside on-call hours"}
        sent = await raw.soc_pages.count_documents({"tenantId": tenant, "sentAt": {"$gte": (now - timedelta(hours=1)).isoformat()}})
        if sent >= MAX_PER_HOUR:
            await raw.soc_paging.update_one({"tenantId": tenant}, {"$inc": {"suppressed": 1}})
            return {"paged": False, "why": f"limit of {MAX_PER_HOUR} pages an hour reached"}
    await _ensure_index(raw)
    from pymongo.errors import DuplicateKeyError
    record = {"id": str(uuid.uuid4()), "tenantId": tenant, "alertId": alert_id, "title": alert.get("title"),
              "severity": alert.get("severity"), "reason": reason, "provider": cfg["provider"],
              "dedupKey": f"omni-{alert_id}", "status": "sending", "attempts": 0, "sentAt": now.isoformat()}
    try:
        await raw.soc_pages.insert_one(record)
    except DuplicateKeyError:
        return {"paged": False, "why": "this alert has already paged"}
    return await _deliver(raw, cfg, alert, record)


async def _deliver(raw, cfg: Dict[str, Any], alert: Dict[str, Any], record: Dict[str, Any]) -> Dict[str, Any]:
    ok, error = await _send(cfg, "trigger", alert, record["reason"], record["dedupKey"])
    now = _now().isoformat()
    await raw.soc_pages.update_one({"id": record["id"]}, {"$set": {"status": "triggered" if ok else "failed", "error": error,
                                                                   "sentAt": now}, "$inc": {"attempts": 1}})
    await raw.soc_paging.update_one({"tenantId": record["tenantId"]}, {"$set": {"lastResult": {"at": now, "ok": ok, "error": error}}})
    return {"paged": ok, "provider": cfg["provider"], "error": error, "pageId": record["id"]}


def schedule_new(alert: Dict[str, Any]) -> None:
    """Called by soc_alerts.record_alert for every new alert: pages it in the background, never blocks or raises."""
    if alert.get("pagingTest") or _rank(alert.get("severity")) > _rank("high"):
        return

    async def run() -> None:
        try:
            from database import get_database
            await page(get_database(), alert["id"], alert.get("tenantId"), "new")
        except Exception as exc:
            logger.warning("Paging for alert %s failed: %s", alert.get("id"), exc)
    task = asyncio.get_running_loop().create_task(run())
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)


async def send_test(db, tenant: str, who: str) -> Dict[str, Any]:
    """A critical test alert in the console, paged now whatever the hours or severity; closing it resolves the page."""
    if not await _raw(db).soc_paging.find_one({"tenantId": tenant, "secret": {"$exists": True}}, {"_id": 1}):
        raise PagingError("Save the paging settings first", 409)
    now = _now().isoformat()
    alert = {"id": str(uuid.uuid4()), "tenantId": tenant, "type": "paging_test", "severity": "critical", "status": "open",
             "title": "Paging test from Omni-Agent", "pagingTest": True, "created_at": now, "lastSeenAt": now, "occurrences": 1,
             "description": f"Sent by {who}. Close this alert in the console to resolve the page."}
    await _raw(db).security_alerts.insert_one(dict(alert))
    return {"alertId": alert["id"], **await page(db, alert["id"], tenant, "test", force=True)}


async def sweep(db, now: Optional[datetime] = None) -> Dict[str, int]:
    """Resolve pages whose alert is no longer active, retry failed ones, and page acknowledge-target breaches."""
    import soc_context
    raw, now = _raw(db), now or _now()
    counts = {"resolved": 0, "retried": 0, "breaches": 0}
    configs = {c["tenantId"]: c async for c in raw.soc_paging.find({"secret": {"$exists": True}}, {"_id": 0})}
    stale = (now - timedelta(minutes=2)).isoformat()  # a "sending" page older than this lost its process
    async for p in raw.soc_pages.find({"status": {"$in": ["triggered", "failed", "sending"]}}, {"_id": 0}).limit(500):
        if p["status"] == "sending" and p["sentAt"] > stale:
            continue
        cfg = configs.get(p["tenantId"])
        if not cfg or cfg["provider"] != p["provider"]:
            why = "paging was removed" if not cfg else f"paging moved to {PROVIDER_NAMES[cfg['provider']]}"
            await raw.soc_pages.update_one({"id": p["id"]}, {"$set": {"status": "left_open", "resolveError": f"{why}; close it there"}})
            continue
        alert = await raw.security_alerts.find_one({"id": p["alertId"]}, {"_id": 0}) or {"id": p["alertId"], "status": "archived"}
        if status_of(alert)[0] not in ("closed", "merged", "archived"):  # still active: retry a page that never went out
            if p["status"] != "triggered" and p.get("attempts", 0) < MAX_ATTEMPTS and cfg.get("enabled"):
                counts["retried"] += 1
                await _deliver(raw, cfg, alert, p)
            continue
        if p["status"] != "triggered":  # closed before its page went out: nothing to resolve
            await raw.soc_pages.update_one({"id": p["id"]}, {"$set": {"status": "cancelled", "resolvedAt": now.isoformat()}})
            continue
        ok, error = await _send(cfg, "resolve", alert, p["reason"], p["dedupKey"])
        given_up = not ok and p.get("resolveAttempts", 0) + 1 >= MAX_ATTEMPTS
        await raw.soc_pages.update_one({"id": p["id"]}, {
            "$set": {"status": "resolved" if ok else ("left_open" if given_up else "triggered"),
                     "resolvedAt": now.isoformat() if ok else None, "resolveError": error},
            "$inc": {"resolveAttempts": 1}})
        counts["resolved"] += ok
    for tenant, cfg in configs.items():
        if not (cfg.get("enabled") and cfg.get("pageBreaches") and cfg.get("enabledAt")):
            continue
        targets = await soc_context.sla_targets(db, tenant)
        query = {"tenantId": {"$in": [None, "platform-admin"]} if tenant == "platform-admin" else tenant,
                 "status": {"$in": ["open", "new"]}, "created_at": {"$gte": cfg["enabledAt"]},
                 "severity": {"$in": [s for s in SEVERITIES if _rank(s) <= _rank(cfg["breachSeverity"])]}}
        async for a in raw.security_alerts.find(query, {"_id": 0, "id": 1, "severity": 1, "status": 1, "created_at": 1,
                                                        "acknowledgedAt": 1}).limit(200):
            state = soc_context.sla_state({**a, "createdAt": a.get("created_at")}, targets, now)
            if state and state["ackBreached"] and not await raw.soc_pages.find_one({"tenantId": tenant, "alertId": a["id"]}, {"_id": 1}):
                counts["breaches"] += (await page(db, a["id"], tenant, "ack_breach")).get("paged", False)
    return counts


async def sweep_loop() -> None:
    """Every minute: resolve, retry and breach-page (one organization's failure never stops the others)."""
    from database import get_database
    await asyncio.sleep(90)
    while True:
        try:
            await sweep(get_database())
        except Exception as exc:
            logger.warning("Paging sweep failed: %s", exc)
        await asyncio.sleep(60)

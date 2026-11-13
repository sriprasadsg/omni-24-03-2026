"""The daily digest for one organization (Phase 86, ACTV-04, D-01..D-04).

``send_for_tenant`` claims (tenantId, day) first (a unique index: at most once per organization and UTC day,
across restarts and workers), counts what the last 24 hours held, and stays quiet when there is nothing to say.
Otherwise it stores ONE in-app notice addressed to the organization's admins (the ``tenant_admins`` audience:
only readers holding ``*`` or manage:agents see it) and emails the admin-role users when mail is configured.
It never uses the general notice helper or the pending-agents recipients fan-out: those page the on-call channel
and copy into the platform feed, and a digest must reach neither.

Every query uses the raw handle with an explicit tenantId. A failed notice or email is logged and never raises.
"""
import asyncio
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Tuple

from pymongo.errors import DuplicateKeyError

from autonomous_ops import PLATFORM_TENANT_ID, incident_views, ledger, views
from autonomous_ops import scope
from autonomous_ops.scope import raw

from . import (DIGEST_HOUR_UTC, DIGEST_SECTION_CAP, DIGESTS, DONE_STATES, EXCLUDED_KINDS, SHADOW_STATE,
               UNDONE_STATES)
from . import digest_text as text
from .digest_text import DigestItem, Group

logger = logging.getLogger(__name__)

EVENT = "autonomous_ops.daily_digest"
EMAIL_TIMEOUT = 30                     # seconds one send may take (the SMTP call has no timeout of its own)
INACTIVE_STATUSES = ("Inactive", "Disabled", "Pending", "Suspended", "Locked")


def window(day: str) -> Tuple[datetime, datetime]:
    """[start, end) of the digest for UTC ``day`` (YYYY-MM-DD): the 24 hours before 07:00 UTC of that day. A row
    finished at exactly 07:00:00 belongs to the next day's digest."""
    end = datetime.strptime(day, "%Y-%m-%d").replace(hour=DIGEST_HOUR_UTC, tzinfo=timezone.utc)
    return end - timedelta(hours=24), end


async def ensure_indexes(db) -> None:
    """The once-per-day claim index and the finishedAt index the window queries use (the same definition twice is a
    no-op, so this is safe on every first pass)."""
    rdb = raw(db)
    await rdb[DIGESTS].create_index([("tenantId", 1), ("day", 1)], unique=True, name="digest_once_per_day")
    await rdb.autonomy_actions.create_index([("tenantId", 1), ("finishedAt", -1)], name="tenant_finished")


async def _group(db, tenant_id: str, flt: Dict[str, Any], by: str, now: datetime) -> Group:
    """The count of rows matching ``flt`` and the newest DIGEST_SECTION_CAP of them as digest items."""
    rdb = raw(db)
    full = {"tenantId": tenant_id, "kind": {"$nin": list(EXCLUDED_KINDS)}, **flt}
    total = await rdb.autonomy_actions.count_documents(full)
    if not total:
        return Group(0, [])
    found = rdb.autonomy_actions.find(full, {"_id": 0}).sort([(by, -1), ("id", -1)]).limit(DIGEST_SECTION_CAP)
    rows = [ledger._normalize(r) async for r in found]
    hosts = await views._host_names(db, tenant_id, rows)
    items: List[DigestItem] = []
    for row in rows:
        shown = views.present_row(row, viewer_is_platform_staff=False, now=now,
                                  host=hosts.get(str(row["targets"][0])) if row.get("targets") else None)
        items.append(DigestItem(id=str(row.get("id")), at=row.get(by), action_label=shown.get("actionLabel") or "",
                                target=shown.get("host") or shown.get("target"), rule_id=shown.get("ruleId"),
                                command=row.get("command")))
    return Group(total, items)


async def gather(db, tenant_id: str, day: str, now: datetime) -> Tuple[Group, Group, Group, Group]:
    """(ran, undone, waiting, simulation) for one organization. Ran and undone are by finishedAt in the window,
    simulation by createdAt in the window, waiting is the screen's own Needs your decision set at ``now``."""
    start, end = window(day)
    span = {"$gte": start, "$lt": end}
    ran = await _group(db, tenant_id, {"state": {"$in": list(DONE_STATES)}, "finishedAt": span}, "finishedAt", now)
    undone = await _group(db, tenant_id, {"state": {"$in": list(UNDONE_STATES)}, "finishedAt": span}, "finishedAt", now)
    waiting = await _group(db, tenant_id, {"$or": incident_views._waiting_filter(now)}, "createdAt", now)
    simulation = await _group(db, tenant_id, {"state": SHADOW_STATE, "createdAt": span}, "createdAt", now)
    return ran, undone, waiting, simulation


async def _claim(db, tenant_id: str, day: str, now: datetime) -> bool:
    """Write the (tenantId, day) claim; False when it already exists (sent, quiet or taken by another runner)."""
    try:
        await raw(db)[DIGESTS].insert_one({"tenantId": tenant_id, "day": day, "state": "claimed", "claimedAt": now})
        return True
    except DuplicateKeyError:
        return False


async def _post_notice(db, tenant_id: str, message: str, meta: Dict[str, Any]) -> bool:
    """One notice for the organization's admins only (audience tag), never for on-call or the platform feed."""
    try:
        import pending_agents  # lazy: it imports other notice modules lazily too
        await pending_agents._post_in_app(
            raw(db), tenant_id, text.notice_title(), message, "info",
            {"source": "autonomous_ops", "event": EVENT, "audience": pending_agents.TENANT_ADMIN_AUDIENCE, **meta})
        return True
    except Exception as exc:
        logger.warning("autonomous_ops digest: the notice for %s was not stored: %s", tenant_id, type(exc).__name__)
        return False


async def _admin_emails(db, tenant_id: str) -> List[str]:
    from auth_roles import TENANT_ADMIN_ROLE_NAMES
    found = raw(db).users.find({"tenantId": tenant_id, "role": {"$in": list(TENANT_ADMIN_ROLE_NAMES)},
                                "status": {"$nin": list(INACTIVE_STATUSES)}}, {"_id": 0, "email": 1})
    seen: Dict[str, str] = {}
    async for user in found:
        address = str(user.get("email") or "").strip()
        if address and "@" in address:
            seen.setdefault(address.casefold(), address)
    return sorted(seen.values(), key=str.casefold)


async def _smtp_for(tenant_id: str):
    """The mail configuration of the organization (own, tenant or platform), read under its tenant scope."""
    from auth_password_reset_endpoints import _resolve_smtp_config
    from database import get_database
    with scope.tenant_scope(tenant_id):
        return await _resolve_smtp_config(get_database(), tenant_id)


async def _send_emails(db, tenant_id: str, day: str, sections, counts: Dict[str, int]) -> Dict[str, int]:
    """Email the digest to the admin-role users: {sent, failed}. Nothing is attempted without an http(s) link base or
    a mail configuration; every send is time-limited and a failure is only counted."""
    outcome = {"sent": 0, "failed": 0}
    base = os.getenv("FRONTEND_URL", "").strip().rstrip("/")
    if not base.startswith(("http://", "https://")):
        logger.info("autonomous_ops digest: FRONTEND_URL is not an http(s) address; no email for %s", tenant_id)
        return outcome
    try:
        smtp = await _smtp_for(tenant_id)
        if not smtp:
            logger.info("autonomous_ops digest: no mail configuration for %s; no email", tenant_id)
            return outcome
        tenant = await raw(db).tenants.find_one({"id": tenant_id}, {"_id": 0, "name": 1})
        org = str((tenant or {}).get("name") or tenant_id)
        subject = text.email_subject(org, counts["ran"], counts["undone"], counts["waiting"])
        body_text, body_html = text.email_text(org, day, sections, base), text.email_html(org, day, sections, base)
        from email_service import email_service
        for address in await _admin_emails(db, tenant_id):
            try:
                result = await asyncio.wait_for(
                    email_service.send_email(smtp_config=smtp, to_email=address, subject=subject,
                                             body_text=body_text, body_html=body_html), EMAIL_TIMEOUT)
                ok = bool(result and result.get("success"))
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning("autonomous_ops digest: email for %s failed: %s", tenant_id, type(exc).__name__)
                ok = False
            outcome["sent" if ok else "failed"] += 1
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        logger.warning("autonomous_ops digest: the email step for %s failed: %s", tenant_id, type(exc).__name__)
    return outcome


async def send_for_tenant(db, tenant_id: str, day: str, now: datetime) -> str:
    """One digest for one organization and UTC day: 'already_claimed', 'quiet' or 'sent' ('skipped' for the platform
    organization). Claims first, so a restart, a retry or a second worker never sends a second one (at most once:
    a crash between the claim and the notice loses that day's digest, and the claim stays 'claimed')."""
    if not tenant_id or tenant_id == PLATFORM_TENANT_ID:
        return "skipped"
    if not await _claim(db, tenant_id, day, now):
        return "already_claimed"
    claims = raw(db)[DIGESTS]
    try:
        sections = await gather(db, tenant_id, day, now)
    except (Exception, asyncio.CancelledError):
        await claims.delete_one({"tenantId": tenant_id, "day": day, "state": "claimed"})   # nothing was sent yet
        raise
    counts = dict(zip(("ran", "undone", "waiting", "simulation"), (g.total for g in sections)))
    if not any(counts.values()):
        await claims.update_one({"tenantId": tenant_id, "day": day}, {"$set": {"state": "quiet", "counts": counts}})
        return "quiet"
    noticed = await _post_notice(db, tenant_id, text.notice_text(*sections), {"day": day, "counts": counts})
    emailed = await _send_emails(db, tenant_id, day, sections, counts)
    try:
        await claims.update_one({"tenantId": tenant_id, "day": day}, {"$set": {
            "state": "sent", "sentAt": datetime.now(timezone.utc), "counts": counts, "email": emailed,
            "notice": noticed}})
    except Exception as exc:
        logger.warning("autonomous_ops digest: the record for %s on %s was not updated: %s", tenant_id, day,
                       type(exc).__name__)
    return "sent"

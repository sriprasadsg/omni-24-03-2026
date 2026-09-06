"""Append-only control-session audit trail (Phase 74-02, D-03).

Only `write_audit` (insert) and `list_audit` (read) are exposed — there is
no update/delete function anywhere in this module, so a record, once
written, can never be altered or removed by anything importing it. This is
the whole mitigation for the repudiation threat: a remote-control session
is high-privilege, and the trail must survive the very admin who could
otherwise rewrite it.
"""
import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


async def write_audit(db, tenant_id: str, record: Dict[str, Any]) -> str:
    """Inserts one immutable audit record for a remote-control session.

    Record schema (open dict — the house pattern does not validate, and a
    rejected audit write would be worse than a loosely-shaped one):

      session_id          — the tunnel session that was controlled
      agent_id            — the endpoint agent
      event               — one of `session_start`, `consent_decision`, `session_end`
      requester_name      — display name of the admin who requested control
      requester_email     — username/email of the requesting admin
      requester_role      — role as resolved at request time
      mode                — `view` or `control`
      consent_decision    — `accept`, `decline`, `timeout`, or absent
      disconnect_reason   — `admin_disconnect`, `platform_force_kill`,
                            `endpoint_stop`, `tunnel_drop`, `consent_declined`,
                            `consent_timeout`, or absent

    Never write raw input frames, keystrokes, coordinates, or screenshot
    data: the trail records that a session happened and who authorised it,
    not what was typed.
    """
    doc = dict(record)
    doc.setdefault("tenantId", tenant_id)
    doc.setdefault("ts", datetime.now(timezone.utc).isoformat())
    result = await db.control_session_audit.insert_one(doc)

    # Push OCSF event to subscribed external SIEM webhooks (COMM-01).
    # Fire-and-forget; never raises into the control-session path.
    try:
        from soc_integration_service import push_ocsf_event
        asyncio.create_task(push_ocsf_event("remote_control.event", doc))
    except Exception as e:
        logger.debug("Control-session OCSF push failed (non-fatal): %s", e)

    return str(result.inserted_id)


async def list_audit(
    db,
    tenant_id: str,
    filters: Optional[Dict[str, Any]] = None,
    limit: int = 100,
) -> List[Dict[str, Any]]:
    query: Dict[str, Any] = {"tenantId": tenant_id}
    if filters:
        query.update(filters)
    cursor = db.control_session_audit.find(query, {"_id": 0}).sort("ts", -1).limit(limit)
    return await cursor.to_list(length=limit)
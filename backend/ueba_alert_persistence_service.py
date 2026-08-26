"""
UEBA alert-persistence helper, extracted from ueba_service.py (CLAUDE.md
500-line cap — file was 690 lines) to mirror the agent_heartbeat_alerts_service.py
split (Phase 46 Plan 05). Self-contained: only needs a db handle plus the
alert fields.
"""
import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Dict

logger = logging.getLogger(__name__)


async def _persist_alert(db, alert_type: str, severity: str, title: str, description: str, metadata: Dict[str, Any]):
    now = datetime.now(timezone.utc).isoformat()
    alert = {
        "type": alert_type,
        "severity": severity,
        "title": title,
        "description": description,
        "metadata": metadata,
        "created_at": now,
        "status": "new",
        "timestamp": now,
    }
    await db.security_alerts.insert_one(alert)

    # Push OCSF event to subscribed external SIEM webhooks (COMM-01).
    # Fire-and-forget; never raises into the UEBA pipeline.
    try:
        from soc_integration_service import push_ocsf_event
        asyncio.create_task(push_ocsf_event("ueba.anomaly", alert))
    except Exception as e:
        logger.debug("UEBA OCSF push failed (non-fatal): %s", e)

    # Publish to streaming broker so the Streaming Dashboard receives live events
    try:
        from streaming_service import broker as _broker
        _alert_copy = {k: v for k, v in alert.items() if k != "_id"}
        import asyncio as _asyncio
        _asyncio.create_task(_broker.publish("security_events", _alert_copy))
    except Exception as e:
        logger.debug("Security event streaming publish failed (non-fatal): %s", e)

    # Append an immutable blockchain audit block for this security event
    try:
        import hashlib as _hl
        import json as _json
        last_block = await db.blockchain_audit.find_one(
            {}, {"_id": 0, "blockNumber": 1, "hash": 1}, sort=[("blockNumber", -1)]
        )
        prev_num = last_block["blockNumber"] if last_block else 0
        prev_hash = last_block["hash"] if last_block else "0" * 64
        block_data = {
            "blockNumber": prev_num + 1,
            "previousHash": prev_hash,
            "timestamp": now,
            "eventType": alert_type,
            "severity": severity,
            "title": title,
        }
        block_data["hash"] = _hl.sha256(
            _json.dumps(block_data, sort_keys=True).encode()
        ).hexdigest()
        await db.blockchain_audit.insert_one(block_data)
    except Exception as e:
        logger.debug("Blockchain audit block write failed (non-fatal): %s", e)


# Public alias — five existing heartbeat call sites (shadow_ai, ueba_anomaly,
# fim_violation, pii_detected, runtime_security in agent_heartbeat_endpoints.py
# / agent_heartbeat_alerts_service.py) already do
# `from ueba_service import persist_security_alert` wrapped in
# `try/except ImportError: pass`. ueba_service.py re-exports both names from
# here unchanged, so that import path keeps working verbatim (do NOT rename
# `_persist_alert` — its internal call sites in ueba_service.py/ueba_analysis.py
# reference the private name directly). This is the ONLY alert-persistence
# path; never add a second one.
persist_security_alert = _persist_alert

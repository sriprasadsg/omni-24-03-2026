from fastapi import APIRouter, Depends, HTTPException, Body, BackgroundTasks, Request, Response
from typing import Dict, Any
from database import get_database
from datetime import datetime, timezone
import re
from agent_auth import verify_agent_key
from rate_limiter import limiter, agent_limiter
import logging

router = APIRouter(prefix="/api/agents", tags=["Agents"])
logger = logging.getLogger("agent_heartbeat_endpoints")


@router.post("/{agent_id}/heartbeat")
@agent_limiter.limit("60/minute")
async def report_heartbeat(
    request: Request,
    response: Response,
    agent_id: str,
    background_tasks: BackgroundTasks,
    payload: Dict[str, Any] = Body(...),
    _tenant: Dict[str, Any] = Depends(verify_agent_key)
):
    """
    Receive heartbeat from agent.
    Updates status, lastSeen, and processes all capability data pipelines.
    """
    if not _tenant:
        raise HTTPException(status_code=403, detail="Agent authentication required")
    db = get_database()
    _hb_tenant_id = _tenant.get("id") or None
    _hb_agent_filter: dict = {"id": agent_id}
    if _hb_tenant_id:
        _hb_agent_filter["tenantId"] = _hb_tenant_id

    existing_agent = await db.agents.find_one(_hb_agent_filter)

    # ── Agent limit check — block new agents when tenant is at capacity ───────
    if not existing_agent and _hb_tenant_id:
        tenant_doc = await db.tenants.find_one({"id": _hb_tenant_id})
        if tenant_doc:
            agent_limit = tenant_doc.get("maxAgents", 5)
            current_count = await db.agents.count_documents({"tenantId": _hb_tenant_id})
            if current_count >= agent_limit:
                logger.warning(
                    "Heartbeat rejected: tenant %s at agent limit (%d/%d)",
                    _hb_tenant_id, current_count, agent_limit,
                )
                raise HTTPException(
                    status_code=403,
                    detail=f"Agent limit reached ({agent_limit}). Please upgrade your plan to add more agents.",
                )

    if existing_agent:
        # ── Quarantine check — reject heartbeats from isolated agents ─────────
        if existing_agent.get("quarantined"):
            logger.warning("Heartbeat rejected: agent %s is quarantined", agent_id)
            raise HTTPException(
                status_code=403,
                detail="Agent is quarantined. Contact your administrator to release it.",
            )

        stored_device_id = existing_agent.get("deviceId")
        incoming_device_id = payload.get("device_id") or payload.get("deviceId")
        if stored_device_id and incoming_device_id and stored_device_id != incoming_device_id:
            logger.error("SECURITY ALERT: Hardware mismatch for agent %s. Stored: %s, Incoming: %s",
                         agent_id, stored_device_id, incoming_device_id)
            raise HTTPException(status_code=403, detail="Hardware ID mismatch. This session has been blocked.")
        if not stored_device_id and incoming_device_id:
            await db.agents.update_one(_hb_agent_filter, {"$set": {"deviceId": incoming_device_id}})

    update_data: Dict[str, Any] = {
        "status": "Online",
        "lastSeen": datetime.now(timezone.utc).isoformat(),
        "ipAddress": payload.get("ipAddress"),
        "platform": payload.get("platform"),
        "version": payload.get("version"),
    }

    if "meta" in payload:
        for key, value in payload["meta"].items():
            if key in ("capabilities", "available_capabilities"):
                update_data["availableCapabilities"] = value
            elif key == "capabilities_status":
                update_data["meta.capabilities_status"] = value
            else:
                update_data[f"meta.{key}"] = value

    if payload.get("hostname"):
        update_data["hostname"] = payload["hostname"]
    if payload.get("device_id"):
        update_data["deviceId"] = payload["device_id"]

    await db.agents.update_one(
        _hb_agent_filter,
        {"$set": update_data, "$setOnInsert": {"registeredAt": datetime.now(timezone.utc).isoformat()}},
        upsert=True
    )
    _meta = payload.get("meta", {})
    if _meta.get("current_cpu") is not None or _meta.get("current_memory") is not None:
        _snapshot = {
            "agent_id": agent_id,
            "hostname": payload.get("hostname", agent_id),
            "cpu": _meta.get("current_cpu", 0),
            "memory": _meta.get("current_memory", 0),
            "disk": _meta.get("disk_usage", 0),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        await db.agent_metrics_history.insert_one(_snapshot)
        count = await db.agent_metrics_history.count_documents({"agent_id": agent_id})
        if count > 100:
            oldest = await db.agent_metrics_history.find(
                {"agent_id": agent_id}, {"_id": 1}
            ).sort("timestamp", 1).limit(count - 100).to_list(length=count - 100)
            if oldest:
                await db.agent_metrics_history.delete_many({"_id": {"$in": [d["_id"] for d in oldest]}})

    hostname = payload.get("hostname")
    if hostname:
        asset_id = f"asset-{hostname}"
        asset_update: Dict[str, Any] = {
            "ipAddress": payload.get("ipAddress"),
            "osName": payload.get("platform"),
            "lastScanned": datetime.now(timezone.utc).isoformat(),
            "agentStatus": "Online",
            "agentVersion": payload.get("version", ""),
            "agentId": agent_id,
        }

        if "meta" in payload:
            meta = payload["meta"]
            asset_update["currentMetrics"] = {
                "cpuUsage": meta.get("current_cpu", 0),
                "memoryUsage": meta.get("current_memory", 0),
                "diskUsage": meta.get("disk_usage", 0),
                "totalMemoryGB": meta.get("total_memory_gb", 0),
                "availableMemoryGB": meta.get("available_memory_gb", 0),
                "diskTotalGB": meta.get("disk_total_gb", 0),
                "diskUsedGB": meta.get("disk_used_gb", 0),
                "diskFreeGB": meta.get("disk_free_gb", 0),
                "collectedAt": datetime.now(timezone.utc).isoformat()
            }
            os_ver = meta.get("os_version") or meta.get("os_version_detail")
            if os_ver and os_ver not in ("Unknown", "", None):
                asset_update["osVersion"] = os_ver
            if meta.get("installed_software"):
                asset_update["installedSoftware"] = meta["installed_software"]
            # Hoist software_management.installed_software if flat key not present
            if not asset_update.get("installedSoftware"):
                sw_mgmt = meta.get("software_management", {})
                if isinstance(sw_mgmt, dict) and sw_mgmt.get("installed_software"):
                    asset_update["installedSoftware"] = sw_mgmt["installed_software"]
            if meta.get("cpu_model") and meta["cpu_model"] not in ("Unknown", "Unknown CPU", ""):
                asset_update["cpuModel"] = meta["cpu_model"]
            if meta.get("memory_gb") and meta["memory_gb"] not in ("Unknown", ""):
                asset_update["ram"] = meta["memory_gb"]
            if meta.get("disks"):
                asset_update["disks"] = meta["disks"]
            serial = meta.get("serial_number")
            if serial and serial not in ("Unknown", "Not Available", "", None):
                asset_update["serialNumber"] = serial
            mac = meta.get("mac_address")
            if mac and mac not in ("00:00:00:00:00:00", "Unknown", "", None):
                asset_update["macAddress"] = mac
            if meta.get("mac_addresses"):
                asset_update["macAddresses"] = meta["mac_addresses"]
            kernel_val = meta.get("kernel_version") or meta.get("os_version_detail")
            if kernel_val and kernel_val not in ("Unknown", "", None):
                asset_update["kernel"] = kernel_val
                asset_update["osBuild"] = kernel_val
            os_release = meta.get("os_release")
            if os_release and os_release not in ("Unknown", "", None):
                asset_update["osDisplayVersion"] = os_release
            os_full_name = meta.get("os_full_name")
            if os_full_name and os_full_name not in ("Unknown", "", None):
                asset_update["osFullName"] = os_full_name
                _ed = re.search(r'\b(Home|Pro|Enterprise|Education|Standard|Datacenter|Server)\b',
                                os_full_name, re.IGNORECASE)
                if _ed:
                    asset_update["osEdition"] = _ed.group(1)
            install_date = meta.get("install_date")
            if install_date and install_date not in ("Unknown", "", None):
                asset_update["osInstalledOn"] = install_date

        _hb_asset_filter: dict = {"id": asset_id}
        if _hb_tenant_id:
            _hb_asset_filter["tenantId"] = _hb_tenant_id
        try:
            await db.assets.update_one(
                _hb_asset_filter,
                {
                    "$set": asset_update,
                    "$setOnInsert": {
                        "tenantId": _hb_tenant_id,
                        "status": "active", "type": "server", "hostname": hostname
                    }
                },
                upsert=True
            )
        except Exception as e:
            if "E11000 duplicate key error" in str(e):
                await db.assets.update_one(_hb_asset_filter, {"$set": asset_update})
            else:
                logger.error("ERROR updating asset: %s", e)

        try:
            if "meta" in payload:
                meta = payload["meta"]
                metric_doc = {
                    "agent_id": agent_id, "asset_id": asset_id,
                    "tenant_id": payload.get("tenantId") or (_tenant["id"] if _tenant else None),
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "cpu_percent": meta.get("current_cpu", 0),
                    "memory_percent": meta.get("current_memory", 0),
                    "disk_percent": meta.get("disk_usage", 0),
                    "memory_used_mb": meta.get("current_cpu", 0) * (meta.get("total_memory_gb", 16) * 1024 / 100),
                    "memory_total_mb": meta.get("total_memory_gb", 16) * 1024,
                    "disk_used_gb": meta.get("disk_used_gb", 0),
                    "disk_total_gb": meta.get("disk_total_gb", 500),
                }
                await db.agent_metrics.insert_one(metric_doc)
                await db.asset_metrics.insert_one(metric_doc)
        except Exception as archive_err:
            logger.error("Failed to archive historical metrics: %s", archive_err)

    meta = payload.get("meta", {})

    if "compliance_enforcement" in meta:
        try:
            from compliance_endpoints import process_automated_evidence
            await process_automated_evidence(payload.get("hostname", agent_id), meta["compliance_enforcement"], db)
        except Exception as e:
            logger.error("ERROR processing compliance evidence: %s", e)

    if "log_collection" in meta:
        log_data = meta["log_collection"][:200] if isinstance(meta["log_collection"], list) else []
        if isinstance(log_data, list):
            db_logs = [{
                "tenantId": _hb_tenant_id, "agentId": agent_id,
                "service": e.get("service", "os"), "level": e.get("level", "INFO"),
                "message": e.get("message", ""), "timestamp": e.get("timestamp", datetime.now(timezone.utc).isoformat()),
                "hostname": payload.get("hostname", "unknown"), "rawData": e
            } for e in log_data]
            if db_logs:
                await db.logs.insert_many(db_logs)
                try:
                    from streaming_service import broker
                    for log in db_logs:
                        background_tasks.add_task(broker.publish, f"logs:{_hb_tenant_id}", log)
                except ImportError:
                    pass

    if "persistence_detection" in meta:
        p_data = meta["persistence_detection"]
        if isinstance(p_data, dict) and p_data.get("findings"):
            import uuid as _uuid
            await db.persistence_results.insert_one({
                "id": _uuid.uuid4().hex, "tenantId": _hb_tenant_id,
                "agentId": agent_id, "findings": p_data.get("findings", []),
                "count": p_data.get("count", 0), "platform": p_data.get("platform"),
                "timestamp": datetime.now(timezone.utc).isoformat()
            })

    if "shadow_ai" in meta:
        s_data = meta["shadow_ai"]
        if isinstance(s_data, dict) and s_data.get("ai_connections"):
            import uuid as _uuid

            async def _persist_shadow_ai(connections: list, _agent_id: str, _tenant_id: str) -> None:
                events = [
                    {
                        "id": _uuid.uuid4().hex, "tenantId": _tenant_id,
                        "agent_id": _agent_id, "process": c.get("process"),
                        "remote_ip": c.get("remote_ip"), "remote_host": c.get("remote_host"),
                        "timestamp": c.get("timestamp", datetime.now(timezone.utc).isoformat()),
                    }
                    for c in connections
                ]
                if events:
                    await db.shadow_ai_events.insert_many(events, ordered=False)
                try:
                    from ueba_service import persist_security_alert
                    for evt in events:
                        await persist_security_alert(
                            db, alert_type="shadow_ai", severity="medium",
                            title=f"Shadow AI Usage Detected: {evt.get('remote_host')}",
                            description=f"Process '{evt.get('process')}' on agent {_agent_id} connected to {evt.get('remote_host')}.",
                            metadata=evt,
                        )
                except ImportError:
                    pass

            background_tasks.add_task(_persist_shadow_ai, s_data["ai_connections"], agent_id, _hb_tenant_id)

    if "ueba" in meta:
        u_data = meta["ueba"]
        if isinstance(u_data, dict):
            for anomaly in u_data.get("anomalies_detected", []):
                try:
                    from ueba_service import persist_security_alert
                    background_tasks.add_task(
                        persist_security_alert, db, alert_type="ueba_anomaly",
                        severity=anomaly.get("severity", "medium").lower(),
                        title=f"UEBA Anomaly: {anomaly.get('type')}",
                        description=f"{anomaly.get('type')} detected for user {anomaly.get('user')}.",
                        metadata={**anomaly, "agent_id": agent_id, "tenantId": _hb_tenant_id}
                    )
                except ImportError:
                    pass

    if "software_inventory" in meta:
        sw_list = meta["software_inventory"]
        if isinstance(sw_list, list) and sw_list:
            hostname = payload.get("hostname", agent_id)

            async def _upsert_software(items: list, _agent_id: str, _tenant_id: str, _hostname: str) -> None:
                # Serial update_one() at 100-1000 items/heartbeat blocks the event loop.
                # Use bulk_write() with Upsert operations instead — one round-trip for all items.
                from pymongo import UpdateOne
                scanned_at = datetime.now(timezone.utc).isoformat()
                ops = [
                    UpdateOne(
                        {"agent_id": _agent_id, "name": sw.get("name")},
                        {"$set": {
                            "agent_id": _agent_id, "agent_name": _hostname,
                            "tenant_id": _tenant_id,
                            "name": sw.get("name"), "current_version": sw.get("current_version"),
                            "latest_version": sw.get("latest_version"), "pkg_type": sw.get("pkg_type", "unknown"),
                            "is_outdated": sw.get("is_outdated", False),
                            "last_scanned": scanned_at,
                        }},
                        upsert=True,
                    )
                    for sw in items if sw.get("name")
                ]
                if ops:
                    await db.software_inventory.bulk_write(ops, ordered=False)

            background_tasks.add_task(_upsert_software, sw_list, agent_id, _hb_tenant_id, hostname)

    if "fim" in meta:
        fim_data = meta["fim"]
        if isinstance(fim_data, dict) and fim_data.get("violations"):
            for v in fim_data["violations"][:200]:
                try:
                    from ueba_service import persist_security_alert
                    background_tasks.add_task(
                        persist_security_alert, db, alert_type="fim_violation", severity="high",
                        title=f"File Integrity Violation: {v.get('path')}",
                        description=f"Critical file modified on agent {agent_id}: {v.get('path')}.",
                        metadata={**v, "agent_id": agent_id, "tenantId": _hb_tenant_id},
                    )
                except ImportError:
                    pass
            _allowed_fim = {"path", "hash", "size", "modified", "action", "severity"}
            await db.fim_violations.insert_many([
                {k: v_item[k] for k in _allowed_fim if k in v_item} | {
                    "agent_id": agent_id,
                    "tenantId": _hb_tenant_id,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
                for v_item in fim_data["violations"][:200]
            ])

    if "pii_scanner" in meta:
        pii_data = meta["pii_scanner"]
        if isinstance(pii_data, dict) and pii_data.get("pii_found"):
            try:
                from ueba_service import persist_security_alert
                background_tasks.add_task(
                    persist_security_alert, db, alert_type="pii_detected", severity="high",
                    title=f"PII Detected on Agent {agent_id}",
                    description=f"{pii_data.get('findings_count', 0)} file(s) contain PII patterns.",
                    metadata={**pii_data, "agent_id": agent_id, "tenantId": _hb_tenant_id},
                )
            except ImportError:
                pass
            _allowed_pii = {"findings_count", "pii_found", "files_scanned", "categories"}
            await db.pii_findings.update_one(
                {"agent_id": agent_id},
                {"$set": {k: pii_data[k] for k in _allowed_pii if k in pii_data} | {
                    "agent_id": agent_id,
                    "tenantId": _hb_tenant_id,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }},
                upsert=True,
            )

    if "runtime_security" in meta:
        rs_data = meta["runtime_security"]
        if isinstance(rs_data, dict) and rs_data.get("suspicious_activities"):
            for item in [a for a in rs_data["suspicious_activities"] if a.get("severity") in ("critical", "high")]:
                try:
                    from ueba_service import persist_security_alert
                    background_tasks.add_task(
                        persist_security_alert, db, alert_type="runtime_security",
                        severity=item.get("severity", "high"),
                        title=f"Runtime Threat: {item.get('type')} on {agent_id}",
                        description=item.get("description", "Suspicious runtime activity detected"),
                        metadata={"type": item.get("type"), "severity": item.get("severity"),
                                  "description": item.get("description"), "agent_id": agent_id,
                                  "tenantId": _hb_tenant_id},
                    )
                except ImportError:
                    pass

    task_feedback_list = meta.get("task_feedback", [])
    if isinstance(task_feedback_list, list) and task_feedback_list:
        try:
            from response_orchestrator import ResponseOrchestrator
            _orch = ResponseOrchestrator()
            for fb in task_feedback_list:
                if fb.get("task_id"):
                    await _orch.record_feedback(
                        task_id=fb["task_id"], success=fb.get("success", True),
                        false_positive=fb.get("false_positive", False),
                        message=fb.get("message", ""), reported_by="agent",
                    )
        except Exception as fb_err:
            logger.error("ERROR processing task feedback: %s", fb_err)

    return {"success": True}

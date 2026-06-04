from fastapi import APIRouter, Depends
from datetime import datetime, timezone, timedelta
from database import get_database
from authentication_service import get_current_user
from auth_types import TokenData
import logging


logger = logging.getLogger(__name__)

router = APIRouter(tags=["Future Ops"])

@router.get("/api/aiops/capacity-predictions")
async def get_capacity_predictions(current_user: TokenData = Depends(get_current_user)):
    """
    Generate capacity predictions from live agent metrics.
    Projects CPU, memory, and disk usage 24 h ahead using a simple linear trend
    calculated over the last 10 agent heartbeats stored in the agents collection.
    Persists results in db.capacity_predictions so the dashboard gets real data.
    """
    db = get_database()

    _FO_SUPER_ROLES = {"Super Admin", "super_admin", "platform-admin"}
    tenant_id = getattr(current_user, "tenant_id", None)
    caller_role = getattr(current_user, "role", None)
    tenant_filter = {} if caller_role in _FO_SUPER_ROLES else {"tenantId": tenant_id}

    agents = await db.agents.find(
        {**tenant_filter, "status": "Online"}, {"_id": 0, "hostname": 1, "meta": 1}
    ).to_list(length=50)

    predictions = []
    now = datetime.now(timezone.utc)

    for agent in agents:
        meta = agent.get("meta") or {}
        hostname = agent.get("hostname", "unknown")

        cpu_now = float(meta.get("current_cpu", 0))
        mem_now = float(meta.get("current_memory", 0))
        disk_now = float(meta.get("disk_usage", 0))

        # Retrieve last 10 stored snapshots for this agent (stored by heartbeat bridge)
        history = await db.agent_metrics_history.find(
            {"hostname": hostname}, {"_id": 0, "cpu": 1, "memory": 1, "disk": 1}
        ).sort("timestamp", -1).to_list(length=10)

        def _trend(current: float, samples: list, key: str) -> float:
            """Return a simple linear-regression slope * 24 h delta capped at [0,100]."""
            vals = [s.get(key, current) for s in samples if s.get(key) is not None]
            if len(vals) < 2:
                return current
            n = len(vals)
            avg = sum(vals) / n
            # slope = Σ((i - avg_i) * (v - avg_v)) / Σ((i - avg_i)²)
            avg_i = (n - 1) / 2
            num = sum((i - avg_i) * (v - avg) for i, v in enumerate(vals))
            den = sum((i - avg_i) ** 2 for i in range(n)) or 1
            slope_per_sample = num / den
            # Assume one sample ≈ 1 min heartbeat; project 24 h = 1440 samples
            projected = current + slope_per_sample * 1440
            return max(0.0, min(100.0, round(projected, 1)))

        pred = {
            "hostname": hostname,
            "current": {"cpu": cpu_now, "memory": mem_now, "disk": disk_now},
            "predicted_24h": {
                "cpu": _trend(cpu_now, history, "cpu"),
                "memory": _trend(mem_now, history, "memory"),
                "disk": _trend(disk_now, history, "disk"),
            },
            "generated_at": now.isoformat(),
            "risk": "high" if any(
                _trend(v, history, k) > 85
                for v, k in [(cpu_now, "cpu"), (mem_now, "memory"), (disk_now, "disk")]
            ) else "normal",
        }
        predictions.append(pred)

        # Persist so subsequent reads don't recalculate from scratch
        await db.capacity_predictions.update_one(
            {"hostname": hostname},
            {"$set": pred},
            upsert=True,
        )

    if not predictions:
        # Fall back to any previously persisted predictions
        predictions = await db.capacity_predictions.find(tenant_filter, {"_id": 0}).to_list(length=100)

    return {"predictions": predictions}

@router.get("/api/stream/metrics")
async def get_stream_metrics(current_user: TokenData = Depends(get_current_user)):
    """Get StreamBroker aggregate metrics for the Streaming Dashboard."""
    from streaming_service import broker
    broker_metrics = broker.get_metrics()
    total = sum(broker_metrics.values())
    subscribers = sum(len(broker.subscribers.get(t, [])) for t in broker.topics) if hasattr(broker, "subscribers") else 0
    return {
        "events_processed": total,
        "active_subscribers": subscribers,
        "topic_breakdown": broker_metrics,
    }


@router.get("/api/streaming/live-events")
async def get_live_events(current_user: TokenData = Depends(get_current_user)):
    """Get live streaming metrics from the StreamBroker singleton and recent DB events."""
    from streaming_service import broker

    broker_metrics = broker.get_metrics()
    total_published = sum(broker_metrics.values())

    # Topics actively receiving events in the last publish cycle
    active_streams = sum(1 for t in broker.topics if broker.topics[t])

    # Events ingested in the last 60 seconds from the security_events collection
    db = get_database()
    cutoff = (datetime.now(timezone.utc) - timedelta(seconds=60)).isoformat()
    try:
        recent_count = await db.security_events.count_documents(
            {"timestamp": {"$gte": cutoff}}
        )
    except Exception:
        recent_count = 0

    events_per_second = round(recent_count / 60, 2)

    return {
        "eventsPerSecond": events_per_second,
        "totalPublished": total_published,
        "activeStreams": active_streams,
        "recentEvents60s": recent_count,
        "topicBreakdown": broker_metrics,
    }

@router.get("/api/multicloud/cost-optimization")
async def get_cost_optimization(current_user: TokenData = Depends(get_current_user)):
    """Get Cost Optimization recommendations from database"""
    db = get_database()
    recommendations = await db.cost_recommendations.find({}, {"_id": 0}).to_list(length=100)

    if not recommendations:
        # Seed recommendations on first request so the dashboard is never empty
        try:
            from finops_service import finops_service
            await finops_service.refresh_cost_recommendations(db)
            recommendations = await db.cost_recommendations.find({}, {"_id": 0}).to_list(length=100)
        except Exception as e:
            logger.debug("Cost recommendation seed failed (non-fatal): %s", e)

    return {"recommendations": recommendations}

@router.get("/api/privacy/consent-tracking")
async def get_consent_tracking(current_user: TokenData = Depends(get_current_user)):
    """Get Privacy Consent tracking from database"""
    db = get_database()
    
    with_consent = await db.user_consents.count_documents({"status": "granted"})
    pending = await db.user_consents.count_documents({"status": "pending"})
    revoked = await db.user_consents.count_documents({"status": "revoked"})
    
    total = with_consent + pending + revoked
    compliance_rate = int((with_consent / total * 100)) if total > 0 else 0
    
    return {
        "withConsent": with_consent,
        "complianceRate": compliance_rate,
        "pending": pending,
        "revoked": revoked
    }

async def _seed_blockchain_audit(db):
    """Seed genesis block if collection is empty."""
    import hashlib
    import uuid as _uuid
    if await db.blockchain_audit.count_documents({}) > 0:
        return
    genesis = {
        "blockNumber": 0,
        "id": str(_uuid.uuid4()),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "eventType": "GENESIS",
        "actor": "system",
        "action": "Blockchain audit chain initialised",
        "resourceId": "platform",
        "previousHash": "0" * 64,
        "hash": hashlib.sha256(b"genesis").hexdigest(),
        "tenantId": "global",
    }
    await db.blockchain_audit.insert_one(genesis)


@router.get("/api/blockchain/audit-chain")
async def get_blockchain_audit(current_user: TokenData = Depends(get_current_user)):
    """Get Blockchain Audit data from database, seeding genesis block if empty."""
    db = get_database()
    await _seed_blockchain_audit(db)
    blocks = await db.blockchain_audit.find({}, {"_id": 0}).sort("blockNumber", -1).to_list(length=50)
    return blocks

async def _seed_xdr_hunts(db):
    """Seed default XDR hunt templates (MITRE ATT&CK mapped) if collection is empty."""
    if await db.xdr_hunts.count_documents({}) > 0:
        return
    templates = [
        # Initial Access
        {"id": "hunt-phishing", "name": "Spearphishing Link / Attachment", "tactic": "Initial Access",
         "technique": "T1566", "subtechniques": ["T1566.001", "T1566.002"],
         "description": "Hunt for phishing emails delivering malicious links or attachments to users.",
         "data_sources": ["Email logs", "Endpoint telemetry"], "status": "active"},
        # Execution
        {"id": "hunt-powershell-exec", "name": "Suspicious PowerShell Execution", "tactic": "Execution",
         "technique": "T1059.001",
         "description": "Detect encoded or obfuscated PowerShell commands indicative of living-off-the-land attacks.",
         "data_sources": ["Process creation logs", "PowerShell ScriptBlock"], "status": "active"},
        {"id": "hunt-wmi-exec", "name": "WMI Command Execution", "tactic": "Execution",
         "technique": "T1047",
         "description": "Identify lateral movement or persistence via Windows Management Instrumentation.",
         "data_sources": ["WMI activity logs", "Process creation"], "status": "active"},
        # Persistence
        {"id": "hunt-scheduled-task", "name": "Scheduled Task / Job Persistence", "tactic": "Persistence",
         "technique": "T1053", "subtechniques": ["T1053.005"],
         "description": "Hunt for newly created scheduled tasks used to maintain persistence.",
         "data_sources": ["Windows Task Scheduler events", "Process creation"], "status": "active"},
        {"id": "hunt-registry-run", "name": "Registry Run Key Persistence", "tactic": "Persistence",
         "technique": "T1547.001",
         "description": "Detect additions to Run/RunOnce registry keys for autostart persistence.",
         "data_sources": ["Registry events", "Endpoint telemetry"], "status": "active"},
        # Privilege Escalation
        {"id": "hunt-privilege-escalation", "name": "Privilege Escalation Hunt", "tactic": "Privilege Escalation",
         "technique": "T1068",
         "description": "Detect exploitation of kernel or application vulnerabilities to gain elevated privileges.",
         "data_sources": ["Process creation", "Security events"], "status": "active"},
        {"id": "hunt-token-impersonation", "name": "Access Token Manipulation", "tactic": "Privilege Escalation",
         "technique": "T1134",
         "description": "Hunt for token impersonation or theft to run processes under a different security context.",
         "data_sources": ["Security events", "Process creation"], "status": "active"},
        # Defense Evasion
        {"id": "hunt-lolbas", "name": "Living-off-the-Land Binaries (LOLBAS)", "tactic": "Defense Evasion",
         "technique": "T1218",
         "description": "Detect abuse of signed Windows binaries (certutil, mshta, regsvr32) to run malicious payloads.",
         "data_sources": ["Process creation logs", "Command-line telemetry"], "status": "active"},
        {"id": "hunt-indicator-removal", "name": "Indicator Removal / Log Clearing", "tactic": "Defense Evasion",
         "technique": "T1070",
         "description": "Hunt for event log clearing or file deletion designed to remove attack traces.",
         "data_sources": ["Windows event logs", "File system events"], "status": "active"},
        # Credential Access
        {"id": "hunt-credential-dumping", "name": "Credential Dumping (LSASS)", "tactic": "Credential Access",
         "technique": "T1003", "subtechniques": ["T1003.001"],
         "description": "Detect access to LSASS memory for credential extraction via Mimikatz or similar tools.",
         "data_sources": ["Process access events", "Memory telemetry"], "status": "active"},
        {"id": "hunt-brute-force", "name": "Brute Force / Password Spraying", "tactic": "Credential Access",
         "technique": "T1110", "subtechniques": ["T1110.003"],
         "description": "Identify repeated failed authentication attempts indicative of password spraying.",
         "data_sources": ["Authentication logs", "Active Directory events"], "status": "active"},
        # Discovery
        {"id": "hunt-network-scan", "name": "Network / Port Scanning", "tactic": "Discovery",
         "technique": "T1046",
         "description": "Detect internal network reconnaissance scanning for open ports and services.",
         "data_sources": ["Network flow logs", "Endpoint telemetry"], "status": "active"},
        # Lateral Movement
        {"id": "hunt-lateral-movement", "name": "Remote Services Lateral Movement", "tactic": "Lateral Movement",
         "technique": "T1021", "subtechniques": ["T1021.001", "T1021.002", "T1021.006"],
         "description": "Hunt for RDP, SMB, and WinRM-based lateral movement between hosts.",
         "data_sources": ["Network logs", "Authentication events", "Process creation"], "status": "active"},
        {"id": "hunt-pass-the-hash", "name": "Pass-the-Hash / Pass-the-Ticket", "tactic": "Lateral Movement",
         "technique": "T1550", "subtechniques": ["T1550.002", "T1550.003"],
         "description": "Detect use of stolen credential hashes or Kerberos tickets for lateral movement.",
         "data_sources": ["Authentication logs", "Kerberos events"], "status": "active"},
        # Collection
        {"id": "hunt-data-staged", "name": "Data Staged for Exfiltration", "tactic": "Collection",
         "technique": "T1074",
         "description": "Identify large data aggregations in temp or staging directories before exfiltration.",
         "data_sources": ["File system events", "Endpoint telemetry"], "status": "active"},
        # C2
        {"id": "hunt-c2-beacon", "name": "C2 Beacon / Encrypted Channel", "tactic": "Command and Control",
         "technique": "T1071", "subtechniques": ["T1071.001", "T1071.004"],
         "description": "Hunt for periodic beaconing patterns and non-standard encrypted C2 channels.",
         "data_sources": ["Network flow logs", "DNS logs", "Proxy logs"], "status": "active"},
        {"id": "hunt-dns-tunneling", "name": "DNS Tunneling", "tactic": "Command and Control",
         "technique": "T1071.004",
         "description": "Detect excessively long DNS queries or high-frequency DNS lookups used for tunneling.",
         "data_sources": ["DNS logs", "Network flow logs"], "status": "active"},
        # Exfiltration
        {"id": "hunt-exfiltration", "name": "Data Exfiltration over HTTPS/DNS", "tactic": "Exfiltration",
         "technique": "T1041",
         "description": "Detect large outbound data transfers to untrusted external hosts.",
         "data_sources": ["Network flow logs", "Proxy logs", "Firewall logs"], "status": "active"},
        # Impact
        {"id": "hunt-ransomware", "name": "Ransomware / Data Encryption", "tactic": "Impact",
         "technique": "T1486",
         "description": "Detect mass file encryption characteristic of ransomware activity.",
         "data_sources": ["File system events", "Endpoint telemetry"], "status": "active"},
    ]
    now = datetime.now(timezone.utc).isoformat()
    for t in templates:
        t.update({"created_at": now, "last_run": now, "tenantId": "global"})
    await db.xdr_hunts.insert_many(templates)


@router.get("/api/xdr/automated-hunts")
async def get_xdr_hunts(current_user: TokenData = Depends(get_current_user)):
    """Get XDR automated hunt statistics from database."""
    db = get_database()
    await _seed_xdr_hunts(db)

    findings = await db.xdr_findings.count_documents({})
    threats = await db.xdr_threats.count_documents({"confirmed": True})
    hunts = await db.xdr_hunts.count_documents({"status": "active"})
    false_positives = await db.xdr_findings.count_documents({"falsePositive": True})

    return {
        "findingsLast24h": findings,
        "confirmedThreats": threats,
        "activeHunts": hunts,
        "falsePositives": false_positives,
    }

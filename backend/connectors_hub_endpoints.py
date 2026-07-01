"""Connectors Hub Endpoints — /api/connectors-hub/"""
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from authentication_service import get_current_user, TokenData
from database import get_database
from datetime import datetime, timezone
from typing import Optional, List
import random
import uuid

router = APIRouter(prefix="/api/connectors-hub", tags=["Connectors Hub"])

# ---------------------------------------------------------------------------
# Connector catalog (35 entries)
# ---------------------------------------------------------------------------

CONNECTORS_CATALOG: List[dict] = [
    # Microsoft
    {
        "connector_id": "microsoft-defender-endpoint",
        "name": "Microsoft Defender for Endpoint",
        "vendor": "Microsoft",
        "category": "microsoft",
        "description": "EDR telemetry — device events, alerts, and advanced hunting from MDE",
        "requires_fields": ["tenant_id", "client_id", "client_secret"],
        "data_types": ["DeviceEvents", "DeviceAlertEvents", "DeviceNetworkEvents"],
    },
    {
        "connector_id": "microsoft-defender-office365",
        "name": "Microsoft Defender for Office 365",
        "vendor": "Microsoft",
        "category": "microsoft",
        "description": "Email threat intelligence — phishing, malware, and safe-links events",
        "requires_fields": ["tenant_id", "client_id", "client_secret"],
        "data_types": ["EmailEvents", "EmailAttachmentInfo", "UrlClickEvents"],
    },
    {
        "connector_id": "microsoft-defender-identity",
        "name": "Microsoft Defender for Identity",
        "vendor": "Microsoft",
        "category": "microsoft",
        "description": "Identity threat detection — lateral movement and pass-the-hash alerts",
        "requires_fields": ["tenant_id", "client_id", "client_secret"],
        "data_types": ["IdentityLogonEvents", "IdentityQueryEvents"],
    },
    {
        "connector_id": "microsoft-defender-cloud-apps",
        "name": "Microsoft Defender for Cloud Apps",
        "vendor": "Microsoft",
        "category": "microsoft",
        "description": "CASB — cloud app usage, shadow IT, and anomalous activity",
        "requires_fields": ["tenant_id", "client_id", "client_secret"],
        "data_types": ["CloudAppEvents", "CloudAppActivity"],
    },
    {
        "connector_id": "microsoft-entra-id",
        "name": "Microsoft Entra ID",
        "vendor": "Microsoft",
        "category": "microsoft",
        "description": "Azure AD sign-in and audit logs for identity monitoring",
        "requires_fields": ["tenant_id", "client_id", "client_secret"],
        "data_types": ["SigninLogs", "AuditLogs", "AADRiskyUsers"],
    },
    {
        "connector_id": "microsoft-intune",
        "name": "Microsoft Intune",
        "vendor": "Microsoft",
        "category": "microsoft",
        "description": "Device compliance and configuration management events",
        "requires_fields": ["tenant_id", "client_id", "client_secret"],
        "data_types": ["IntuneDevices", "IntuneComplianceEvents"],
    },
    {
        "connector_id": "microsoft-365",
        "name": "Microsoft 365",
        "vendor": "Microsoft",
        "category": "microsoft",
        "description": "Unified audit log for Exchange, SharePoint, Teams, and OneDrive",
        "requires_fields": ["tenant_id", "client_id", "client_secret"],
        "data_types": ["OfficeActivity", "SharePointAudit", "TeamsActivity"],
    },
    {
        "connector_id": "azure-monitor",
        "name": "Azure Monitor",
        "vendor": "Microsoft",
        "category": "microsoft",
        "description": "Azure platform logs — activity log, diagnostics, and metrics",
        "requires_fields": ["subscription_id", "client_id", "client_secret", "tenant_id"],
        "data_types": ["AzureActivity", "AzureDiagnostics"],
    },
    {
        "connector_id": "azure-ad",
        "name": "Azure AD",
        "vendor": "Microsoft",
        "category": "microsoft",
        "description": "Legacy Azure Active Directory connector for sign-in and provisioning events",
        "requires_fields": ["tenant_id", "client_id", "client_secret"],
        "data_types": ["SigninLogs", "AuditLogs"],
    },
    # Endpoint Security
    {
        "connector_id": "crowdstrike-falcon",
        "name": "CrowdStrike Falcon",
        "vendor": "CrowdStrike",
        "category": "endpoint",
        "description": "Next-gen EDR — process, network, and file telemetry from Falcon sensor",
        "requires_fields": ["client_id", "client_secret", "base_url"],
        "data_types": ["FDREvent", "DetectionSummary", "IncidentSummary"],
    },
    {
        "connector_id": "sentinelone",
        "name": "SentinelOne",
        "vendor": "SentinelOne",
        "category": "endpoint",
        "description": "AI-powered EDR with deep visibility and autonomous response",
        "requires_fields": ["api_token", "management_url"],
        "data_types": ["Threats", "Activities", "DeepVisibility"],
    },
    {
        "connector_id": "carbon-black",
        "name": "VMware Carbon Black",
        "vendor": "VMware",
        "category": "endpoint",
        "description": "Behavioral EDR with streaming prevention and threat hunting",
        "requires_fields": ["api_key", "org_key", "cb_url"],
        "data_types": ["CBEvents", "CBAlerts", "CBProcesses"],
    },
    {
        "connector_id": "sophos-intercept-x",
        "name": "Sophos Intercept X",
        "vendor": "Sophos",
        "category": "endpoint",
        "description": "Deep learning endpoint protection and threat intelligence",
        "requires_fields": ["client_id", "client_secret"],
        "data_types": ["SophosAlerts", "SophosEvents"],
    },
    {
        "connector_id": "symantec-endpoint",
        "name": "Symantec Endpoint Security",
        "vendor": "Broadcom",
        "category": "endpoint",
        "description": "Enterprise endpoint protection with adaptive threat response",
        "requires_fields": ["api_key", "domain_id"],
        "data_types": ["SEPMEvents", "SEPMAlerts"],
    },
    # Vulnerability
    {
        "connector_id": "qualys-vmdr",
        "name": "Qualys VMDR",
        "vendor": "Qualys",
        "category": "vulnerability",
        "description": "Vulnerability management, detection, and response platform",
        "requires_fields": ["api_key", "username", "password", "platform_url"],
        "data_types": ["QualysFindings", "QualysAssets"],
    },
    {
        "connector_id": "tenable-io",
        "name": "Tenable.io",
        "vendor": "Tenable",
        "category": "vulnerability",
        "description": "Cloud-based vulnerability management and web application scanning",
        "requires_fields": ["access_key", "secret_key"],
        "data_types": ["TenableVulnerabilities", "TenableAssets"],
    },
    {
        "connector_id": "rapid7-insightvm",
        "name": "Rapid7 InsightVM",
        "vendor": "Rapid7",
        "category": "vulnerability",
        "description": "Live vulnerability and endpoint analytics with risk scoring",
        "requires_fields": ["api_key", "base_url"],
        "data_types": ["R7Vulnerabilities", "R7Assets"],
    },
    # Network
    {
        "connector_id": "palo-alto-networks",
        "name": "Palo Alto Networks NGFW",
        "vendor": "Palo Alto Networks",
        "category": "network",
        "description": "Next-gen firewall traffic, threat, and URL filtering logs",
        "requires_fields": ["api_key", "firewall_ip"],
        "data_types": ["PANTrafficLog", "PANThreatLog", "PANURLLog"],
    },
    {
        "connector_id": "fortinet-fortigate",
        "name": "Fortinet FortiGate",
        "vendor": "Fortinet",
        "category": "network",
        "description": "FortiGate firewall and UTM syslog events",
        "requires_fields": ["api_token", "fortigate_ip"],
        "data_types": ["FGTTrafficLog", "FGTEventLog", "FGTUTMLog"],
    },
    {
        "connector_id": "check-point",
        "name": "Check Point Firewall",
        "vendor": "Check Point",
        "category": "network",
        "description": "Check Point firewall traffic and IPS log export",
        "requires_fields": ["api_key", "management_server"],
        "data_types": ["CPTrafficLog", "CPIPSLog"],
    },
    {
        "connector_id": "cisco-asa",
        "name": "Cisco ASA",
        "vendor": "Cisco",
        "category": "network",
        "description": "Cisco ASA firewall syslog and VPN events",
        "requires_fields": ["syslog_host", "syslog_port"],
        "data_types": ["CiscoASALog", "CiscoVPNLog"],
    },
    {
        "connector_id": "zscaler-zia",
        "name": "Zscaler ZIA",
        "vendor": "Zscaler",
        "category": "network",
        "description": "Cloud-based SWG and CASB web traffic and DLP logs",
        "requires_fields": ["api_key", "cloud_name"],
        "data_types": ["ZIAWebLog", "ZIADNSLog", "ZIAFirewallLog"],
    },
    {
        "connector_id": "cisco-umbrella",
        "name": "Cisco Umbrella",
        "vendor": "Cisco",
        "category": "network",
        "description": "DNS-layer security and cloud-delivered secure web gateway",
        "requires_fields": ["api_key", "api_secret", "org_id"],
        "data_types": ["UmbrellaDNSLog", "UmbrellaProxyLog"],
    },
    # Cloud
    {
        "connector_id": "aws-cloudtrail",
        "name": "AWS CloudTrail",
        "vendor": "Amazon",
        "category": "cloud",
        "description": "AWS API activity logging for governance, compliance, and auditing",
        "requires_fields": ["aws_access_key_id", "aws_secret_access_key", "region", "s3_bucket"],
        "data_types": ["AWSCloudTrailLog"],
    },
    {
        "connector_id": "aws-security-hub",
        "name": "AWS Security Hub",
        "vendor": "Amazon",
        "category": "cloud",
        "description": "Aggregated security findings from AWS services and partners",
        "requires_fields": ["aws_access_key_id", "aws_secret_access_key", "region"],
        "data_types": ["AWSSecurityFinding"],
    },
    {
        "connector_id": "gcp-audit-logs",
        "name": "GCP Audit Logs",
        "vendor": "Google",
        "category": "cloud",
        "description": "Google Cloud admin activity, data access, and system event logs",
        "requires_fields": ["service_account_json", "project_id"],
        "data_types": ["GCPAdminActivity", "GCPDataAccess"],
    },
    {
        "connector_id": "gcp-security-command-center",
        "name": "GCP Security Command Center",
        "vendor": "Google",
        "category": "cloud",
        "description": "GCP risk dashboard and threat intelligence findings",
        "requires_fields": ["service_account_json", "organization_id"],
        "data_types": ["GCPSCCFinding"],
    },
    # ITSM
    {
        "connector_id": "servicenow",
        "name": "ServiceNow",
        "vendor": "ServiceNow",
        "category": "itsm",
        "description": "Bi-directional incident and change management ticket integration",
        "requires_fields": ["instance_url", "username", "password"],
        "data_types": ["SNowIncident", "SNowChange"],
    },
    {
        "connector_id": "jira",
        "name": "Jira",
        "vendor": "Atlassian",
        "category": "itsm",
        "description": "Security case management via Jira issue tracking",
        "requires_fields": ["base_url", "api_token", "email"],
        "data_types": ["JiraIssue"],
    },
    {
        "connector_id": "freshservice",
        "name": "Freshservice",
        "vendor": "Freshworks",
        "category": "itsm",
        "description": "IT service management with automated ticket creation from alerts",
        "requires_fields": ["api_key", "domain"],
        "data_types": ["FreshserviceTicket"],
    },
    {
        "connector_id": "thehive",
        "name": "TheHive",
        "vendor": "StrangeBee",
        "category": "itsm",
        "description": "Open-source SOAR and incident response platform for security teams",
        "requires_fields": ["api_key", "thehive_url"],
        "data_types": ["TheHiveAlert", "TheHiveCase", "TheHiveObservable"],
    },
    {
        "connector_id": "pagerduty",
        "name": "PagerDuty",
        "vendor": "PagerDuty",
        "category": "itsm",
        "description": "Incident management and on-call alerting for critical security events",
        "requires_fields": ["api_key", "service_key"],
        "data_types": ["PagerDutyIncident", "PagerDutyAlert"],
    },
    # Threat Intel
    {
        "connector_id": "virustotal",
        "name": "VirusTotal",
        "vendor": "Google",
        "category": "threat_intel",
        "description": "File, URL, IP, and domain reputation via VirusTotal API",
        "requires_fields": ["api_key"],
        "data_types": ["VTFileReport", "VTURLReport", "VTIPReport"],
    },
    {
        "connector_id": "misp",
        "name": "MISP Threat Intelligence",
        "vendor": "MISP Project",
        "category": "threat_intel",
        "description": "Open-source threat intelligence sharing platform",
        "requires_fields": ["api_key", "misp_url"],
        "data_types": ["MISPEvent", "MISPAttribute"],
    },
    {
        "connector_id": "alienvault-otx",
        "name": "AlienVault OTX",
        "vendor": "AT&T Cybersecurity",
        "category": "threat_intel",
        "description": "Open threat exchange — community threat intelligence pulses",
        "requires_fields": ["api_key"],
        "data_types": ["OTXPulse", "OTXIndicator"],
    },
    # Log Sources
    {
        "connector_id": "syslog-cef",
        "name": "Syslog CEF",
        "vendor": "Generic",
        "category": "log_source",
        "description": "Common Event Format syslog receiver for generic security devices",
        "requires_fields": ["syslog_host", "syslog_port"],
        "data_types": ["CEFEvent"],
    },
    {
        "connector_id": "windows-event-forwarding",
        "name": "Windows Event Forwarding",
        "vendor": "Microsoft",
        "category": "log_source",
        "description": "WEF-based Windows security event collection via WEC",
        "requires_fields": ["wec_server", "subscription_name"],
        "data_types": ["SecurityEvent", "SystemEvent", "ApplicationEvent"],
    },
    {
        "connector_id": "splunk-hec",
        "name": "Splunk HEC",
        "vendor": "Splunk",
        "category": "log_source",
        "description": "Ingest events from Splunk via HTTP Event Collector forwarding",
        "requires_fields": ["hec_url", "hec_token"],
        "data_types": ["SplunkEvent"],
    },
]

# Build a quick lookup by connector_id
_CATALOG_MAP = {c["connector_id"]: c for c in CONNECTORS_CATALOG}

VALID_CATEGORIES = {
    "microsoft", "endpoint", "vulnerability", "network",
    "cloud", "itsm", "threat_intel", "log_source",
}


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class ConfigureRequest(BaseModel):
    config: dict


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _strip_id(doc: dict) -> dict:
    doc.pop("_id", None)
    return doc


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/")
async def list_connectors(
    category: Optional[str] = Query(None, description="Filter by category"),
    current_user: TokenData = Depends(get_current_user),
):
    """Return catalog entries merged with tenant-saved connector configs."""
    if category and category not in VALID_CATEGORIES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid category. Must be one of: {sorted(VALID_CATEGORIES)}",
        )

    db = get_database()
    # Load all saved configs for this tenant
    configs: dict = {}
    cursor = db.connector_configs.find({"tenantId": current_user.tenant_id})
    async for doc in cursor:
        configs[doc["connector_id"]] = doc

    results = []
    for entry in CONNECTORS_CATALOG:
        if category and entry["category"] != category:
            continue
        merged = dict(entry)
        saved = configs.get(entry["connector_id"])
        if saved:
            merged["enabled"] = saved.get("enabled", False)
            merged["status"] = saved.get("status", "disconnected")
            merged["last_sync"] = saved.get("last_sync")
            merged["sync_count"] = saved.get("sync_count", 0)
            merged["error_message"] = saved.get("error_message")
        else:
            merged["enabled"] = False
            merged["status"] = "disconnected"
            merged["last_sync"] = None
            merged["sync_count"] = 0
            merged["error_message"] = None
        results.append(merged)

    return results


@router.post("/{connector_id}/configure", status_code=200)
async def configure_connector(
    connector_id: str,
    body: ConfigureRequest,
    current_user: TokenData = Depends(get_current_user),
):
    """Save or update connector configuration."""
    catalog_entry = _CATALOG_MAP.get(connector_id)
    if not catalog_entry:
        raise HTTPException(status_code=404, detail=f"Connector '{connector_id}' not found in catalog")

    # Validate required fields
    missing = [f for f in catalog_entry["requires_fields"] if f not in body.config]
    if missing:
        raise HTTPException(
            status_code=422,
            detail=f"Missing required config fields: {missing}",
        )

    db = get_database()
    now = _now_iso()
    existing = await db.connector_configs.find_one(
        {"connector_id": connector_id, "tenantId": current_user.tenant_id}
    )

    if existing:
        await db.connector_configs.update_one(
            {"connector_id": connector_id, "tenantId": current_user.tenant_id},
            {"$set": {"config": body.config, "status": "pending", "updated_at": now}},
        )
    else:
        await db.connector_configs.insert_one({
            "id": str(uuid.uuid4()),
            "tenantId": current_user.tenant_id,
            "connector_id": connector_id,
            "enabled": False,
            "config": body.config,
            "status": "pending",
            "last_sync": None,
            "sync_count": 0,
            "error_message": None,
            "created_at": now,
            "updated_at": now,
        })

    return {"connector_id": connector_id, "status": "pending", "message": "Configuration saved"}


@router.post("/{connector_id}/test")
async def test_connector(
    connector_id: str,
    current_user: TokenData = Depends(get_current_user),
):
    """Mock connection test — checks for presence of an api_key or api_token."""
    if connector_id not in _CATALOG_MAP:
        raise HTTPException(status_code=404, detail=f"Connector '{connector_id}' not found in catalog")

    db = get_database()
    saved = await db.connector_configs.find_one(
        {"connector_id": connector_id, "tenantId": current_user.tenant_id}
    )

    if not saved:
        raise HTTPException(status_code=400, detail="Connector is not configured. Call /configure first.")

    config = saved.get("config", {})
    has_credential = any(
        k in config for k in ("api_key", "api_token", "client_secret", "access_key", "hec_token", "service_account_json")
    )

    if has_credential:
        new_status = "connected"
        error_msg = None
        msg = "Connection successful"
    else:
        new_status = "error"
        error_msg = "No valid API key or token found in configuration"
        msg = error_msg

    await db.connector_configs.update_one(
        {"connector_id": connector_id, "tenantId": current_user.tenant_id},
        {"$set": {"status": new_status, "error_message": error_msg, "updated_at": _now_iso()}},
    )

    return {"connector_id": connector_id, "status": new_status, "message": msg}


@router.post("/{connector_id}/enable")
async def enable_connector(
    connector_id: str,
    current_user: TokenData = Depends(get_current_user),
):
    """Enable a connector and mark it connected."""
    if connector_id not in _CATALOG_MAP:
        raise HTTPException(status_code=404, detail=f"Connector '{connector_id}' not found in catalog")

    db = get_database()
    result = await db.connector_configs.update_one(
        {"connector_id": connector_id, "tenantId": current_user.tenant_id},
        {"$set": {"enabled": True, "status": "connected", "updated_at": _now_iso()}},
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=400, detail="Connector not configured. Call /configure first.")
    return {"connector_id": connector_id, "enabled": True, "status": "connected"}


@router.post("/{connector_id}/disable")
async def disable_connector(
    connector_id: str,
    current_user: TokenData = Depends(get_current_user),
):
    """Disable a connector."""
    if connector_id not in _CATALOG_MAP:
        raise HTTPException(status_code=404, detail=f"Connector '{connector_id}' not found in catalog")

    db = get_database()
    result = await db.connector_configs.update_one(
        {"connector_id": connector_id, "tenantId": current_user.tenant_id},
        {"$set": {"enabled": False, "updated_at": _now_iso()}},
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=400, detail="Connector not configured. Call /configure first.")
    return {"connector_id": connector_id, "enabled": False}


@router.post("/{connector_id}/sync")
async def sync_connector(
    connector_id: str,
    current_user: TokenData = Depends(get_current_user),
):
    """Mock data pull — increments sync count and updates last_sync timestamp."""
    if connector_id not in _CATALOG_MAP:
        raise HTTPException(status_code=404, detail=f"Connector '{connector_id}' not found in catalog")

    db = get_database()
    saved = await db.connector_configs.find_one(
        {"connector_id": connector_id, "tenantId": current_user.tenant_id}
    )
    if not saved:
        raise HTTPException(status_code=400, detail="Connector not configured. Call /configure first.")

    if not saved.get("enabled"):
        raise HTTPException(status_code=400, detail="Connector is disabled. Enable it before syncing.")

    records_pulled = random.randint(10, 500)
    now = _now_iso()

    await db.connector_configs.update_one(
        {"connector_id": connector_id, "tenantId": current_user.tenant_id},
        {"$inc": {"sync_count": 1}, "$set": {"last_sync": now, "status": "connected"}},
    )

    return {
        "synced": True,
        "records_pulled": records_pulled,
        "connector_id": connector_id,
        "synced_at": now,
    }


@router.get("/stats")
async def get_stats(current_user: TokenData = Depends(get_current_user)):
    """Return aggregated connector statistics for the tenant."""
    db = get_database()
    tenant_filter = {"tenantId": current_user.tenant_id}

    configured = await db.connector_configs.count_documents(tenant_filter)
    connected = await db.connector_configs.count_documents({**tenant_filter, "status": "connected"})
    disconnected = await db.connector_configs.count_documents({**tenant_filter, "status": "disconnected"})
    errors = await db.connector_configs.count_documents({**tenant_filter, "status": "error"})

    by_category: dict = {}
    for cat in VALID_CATEGORIES:
        connector_ids_in_cat = [c["connector_id"] for c in CONNECTORS_CATALOG if c["category"] == cat]
        count = await db.connector_configs.count_documents(
            {**tenant_filter, "connector_id": {"$in": connector_ids_in_cat}, "status": "connected"}
        )
        by_category[cat] = count

    return {
        "total": len(CONNECTORS_CATALOG),
        "configured": configured,
        "connected": connected,
        "disconnected": disconnected,
        "errors": errors,
        "by_category": by_category,
    }

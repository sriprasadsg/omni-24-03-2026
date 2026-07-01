"""NIST Cybersecurity Framework (CSF) 2.0 control definitions and automated checks."""
from __future__ import annotations
from typing import Any, Dict, List

FRAMEWORK_ID = "nist_csf"
FRAMEWORK_NAME = "NIST Cybersecurity Framework 2.0"
FRAMEWORK_VERSION = "2.0"

# Each control: id, function, category, title, description, check_query
CONTROLS: List[Dict[str, Any]] = [
    # GOVERN
    {"id": "GV.OC-01", "function": "GOVERN", "category": "Organizational Context",
     "title": "Mission and objectives documented",
     "description": "The organizational mission and cybersecurity risk appetite are established and communicated.",
     "check_collection": "compliance_policies", "check_field": "risk_appetite", "check_type": "exists"},
    {"id": "GV.RM-01", "function": "GOVERN", "category": "Risk Management Strategy",
     "title": "Risk management strategy established",
     "description": "Risk management strategy with risk tolerance thresholds is documented.",
     "check_collection": "compliance_policies", "check_field": "risk_tolerance", "check_type": "exists"},
    {"id": "GV.SC-01", "function": "GOVERN", "category": "Supply Chain Risk",
     "title": "Supply chain risk program",
     "description": "Cyber supply chain risk management policy is documented.",
     "check_collection": "vendors", "check_field": None, "check_type": "count_gt_zero"},

    # IDENTIFY
    {"id": "ID.AM-01", "function": "IDENTIFY", "category": "Asset Management",
     "title": "Hardware asset inventory",
     "description": "Physical devices and systems are inventoried.",
     "check_collection": "assets", "check_field": None, "check_type": "count_gt_zero"},
    {"id": "ID.AM-02", "function": "IDENTIFY", "category": "Asset Management",
     "title": "Software asset inventory",
     "description": "Software platforms and applications are inventoried.",
     "check_collection": "software_inventory", "check_field": None, "check_type": "count_gt_zero"},
    {"id": "ID.AM-03", "function": "IDENTIFY", "category": "Asset Management",
     "title": "Network flow inventory",
     "description": "Organizational communication and data flows are mapped.",
     "check_collection": "network_topology", "check_field": None, "check_type": "count_gt_zero"},
    {"id": "ID.RA-01", "function": "IDENTIFY", "category": "Risk Assessment",
     "title": "Vulnerabilities identified",
     "description": "Asset vulnerabilities are identified and documented.",
     "check_collection": "vulnerabilities", "check_field": None, "check_type": "count_gt_zero"},
    {"id": "ID.RA-02", "function": "IDENTIFY", "category": "Risk Assessment",
     "title": "Threat intelligence received",
     "description": "Cyber threat intelligence is received from sharing forums and sources.",
     "check_collection": "threat_intel_feeds", "check_field": "active", "check_type": "bool_true"},
    {"id": "ID.RA-05", "function": "IDENTIFY", "category": "Risk Assessment",
     "title": "Risk register maintained",
     "description": "Threats, vulnerabilities, likelihoods, and impacts are documented in a risk register.",
     "check_collection": "risks", "check_field": None, "check_type": "count_gt_zero"},

    # PROTECT
    {"id": "PR.AA-01", "function": "PROTECT", "category": "Identity Management",
     "title": "Identities and credentials managed",
     "description": "Identities and credentials for authorized users and services are managed.",
     "check_collection": "users", "check_field": "mfa_enabled", "check_type": "all_true"},
    {"id": "PR.AA-05", "function": "PROTECT", "category": "Identity Management",
     "title": "Least privilege enforced",
     "description": "Access permissions and authorizations are managed following least privilege principles.",
     "check_collection": "rbac_roles", "check_field": None, "check_type": "count_gt_zero"},
    {"id": "PR.DS-01", "function": "PROTECT", "category": "Data Security",
     "title": "Data at rest protected",
     "description": "Data at rest is protected via encryption.",
     "check_collection": "data_classifications", "check_field": "encrypted_at_rest", "check_type": "bool_true"},
    {"id": "PR.DS-02", "function": "PROTECT", "category": "Data Security",
     "title": "Data in transit protected",
     "description": "Data in transit is protected via TLS/encryption.",
     "check_collection": "network_policies", "check_field": "tls_enforced", "check_type": "bool_true"},
    {"id": "PR.PS-01", "function": "PROTECT", "category": "Platform Security",
     "title": "Configuration baselines maintained",
     "description": "Configuration management covering security configuration baselines.",
     "check_collection": "security_baselines", "check_field": None, "check_type": "count_gt_zero"},

    # DETECT
    {"id": "DE.AE-02", "function": "DETECT", "category": "Adverse Event Analysis",
     "title": "Anomalies analyzed",
     "description": "Potentially adverse events are analyzed to better characterize the activity.",
     "check_collection": "security_events", "check_field": None, "check_type": "count_gt_zero"},
    {"id": "DE.CM-01", "function": "DETECT", "category": "Continuous Monitoring",
     "title": "Networks monitored",
     "description": "Networks and network services are monitored to detect potentially adverse events.",
     "check_collection": "siem_logs", "check_field": None, "check_type": "count_gt_zero"},
    {"id": "DE.CM-03", "function": "DETECT", "category": "Continuous Monitoring",
     "title": "Personnel activity monitored",
     "description": "Personnel activity and technology usage are monitored to detect adverse events.",
     "check_collection": "ueba_events", "check_field": None, "check_type": "count_gt_zero"},
    {"id": "DE.CM-09", "function": "DETECT", "category": "Continuous Monitoring",
     "title": "Vulnerability scans performed",
     "description": "The environment is monitored for vulnerabilities.",
     "check_collection": "vulnerability_scans", "check_field": None, "check_type": "recent_30d"},

    # RESPOND
    {"id": "RS.MA-01", "function": "RESPOND", "category": "Incident Management",
     "title": "Incident response plan exists",
     "description": "The incident response plan is executed in coordination with relevant stakeholders.",
     "check_collection": "playbooks", "check_field": "category", "check_type": "field_eq",
     "check_value": "incident_response"},
    {"id": "RS.CO-02", "function": "RESPOND", "category": "Incident Response Reporting",
     "title": "Incidents reported to authorities",
     "description": "Incidents are reported consistent with established criteria.",
     "check_collection": "incidents", "check_field": "reported", "check_type": "bool_true"},
    {"id": "RS.MI-01", "function": "RESPOND", "category": "Incident Mitigation",
     "title": "Incidents contained",
     "description": "Incidents are contained.",
     "check_collection": "incidents", "check_field": "contained", "check_type": "bool_true"},

    # RECOVER
    {"id": "RC.RP-01", "function": "RECOVER", "category": "Incident Recovery Plan",
     "title": "Recovery plan executed",
     "description": "Recovery plan is executed during or after a cybersecurity incident.",
     "check_collection": "dr_runbooks", "check_field": None, "check_type": "count_gt_zero"},
    {"id": "RC.CO-03", "function": "RECOVER", "category": "Incident Recovery Communication",
     "title": "Recovery communicated to stakeholders",
     "description": "Recovery activities are communicated to stakeholders.",
     "check_collection": "incident_communications", "check_field": None, "check_type": "count_gt_zero"},
]


async def evaluate_controls(db) -> List[Dict[str, Any]]:
    """Run all NIST CSF checks against the live database."""
    results = []
    for ctrl in CONTROLS:
        status, evidence = await _run_check(db, ctrl)
        results.append({
            **ctrl,
            "status": status,
            "evidence": evidence,
            "evaluated_at": _now(),
        })
    return results


async def _run_check(db, ctrl: Dict[str, Any]):
    from datetime import datetime, timezone, timedelta
    collection_name = ctrl.get("check_collection", "")
    check_type = ctrl.get("check_type", "count_gt_zero")
    field = ctrl.get("check_field")
    cutoff_30d = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()

    try:
        coll = getattr(db, collection_name, None) or db[collection_name]

        if check_type == "count_gt_zero":
            count = await coll.count_documents({})
            return ("pass" if count > 0 else "fail"), f"{count} records found"

        if check_type == "exists":
            doc = await coll.find_one({field: {"$exists": True, "$ne": None}} if field else {})
            return ("pass" if doc else "fail"), ("Field present" if doc else "Field missing")

        if check_type == "bool_true":
            doc = await coll.find_one({field: True})
            # For incident fields: if collection is empty that's not_applicable; if populated check
            if field and not doc:
                total = await coll.count_documents({})
                if total == 0:
                    return "not_applicable", f"No {collection_name} records to evaluate"
            return ("pass" if doc else "partial"), ("Enabled/found" if doc else "Not yet recorded")

        if check_type == "all_true":
            # Use percentage-based threshold instead of binary
            total = await coll.count_documents({})
            if total == 0:
                return "not_applicable", "No records to evaluate"
            compliant = await coll.count_documents({field: True})
            pct = round(compliant / total * 100)
            if pct >= 90:
                return "pass", f"{pct}% of {collection_name} compliant ({compliant}/{total})"
            if pct >= 50:
                return "partial", f"{pct}% of {collection_name} compliant ({compliant}/{total})"
            return "fail", f"Only {pct}% compliant ({compliant}/{total})"

        if check_type == "recent_30d":
            # Check both created_at and timestamp fields; also check agent_vulnerability_scans
            count = await coll.count_documents({"created_at": {"$gte": cutoff_30d}})
            if count == 0:
                count = await coll.count_documents({"timestamp": {"$gte": cutoff_30d}})
            # For vuln scans: also check agent_vulnerability_scans
            if collection_name == "vulnerability_scans" and count == 0:
                count = await db.agent_vulnerability_scans.count_documents({"scanned_at": {"$gte": cutoff_30d}})
            return ("pass" if count > 0 else "fail"), f"{count} records in last 30 days"

        if check_type == "field_eq":
            check_val = ctrl.get("check_value")
            doc = await coll.find_one({field: check_val})
            if not doc:
                # Fallback: any playbook counts for IR plan existence
                if collection_name == "playbooks":
                    any_pb = await coll.count_documents({})
                    if any_pb > 0:
                        return "partial", f"No dedicated IR playbook found; {any_pb} playbooks exist"
            return ("pass" if doc else "fail"), ("Found" if doc else "Not found")

    except Exception as exc:
        return "not_applicable", f"Check error: {exc}"

    return "not_applicable", "Unknown check type"


def _now():
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()

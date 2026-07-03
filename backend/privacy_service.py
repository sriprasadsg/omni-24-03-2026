"""
GDPR / CCPA Privacy Module Service
Handles data subject requests (DSR), consent management, data inventory,
retention policies, and breach notification obligations.
"""

import uuid
import logging
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

from database import get_database

logger = logging.getLogger(__name__)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _gen_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


def _fail_closed_tenant_id(tenant_id: Optional[str]) -> str:
    """Fail-closed tenant_id for TIA/LIA/Notice/Contract collections, which are
    accessed via the raw db._db.<collection> (not the TenantIsolatedCollection
    wrapper). Mirrors TenantIsolatedCollection's own sentinel in database.py so
    callers with no tenant context (e.g. platform-admin accounts whose
    TokenData.tenant_id is None) never collide on a shared `tenantId: None`
    partition."""
    return tenant_id or "NON_EXISTENT_TENANT_ISOLATION_EMERGENCY"

DSR_TYPES = {
    "access": {"name": "Right of Access (Art. 15 GDPR)", "sla_days": 30},
    "erasure": {"name": "Right to Erasure / Right to be Forgotten (Art. 17 GDPR / CCPA)", "sla_days": 30},
    "portability": {"name": "Right to Data Portability (Art. 20 GDPR)", "sla_days": 30},
    "rectification": {"name": "Right to Rectification (Art. 16 GDPR)", "sla_days": 30},
    "restriction": {"name": "Right to Restrict Processing (Art. 18 GDPR)", "sla_days": 30},
    "objection": {"name": "Right to Object (Art. 21 GDPR)", "sla_days": 30},
    "opt_out_sale": {"name": "Right to Opt-Out of Sale (CCPA)", "sla_days": 15},
    "know": {"name": "Right to Know (CCPA)", "sla_days": 45},
}

DSR_STATUSES = ["received", "identity_verified", "in_progress", "completed", "denied", "withdrawn"]

DATA_CATEGORIES = [
    "name", "email", "phone", "address", "ip_address", "device_id",
    "location_data", "financial_data", "health_data", "biometric_data",
    "behavioral_data", "preferences", "communications", "employment_data",
    "special_category",
]

LEGAL_BASES = [
    "consent", "contract", "legal_obligation", "vital_interests",
    "public_task", "legitimate_interests",
]

RETENTION_PERIODS = {
    "logs": 90,
    "audit_events": 365,
    "user_accounts": 1825,  # 5 years
    "compliance_evidence": 2190,  # 6 years
    "security_events": 365,
    "billing_records": 2555,  # 7 years
}


# ── Data Subject Requests ──────────────────────────────────────────────────────

async def create_dsr(tenant_id: str, submitted_by: str, data: Dict[str, Any]) -> Dict[str, Any]:
    db = get_database()
    dsr_type = data.get("type", "access")
    if dsr_type not in DSR_TYPES:
        raise ValueError(f"Invalid DSR type. Choose from: {list(DSR_TYPES.keys())}")

    now = datetime.now(timezone.utc)
    sla_days = DSR_TYPES[dsr_type]["sla_days"]
    due_date = now + timedelta(days=sla_days)

    dsr = {
        "id": str(uuid.uuid4()),
        "tenant_id": tenant_id,
        "reference_number": f"DSR-{now.strftime('%Y%m')}-{str(uuid.uuid4())[:6].upper()}",
        "type": dsr_type,
        "type_name": DSR_TYPES[dsr_type]["name"],
        "status": "received",
        "subject_name": data.get("subject_name", ""),
        "subject_email": data.get("subject_email", ""),
        "subject_identifier": data.get("subject_identifier", ""),
        "regulation": data.get("regulation", "GDPR"),
        "description": data.get("description", ""),
        "submitted_by": submitted_by,
        "submitted_at": now.isoformat(),
        "due_date": due_date.isoformat(),
        "sla_days": sla_days,
        "assigned_to": data.get("assigned_to", ""),
        "identity_verified": False,
        "identity_verified_at": None,
        "completed_at": None,
        "deny_reason": None,
        "data_categories_affected": data.get("data_categories", []),
        "response_notes": "",
        "is_overdue": False,
        "audit_trail": [
            {
                "event": "received",
                "actor": submitted_by,
                "timestamp": now.isoformat(),
                "detail": f"DSR received: {DSR_TYPES[dsr_type]['name']}",
            }
        ],
    }

    await db.data_subject_requests.insert_one(dsr)
    logger.info("[Privacy] DSR %s created: %s", dsr["reference_number"], dsr_type)
    return dsr


async def update_dsr_status(
    dsr_id: str, actor: str, tenant_id: str, role: str, new_status: str, note: str = ""
) -> bool:
    db = get_database()
    query = {"id": dsr_id}
    if role != "super_admin":
        query["tenant_id"] = tenant_id

    dsr = await db.data_subject_requests.find_one(query)
    if not dsr:
        return False

    now = datetime.now(timezone.utc)
    update = {"status": new_status}

    if new_status == "identity_verified":
        update["identity_verified"] = True
        update["identity_verified_at"] = now.isoformat()
    elif new_status == "completed":
        update["completed_at"] = now.isoformat()
    elif new_status == "denied":
        update["deny_reason"] = note

    await db.data_subject_requests.update_one(
        {"id": dsr_id},
        {
            "$set": update,
            "$push": {
                "audit_trail": {
                    "event": new_status,
                    "actor": actor,
                    "timestamp": now.isoformat(),
                    "detail": note or f"Status changed to {new_status}",
                }
            },
        },
    )
    return True


async def list_dsrs(tenant_id: str, role: str, status: Optional[str] = None) -> List[Dict[str, Any]]:
    db = get_database()
    query = {} if role == "super_admin" else {"tenant_id": tenant_id}
    if status:
        query["status"] = status

    now = datetime.now(timezone.utc).isoformat()
    dsrs = await db.data_subject_requests.find(query).sort("submitted_at", -1).to_list(length=500)
    for d in dsrs:
        d["_id"] = str(d["_id"])
        d["is_overdue"] = (
            d["status"] not in ("completed", "denied", "withdrawn")
            and d.get("due_date", "") < now
        )
    return dsrs


# ── Consent Management ─────────────────────────────────────────────────────────

async def record_consent(tenant_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
    db = get_database()
    now = datetime.now(timezone.utc)
    consent = {
        "id": str(uuid.uuid4()),
        "tenant_id": tenant_id,
        "subject_id": data.get("subject_id", ""),
        "subject_email": data.get("subject_email", ""),
        "purpose": data.get("purpose", ""),
        "legal_basis": data.get("legal_basis", "consent"),
        "data_categories": data.get("data_categories", []),
        "granted": data.get("granted", True),
        "consent_version": data.get("consent_version", "1.0"),
        "source": data.get("source", "platform"),
        "ip_address": data.get("ip_address", ""),
        "recorded_at": now.isoformat(),
        "expires_at": data.get("expires_at"),
        "withdrawn_at": None,
    }
    await db.consent_records.insert_one(consent)
    return consent


async def withdraw_consent(consent_id: str, tenant_id: str, role: str) -> bool:
    db = get_database()
    query = {"id": consent_id}
    if role != "super_admin":
        query["tenant_id"] = tenant_id
    result = await db.consent_records.update_one(
        query,
        {"$set": {"granted": False, "withdrawn_at": datetime.now(timezone.utc).isoformat()}},
    )
    return result.modified_count > 0


# ── Data Inventory / Processing Activities ─────────────────────────────────────

async def create_processing_activity(tenant_id: str, created_by: str, data: Dict[str, Any]) -> Dict[str, Any]:
    db = get_database()
    activity = {
        "id": str(uuid.uuid4()),
        "tenant_id": tenant_id,
        "name": data.get("name", ""),
        "description": data.get("description", ""),
        "purpose": data.get("purpose", ""),
        "legal_basis": data.get("legal_basis", "legitimate_interests"),
        "data_categories": data.get("data_categories", []),
        "data_subjects": data.get("data_subjects", []),
        "recipients": data.get("recipients", []),
        "third_countries": data.get("third_countries", []),
        "retention_period_days": data.get("retention_period_days", 365),
        "security_measures": data.get("security_measures", []),
        "dpia_required": data.get("dpia_required", False),
        "dpia_completed": data.get("dpia_completed", False),
        "created_by": created_by,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "status": "active",
    }
    await db.processing_activities.insert_one(activity)
    return activity


async def list_processing_activities(tenant_id: str, role: str) -> List[Dict[str, Any]]:
    db = get_database()
    query = {} if role == "super_admin" else {"tenant_id": tenant_id}
    activities = await db.processing_activities.find(query).sort("created_at", -1).to_list(length=200)
    for a in activities:
        a["_id"] = str(a["_id"])
    return activities


# ── Breach Notifications ───────────────────────────────────────────────────────

async def create_breach_notification(tenant_id: str, reported_by: str, data: Dict[str, Any]) -> Dict[str, Any]:
    db = get_database()
    now = datetime.now(timezone.utc)
    # GDPR requires notification to supervisory authority within 72 hours
    authority_deadline = now + timedelta(hours=72)

    breach = {
        "id": str(uuid.uuid4()),
        "tenant_id": tenant_id,
        "reference": f"BREACH-{now.strftime('%Y%m%d')}-{str(uuid.uuid4())[:6].upper()}",
        "reported_by": reported_by,
        "reported_at": now.isoformat(),
        "incident_date": data.get("incident_date", now.isoformat()),
        "discovered_date": data.get("discovered_date", now.isoformat()),
        "description": data.get("description", ""),
        "breach_type": data.get("breach_type", "unauthorized_access"),
        "data_categories_affected": data.get("data_categories_affected", []),
        "estimated_subjects_affected": data.get("estimated_subjects_affected", 0),
        "authority_notified": False,
        "authority_notification_deadline": authority_deadline.isoformat(),
        "authority_notified_at": None,
        "subjects_notified": False,
        "subjects_notified_at": None,
        "notification_required": data.get("notification_required", True),
        "risk_level": data.get("risk_level", "high"),
        "remediation_actions": data.get("remediation_actions", []),
        "status": "open",
        "linked_incident_id": data.get("linked_incident_id", ""),
        "created_at": now.isoformat(),
    }
    await db.breach_notifications.insert_one(breach)
    logger.warning("[Privacy] Breach notification %s created — 72h GDPR deadline: %s", breach["reference"], authority_deadline.isoformat())
    return breach


# ─── Transfer Impact Assessments (TIA) ─────────────────────────────────────────


async def create_tia(db, tenant_id: str, data: dict) -> dict:
    tenant_id = _fail_closed_tenant_id(tenant_id)
    doc = {"id": _gen_id("tia"), "tenantId": tenant_id, "created_at": _now_iso(), "updated_at": _now_iso(), **data}
    if doc.get("risk_level") not in ("low", "medium", "high"):
        raise ValueError("risk_level must be low/medium/high")
    await db._db.privacy_tia.insert_one(doc)
    doc.pop("_id", None)
    return doc


async def list_tia(db, tenant_id: str) -> list:
    tenant_id = _fail_closed_tenant_id(tenant_id)
    return await db._db.privacy_tia.find({"tenantId": tenant_id}, {"_id": 0}).sort("created_at", -1).to_list(length=100)


# ─── Legitimate Interest Assessments (LIA) ─────────────────────────────────────


async def create_lia(db, tenant_id: str, data: dict) -> dict:
    tenant_id = _fail_closed_tenant_id(tenant_id)
    doc = {"id": _gen_id("lia"), "tenantId": tenant_id, "created_at": _now_iso(), "updated_at": _now_iso(), **data}
    await db._db.privacy_lia.insert_one(doc)
    doc.pop("_id", None)
    return doc


async def list_lia(db, tenant_id: str) -> list:
    tenant_id = _fail_closed_tenant_id(tenant_id)
    return await db._db.privacy_lia.find({"tenantId": tenant_id}, {"_id": 0}).sort("created_at", -1).to_list(length=100)


# ─── Privacy Notices ───────────────────────────────────────────────────────────


async def create_notice(db, tenant_id: str, data: dict) -> dict:
    tenant_id = _fail_closed_tenant_id(tenant_id)
    notice_id = _gen_id("notice")
    version = data.get("version", 1)
    doc = {
        "id": notice_id, "tenantId": tenant_id, "title": data.get("title", ""),
        "effective_date": data.get("effective_date"), "applies_to": data.get("applies_to", ""),
        "current_version": version,
        "versions": [{"version": version, "content_html": data.get("content_html", ""), "published_at": _now_iso()}],
        "created_at": _now_iso(), "updated_at": _now_iso(),
    }
    await db._db.privacy_notices.insert_one(doc)
    doc.pop("_id", None)
    return doc


async def list_notices(db, tenant_id: str) -> list:
    tenant_id = _fail_closed_tenant_id(tenant_id)
    return await db._db.privacy_notices.find({"tenantId": tenant_id}, {"_id": 0}).sort("created_at", -1).to_list(length=100)


async def get_notice_versions(db, notice_id: str, tenant_id: str) -> list:
    tenant_id = _fail_closed_tenant_id(tenant_id)
    notice = await db._db.privacy_notices.find_one({"id": notice_id, "tenantId": tenant_id}, {"_id": 0})
    return sorted(notice.get("versions", []), key=lambda v: v.get("version", 0), reverse=True) if notice else []


# ─── Contract Lifecycle ────────────────────────────────────────────────────────


async def create_contract(db, tenant_id: str, data: dict) -> dict:
    tenant_id = _fail_closed_tenant_id(tenant_id)
    valid_types = {"DPA", "MSA", "NDA", "SCC"}
    valid_statuses = {"draft", "review", "signed", "expired"}
    if data.get("type") not in valid_types:
        raise ValueError(f"type must be one of {valid_types}")
    if data.get("status") not in valid_statuses:
        raise ValueError(f"status must be one of {valid_statuses}")
    doc = {"id": _gen_id("contract"), "tenantId": tenant_id, "created_at": _now_iso(), "updated_at": _now_iso(), **data}
    await db._db.privacy_contracts.insert_one(doc)
    doc.pop("_id", None)
    return doc


async def list_contracts(db, tenant_id: str) -> list:
    tenant_id = _fail_closed_tenant_id(tenant_id)
    return await db._db.privacy_contracts.find({"tenantId": tenant_id}, {"_id": 0}).sort("expiry_date", 1).to_list(length=100)


async def get_expiring_contracts(db, tenant_id: str, within_days: int = 30) -> list:
    tenant_id = _fail_closed_tenant_id(tenant_id)
    from datetime import timedelta
    cutoff = (datetime.now(timezone.utc) + timedelta(days=within_days)).strftime("%Y-%m-%d")
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    query = {"tenantId": tenant_id, "expiry_date": {"$lte": cutoff, "$gte": today}}
    return await db._db.privacy_contracts.find(query, {"_id": 0}).sort("expiry_date", 1).to_list(length=100)


async def get_privacy_summary(tenant_id: str, role: str) -> Dict[str, Any]:
    """Lightweight summary used by the PrivacyDashboard header cards."""
    db = get_database()
    query: Dict[str, Any] = {} if role == "super_admin" else {"tenant_id": tenant_id}
    now = datetime.now(timezone.utc).isoformat()

    total_dsrs = await db.data_subject_requests.count_documents(query)
    open_dsrs = await db.data_subject_requests.count_documents({**query, "status": {"$nin": ["completed", "denied", "withdrawn"]}})
    overdue_dsrs = await db.data_subject_requests.count_documents({
        **query,
        "status": {"$nin": ["completed", "denied", "withdrawn"]},
        "due_date": {"$lt": now},
    })
    open_breaches = await db.breach_notifications.count_documents({**query, "status": "open"})
    consent_granted = await db.consent_records.count_documents({**query, "granted": True})
    # Also count user_consents (populated at signup)
    uc_granted = await db.user_consents.count_documents({"status": "granted"})
    consent_granted = max(consent_granted, uc_granted)

    return {
        "total_dsrs": total_dsrs,
        "open_dsrs": open_dsrs,
        "overdue_dsrs": overdue_dsrs,
        "open_breaches": open_breaches,
        "consent_granted": consent_granted,
        "regulations_supported": ["GDPR", "CCPA", "LGPD", "PDPA", "PIPEDA"],
    }


async def get_privacy_dashboard(tenant_id: str, role: str) -> Dict[str, Any]:
    db = get_database()
    query = {} if role == "super_admin" else {"tenant_id": tenant_id}
    now = datetime.now(timezone.utc).isoformat()

    dsr_counts = {}
    for status in DSR_STATUSES:
        dsr_counts[status] = await db.data_subject_requests.count_documents({**query, "status": status})

    overdue_dsrs = await db.data_subject_requests.count_documents({
        **query,
        "status": {"$nin": ["completed", "denied", "withdrawn"]},
        "due_date": {"$lt": now},
    })

    open_breaches = await db.breach_notifications.count_documents({**query, "status": "open"})
    breach_deadlines_missed = await db.breach_notifications.count_documents({
        **query,
        "authority_notified": False,
        "authority_notification_deadline": {"$lt": now},
    })

    total_activities = await db.processing_activities.count_documents(query)
    dpia_pending = await db.processing_activities.count_documents({**query, "dpia_required": True, "dpia_completed": False})

    return {
        "dsr_counts": dsr_counts,
        "total_dsrs": sum(dsr_counts.values()),
        "overdue_dsrs": overdue_dsrs,
        "open_breaches": open_breaches,
        "breach_deadlines_missed": breach_deadlines_missed,
        "processing_activities": total_activities,
        "dpia_pending": dpia_pending,
        "dsr_types": {k: v["name"] for k, v in DSR_TYPES.items()},
        "data_categories": DATA_CATEGORIES,
        "legal_bases": LEGAL_BASES,
        "regulations_supported": ["GDPR", "CCPA", "LGPD", "PDPA", "PIPEDA"],
        "retention_defaults": RETENTION_PERIODS,
    }

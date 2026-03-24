"""
DLP Service — Data Loss Prevention
------------------------------------
Detects PII, bulk data exports, and sensitive data patterns.
"""

import re
import hashlib
import uuid
from datetime import datetime, timezone
from typing import Optional
from database import get_database

# ─── PII Pattern Definitions ──────────────────────────────────────────────────

PII_PATTERNS = [
    {"name": "US Social Security Number", "type": "SSN",
     "pattern": r"\b(?!000|666|9\d{2})\d{3}[-\s]?(?!00)\d{2}[-\s]?(?!0000)\d{4}\b",
     "severity": "critical"},
    {"name": "Credit Card Number (Visa/MC/Amex)", "type": "CREDIT_CARD",
     "pattern": r"\b(?:4[0-9]{12}(?:[0-9]{3})?|5[1-5][0-9]{14}|3[47][0-9]{13}|(?:6011|622(?:12[6-9]|1[3-9]\d|[2-8]\d{2}|9[01]\d|92[0-5])[0-9]{10}|64[4-9][0-9]{13}|65[0-9]{14}))\b",
     "severity": "critical"},
    {"name": "IBAN (International Bank Account)", "type": "IBAN",
     "pattern": r"\b[A-Z]{2}\d{2}[A-Z0-9]{1,30}\b",
     "severity": "high"},
    {"name": "Email Address", "type": "EMAIL",
     "pattern": r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b",
     "severity": "medium"},
    {"name": "Phone Number (US)", "type": "PHONE_US",
     "pattern": r"\b(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b",
     "severity": "medium"},
    {"name": "AWS Access Key", "type": "AWS_KEY",
     "pattern": r"\bAKIA[0-9A-Z]{16}\b",
     "severity": "critical"},
    {"name": "Generic API Key / Secret", "type": "API_KEY",
     "pattern": r"(?i)(?:api[_-]?key|secret|token|password)\s*[=:]\s*['\"]?([A-Za-z0-9\-_]{20,})['\"]?",
     "severity": "high"},
    {"name": "Passport Number (US)", "type": "PASSPORT",
     "pattern": r"\b[A-Z][0-9]{8}\b",
     "severity": "high"},
    {"name": "Date of Birth", "type": "DOB",
     "pattern": r"\b(?:0?[1-9]|1[0-2])[/-](?:0?[1-9]|[12]\d|3[01])[/-](?:19|20)\d{2}\b",
     "severity": "medium"},
    {"name": "Private Key Header", "type": "PRIVATE_KEY",
     "pattern": r"-----BEGIN (?:RSA |EC )?PRIVATE KEY-----",
     "severity": "critical"},
]

SENSITIVITY_KEYWORDS = {
    "restricted": ["top secret", "classified", "confidential", "restricted", "do not distribute", "eyes only"],
    "confidential": ["internal only", "internal use", "proprietary", "trade secret", "customer data", "pii"],
    "internal": ["draft", "internal", "not for external", "working document"],
    "public": [],
}


# ─── PII Scanning ─────────────────────────────────────────────────────────────

def scan_text_for_pii(text: str) -> list[dict]:
    """Scan a text string for PII patterns. Returns list of findings."""
    findings = []
    seen = set()
    for pattern_def in PII_PATTERNS:
        matches = re.findall(pattern_def["pattern"], text)
        for match in matches:
            value = match if isinstance(match, str) else match[0]
            key = f"{pattern_def['type']}:{hashlib.sha256(value.encode()).hexdigest()[:16]}"
            if key not in seen:
                seen.add(key)
                findings.append({
                    "type": pattern_def["type"],
                    "name": pattern_def["name"],
                    "severity": pattern_def["severity"],
                    "redacted_value": value[:4] + "****" + value[-2:] if len(value) > 6 else "****",
                })
    return findings


def classify_sensitivity(text: str) -> str:
    """Classify document sensitivity level."""
    text_lower = text.lower()
    for level, keywords in SENSITIVITY_KEYWORDS.items():
        if any(kw in text_lower for kw in keywords):
            return level
    return "public"


async def scan_file_bytes(content: bytes, filename: str, user_id: str, tenant_id: str) -> dict:
    """
    Scan uploaded file bytes for PII.
    Supports text-based files (txt, csv, json, xml, log, etc.).
    """
    try:
        text = content.decode("utf-8", errors="replace")
    except Exception:
        return {"success": False, "error": "Cannot decode file for PII scanning"}

    findings = scan_text_for_pii(text)
    sensitivity = classify_sensitivity(text)
    scan_id = str(uuid.uuid4())

    incident_doc = {
        "scan_id": scan_id,
        "filename": filename,
        "user_id": user_id,
        "tenant_id": tenant_id,
        "findings": findings,
        "finding_count": len(findings),
        "sensitivity": sensitivity,
        "status": "open" if findings else "clean",
        "scanned_at": datetime.now(timezone.utc).isoformat(),
    }

    if findings:
        db = get_database()
        await db.dlp_incidents.insert_one(incident_doc)

    incident_doc.pop("_id", None)
    return {"success": True, **incident_doc}


# ─── Bulk Export Detection ────────────────────────────────────────────────────

async def check_bulk_export(user_id: str, tenant_id: str, record_count: int) -> bool:
    """
    Flag if a user has exported >500 records in the past 10 minutes.
    Returns True if this constitutes a bulk export anomaly.
    """
    db = get_database()
    from datetime import timedelta
    window_start = (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat()
    recent_exports = await db.dlp_export_events.count_documents({
        "user_id": user_id,
        "tenant_id": tenant_id,
        "timestamp": {"$gte": window_start},
    })
    await db.dlp_export_events.insert_one({
        "user_id": user_id,
        "tenant_id": tenant_id,
        "record_count": record_count,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })
    total = recent_exports * 100 + record_count  # Approximate
    return total > 500


# ─── Policy Management ────────────────────────────────────────────────────────

async def get_policies(tenant_id: str) -> list:
    db = get_database()
    docs = await db.dlp_policies.find({"tenant_id": tenant_id}).to_list(100)
    for d in docs:
        d["_id"] = str(d["_id"])
    return docs


async def create_policy(tenant_id: str, policy: dict) -> dict:
    db = get_database()
    doc = {
        "policy_id": str(uuid.uuid4()),
        "tenant_id": tenant_id,
        "name": policy.get("name"),
        "pattern": policy.get("pattern"),
        "severity": policy.get("severity", "medium"),
        "action": policy.get("action", "alert"),  # "alert" | "block"
        "enabled": True,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.dlp_policies.insert_one(doc)
    return {"success": True, "policy_id": doc["policy_id"]}


# ─── Incident Management ─────────────────────────────────────────────────────

async def list_incidents(tenant_id: str, status: Optional[str] = None) -> list:
    db = get_database()
    query: dict = {"tenant_id": tenant_id}
    if status:
        query["status"] = status
    docs = await db.dlp_incidents.find(query).sort("scanned_at", -1).limit(100).to_list(100)
    for d in docs:
        d["_id"] = str(d["_id"])
    return docs


async def resolve_incident(scan_id: str, reviewer: str) -> dict:
    db = get_database()
    result = await db.dlp_incidents.update_one(
        {"scan_id": scan_id},
        {"$set": {"status": "resolved", "reviewed_by": reviewer,
                  "resolved_at": datetime.now(timezone.utc).isoformat()}}
    )
    return {"success": result.modified_count > 0}

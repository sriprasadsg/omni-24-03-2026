"""
DLP Service — Data Loss Prevention
------------------------------------
Detects PII, bulk data exports, and sensitive data patterns.
"""

import asyncio
import json
import logging
import os
import re
import hashlib
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional
from database import get_database

try:  # admin-written policy patterns run with a timeout when the regex module is present
    import regex as _policy_re
except ImportError:  # pragma: no cover - the backend venv ships it
    _policy_re = None

logger = logging.getLogger(__name__)

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


# ─── Export DLP: bulk exports and policies on exported rows ───────────────────
# Export events and incidents are written through the raw handle with explicit tenant
# fields: the export middleware runs outside the route's tenant context.

BULK_EXPORT_WINDOW = timedelta(minutes=10)
BULK_EXPORT_ROWS = int(os.getenv("DLP_BULK_EXPORT_ROWS", "5000"))
BULK_EXPORT_BYTES = int(float(os.getenv("DLP_BULK_EXPORT_MB", "50")) * 1024 * 1024)
# Built-in patterns precise enough to apply to every export (the SSN/phone/date ones match
# ordinary numbers in audit logs and inventories, so they stay on the file scanner only).
_EXPORT_BUILTIN_TYPES = frozenset({"AWS_KEY", "PRIVATE_KEY"})
_EXPORT_SCAN_MAX_CHARS = 2_000_000
_POLICY_TIMEOUT_S = 0.5
_export_index_ready = False


async def check_bulk_export(user_id: str, tenant_id: Optional[str], record_count: int,
                            byte_count: int = 0, path: Optional[str] = None) -> bool:
    """Record one export; True when the user's exports in the last 10 minutes add up to a
    bulk export (more than DLP_BULK_EXPORT_ROWS rows or DLP_BULK_EXPORT_MB megabytes)."""
    global _export_index_ready
    raw = get_database()._db
    if not _export_index_ready:
        await raw.dlp_export_events.create_index("at", expireAfterSeconds=86400)
        _export_index_ready = True
    now = datetime.now(timezone.utc)
    await raw.dlp_export_events.insert_one({
        "user_id": user_id, "tenant_id": tenant_id, "record_count": int(record_count or 0),
        "byte_count": int(byte_count or 0), "path": path, "at": now,
    })
    totals = await raw.dlp_export_events.aggregate([
        {"$match": {"user_id": user_id, "tenant_id": tenant_id, "at": {"$gte": now - BULK_EXPORT_WINDOW}}},
        {"$group": {"_id": None, "rows": {"$sum": "$record_count"}, "bytes": {"$sum": "$byte_count"}}},
    ]).to_list(1)
    rows = totals[0]["rows"] if totals else 0
    size = totals[0]["bytes"] if totals else 0
    return rows > BULK_EXPORT_ROWS or size > BULK_EXPORT_BYTES


def _policy_hits(pattern: Optional[str], text: str) -> Optional[bool]:
    """Whether an admin-written pattern matches; None when it is invalid or runs too long."""
    if not pattern:
        return None
    try:
        if _policy_re is not None:
            return _policy_re.search(pattern, text, timeout=_POLICY_TIMEOUT_S) is not None
        return re.search(pattern, text) is not None
    except (TimeoutError, re.error, Exception):
        return None


def validate_policy_pattern(pattern: str) -> None:
    """Raise ValueError unless ``pattern`` compiles (an invalid block policy would block every export)."""
    try:
        (_policy_re or re).compile(pattern)
    except Exception as exc:
        raise ValueError(f"Invalid pattern: {exc}") from exc


def _scan_export_text(text: str, policies: list) -> tuple:
    blocking, alerting = [], []
    for policy in policies:
        hit = _policy_hits(policy.get("pattern"), text)
        if not hit and not (hit is None and policy.get("action") == "block"):
            continue
        finding = {"type": "POLICY", "name": policy.get("name") or "DLP policy",
                   "severity": policy.get("severity", "medium"), "policy_id": policy.get("policy_id")}
        if hit is None:  # a block policy that cannot be evaluated blocks (fail closed)
            finding["type"], finding["name"] = "POLICY_UNEVALUATED", f"{finding['name']} (could not be evaluated)"
        (blocking if policy.get("action") == "block" else alerting).append(finding)
    alerting += [f for f in scan_text_for_pii(text) if f["type"] in _EXPORT_BUILTIN_TYPES]
    return blocking, alerting


async def scan_export(rows: list, tenant_id: Optional[str]) -> tuple:
    """(blocking, alerting) findings for exported rows: the tenant's enabled DLP policies plus
    the precise built-in patterns. Runs off the event loop; admin patterns have a timeout."""
    text = "\n".join(json.dumps(r, default=str) for r in rows)[:_EXPORT_SCAN_MAX_CHARS]
    policies = []
    if tenant_id:
        policies = await get_database()._db.dlp_policies.find(
            {"tenant_id": tenant_id, "enabled": True}, {"_id": 0}).to_list(100)
    return await asyncio.to_thread(_scan_export_text, text, policies)


async def record_export_incident(user_id: str, tenant_id: Optional[str], source: str,
                                 findings: list, *, blocked: bool, kind: str = "export") -> str:
    """Open a DLP incident for an export (policy hit or bulk export); returns its scan_id."""
    scan_id = str(uuid.uuid4())
    await get_database()._db.dlp_incidents.insert_one({
        "scan_id": scan_id, "kind": kind, "filename": source, "user_id": user_id,
        "tenant_id": tenant_id, "tenantId": tenant_id, "findings": findings,
        "finding_count": len(findings), "sensitivity": "restricted" if blocked else "confidential",
        "action": "blocked" if blocked else "alerted", "status": "open",
        "scanned_at": datetime.now(timezone.utc).isoformat(),
    })
    logger.warning("DLP export incident %s (%s) for %s in tenant %s: %s", scan_id,
                   "blocked" if blocked else "alert", user_id, tenant_id, [f.get("name") for f in findings])
    return scan_id


async def open_bulk_export_incident(user_id: str, tenant_id: Optional[str], path: Optional[str]) -> bool:
    """One open bulk-export incident per user per window; False when one is already open."""
    raw = get_database()._db
    since = (datetime.now(timezone.utc) - BULK_EXPORT_WINDOW).isoformat()
    if await raw.dlp_incidents.find_one({"kind": "bulk_export", "user_id": user_id, "tenant_id": tenant_id,
                                         "status": "open", "scanned_at": {"$gte": since}}):
        return False
    await record_export_incident(user_id, tenant_id, path or "export", [{
        "type": "BULK_EXPORT", "name": "Bulk data export", "severity": "high",
        "detail": f"More than {BULK_EXPORT_ROWS} rows or {BULK_EXPORT_BYTES // (1024 * 1024)} MB exported "
                  f"in {int(BULK_EXPORT_WINDOW.total_seconds() // 60)} minutes",
    }], blocked=False, kind="bulk_export")
    return True


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

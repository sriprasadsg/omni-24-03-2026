"""
Binary Analysis API Endpoints
File upload for static PE analysis, YARA scanning, and lightweight sandbox.
"""
from fastapi import APIRouter, Body, Depends, HTTPException, UploadFile, File, Query, BackgroundTasks
from typing import Optional
from datetime import datetime, timezone
from database import get_database
from authentication_service import get_current_user
from auth_types import TokenData
from binary_analysis_service import binary_analysis_service
import asyncio
import uuid

router = APIRouter(prefix="/api/analysis", tags=["Binary Analysis"])

# Max file size: 50 MB
MAX_FILE_SIZE = 50 * 1024 * 1024


# ------------------------------------------------------------------
# File Analysis
# ------------------------------------------------------------------

@router.post("/file")
async def analyze_file(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    run_sandbox: bool = Query(default=False, description="Run lightweight subprocess sandbox"),
    current_user: TokenData = Depends(get_current_user)
):
    """
    Submit a file for binary analysis.
    Returns a job ID for polling. Analysis runs in a background task.
    """
    db = get_database()

    # Size guard
    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(status_code=413, detail=f"File exceeds max size ({MAX_FILE_SIZE // (1024*1024)} MB)")

    # MIME type validation — reject clearly non-binary content types
    ALLOWED_MIME_PREFIXES = ("application/octet-stream", "application/x-", "application/vnd.microsoft.portable-executable")
    EXPLICITLY_DENIED_MIME_PREFIXES = ("text/", "image/", "audio/", "video/")
    content_type = (file.content_type or "").lower().split(";")[0].strip()
    if content_type and any(content_type.startswith(denied) for denied in EXPLICITLY_DENIED_MIME_PREFIXES):
        raise HTTPException(status_code=400, detail="Invalid file type for binary analysis")
    EXACT_ALLOWED = {
        "application/octet-stream",
        "application/x-executable",
        "application/x-elf",
        "application/x-dosexec",
        "application/x-msdownload",
        "application/vnd.microsoft.portable-executable",
    }
    if content_type and content_type not in EXACT_ALLOWED and not content_type.startswith("application/x-"):
        raise HTTPException(status_code=400, detail="Invalid file type for binary analysis")

    job_id = f"ANA-{uuid.uuid4().hex[:12]}"
    job = {
        "job_id": job_id,
        "filename": file.filename,
        "file_size": len(content),
        "submitted_by": current_user.username,
        "submitted_at": datetime.now(timezone.utc).isoformat(),
        "status": "queued",
        "run_sandbox": run_sandbox,
        "report": None,
    }
    await db.analysis_jobs.insert_one(job)
    job.pop("_id", None)

    # Run in background (pass tenant_id so custom YARA rules are scoped correctly)
    tenant_id = getattr(current_user, "tenant_id", None)
    background_tasks.add_task(_run_analysis, job_id, content, file.filename, run_sandbox, tenant_id)

    return {"status": "queued", "job_id": job_id, "filename": file.filename}


async def _run_analysis(job_id: str, content: bytes, filename: str, run_sandbox: bool, tenant_id: Optional[str] = None):
    """Background task: run analysis and store report in MongoDB."""
    import functools
    db = get_database()
    try:
        await db.analysis_jobs.update_one(
            {"job_id": job_id}, {"$set": {"status": "running"}}
        )
        # Fetch enabled custom YARA rules for this tenant
        custom_query: dict = {"enabled": True}
        if tenant_id:
            custom_query["tenantId"] = tenant_id
        custom_rules = await db.custom_yara_rules.find(custom_query, {"_id": 0, "name": 1, "content": 1}).to_list(length=200)

        # Run in executor to avoid blocking the event loop
        loop = asyncio.get_event_loop()
        report = await loop.run_in_executor(
            None,
            functools.partial(binary_analysis_service.analyze, content, filename, custom_rules=custom_rules),
        )
        await db.analysis_jobs.update_one(
            {"job_id": job_id},
            {"$set": {
                "status": "completed",
                "report": report,
                "completed_at": datetime.now(timezone.utc).isoformat(),
            }}
        )
    except Exception as e:
        import logging as _l
        _l.getLogger(__name__).error("Binary analysis failed for job %s: %s", job_id, e)
        await db.analysis_jobs.update_one(
            {"job_id": job_id},
            {"$set": {"status": "failed", "error": "Analysis failed"}}
        )


# ------------------------------------------------------------------
# Poll / Retrieve Report
# ------------------------------------------------------------------

_ANALYSIS_SUPER_ROLES = {"Super Admin", "super_admin", "platform-admin"}
_YARA_WRITE_ROLES = {
    "Super Admin", "super_admin", "platform-admin",
    "Tenant Admin", "admin", "security_analyst",
}


@router.get("/report/{job_id}")
async def get_report(
    job_id: str,
    current_user: TokenData = Depends(get_current_user)
):
    """Get the analysis report for a given job ID."""
    db = get_database()
    user_role = getattr(current_user, "role", "")
    job_filter: dict = {"job_id": job_id}
    if user_role not in _ANALYSIS_SUPER_ROLES:
        user_tenant = getattr(current_user, "tenant_id", None)
        if user_tenant:
            job_filter["tenantId"] = user_tenant
        job_filter["submitted_by"] = current_user.username
    job = await db.analysis_jobs.find_one(job_filter, {"_id": 0})
    if not job:
        raise HTTPException(status_code=404, detail="Analysis job not found")
    return job


# ------------------------------------------------------------------
# History
# ------------------------------------------------------------------

@router.get("/history")
async def get_analysis_history(
    verdict: Optional[str] = None,
    limit: int = Query(default=50, le=200),
    current_user: TokenData = Depends(get_current_user)
):
    """List all completed analysis jobs."""
    db = get_database()
    user_role = getattr(current_user, "role", "")
    query: dict = {"status": "completed"}
    if user_role not in _ANALYSIS_SUPER_ROLES:
        user_tenant = getattr(current_user, "tenant_id", None)
        if user_tenant:
            query["tenantId"] = user_tenant
        query["submitted_by"] = current_user.username
    if verdict:
        query["report.verdict"] = verdict
    jobs = await db.analysis_jobs.find(
        query,
        {"_id": 0, "job_id": 1, "filename": 1, "submitted_at": 1,
         "report.verdict": 1, "report.threat_score": 1, "report.yara_matches": 1,
         "report.sha256": 1, "report.file_type": 1}
    ).sort("submitted_at", -1).limit(limit).to_list(length=limit)
    return jobs


# ------------------------------------------------------------------
# Quick Hash Lookup (IOC check without uploading)
# ------------------------------------------------------------------

@router.get("/hash/{sha256}")
async def check_hash(
    sha256: str,
    current_user: TokenData = Depends(get_current_user)
):
    """
    Look up a SHA-256 hash against previously analyzed files and the EDR IOC blocklist.
    """
    db = get_database()
    user_role = getattr(current_user, "role", "")
    tenant_id = getattr(current_user, "tenant_id", None)
    hash_filter: dict = {"report.sha256": sha256}
    if user_role not in _ANALYSIS_SUPER_ROLES:
        hash_filter["submitted_by"] = current_user.username
    # Check analysis history
    job = await db.analysis_jobs.find_one(
        hash_filter, {"_id": 0, "report": 1, "submitted_at": 1}
    )
    # Check IOC blocklist — scoped to caller's tenant for non-super-admins
    ioc_filter: dict = {"sha256": sha256}
    if user_role not in _ANALYSIS_SUPER_ROLES and tenant_id:
        ioc_filter["tenantId"] = tenant_id
    ioc = await db.edr_ioc.find_one(ioc_filter, {"_id": 0})

    return {
        "sha256": sha256,
        "in_ioc_blocklist": bool(ioc),
        "ioc_info": ioc,
        "previously_analyzed": bool(job),
        "previous_verdict": (job["report"].get("verdict") if job else None),
        "previous_threat_score": (job["report"].get("threat_score") if job else None),
    }


# ──────────────────────────────────────────────────────────────────────────────
# Custom YARA Rule Editor  (per-tenant DB-backed rules)
# ──────────────────────────────────────────────────────────────────────────────

def _validate_yara_syntax(content: str) -> Optional[str]:
    """Return an error string if syntax is obviously wrong, else None."""
    import re
    stripped = content.strip()
    if not stripped:
        return "Rule content is empty"
    if not re.search(r'\brule\s+\w+', stripped):
        return "Missing 'rule <name>' declaration"
    if 'condition:' not in stripped:
        return "Missing 'condition:' section"
    if '{' not in stripped or '}' not in stripped:
        return "Missing rule braces { }"
    try:
        import yara  # type: ignore
        yara.compile(source=content)
    except ImportError:
        pass  # yara-python not installed — skip compile check
    except Exception as e:
        return str(e)
    return None


@router.get("/yara-rules")
async def list_yara_rules(current_user: TokenData = Depends(get_current_user)):
    db = get_database()
    tid = getattr(current_user, "tenant_id", None)
    query: dict = {"tenantId": tid} if tid else {}
    rules = await db.custom_yara_rules.find(query, {"_id": 0}).to_list(length=500)
    return rules


@router.post("/yara-rules")
async def create_yara_rule(
    payload: dict = Body(...),
    current_user: TokenData = Depends(get_current_user),
):
    if getattr(current_user, "role", None) not in _YARA_WRITE_ROLES:
        raise HTTPException(status_code=403, detail="Security Analyst or Admin role required")
    content = (payload.get("content") or "").strip()
    err = _validate_yara_syntax(content)
    if err:
        raise HTTPException(status_code=422, detail=f"Invalid YARA syntax: {err}")
    db = get_database()
    rule = {
        "id": str(uuid.uuid4()),
        "name": (payload.get("name") or "custom_rule").strip()[:80],
        "content": content,
        "description": (payload.get("description") or "")[:256],
        "enabled": payload.get("enabled", True),
        "tenantId": getattr(current_user, "tenant_id", None),
        "createdBy": current_user.username,
        "createdAt": datetime.now(timezone.utc).isoformat(),
    }
    await db.custom_yara_rules.insert_one({**rule})
    rule.pop("_id", None)
    return rule


@router.put("/yara-rules/{rule_id}")
async def update_yara_rule(
    rule_id: str,
    payload: dict = Body(...),
    current_user: TokenData = Depends(get_current_user),
):
    if getattr(current_user, "role", None) not in _YARA_WRITE_ROLES:
        raise HTTPException(status_code=403, detail="Security Analyst or Admin role required")
    db = get_database()
    tid = getattr(current_user, "tenant_id", None)
    filt: dict = {"id": rule_id}
    if tid:
        filt["tenantId"] = tid
    content = (payload.get("content") or "").strip()
    if content:
        err = _validate_yara_syntax(content)
        if err:
            raise HTTPException(status_code=422, detail=f"Invalid YARA syntax: {err}")
    updates: dict = {"updatedAt": datetime.now(timezone.utc).isoformat()}
    for key in ("name", "content", "description", "enabled"):
        if key in payload:
            updates[key] = payload[key]
    result = await db.custom_yara_rules.update_one(filt, {"$set": updates})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Rule not found")
    rule = await db.custom_yara_rules.find_one(filt, {"_id": 0})
    return rule


@router.delete("/yara-rules/{rule_id}")
async def delete_yara_rule(
    rule_id: str,
    current_user: TokenData = Depends(get_current_user),
):
    if getattr(current_user, "role", None) not in _YARA_WRITE_ROLES:
        raise HTTPException(status_code=403, detail="Security Analyst or Admin role required")
    db = get_database()
    tid = getattr(current_user, "tenant_id", None)
    filt: dict = {"id": rule_id}
    if tid:
        filt["tenantId"] = tid
    await db.custom_yara_rules.delete_one(filt)
    return {"success": True}


@router.post("/yara-rules/validate")
async def validate_yara_rule(
    payload: dict = Body(...),
    _current_user: TokenData = Depends(get_current_user),
):
    content = (payload.get("content") or "").strip()
    err = _validate_yara_syntax(content)
    return {"valid": err is None, "error": err}


"""
Binary Analysis API Endpoints
File upload for static PE analysis, YARA scanning, and lightweight sandbox.
"""
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query, BackgroundTasks
from fastapi.responses import JSONResponse
from typing import Optional, List
from datetime import datetime
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

    job_id = f"ANA-{uuid.uuid4().hex[:12]}"
    job = {
        "job_id": job_id,
        "filename": file.filename,
        "file_size": len(content),
        "submitted_by": current_user.username,
        "submitted_at": datetime.utcnow().isoformat(),
        "status": "queued",
        "run_sandbox": run_sandbox,
        "report": None,
    }
    await db.analysis_jobs.insert_one(job)
    job.pop("_id", None)

    # Run in background
    background_tasks.add_task(_run_analysis, job_id, content, file.filename, run_sandbox)

    return {"status": "queued", "job_id": job_id, "filename": file.filename}


async def _run_analysis(job_id: str, content: bytes, filename: str, run_sandbox: bool):
    """Background task: run analysis and store report in MongoDB."""
    db = get_database()
    try:
        await db.analysis_jobs.update_one(
            {"job_id": job_id}, {"$set": {"status": "running"}}
        )
        # Run in executor to avoid blocking the event loop
        loop = asyncio.get_event_loop()
        report = await loop.run_in_executor(
            None, binary_analysis_service.analyze, content, filename
        )
        await db.analysis_jobs.update_one(
            {"job_id": job_id},
            {"$set": {
                "status": "completed",
                "report": report,
                "completed_at": datetime.utcnow().isoformat(),
            }}
        )
    except Exception as e:
        await db.analysis_jobs.update_one(
            {"job_id": job_id},
            {"$set": {"status": "failed", "error": str(e)}}
        )


# ------------------------------------------------------------------
# Poll / Retrieve Report
# ------------------------------------------------------------------

@router.get("/report/{job_id}")
async def get_report(
    job_id: str,
    current_user: TokenData = Depends(get_current_user)
):
    """Get the analysis report for a given job ID."""
    db = get_database()
    job = await db.analysis_jobs.find_one({"job_id": job_id}, {"_id": 0})
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
    query = {"status": "completed"}
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
    # Check analysis history
    job = await db.analysis_jobs.find_one(
        {"report.sha256": sha256}, {"_id": 0, "report": 1, "submitted_at": 1}
    )
    # Check IOC blocklist
    ioc = await db.edr_ioc.find_one({"sha256": sha256}, {"_id": 0})

    return {
        "sha256": sha256,
        "in_ioc_blocklist": bool(ioc),
        "ioc_info": ioc,
        "previously_analyzed": bool(job),
        "previous_verdict": (job["report"].get("verdict") if job else None),
        "previous_threat_score": (job["report"].get("threat_score") if job else None),
    }

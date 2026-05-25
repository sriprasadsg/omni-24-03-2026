from fastapi import APIRouter, HTTPException, Depends
import logging
from datetime import datetime, timezone
import asyncio
from database import get_database
from patch_service import get_patch_service
from security_service import get_security_service
from authentication_service import get_current_user
from auth_types import TokenData
import base64

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/patches", tags=["Patch Management"])

_PATCH_ADMIN_ROLES = {"Super Admin", "super_admin", "admin", "platform-admin"}

@router.get("")
async def list_patches(
    tenant_id: str = None,
    current_user: TokenData = Depends(get_current_user),
):
    """List all patches"""
    db = get_database()
    is_admin = getattr(current_user, "role", "") in _PATCH_ADMIN_ROLES
    caller_tenant = getattr(current_user, "tenant_id", "default")
    if tenant_id and not is_admin and tenant_id != caller_tenant:
        raise HTTPException(status_code=403, detail="Not authorized to view patches for this tenant")
    effective_tenant = tenant_id if (tenant_id and is_admin) else caller_tenant
    patches = await db.patches.find({"tenantId": effective_tenant}, {"_id": 0}).to_list(length=100)
    return patches

from pydantic import BaseModel
from typing import List, Optional

class PatchDeploymentRequest(BaseModel):
    patch_ids: List[str]
    asset_ids: List[str]
    deployment_type: str = "Immediate"
    schedule_time: Optional[str] = None
    tenantId: Optional[str] = None

class SoftwareUpdateRequest(BaseModel):
    agent_id: str
    package_name: str
    pkg_type: str
    tenant_id: Optional[str] = None

class OsPatchRequest(BaseModel):
    agent_id: str
    patch_ids: List[str]
    tenant_id: Optional[str] = None

class BulkSoftwareUpdateRequest(BaseModel):
    updates: List[SoftwareUpdateRequest]
    tenant_id: Optional[str] = None

@router.post("/deploy")
async def create_deployment_job(
    request: PatchDeploymentRequest,
    current_user: TokenData = Depends(get_current_user),
):
    """
    Schedule a patch deployment job.

    For each (patch, asset) pair:
      1. Resolve the patch doc to get its KB/package identifier.
      2. Look up the agent for the asset.
      3. Queue an agent_instructions doc so the agent picks it up on next poll.

    Immediate deployments also start a progress-simulation task so the
    frontend progress bar moves while waiting for real agent callbacks.
    Scheduled deployments are dispatched by the APScheduler every minute.
    """
    try:
        from scheduler import simulate_patch_deployment
        db = get_database()

        job_id = f"job-{int(datetime.now(timezone.utc).timestamp())}"
        is_immediate = request.deployment_type != "Scheduled"
        tenant_id = request.tenantId or getattr(current_user, "tenant_id", "default")
        now = datetime.now(timezone.utc).isoformat()

        job = {
            "id": job_id,
            "tenantId": tenant_id,
            "patchIds": request.patch_ids,
            "targetAssets": request.asset_ids,
            "status": "In Progress" if is_immediate else "Scheduled",
            "progress": 0,
            "startTime": request.schedule_time or now,
            "scheduledAt": request.schedule_time or now,
            "createdAt": now,
            "createdBy": getattr(current_user, "username", str(current_user)),
            "type": "Patch Deployment",
            "deploymentType": request.deployment_type,
        }

        await db.patch_deployment_jobs.insert_one(job.copy())
        job.pop("_id", None)

        # ── Resolve patch identifiers (KB numbers / package names) ────────────
        patch_docs = []
        for pid in request.patch_ids:
            doc = await db.patches.find_one(
                {"$or": [{"id": pid}, {"_id": pid}, {"cve_id": pid}]},
                {"_id": 0},
            )
            patch_docs.append(doc or {"id": pid, "kb_number": pid, "name": pid})

        def _patch_identifier(doc: dict) -> str:
            """Return the best identifier for the agent instruction string."""
            return (
                doc.get("kb_number")
                or doc.get("package_name")
                or doc.get("name")
                or doc.get("id", "")
            )

        # ── Queue one instruction per agent ───────────────────────────────────
        instructions_queued = 0
        for asset_id in request.asset_ids:
            # Resolve asset → agent
            agent = await db.agents.find_one(
                {"$or": [{"id": asset_id}, {"hostname": asset_id}, {"assetId": asset_id}]},
                {"id": 1, "tenantId": 1},
            )
            if not agent:
                continue
            agent_id = agent["id"]

            # Build KB / package list for this agent
            patch_identifiers = [_patch_identifier(d) for d in patch_docs if _patch_identifier(d)]
            if not patch_identifiers:
                continue

            # Format: "Install Patches: KB5034441 KB5033375 Job: job-xxx"
            # Works for both KB numbers and Linux package names.
            instruction_str = "Install Patches: " + " ".join(patch_identifiers) + f" Job: {job_id}"

            instr_doc = {
                "agent_id":    agent_id,
                "instruction": instruction_str,
                "status":      "pending",
                "created_at":  now,
                "type":        "os_patch_install",
                "job_id":      job_id,
                "metadata":    {"patches": patch_identifiers, "job_id": job_id},
                "payload":     {},
            }

            # For scheduled deployments, tag with scheduledAt so the scheduler
            # only dispatches once the time arrives.
            if not is_immediate and request.schedule_time:
                instr_doc["scheduledAt"] = request.schedule_time
                instr_doc["status"] = "scheduled"

            await db.agent_instructions.insert_one(instr_doc)
            instructions_queued += 1

        job["instructionsQueued"] = instructions_queued

        # ── Simulation task (keeps progress bar alive until agent callbacks) ──
        if is_immediate:
            asyncio.create_task(
                simulate_patch_deployment(
                    job_id,
                    len(request.patch_ids),
                    max(1, len(request.asset_ids)),
                )
            )

        return job
    except Exception as e:
        logger.error("Error creating deployment job: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error")

@router.get("/deployment-jobs")
async def list_deployment_jobs(
    tenant_id: str = None,
    current_user: TokenData = Depends(get_current_user),
):
    """List patch deployment jobs"""
    db = get_database()
    is_admin = getattr(current_user, "role", "") in ("Super Admin", "super_admin", "admin", "platform-admin")
    query = {}
    if tenant_id:
        query["tenantId"] = tenant_id
    elif not is_admin:
        query["tenantId"] = getattr(current_user, "tenant_id", "default")
    jobs = await db.patch_deployment_jobs.find(query, {"_id": 0}).to_list(length=100)
    return jobs

@router.post("/apply-software-update")
async def apply_software_update(
    request: SoftwareUpdateRequest,
    _current_user: TokenData = Depends(get_current_user),
):
    """
    Trigger a package upgrade on an agent.
    """
    try:
        db = get_database()
        
        # Verify agent exists and is online
        agent = await db.agents.find_one({"id": request.agent_id})
        if not agent:
            raise HTTPException(status_code=404, detail="Agent not found")
            
        tenant_id = agent.get("tenantId", "global")
        repo_pkg = await db.local_repo.find_one({
            "tenantId": tenant_id, "pkg_name": request.package_name, "pkg_type": request.pkg_type
        }, sort=[("uploaded_at", -1)])
        
        payload = {
            "package": request.package_name,
            "pkg_type": request.pkg_type
        }
        if repo_pkg:
            payload["download_url"] = f"/api/repo/download/{repo_pkg['filename']}"

        instruction = {
            "agent_id": request.agent_id,
            "instruction": f"upgrade_software: {request.package_name}",
            "status": "pending",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "type": f"upgrade_software: {request.package_name}",
            "payload": payload
        }
        
        await db.agent_instructions.insert_one(instruction)
        return {"success": True, "message": f"Upgrade instruction queued for {request.package_name}"}
    except Exception as e:
        logger.error("Error applying software update: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error")

@router.post("/bulk-apply-software-update")
async def apply_bulk_software_update(
    request: BulkSoftwareUpdateRequest,
    _current_user: TokenData = Depends(get_current_user),
):
    """
    Trigger multiple package upgrades across potentially different agents.
    """
    try:
        db = get_database()
        instructions = []
        for update in request.updates:
            agent = await db.agents.find_one({"id": update.agent_id})
            tenant_id = agent.get("tenantId", "global") if agent else "global"
            
            repo_pkg = await db.local_repo.find_one({
                "tenantId": tenant_id, "pkg_name": update.package_name, "pkg_type": update.pkg_type
            }, sort=[("uploaded_at", -1)])
            
            payload = {
                "package": update.package_name,
                "pkg_type": update.pkg_type
            }
            if repo_pkg:
                payload["download_url"] = f"/api/repo/download/{repo_pkg['filename']}?tenantId={tenant_id}"

            instructions.append({
                "agent_id": update.agent_id,
                "instruction": f"upgrade_software: {update.package_name}",
                "status": "pending",
                "created_at": datetime.now(timezone.utc).isoformat(),
                "type": f"upgrade_software: {update.package_name}",
                "payload": payload
            })
            
        if instructions:
            await db.agent_instructions.insert_many(instructions)
            
        return {"success": True, "count": len(instructions), "message": f"Queued {len(instructions)} upgrade instructions"}
    except Exception as e:
        logger.error("Error applying bulk software update: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error")

@router.post("/apply-os-patches")
async def apply_os_patches(
    request: OsPatchRequest,
    _current_user: TokenData = Depends(get_current_user),
):
    """
    Trigger OS patch installation on an agent.
    """
    try:
        db = get_database()
        
        # Verify agent exists
        agent = await db.agents.find_one({"id": request.agent_id})
        if not agent:
            raise HTTPException(status_code=404, detail="Agent not found")
            
        job_id = f"patch-job-{int(datetime.now(timezone.utc).timestamp())}"
        
        # Agent expects format "Install Patches: KB123 KB456 Job: job-id"
        # Since these might not be KB numbers always (linux apt), we'll try to follow the format loosely or as expected
        patches_str = " ".join(request.patch_ids)
        instruction_str = f"Install Patches: {patches_str} Job: {job_id}"
        
        instruction = {
            "agent_id": request.agent_id,
            "instruction": instruction_str,
            "status": "pending",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "type": "os_patch_install",
            "job_id": job_id,
            "metadata": {
                "patches": request.patch_ids
            }
        }
        
        await db.agent_instructions.insert_one(instruction)
        return {"success": True, "job_id": job_id, "message": "OS patch installation queued"}
    except Exception as e:
        logger.error("Error applying OS patches: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error")

@router.get("/cve/{cve_id}")
async def get_cve_info(
    cve_id: str,
    _current_user: TokenData = Depends(get_current_user),
):
    """Get detailed CVE information from NVD"""
    patch_service = get_patch_service()
    cve_data = await patch_service.get_cve_details(cve_id)
    if not cve_data:
        raise HTTPException(status_code=404, detail="CVE not found")
    return cve_data


@router.get("/{patch_id}/enrich")
async def enrich_patch(
    patch_id: str,
    _current_user: TokenData = Depends(get_current_user),
):
    """
    Enrich a patch with CVE/CVSS/EPSS intelligence
    Returns enhanced patch data with priority scoring
    """
    try:
        db = get_database()
        patch = await db.patches.find_one({"id": patch_id}, {"_id": 0})

        if not patch:
            raise HTTPException(status_code=404, detail="Patch not found")
        
        patch_service = get_patch_service()
        enriched_patch = await patch_service.enrich_patch_with_intelligence(patch)
        
        # Update patch in database with intelligence
        await db.patches.update_one(
            {"id": patch_id},
            {"$set": {
                "cvss_score": enriched_patch.get("cvss_score"),
                "epss_score": enriched_patch.get("epss_score"),
                "priority_score": enriched_patch.get("priority_score"),
                "sla_hours": enriched_patch.get("sla_hours"),
                "patch_deadline": enriched_patch.get("patch_deadline"),
                "cve_details": enriched_patch.get("cve_details"),
                "updated_at": datetime.now(timezone.utc).isoformat()
            }}
        )
        
        return enriched_patch
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error enriching patch: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/enrich-all")
async def enrich_all_patches(
    tenant_id: str = None,
    current_user: TokenData = Depends(get_current_user),
):
    """
    Batch enrich all pending patches with CVE intelligence
    Useful for initial setup or periodic refresh
    """
    try:
        db = get_database()
        is_admin = getattr(current_user, "role", "") in _PATCH_ADMIN_ROLES
        caller_tenant = getattr(current_user, "tenant_id", "default")
        if tenant_id and not is_admin and tenant_id != caller_tenant:
            raise HTTPException(status_code=403, detail="Not authorized to access this tenant")
        effective_tenant = tenant_id if (tenant_id and is_admin) else caller_tenant
        query = {"status": "Pending", "tenantId": effective_tenant}
        
        patches = await db.patches.find(query, {"_id": 0}).to_list(length=500)
        
        patch_service = get_patch_service()
        enriched_count = 0
        
        for patch in patches:
            try:
                enriched = await patch_service.enrich_patch_with_intelligence(patch)
                
                # Update in database
                await db.patches.update_one(
                    {"id": patch["id"]},
                    {"$set": {
                        "cvss_score": enriched.get("cvss_score"),
                        "epss_score": enriched.get("epss_score"),
                        "priority_score": enriched.get("priority_score"),
                        "sla_hours": enriched.get("sla_hours"),
                        "severity": enriched.get("severity", patch.get("severity")),
                        "updated_at": datetime.now(timezone.utc).isoformat()
                    }}
                )
                enriched_count += 1
                
                # Rate limiting to avoid API throttling
                await asyncio.sleep(0.6)  # NVD allows ~1.67 requests/second with API key
                
            except Exception as e:
                logger.error("Error enriching patch %s: %s", patch['id'], e)
                continue
        
        return {
            "success": True,
            "total_patches": len(patches),
            "enriched_count": enriched_count,
            "message": f"Enriched {enriched_count} patches with CVE intelligence"
        }
    except Exception as e:
        logger.error("Error in batch enrichment: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/prioritized")
async def get_prioritized_patches(
    tenant_id: str = None,
    current_user: TokenData = Depends(get_current_user),
):
    """
    Get patches sorted by intelligent priority score
    Returns patches with CVE/CVSS/EPSS data
    """
    try:
        db = get_database()
        is_admin = getattr(current_user, "role", "") in _PATCH_ADMIN_ROLES
        caller_tenant = getattr(current_user, "tenant_id", "default")
        if tenant_id and not is_admin and tenant_id != caller_tenant:
            raise HTTPException(status_code=403, detail="Not authorized to access this tenant")
        effective_tenant = tenant_id if (tenant_id and is_admin) else caller_tenant
        query = {"status": "Pending", "tenantId": effective_tenant}
        
        patches = await db.patches.find(query, {"_id": 0}).to_list(length=500)
        
        # Sort by priority score (descending)
        prioritized = sorted(
            patches,
            key=lambda p: p.get("priority_score", 0),
            reverse=True
        )
        
        return {
            "patches": prioritized,
            "total": len(prioritized)
        }
    except Exception as e:
        logger.error("Error getting prioritized patches: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/compliance-status")
async def get_compliance_status(
    tenant_id: str = None,
    framework: str = "SOC2",
    current_user: TokenData = Depends(get_current_user),
):
    """
    Get patch compliance status against regulatory framework
    Shows patches exceeding SLA deadlines
    """
    try:
        db = get_database()
        is_admin = getattr(current_user, "role", "") in _PATCH_ADMIN_ROLES
        caller_tenant = getattr(current_user, "tenant_id", "default")
        if tenant_id and not is_admin and tenant_id != caller_tenant:
            raise HTTPException(status_code=403, detail="Not authorized to access this tenant")
        effective_tenant = tenant_id if (tenant_id and is_admin) else caller_tenant
        query = {"status": "Pending", "tenantId": effective_tenant}
        
        patches = await db.patches.find(query, {"_id": 0}).to_list(length=500)
        
        now = datetime.now(timezone.utc).timestamp()
        
        # Calculate SLA for patches
        patch_service = get_patch_service()
        compliant = []
        at_risk = []
        overdue = []
        
        for patch in patches:
            severity = patch.get("severity", "Medium")
            sla_hours = patch.get("sla_hours") or patch_service.calculate_patch_sla_hours(severity, framework)
            
            created_at = datetime.fromisoformat(patch.get("createdAt", datetime.now(timezone.utc).isoformat())).timestamp()
            deadline = created_at + (sla_hours * 3600)
            time_remaining = deadline - now
            
            patch_with_sla = {
                **patch,
                "sla_hours": sla_hours,
                "deadline": deadline,
                "time_remaining_hours": time_remaining / 3600
            }
            
            if time_remaining < 0:
                overdue.append(patch_with_sla)
            elif time_remaining < (sla_hours * 0.25 * 3600):  # Less than 25% time remaining
                at_risk.append(patch_with_sla)
            else:
                compliant.append(patch_with_sla)
        
        total = len(patches)
        compliance_rate = (len(compliant) / total * 100) if total > 0 else 100
        
        return {
            "framework": framework,
            "compliance_rate": round(compliance_rate, 2),
            "total_patches": total,
            "compliant": len(compliant),
            "at_risk": len(at_risk),
            "overdue": len(overdue),
            "patches": {
                "compliant": compliant,
                "at_risk": at_risk,
                "overdue": overdue
            }
        }
    except Exception as e:
        logger.error("Error calculating compliance: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error")


# ─────────────────────────────────────────────────────────────────────────────
# Phase 11: Real-Time Software Version Validation Endpoints
# ─────────────────────────────────────────────────────────────────────────────

from software_version_service import get_version_service

@router.post("/scan")
async def trigger_live_software_scan(
    tenant_id: str = None,
    current_user: TokenData = Depends(get_current_user),
):
    """
    Trigger a live software inventory scan on all online agents for a tenant.
    Queues a 'run_software_scan' instruction for every online agent.
    The agent collects: apt list --upgradable, pip list --outdated, winget upgrade (Windows).
    """
    try:
        db = get_database()
        is_admin = getattr(current_user, "role", "") in _PATCH_ADMIN_ROLES
        caller_tenant = getattr(current_user, "tenant_id", "default")
        if tenant_id and not is_admin and tenant_id != caller_tenant:
            raise HTTPException(status_code=403, detail="Not authorized to access this tenant")
        effective_tenant = tenant_id if (tenant_id and is_admin) else caller_tenant
        query = {"status": "Online", "tenantId": effective_tenant}

        agents = await db.agents.find(query, {"_id": 0, "id": 1, "hostname": 1}).to_list(length=200)

        if not agents:
            return {"success": True, "triggered": 0, "message": "No online agents found"}

        now = datetime.now(timezone.utc).isoformat()
        instructions = [
            {
                "agent_id":    agent["id"],
                "instruction": "run_software_scan",
                "status":      "pending",
                "created_at":  now,
                "scan_type":   "software_inventory"
            }
            for agent in agents
        ]

        if instructions:
            await db.agent_instructions.insert_many(instructions)

        return {
            "success":   True,
            "triggered": len(agents),
            "agents":    [a["hostname"] for a in agents],
            "message":   f"Software scan queued for {len(agents)} agent(s). Results will appear within 30 seconds."
        }

    except Exception as e:
        logger.error("/patches/scan error: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/outdated")
async def get_outdated_software(
    tenant_id: str = None,
    pkg_type: str = None,
    current_user: TokenData = Depends(get_current_user),
):
    """
    Returns all software packages where a newer version is available.
    Queries PyPI / npm / Ubuntu Packages API for latest versions.
    Results are cached in MongoDB for 24 hours.

    Query params:
    - tenant_id: filter by tenant
    - pkg_type: filter by 'pip', 'npm', 'apt' (optional)
    """
    try:
        db = get_database()
        is_admin = getattr(current_user, "role", "") in _PATCH_ADMIN_ROLES
        caller_tenant = getattr(current_user, "tenant_id", "default")
        if tenant_id and not is_admin and tenant_id != caller_tenant:
            raise HTTPException(status_code=403, detail="Not authorized to access this tenant")
        effective_tenant = tenant_id if (tenant_id and is_admin) else caller_tenant

        # Fetch software inventory reported by agents
        query: dict = {"tenantId": effective_tenant}
        if pkg_type:
            query["pkg_type"] = pkg_type

        packages = await db.software_inventory.find(query, {"_id": 0}).to_list(length=500)

        if not packages:
            # Fallback: read from agent heartbeat data (meta.installed_software)
            agent_query = {"tenantId": effective_tenant}
            
            # Important: installed_software lives in meta object
            agents = await db.agents.find(
                agent_query, 
                {"_id": 0, "meta.installed_software": 1, "tenantId": 1}
            ).to_list(length=100)

            packages = []
            for agent in agents:
                meta = agent.get("meta", {})
                installed_sw = meta.get("installed_software", [])
                
                for sw in installed_sw:
                    pkg = {
                        "name":            sw.get("name", ""),
                        "current_version": sw.get("version", sw.get("current_version", sw.get("currentVersion", ""))),
                        "pkg_type":        sw.get("pkg_type", sw.get("type", "pip")),
                        "tenantId":        agent.get("tenantId"),
                        "agent_id":        agent.get("id")
                    }
                    if pkg["name"] and pkg["current_version"]:
                        packages.append(pkg)

        version_service = get_version_service()
        outdated = await version_service.get_outdated_packages(packages, db)

        # Sort by update_status: major first, then minor, then patch
        severity_order = {"major": 0, "minor": 1, "patch": 2, "unknown": 3}
        outdated.sort(key=lambda p: severity_order.get(p.get("update_status", "unknown"), 3))

        return {
            "total_checked": len(packages),
            "outdated_count": len(outdated),
            "packages": outdated,
            "scanned_at": datetime.now(timezone.utc).isoformat()
        }

    except Exception as e:
        logger.error("/patches/outdated error: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/os")
async def get_os_patches(
    tenant_id: str = None,
    current_user: TokenData = Depends(get_current_user),
):
    """
    Returns OS-level pending patches grouped by asset.
    Includes:
    - Linux: apt list --upgradable output (stored in agent heartbeat)
    - Windows: pending Windows Update / WinGet upgrades
    - Kernel version vs latest stable
    """
    try:
        db = get_database()
        is_admin = getattr(current_user, "role", "") in _PATCH_ADMIN_ROLES
        caller_tenant = getattr(current_user, "tenant_id", "default")
        if tenant_id and not is_admin and tenant_id != caller_tenant:
            raise HTTPException(status_code=403, detail="Not authorized to access this tenant")
        effective_tenant = tenant_id if (tenant_id and is_admin) else caller_tenant
        query = {"tenantId": effective_tenant}

        agents = await db.agents.find(query, {"_id": 0}).to_list(length=200)

        results = []
        for agent in agents:
            meta = agent.get("meta", {})
            os_patches = meta.get("os_patches", {})
            pending_os_updates = agent.get("pending_os_updates", [])

            # Also check installed_software for OS-level packages
            installed_sw = meta.get("installed_software", [])
            os_packages = [
                sw for sw in installed_sw
                if sw.get("pkg_type", sw.get("type")) in ("apt", "deb", "windows_update", "winget", "yum", "rpm")
            ]

            results.append({
                "agent_id":          agent.get("id"),
                "hostname":          agent.get("hostname", "Unknown"),
                "os":                agent.get("os", agent.get("metadata", {}).get("os", "Unknown")),
                "os_version":        agent.get("metadata", {}).get("os_version", "Unknown"),
                "status":            agent.get("status", "unknown"),
                "pending_count":     os_patches.get("pending_count", len(pending_os_updates)),
                "last_checked":      os_patches.get("last_checked", agent.get("lastSeen")),
                "pending_updates":   pending_os_updates or os_patches.get("items", []),
                "os_packages":       os_packages[:20],  # Cap display at 20
                "tenantId":          agent.get("tenantId")
            })

        total_pending = sum(r["pending_count"] for r in results)

        return {
            "assets": results,
            "total_assets": len(results),
            "total_pending_os_patches": total_pending,
            "scanned_at": datetime.now(timezone.utc).isoformat()
        }

    except Exception as e:
        logger.error("/patches/os error: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error")

@router.post("/{patch_id}/verify-integrity")
async def verify_patch_integrity(
    patch_id: str,
    data: dict,
    _current_user: TokenData = Depends(get_current_user),
):
    """
    Verify patch file integrity using checksums
    """
    try:
        security_service = get_security_service()
        result = security_service.verify_patch_integrity(
            patch_file_path=data.get("file_path"),
            expected_checksums=data.get("expected_checksums", {})
        )
        # Log security event
        db = get_database()
        await security_service.audit_security_event(
            db=db,
            event_type="patch_integrity_verified" if result["valid"] else "patch_integrity_failed",
            details={
                "patch_id": patch_id,
                "valid": result["valid"],
                "verified_checksums": result["verified_checksums"],
                "failed_checksums": result["failed_checksums"]
            },
            severity="info" if result["valid"] else "warning"
        )
        return result
    except Exception as e:
        logger.error("Error verifying patch integrity: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error")

@router.post("/{patch_id}/generate-checksums")
async def generate_patch_checksums(
    patch_id: str,
    data: dict,
    _current_user: TokenData = Depends(get_current_user),
):
    """
    Generate checksums for a patch file
    """
    try:
        security_service = get_security_service()
        checksums = security_service.generate_patch_checksum(
            patch_file_path=data.get("file_path")
        )
        # Store checksums in patch record
        db = get_database()
        await db.patches.update_one(
            {"id": patch_id},
            {"$set": {"checksums": checksums}}
        )
        return {
            "success": True,
            "patch_id": patch_id,
            "checksums": checksums
        }
    except Exception as e:
        logger.error("Error generating checksums: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error")

@router.post("/{patch_id}/verify-signature")
async def verify_patch_signature(
    patch_id: str,
    data: dict,
    _current_user: TokenData = Depends(get_current_user),
):
    """
    Verify digital signature of a patch
    """
    try:
        security_service = get_security_service()
        db = get_database()
        # Get public key
        key_record = await db.signing_keys.find_one({"id": data.get("public_key_id")}, {"_id": 0})
        if not key_record:
            raise HTTPException(status_code=404, detail="Public key not found")
        
        # Decode data
        p_data = base64.b64decode(data.get("patch_data"))
        signature = base64.b64decode(data.get("signature"))
        public_key_pem = key_record["public_key"].encode()
        
        # Verify signature
        result = security_service.verify_patch_signature(
            patch_data=p_data,
            signature=signature,
            public_key_pem=public_key_pem
        )
        # Log security event
        await security_service.audit_security_event(
            db=db,
            event_type="signature_verified" if result["valid"] else "signature_invalid",
            details={
                "patch_id": patch_id,
                "valid": result["valid"],
                "key_id": data.get("public_key_id")
            },
            severity="info" if result["valid"] else "critical"
        )
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error verifying signature: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error")

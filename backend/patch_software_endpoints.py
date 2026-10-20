from fastapi import APIRouter, HTTPException, Depends
import logging
import uuid
from datetime import datetime, timezone
from database import get_database
from authentication_service import get_current_user
from rbac_utils import require_permission
from auth_types import TokenData
from patch_core_endpoints import (
    _PATCH_ADMIN_ROLES,
    SoftwareUpdateRequest,
    OsPatchRequest,
    BulkSoftwareUpdateRequest,
    installable_patch_id,
    pending_entry_id,
    new_patch_job,
    patch_instruction,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/patches", tags=["Patch Management"])


@router.post("/apply-software-update")
async def apply_software_update(
    request: SoftwareUpdateRequest,
    _current_user: TokenData = Depends(require_permission("manage:patches")),
):
    """Trigger a package upgrade on an agent."""
    try:
        db = get_database()
        caller_role = getattr(_current_user, "role", None)
        caller_tid = getattr(_current_user, "tenant_id", None) or None
        agent_q: dict = {"id": request.agent_id}
        if caller_role not in _PATCH_ADMIN_ROLES and caller_tid:
            agent_q["tenantId"] = caller_tid
        agent = await db.agents.find_one(agent_q)
        if not agent:
            raise HTTPException(status_code=404, detail="Agent not found")

        tenant_id = agent.get("tenantId") or None
        repo_pkg = await db.local_repo.find_one(
            {"tenantId": tenant_id, "pkg_name": request.package_name, "pkg_type": request.pkg_type},
            sort=[("uploaded_at", -1)],
        )
        payload: dict = {"package": request.package_name, "pkg_type": request.pkg_type}
        if repo_pkg:
            payload["download_url"] = f"/api/repo/download/{repo_pkg['filename']}"

        await db.agent_instructions.insert_one({
            "id":          uuid.uuid4().hex,
            "agent_id":    request.agent_id,
            "tenantId":    tenant_id,
            "instruction": f"upgrade_software: {request.package_name}",
            "status":      "pending",
            "created_at":  datetime.now(timezone.utc).isoformat(),
            "type":        f"upgrade_software: {request.package_name}",
            "payload":     payload,
        })
        return {"success": True, "message": f"Upgrade instruction queued for {request.package_name}"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error applying software update: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/bulk-apply-software-update")
async def apply_bulk_software_update(
    request: BulkSoftwareUpdateRequest,
    _current_user: TokenData = Depends(require_permission("manage:patches")),
):
    """Trigger multiple package upgrades across different agents."""
    try:
        db = get_database()
        bulk_role = getattr(_current_user, "role", None)
        bulk_tid = getattr(_current_user, "tenant_id", None) or None
        instructions = []
        for update in request.updates[:100]:
            bulk_q: dict = {"id": update.agent_id}
            if bulk_role not in _PATCH_ADMIN_ROLES and bulk_tid:
                bulk_q["tenantId"] = bulk_tid
            agent = await db.agents.find_one(bulk_q)
            tenant_id = (agent.get("tenantId") or None) if agent else None
            repo_pkg = await db.local_repo.find_one(
                {"tenantId": tenant_id, "pkg_name": update.package_name, "pkg_type": update.pkg_type},
                sort=[("uploaded_at", -1)],
            )
            payload: dict = {"package": update.package_name, "pkg_type": update.pkg_type}
            if repo_pkg:
                payload["download_url"] = f"/api/repo/download/{repo_pkg['filename']}?tenantId={tenant_id}"
            instructions.append({
                "id":          uuid.uuid4().hex,
                "agent_id":    update.agent_id,
                "tenantId":    tenant_id,
                "instruction": f"upgrade_software: {update.package_name}",
                "status":      "pending",
                "created_at":  datetime.now(timezone.utc).isoformat(),
                "type":        f"upgrade_software: {update.package_name}",
                "payload":     payload,
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
    _current_user: TokenData = Depends(require_permission("manage:patches")),
):
    """Queue OS patch installation (Windows KBs or Linux packages) on one agent."""
    try:
        patch_ids: list = []
        for pid in request.patch_ids:
            ident = installable_patch_id(pid)
            if not ident:
                raise HTTPException(status_code=400, detail=f"Not an installable KB number or package name: {str(pid)[:80]}")
            if ident not in patch_ids:
                patch_ids.append(ident)
        if not patch_ids:
            raise HTTPException(status_code=400, detail="No patches selected")

        db = get_database()
        os_role = getattr(_current_user, "role", None)
        os_tid = getattr(_current_user, "tenant_id", None) or None
        os_q: dict = {"id": request.agent_id}
        if os_role not in _PATCH_ADMIN_ROLES and os_tid:
            os_q["tenantId"] = os_tid
        agent = await db.agents.find_one(os_q)
        if not agent:
            raise HTTPException(status_code=404, detail="Agent not found")
        if str(agent.get("status", "")).lower() == "uninstalled":
            raise HTTPException(status_code=409, detail="The agent on this asset is uninstalled")

        now = datetime.now(timezone.utc).isoformat()
        job_id = f"patch-job-{int(datetime.now(timezone.utc).timestamp())}-{uuid.uuid4().hex[:6]}"
        targets = [a for a in (agent["id"], agent.get("assetId")) if a]
        job = new_patch_job(job_id, agent.get("tenantId"), patch_ids, targets, [agent["id"]],
                            getattr(_current_user, "username", "unknown"), "Immediate", None, now, "In Progress")
        await db.patch_deployment_jobs.insert_one(job)
        await db.agent_instructions.insert_one(patch_instruction(job_id, agent, patch_ids, now))
        return {"success": True, "job_id": job_id, "message": "OS patch installation queued"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error applying OS patches: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/scan")
async def trigger_live_software_scan(
    tenant_id: str = None,
    current_user: TokenData = Depends(require_permission("manage:patches")),
):
    """Trigger a live software inventory scan on all online agents for a tenant."""
    try:
        db = get_database()
        is_admin = getattr(current_user, "role", "") in _PATCH_ADMIN_ROLES
        caller_tenant = getattr(current_user, "tenant_id", None) or None
        if not caller_tenant and not is_admin:
            raise HTTPException(status_code=403, detail="Tenant context required")
        if tenant_id and not is_admin and tenant_id != caller_tenant:
            raise HTTPException(status_code=403, detail="Not authorized to access this tenant")
        effective_tenant = tenant_id if (tenant_id and is_admin) else caller_tenant

        agents = await db.agents.find(
            {"status": "Online", "tenantId": effective_tenant},
            {"_id": 0, "id": 1, "hostname": 1},
        ).to_list(length=200)

        if not agents:
            return {"success": True, "triggered": 0, "message": "No online agents found"}

        now = datetime.now(timezone.utc).isoformat()
        instructions = [
            {"id": uuid.uuid4().hex, "agent_id": a["id"], "tenantId": effective_tenant,
             "instruction": "run_software_scan", "status": "pending",
             "created_at": now, "scan_type": "software_inventory"}
            for a in agents
        ]
        if instructions:
            await db.agent_instructions.insert_many(instructions)

        return {
            "success":   True,
            "triggered": len(agents),
            "agents":    [a["hostname"] for a in agents],
            "message":   f"Software scan queued for {len(agents)} agent(s). Results will appear within 30 seconds.",
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("/patches/scan error: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/outdated")
async def get_outdated_software(
    tenant_id: str = None,
    pkg_type: str = None,
    current_user: TokenData = Depends(get_current_user),
):
    """Returns all software packages where a newer version is available."""
    try:
        from software_version_service import get_version_service
        db = get_database()
        is_admin = getattr(current_user, "role", "") in _PATCH_ADMIN_ROLES
        caller_tenant = getattr(current_user, "tenant_id", None) or None
        if not caller_tenant and not is_admin:
            raise HTTPException(status_code=403, detail="Tenant context required")
        if tenant_id and not is_admin and tenant_id != caller_tenant:
            raise HTTPException(status_code=403, detail="Not authorized to access this tenant")
        effective_tenant = tenant_id if (tenant_id and is_admin) else caller_tenant

        query: dict = {"tenantId": effective_tenant}
        if pkg_type:
            query["pkg_type"] = pkg_type
        packages = await db.software_inventory.find(query, {"_id": 0}).to_list(length=500)

        if not packages:
            agents = await db.agents.find(
                {"tenantId": effective_tenant},
                {"_id": 0, "meta.installed_software": 1, "tenantId": 1},
            ).to_list(length=100)
            packages = []
            for agent in agents:
                meta = agent.get("meta", {})
                for sw in meta.get("installed_software", []):
                    pkg = {
                        "name":            sw.get("name", ""),
                        "current_version": sw.get("version", sw.get("current_version", sw.get("currentVersion", ""))),
                        "pkg_type":        sw.get("pkg_type", sw.get("type", "pip")),
                        "tenantId":        agent.get("tenantId"),
                        "agent_id":        agent.get("id"),
                    }
                    if pkg["name"] and pkg["current_version"]:
                        packages.append(pkg)

        version_service = get_version_service()
        outdated = await version_service.get_outdated_packages(packages, db)
        severity_order = {"major": 0, "minor": 1, "patch": 2, "unknown": 3}
        outdated.sort(key=lambda p: severity_order.get(p.get("update_status", "unknown"), 3))

        return {
            "total_checked":  len(packages),
            "outdated_count": len(outdated),
            "packages":       outdated,
            "scanned_at":     datetime.now(timezone.utc).isoformat(),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("/patches/outdated error: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error")


def pending_patch_ids(agent: dict) -> tuple:
    """Installable pending-update ids for one agent, with display details.

    The Rust agent reports meta.system_patching.pending_updates as objects
    ({id|kb|package, title, severity}); the Python agent reports
    meta.os_patches.items as plain ids. Only KB numbers and package names survive,
    because those are what the agents' install_patches handler accepts."""
    meta = agent.get("meta", {}) or {}
    ids: list = []
    details: list = []

    def add(ident, title=None, severity=None):
        if ident and ident not in ids:
            ids.append(ident)
            details.append({"id": ident, "title": title or ident, "severity": severity or "Unknown"})

    for u in (meta.get("system_patching", {}) or {}).get("pending_updates", []) or []:
        if isinstance(u, dict):
            add(pending_entry_id(u), u.get("title"), u.get("severity"))
    for item in (meta.get("os_patches", {}) or {}).get("items", []) or []:
        if isinstance(item, str):
            add(pending_entry_id(item))
    for item in agent.get("pending_os_updates", []) or []:
        if isinstance(item, str):
            add(pending_entry_id(item))
    return ids, details


@router.get("/os")
async def get_os_patches(
    tenant_id: str = None,
    current_user: TokenData = Depends(get_current_user),
):
    """Returns OS-level pending patches grouped by asset."""
    try:
        db = get_database()
        is_admin = getattr(current_user, "role", "") in _PATCH_ADMIN_ROLES
        caller_tenant = getattr(current_user, "tenant_id", None) or None
        if not caller_tenant and not is_admin:
            raise HTTPException(status_code=403, detail="Tenant context required")
        if tenant_id and not is_admin and tenant_id != caller_tenant:
            raise HTTPException(status_code=403, detail="Not authorized to access this tenant")
        effective_tenant = tenant_id if (tenant_id and is_admin) else caller_tenant

        agents = await db.agents.find({"tenantId": effective_tenant}, {"_id": 0}).to_list(length=200)
        # Patch jobs still waiting on an agent, so the tab can show the install running
        # (and refresh when it ends) instead of offering the same patches again.
        running = await db.patch_deployment_jobs.find(
            {"tenantId": effective_tenant, "status": "In Progress"},
            {"_id": 0, "id": 1, "type": 1, "dispatchedAgents": 1, "agentResults": 1},
        ).to_list(length=200)
        active_jobs: dict = {}
        for job in running:
            reported = job.get("agentResults") or {}
            for aid in job.get("dispatchedAgents") or []:
                if aid.replace(".", "_").replace("$", "_") not in reported:
                    active_jobs.setdefault(aid, {"id": job.get("id"), "type": job.get("type")})

        results = []
        for agent in agents:
            meta = agent.get("meta", {})
            os_patches = meta.get("os_patches", {})
            system_patching = meta.get("system_patching", {})
            installed_sw = meta.get("installed_software", [])
            os_packages = [
                sw for sw in installed_sw
                if sw.get("pkg_type", sw.get("type")) in ("apt", "deb", "windows_update", "winget", "yum", "rpm")
            ]
            pending_ids, pending_details = pending_patch_ids(agent)
            results.append({
                "agent_id":        agent.get("id"),
                "hostname":        agent.get("hostname", "Unknown"),
                "os":              agent.get("os", agent.get("platform", agent.get("metadata", {}).get("os", "Unknown"))),
                "os_version":      agent.get("metadata", {}).get("os_version", "Unknown"),
                "status":          agent.get("status", "unknown"),
                "pending_count":   len(pending_ids),
                # When the pending list was scanned (Rust "timestamp", Python "last_scan"),
                # not the heartbeat time: os_patches is re-sent every heartbeat.
                "last_checked":    (system_patching.get("timestamp") or system_patching.get("last_scan")
                                    or os_patches.get("last_checked") or agent.get("lastSeen")),
                "active_job":      active_jobs.get(agent.get("id")),
                "scan_error":      system_patching.get("scan_error") or os_patches.get("scan_error"),
                "pending_updates": pending_ids,
                "pending_details": pending_details,
                "os_packages":     os_packages[:20],
                "tenantId":        agent.get("tenantId"),
            })

        return {
            "assets":                  results,
            "total_assets":            len(results),
            "total_pending_os_patches": sum(r["pending_count"] for r in results),
            "scanned_at":              datetime.now(timezone.utc).isoformat(),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("/patches/os error: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error")

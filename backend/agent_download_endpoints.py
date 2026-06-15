import asyncio
import os
import secrets
import shutil
import tempfile
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path
from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks, Query, Request
from fastapi.responses import Response
from database import mongodb
from authentication_service import get_current_user, get_optional_user
import yaml
from typing import Optional, Dict, Any

# Prevents concurrent `cargo build --release` runs when multiple users download simultaneously
_rust_build_lock = asyncio.Lock()

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/agent", tags=["Agent Management"])

async def _cleanup_expired_tokens() -> None:
    """Remove expired tokens from the DB. Best-effort; failures are non-fatal."""
    try:
        db = mongodb.db
        await db.agent_download_tokens.delete_many(
            {"expires_at": {"$lt": datetime.now(timezone.utc).isoformat()}}
        )
    except Exception:
        pass


_DOWNLOAD_SUPER_ROLES = {"super admin", "superadmin", "super_admin", "platform-admin"}
_DOWNLOAD_TENANT_ROLES = {"tenant admin", "tenant_admin", "admin"}

def _check_download_auth(tenant_id: str, user_role: str, user_tenant: Optional[str]) -> None:
    """Raise 403 if user is not allowed to download the given tenant's agent."""
    role_lower = (user_role or "").strip().lower()
    is_super_admin = role_lower in _DOWNLOAD_SUPER_ROLES
    is_own_tenant = (user_tenant == tenant_id) and (role_lower in _DOWNLOAD_TENANT_ROLES)
    if not is_super_admin and not is_own_tenant:
        raise HTTPException(status_code=403, detail="Unauthorized to download agent for this tenant")


@router.post("/download-token/{tenant_id}")
async def create_download_token(
    tenant_id: str,
    current_user=Depends(get_current_user),
):
    """
    Returns a 60-second one-time token that can be used to trigger the
    agent ZIP download via a direct browser navigation (window.location.href),
    avoiding fetch()+blob proxy limitations in the Vite dev server.
    """
    user_role = getattr(current_user, "role", "")
    user_tenant = getattr(current_user, "tenant_id", None)
    _check_download_auth(tenant_id, user_role, user_tenant)

    await _cleanup_expired_tokens()
    token = secrets.token_urlsafe(32)
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=60)
    await mongodb.db.agent_download_tokens.insert_one({
        "token": token,
        "tenant_id": tenant_id,
        "user_role": user_role,
        "user_tenant": user_tenant,
        "expires_at": expires_at.isoformat(),
    })
    return {"token": token}

DEFAULT_PLATFORM_URL = os.getenv("PLATFORM_URL", "")

if not DEFAULT_PLATFORM_URL:
    logger.warning(
        "[AgentDownload] PLATFORM_URL is not set. Agent config will use an auto-detected URL "
        "which may resolve to localhost in some environments. Set PLATFORM_URL in your .env "
        "to the public backend address (e.g. https://api.example.com) before distributing agents."
    )

def cleanup_temp_dir(dir_path: str):
    """Background task to securely remove the temporary directory and zip archive."""
    try:
        shutil.rmtree(dir_path, ignore_errors=True)
        logger.debug("Cleaned up temporary directory: %s", dir_path)
    except Exception as e:
        logger.error("Failed to clean up temp dir %s: %s", dir_path, e)

@router.get("/download/{tenant_id}")
async def download_tenant_agent(
    tenant_id: str,
    request: Request,
    background_tasks: BackgroundTasks,
    api_url: Optional[str] = Query(None, description="Backend API base URL to embed in agent config."),
    download_token: Optional[str] = Query(None, description="One-time token from POST /api/agent/download-token/{tenant_id}."),
    platform: Optional[str] = Query("linux", description="Target platform: 'windows' or 'linux' (default)."),
    current_user=Depends(get_optional_user),
):
    """
    Dynamically generates a `.zip` archive containing the `agent/` folder
    with a customized `config.yaml` using the specified tenant's registration key.

    Authentication: Bearer header (normal API call) or ?download_token=... (direct browser nav).
    The `api_url` query parameter controls what backend URL the agent will point to.
    Priority: api_url param > PLATFORM_URL env var > auto-detect from request origin > localhost fallback.
    """
    # 1. Verify authorization — accept either JWT bearer (current_user) or one-time download token
    if download_token:
        await _cleanup_expired_tokens()
        db = mongodb.db
        token_data = await db.agent_download_tokens.find_one_and_delete(
            {"token": download_token, "expires_at": {"$gt": datetime.now(timezone.utc).isoformat()}}
        )
        if not token_data:
            raise HTTPException(status_code=401, detail="Invalid or expired download token")
        if token_data["tenant_id"] != tenant_id:
            raise HTTPException(status_code=403, detail="Token tenant mismatch")
        user_role = token_data["user_role"]
        user_tenant = token_data["user_tenant"]
    else:
        user_role = getattr(current_user, "role", "")
        user_tenant = getattr(current_user, "tenant_id", None)

    _check_download_auth(tenant_id, user_role, user_tenant)

    # 2. Resolve the API Base URL to embed in config.yaml
    if api_url:
        from urllib.parse import urlparse as _urlparse
        _parsed = _urlparse(api_url)
        if _parsed.scheme not in {"http", "https"} or not _parsed.netloc:
            raise HTTPException(status_code=400, detail="Invalid api_url: must be an absolute http/https URL")
        resolved_url = api_url.rstrip("/")
    elif os.getenv("PLATFORM_URL"):
        resolved_url = os.getenv("PLATFORM_URL").rstrip("/")
    else:
        # Auto-detect from request host header
        host = request.headers.get("host", "")
        hostname = host.split(":")[0] if host else ""
        if not hostname or hostname in ("localhost", "127.0.0.1", "0.0.0.0", "::1"):
            raise HTTPException(
                status_code=400,
                detail=(
                    "Cannot generate agent config: PLATFORM_URL is not set and the request "
                    "host resolves to localhost. Set PLATFORM_URL to the public backend address "
                    "(e.g. https://api.example.com) in your environment before downloading agents."
                ),
            )
        resolved_url = f"http://{hostname}:5000"

    logger.info("Generating agent zip for tenant %s with api_base_url=%s", tenant_id, resolved_url)
    # Audit log
    try:
        from database import get_database as _get_db
        _adb = _get_db()
        await _adb.audit_logs.insert_one({
            "action": "agent.downloaded",
            "actor": user_role,
            "target": tenant_id,
            "tenant_id": user_tenant or tenant_id,
            "ip": request.client.host if request.client else "unknown",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
    except Exception as e:
        logger.debug("Audit log write failed (non-fatal): %s", e)

    # 3. Fetch Tenant Data
    tenant = await mongodb.db.tenants.find_one({"id": tenant_id})
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    registration_key = tenant.get("registrationKey") or ""
    if not registration_key:
        registration_key = f"reg_{secrets.token_hex(16)}"
        await mongodb.db.tenants.update_one(
            {"id": tenant_id},
            {"$set": {"registrationKey": registration_key}},
        )

    tenant_name = tenant.get("name", tenant_id)

    # 4a. Windows EXE package path
    if (platform or "linux").lower() == "windows":
        return await _build_tenant_nsis_exe(
            tenant_id, tenant_name, registration_key, resolved_url, background_tasks
        )

    # 4. Locate Source Agent Directory (Linux/Python fallback)
    base_dir = Path(__file__).parent.parent
    agent_src_dir = base_dir / "agent"

    if not agent_src_dir.exists() or not agent_src_dir.is_dir():
        raise HTTPException(status_code=500, detail="Source agent directory not found on server")

    # 5. Create Temporary Workspace
    temp_dir = Path(tempfile.mkdtemp(prefix=f"omni_agent_{tenant_id}_"))
    agent_dest_dir = temp_dir / "agent"

    try:
        # 6. Copy Agent Files (Excluding existing configs/keys/db/pycache/venv)
        shutil.copytree(
            agent_src_dir,
            agent_dest_dir,
            ignore=shutil.ignore_patterns(
                '__pycache__', '*.pyc', 'config.yaml', '*.key', '*.db',
                '*.log', 'venv', '.venv', 'node_modules', 'buffer.db'
            )
        )

        # 7. Generate Tenant-Specific config.yaml
        # agent_id and agent_token are null until the agent registers on first run;
        # the agent writes them back to config.yaml after successful registration.
        config_data = {
            "agent_id": None,
            "agent_token": None,
            "api_base_url": resolved_url,
            "interval_seconds": 5,
            "registration_key": registration_key,
        }

        config_path = agent_dest_dir / "config.yaml"
        with open(config_path, "w", encoding="utf-8") as f:
            yaml.dump(config_data, f, default_flow_style=False, sort_keys=True)

        # 8. Add a README with instructions
        readme_content = f"""# OmniAgent — {tenant_name}

Pre-configured agent package for tenant: **{tenant_name}**

## Quick Start

1. Ensure Python 3.9+ is installed on the target machine.
2. Navigate into this folder:
   ```
   cd agent
   ```
3. Install dependencies:
   ```
   pip install -r requirements.txt
   ```
4. Run the agent:
   ```
   python agent.py
   ```

The agent is pre-configured and will automatically register with the platform on its first run.
- **API Base URL**: `{resolved_url}`

⚠️  Keep this ZIP secure — it contains pre-configured credentials for your tenant.
"""
        readme_path = agent_dest_dir / "README.md"
        with open(readme_path, "w", encoding="utf-8") as f:
            f.write(readme_content)

        # 9. Create Zip Archive
        zip_filename = f"omni-agent-{tenant_name.replace(' ', '-').lower()}"
        zip_base_name = temp_dir / zip_filename
        shutil.make_archive(
            base_name=str(zip_base_name),
            format="zip",
            root_dir=temp_dir,
            base_dir="agent"
        )

        zip_file_path = f"{zip_base_name}.zip"

        if not os.path.exists(zip_file_path):
            raise Exception("Zip archive creation failed")

        # 10. Read zip into memory
        with open(zip_file_path, "rb") as f:
            zip_content = f.read()

        # 11. Dispatch Background Cleanup
        background_tasks.add_task(cleanup_temp_dir, str(temp_dir))

        # 12. Return File Stream
        download_filename = f"{zip_filename}.zip"
        return Response(
            content=zip_content,
            media_type="application/zip",
            headers={"Content-Disposition": f'attachment; filename="{download_filename}"'}
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to package agent zip: %s", e)
        background_tasks.add_task(cleanup_temp_dir, str(temp_dir))
        raise HTTPException(status_code=500, detail="Internal server error")


# ── Agent Command Dispatch ─────────────────────────────────────────────────────

@router.post("/deploy")
async def agent_deploy_command(
    payload: Dict[str, Any],
    current_user=Depends(get_current_user),
):
    """
    Dispatch a command to one or more agents via the agent_instructions queue.
    Used by AssetDetail (RDP enable/disable) and SoftwareDeployment.
    Body: { agentIds: [...], action: str, packageId?: str, config?: dict }
    """
    from database import get_database
    import uuid

    agent_ids = (payload.get("agentIds") or payload.get("agent_ids") or [])[:500]
    action = payload.get("action", "")
    package_id = payload.get("packageId") or payload.get("package_id", "")

    if not agent_ids or not action:
        raise HTTPException(status_code=400, detail="agentIds and action are required")

    db = get_database()
    caller_role = getattr(current_user, "role", "")
    caller_tenant = getattr(current_user, "tenant_id", None)
    _DEPLOY_SUPER_ROLES = {"Super Admin", "super_admin", "platform-admin"}

    task_id = f"deploy-{uuid.uuid4().hex[:10]}"
    now = datetime.now(timezone.utc).isoformat()

    # Batch-fetch all agents in one query instead of one find_one per agent_id
    batch_filter: dict = {"id": {"$in": agent_ids}}
    if caller_role not in _DEPLOY_SUPER_ROLES and caller_tenant:
        batch_filter["tenantId"] = caller_tenant
    agent_docs = await db.agents.find(batch_filter, {"id": 1}).to_list(length=500)
    valid_agent_ids = {doc["id"] for doc in agent_docs}

    instructions = []
    for agent_id in agent_ids:
        if agent_id not in valid_agent_ids:
            continue  # skip agents not in caller's tenant
        instructions.append({
            "id": f"instr-{uuid.uuid4().hex[:10]}",
            "task_id": task_id,
            "agent_id": agent_id,
            "instruction": action,
            "package_id": package_id,
            "config": payload.get("config", {}),
            "status": "pending",
            "created_at": now,
            "created_by": getattr(current_user, "username", str(current_user)),
        })

    if instructions:
        await db.agent_instructions.insert_many(instructions)

    return {
        "task_id": task_id,
        "agents_targeted": len(agent_ids),
        "action": action,
        "status": "queued",
    }


# ── Windows Per-Tenant Installer Builders ─────────────────────────────────────


async def _ensure_windows_binary(exe_path: Path) -> None:
    """
    Build the Rust agent if the binary doesn't exist yet.
    Uses a lock so only one compilation runs at a time.
    On first download this takes ~2-5 minutes; subsequent downloads are instant.
    """
    if exe_path.exists():
        return

    async with _rust_build_lock:
        if exe_path.exists():  # another request may have finished building while we waited
            return

        src_dir = exe_path.parent.parent.parent  # agent-install/omni-agent-rs
        cargo = shutil.which("cargo")
        if not src_dir.is_dir() or not cargo:
            raise HTTPException(
                status_code=503,
                detail=(
                    "Windows agent binary not found and Rust toolchain (cargo) is not available "
                    "on this server. Pre-build the binary with: "
                    "cd agent-install/omni-agent-rs && cargo build --release"
                ),
            )

        logger.info(
            "Auto-building Windows agent binary (first download, ~2–5 min). "
            "Subsequent downloads will be instant."
        )
        proc = await asyncio.create_subprocess_exec(
            cargo, "build", "--release",
            cwd=str(src_dir),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            _, stderr_bytes = await asyncio.wait_for(proc.communicate(), timeout=600)
        except (asyncio.TimeoutError, TimeoutError):
            raise HTTPException(
                status_code=503,
                detail="Windows agent compilation timed out (>10 min). Try again or pre-build manually.",
            )

        if proc.returncode != 0:
            snippet = (stderr_bytes or b"").decode(errors="replace")[-400:]
            logger.error("cargo build --release failed:\n%s", snippet)
            raise HTTPException(
                status_code=503,
                detail=f"Windows agent compilation failed. Last error output: {snippet}",
            )

        if not exe_path.exists():
            raise HTTPException(
                status_code=503,
                detail="Compilation succeeded but binary was not found at expected path.",
            )

        logger.info("Windows agent binary built successfully: %s", exe_path)


async def _build_tenant_msi(
    tenant_id: str,
    tenant_name: str,
    registration_key: str,
    api_url: str,
    background_tasks: BackgroundTasks,
) -> Response:
    """
    Build a per-tenant MSI with tenant credentials baked in at WiX compile time.
    Returns a single .msi file — no ZIP, no separate config.yaml required.
    """
    base_dir = Path(__file__).parent.parent
    rs_dir = base_dir / "agent-install" / "omni-agent-rs"
    exe_path = rs_dir / "target" / "release" / "omni-agent.exe"
    wxs_path = rs_dir / "omni-agent.wxs"

    await _ensure_windows_binary(exe_path)

    wix = shutil.which("wix")
    if not wix or not wxs_path.exists():
        raise HTTPException(
            status_code=503,
            detail=(
                "WiX toolset not available on this server. "
                "Install WiX 4 or pre-build the MSI manually: "
                "cd agent-install/omni-agent-rs && wix build omni-agent.wxs"
            ),
        )

    temp_dir = Path(tempfile.mkdtemp(prefix=f"omni_msi_{tenant_id}_"))
    try:
        config_data = {
            "api_base_url": api_url,
            "tenant_id": tenant_id,
            "agent_id": "",
            "agent_token": "",
            "registration_key": registration_key,
            "interval_seconds": 30,
            "max_cpu_percent": 20,
            "agentic_mode_enabled": False,
        }
        config_path = temp_dir / "config.yaml"
        with open(config_path, "w", encoding="utf-8") as f:
            yaml.dump(config_data, f, default_flow_style=False, sort_keys=True)

        tenant_safe = tenant_name.replace(" ", "-").lower()
        msi_filename = f"OmniAgent-{tenant_safe}-Setup.msi"
        msi_out = temp_dir / msi_filename

        logger.info("Building per-tenant MSI for %s (api_url=%s)...", tenant_id, api_url)
        proc = await asyncio.create_subprocess_exec(
            wix, "build", str(wxs_path),
            "-d", f"ConfigSource={config_path}",
            "-o", str(msi_out),
            cwd=str(rs_dir),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            _, stderr_bytes = await asyncio.wait_for(proc.communicate(), timeout=600)
        except (asyncio.TimeoutError, TimeoutError):
            raise HTTPException(status_code=503, detail="MSI build timed out (>10 min). Try again.")

        if proc.returncode != 0:
            snippet = (stderr_bytes or b"").decode(errors="replace")[-400:]
            logger.error("wix build failed:\n%s", snippet)
            raise HTTPException(status_code=503, detail=f"MSI build failed: {snippet}")

        if not msi_out.exists():
            raise HTTPException(status_code=503, detail="MSI build succeeded but output file not found.")

        with open(msi_out, "rb") as f:
            content = f.read()

        background_tasks.add_task(cleanup_temp_dir, str(temp_dir))
        return Response(
            content=content,
            media_type="application/octet-stream",
            headers={"Content-Disposition": f'attachment; filename="{msi_filename}"'},
        )
    except HTTPException:
        background_tasks.add_task(cleanup_temp_dir, str(temp_dir))
        raise
    except Exception as e:
        logger.error("Failed to build tenant MSI: %s", e)
        background_tasks.add_task(cleanup_temp_dir, str(temp_dir))
        raise HTTPException(status_code=500, detail="Failed to build Windows MSI installer")


async def _build_tenant_nsis_exe(
    tenant_id: str,
    tenant_name: str,
    registration_key: str,
    api_url: str,
    background_tasks: BackgroundTasks,
) -> Response:
    """
    Build a per-tenant NSIS EXE with credentials baked in via /D defines.
    Falls back to a per-tenant WiX MSI when NSIS is not installed.
    Returns a single .exe or .msi — no ZIP, no separate scripts required.
    """
    makensis = shutil.which("makensis")
    if not makensis:
        logger.info("NSIS not found; falling back to MSI for tenant %s", tenant_id)
        return await _build_tenant_msi(tenant_id, tenant_name, registration_key, api_url, background_tasks)

    base_dir = Path(__file__).parent.parent
    nsi_path = base_dir / "agent-install" / "omni-agent.nsi"
    exe_path = base_dir / "agent-install" / "omni-agent-rs" / "target" / "release" / "omni-agent.exe"

    await _ensure_windows_binary(exe_path)

    temp_dir = Path(tempfile.mkdtemp(prefix=f"omni_exe_{tenant_id}_"))
    try:
        tenant_safe = tenant_name.replace(" ", "-").lower()
        exe_filename = f"OmniAgent-{tenant_safe}-Setup.exe"
        exe_out = temp_dir / exe_filename

        logger.info("Building per-tenant NSIS EXE for %s (api_url=%s)...", tenant_id, api_url)
        proc = await asyncio.create_subprocess_exec(
            makensis,
            f"/DBAKED_API_URL={api_url}",
            f"/DBAKED_TENANT_ID={tenant_id}",
            f"/DBAKED_REG_KEY={registration_key}",
            f"/DOUTFILE={exe_out}",
            str(nsi_path),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            _, stderr_bytes = await asyncio.wait_for(proc.communicate(), timeout=300)
        except (asyncio.TimeoutError, TimeoutError):
            raise HTTPException(status_code=503, detail="EXE build timed out (>5 min). Try again.")

        if proc.returncode != 0:
            snippet = (stderr_bytes or b"").decode(errors="replace")[-400:]
            logger.error("makensis failed:\n%s", snippet)
            raise HTTPException(status_code=503, detail=f"EXE build failed: {snippet}")

        if not exe_out.exists():
            raise HTTPException(status_code=503, detail="NSIS build succeeded but output file not found.")

        with open(exe_out, "rb") as f:
            content = f.read()

        background_tasks.add_task(cleanup_temp_dir, str(temp_dir))
        return Response(
            content=content,
            media_type="application/octet-stream",
            headers={"Content-Disposition": f'attachment; filename="{exe_filename}"'},
        )
    except HTTPException:
        background_tasks.add_task(cleanup_temp_dir, str(temp_dir))
        raise
    except Exception as e:
        logger.error("Failed to build tenant EXE: %s", e)
        background_tasks.add_task(cleanup_temp_dir, str(temp_dir))
        raise HTTPException(status_code=500, detail="Failed to build Windows EXE installer")


@router.get("/download/{tenant_id}/msi")
async def download_tenant_agent_msi(
    tenant_id: str,
    request: Request,
    background_tasks: BackgroundTasks,
    api_url: Optional[str] = Query(None, description="Backend API base URL to embed in agent config."),
    download_token: Optional[str] = Query(None),
    current_user=Depends(get_optional_user),
):
    """
    Build and return a per-tenant MSI with tenant credentials baked in.
    Single .msi file — no ZIP, no separate config.yaml or scripts required.
    On first download, compiles the Rust binary and builds the MSI on-demand.
    """
    if download_token:
        await _cleanup_expired_tokens()
        token_data = await mongodb.db.agent_download_tokens.find_one_and_delete(
            {"token": download_token, "expires_at": {"$gt": datetime.now(timezone.utc).isoformat()}}
        )
        if not token_data:
            raise HTTPException(status_code=401, detail="Invalid or expired download token")
        if token_data["tenant_id"] != tenant_id:
            raise HTTPException(status_code=403, detail="Token tenant mismatch")
        user_role = token_data["user_role"]
        user_tenant = token_data["user_tenant"]
    else:
        user_role = getattr(current_user, "role", "")
        user_tenant = getattr(current_user, "tenant_id", None)

    _check_download_auth(tenant_id, user_role, user_tenant)

    tenant = await mongodb.db.tenants.find_one({"id": tenant_id})
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    registration_key = tenant.get("registrationKey") or ""
    if not registration_key:
        registration_key = f"reg_{secrets.token_hex(16)}"
        await mongodb.db.tenants.update_one({"id": tenant_id}, {"$set": {"registrationKey": registration_key}})

    tenant_name = tenant.get("name", tenant_id)

    if api_url:
        from urllib.parse import urlparse as _up
        _p = _up(api_url)
        if _p.scheme not in {"http", "https"} or not _p.netloc:
            raise HTTPException(status_code=400, detail="Invalid api_url: must be an absolute http/https URL")
        platform_url = api_url.rstrip("/")
    elif os.getenv("PLATFORM_URL"):
        platform_url = os.getenv("PLATFORM_URL").rstrip("/")
    else:
        host = request.headers.get("host", "")
        hostname = host.split(":")[0] if host else ""
        if not hostname or hostname in ("localhost", "127.0.0.1", "0.0.0.0", "::1"):
            raise HTTPException(
                status_code=400,
                detail="Cannot generate agent config: set PLATFORM_URL to the public backend address.",
            )
        platform_url = f"http://{hostname}:5000"

    logger.info("MSI download requested for tenant %s (api_url=%s)", tenant_id, platform_url)
    return await _build_tenant_msi(tenant_id, tenant_name, registration_key, platform_url, background_tasks)


# ── Agent Install Instructions ─────────────────────────────────────────────────

@router.get("/install/{tenant_id}")
async def get_agent_install_instructions(
    tenant_id: str,
    request: Request,
    current_user=Depends(get_optional_user),
):
    """
    Return agent installation instructions for a tenant.
    Includes the registration key, platform URL, and multi-platform install commands.
    Tests: B8 — GET /api/agents/install/:tenant_id
    """
    _check_download_auth(
        tenant_id,
        getattr(current_user, "role", "") if current_user else "",
        getattr(current_user, "tenant_id", None) if current_user else None,
    )

    tenant = await mongodb.db.tenants.find_one({"id": tenant_id})
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    reg_key = tenant.get("registrationKey") or ""
    if not reg_key:
        # Tenant was created before registrationKey was introduced — generate and persist one now.
        reg_key = f"reg_{secrets.token_hex(16)}"
        await mongodb.db.tenants.update_one(
            {"id": tenant_id},
            {"$set": {"registrationKey": reg_key}},
        )

    platform_url = os.getenv("PLATFORM_URL", "").rstrip("/") or f"http://{request.headers.get('host', 'localhost:5000')}"

    download_url = f"{platform_url}/api/agent/download/{tenant_id}"
    linux_install = (
        f"curl -sSL {download_url} -o agent.zip && "
        "unzip agent.zip && cd agent && "
        f"python agent.py --api-url {platform_url} --registration-key {reg_key}"
    )
    windows_install = (
        f"Invoke-WebRequest -Uri '{download_url}' -OutFile agent.zip; "
        "Expand-Archive agent.zip -DestinationPath agent; "
        f"cd agent; python agent.py --api-url {platform_url} --registration-key {reg_key}"
    )

    return {
        "tenant_id": tenant_id,
        "tenant_name": tenant.get("name", ""),
        "registration_key": reg_key,
        "platform_url": platform_url,
        "download_url": download_url,
        "instructions": {
            "linux": linux_install,
            "windows": windows_install,
            "docker": (
                f"docker run -d --name omni-agent "
                f"-e PLATFORM_URL={platform_url} "
                f"-e REGISTRATION_KEY={reg_key} "
                "ghcr.io/omni-agent/agent:latest"
            ),
        },
        "requirements": ["Python 3.10+", "pip install -r requirements.txt"],
    }

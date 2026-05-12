import os
import secrets
import shutil
import tempfile
from datetime import datetime, timezone, timedelta
from pathlib import Path
from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks, Query, Request
from fastapi.responses import Response
from database import mongodb
from authentication_service import get_current_user, get_optional_user
import yaml
from typing import Optional, Dict, Any

router = APIRouter(prefix="/api/agent", tags=["Agent Management"])

# Short-lived one-time download tokens {token: {tenant_id, user_role, user_tenant, expires_at}}
_download_tokens: Dict[str, Dict[str, Any]] = {}

def _cleanup_expired_tokens() -> None:
    now = datetime.now(timezone.utc)
    expired = [k for k, v in _download_tokens.items() if v["expires_at"] < now]
    for k in expired:
        del _download_tokens[k]


def _check_download_auth(tenant_id: str, user_role: str, user_tenant: Optional[str]) -> None:
    """Raise 403 if user is not allowed to download the given tenant's agent."""
    is_super_admin = user_role in ("Super Admin", "superadmin", "super_admin")
    is_own_tenant = (user_tenant == tenant_id) and (user_role in ("Tenant Admin", "tenant_admin", "Admin"))
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

    _cleanup_expired_tokens()
    token = secrets.token_urlsafe(32)
    _download_tokens[token] = {
        "tenant_id": tenant_id,
        "user_role": user_role,
        "user_tenant": user_tenant,
        "expires_at": datetime.now(timezone.utc) + timedelta(seconds=60),
    }
    return {"token": token}

# The platform URL can be set via an environment variable for cloud/production deployments.
# Falls back to http://localhost:5000 if unset.
DEFAULT_PLATFORM_URL = os.getenv("PLATFORM_URL", "http://localhost:5000")

def cleanup_temp_dir(dir_path: str):
    """Background task to securely remove the temporary directory and zip archive."""
    try:
        shutil.rmtree(dir_path, ignore_errors=True)
        print(f"[DEBUG] Cleaned up temporary directory: {dir_path}")
    except Exception as e:
        print(f"[ERROR] Failed to clean up temp dir {dir_path}: {e}")

@router.get("/download/{tenant_id}")
async def download_tenant_agent(
    tenant_id: str,
    request: Request,
    background_tasks: BackgroundTasks,
    api_url: Optional[str] = Query(None, description="Backend API base URL to embed in agent config. If omitted, auto-detected from request or PLATFORM_URL env var."),
    download_token: Optional[str] = Query(None, description="One-time token from POST /api/agent/download-token/{tenant_id}. Use instead of Bearer auth for direct browser navigation."),
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
        _cleanup_expired_tokens()
        token_data = _download_tokens.pop(download_token, None)
        if not token_data or token_data["expires_at"] < datetime.now(timezone.utc):
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
        resolved_url = api_url.rstrip("/")
    elif os.getenv("PLATFORM_URL"):
        resolved_url = os.getenv("PLATFORM_URL").rstrip("/")
    else:
        # Auto-detect from request: use the host of the incoming request, port 5000
        host = request.headers.get("host", "localhost:5000")
        # Strip any existing port; always append :5000 for backend
        hostname = host.split(":")[0]
        resolved_url = f"http://{hostname}:5000"

    print(f"[INFO] Generating agent zip for tenant {tenant_id} with api_base_url={resolved_url}")

    # 3. Fetch Tenant Data
    tenant = await mongodb.db.tenants.find_one({"id": tenant_id})
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    registration_key = tenant.get("registrationKey")
    if not registration_key:
        raise HTTPException(status_code=500, detail="Tenant lacks a registration key")

    tenant_name = tenant.get("name", tenant_id)

    # 4. Locate Source Agent Directory
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
        with open(config_path, "w") as f:
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

The agent is pre-configured with:
- **API Base URL**: `{resolved_url}`  
- **Registration Key**: `{registration_key}`

The agent will automatically register with the platform on its first run.
"""
        readme_path = agent_dest_dir / "README.md"
        with open(readme_path, "w") as f:
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
        print(f"[ERROR] Failed to package agent zip: {str(e)}")
        background_tasks.add_task(cleanup_temp_dir, str(temp_dir))
        raise HTTPException(status_code=500, detail=f"Internal server error packaging the agent: {str(e)}")


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

    agent_ids = payload.get("agentIds") or payload.get("agent_ids") or []
    action = payload.get("action", "")
    package_id = payload.get("packageId") or payload.get("package_id", "")

    if not agent_ids or not action:
        raise HTTPException(status_code=400, detail="agentIds and action are required")

    db = get_database()
    task_id = f"deploy-{uuid.uuid4().hex[:10]}"
    now = datetime.now(timezone.utc).isoformat()
    instructions = []
    for agent_id in agent_ids:
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




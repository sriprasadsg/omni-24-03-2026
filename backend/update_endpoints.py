from fastapi import APIRouter, HTTPException, BackgroundTasks
import logging
from fastapi.responses import FileResponse, JSONResponse
import os
import glob
import subprocess
import time
import uuid
import asyncio
import threading
from concurrent.futures import ThreadPoolExecutor

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/agent-updates",
    tags=["Agent Update"]
)

# ── Storage & build config ──────────────────────────────────
BINARY_STORAGE_PATH = os.path.join(os.path.dirname(__file__), "static")
BUILD_STATE = {}  # task_id → {"status": "building"|"done"|"failed", "path": ..., "error": ...}
_executor = ThreadPoolExecutor(max_workers=1)

# Paths used by the Spyglass build pipeline
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
WIN_INSTALLER_SCRIPT = os.path.join(PROJECT_ROOT, "agent", "installer", "OmniAgent-Setup.iss")
NSIS_SCRIPT = os.path.join(PROJECT_ROOT, "agent-install", "omni-agent.nsi")
SPYGLASS_DIR = os.path.join(PROJECT_ROOT, "build", "spyglass")
SPYGLASS_UNIFIED = os.path.join(SPYGLASS_DIR, "unified-collection.ps1")
AGENT_COLLECT_PS1 = os.path.join(PROJECT_ROOT, "agent", "installer", "Collect-Evidence.ps1")


def _run_build(task_id: str):
    """Build the EXE/MSI installer with spyglass evidence capture (runs on thread pool)."""
    import sys
    import shutil

    # Windows-only build: powershell.exe, iscc.exe, makensis — none exist on Linux.
    if sys.platform != "win32":
        logger.info("[Build] Skipping EXE build (not Windows)")
        BUILD_STATE[task_id] = {"status": "failed", "path": None, "error": "Windows EXE build requires Windows"}
        return

    BUILD_STATE[task_id] = {"status": "building", "path": None, "error": None}
    try:
        out_dir = os.path.join(PROJECT_ROOT, "agent", "installer", "dist")
        os.makedirs(out_dir, exist_ok=True)

        # 1. Copy collect script into spyglass dir so unified-collection.ps1 can find it
        spyglass_build_dir = os.path.join(PROJECT_ROOT, "build", "spyglass")
        os.makedirs(spyglass_build_dir, exist_ok=True)
        if os.path.exists(AGENT_COLLECT_PS1):
            shutil.copy2(AGENT_COLLECT_PS1, os.path.join(spyglass_build_dir, "Collect-Evidence.ps1"))

        # 2. Run Spyglass unified collection (generates spyglass.json manifest)
        #    This validates Collect-Evidence.ps1, snapshots PS env, and hashes artifacts
        if os.path.exists(SPYGLASS_UNIFIED):
            logger.info("[Spyglass] Running unified evidence collection...")
            ps_result = subprocess.run(
                ["powershell.exe", "-ExecutionPolicy", "Bypass", "-File", SPYGLASS_UNIFIED,
                 "-BuildRoot", spyglass_build_dir],
                capture_output=True, text=True, timeout=120
            )
            if ps_result.returncode != 0:
                logger.warning("[Spyglass] Non-zero exit %d: %s", ps_result.returncode, ps_result.stderr)
            else:
                logger.info("[Spyglass] Evidence manifest generated: %s",
                            os.path.join(spyglass_build_dir, "spyglass", "spyglass.json"))
        else:
            logger.warning("[Spyglass] unified-collection.ps1 not found at %s — skipping", SPYGLASS_UNIFIED)

        # 3. Build EXE installer
        #    Try InnoSetup first (iscc.exe), fall back to NSIS (makensis)
        installer_exe = None

        # 3a. InnoSetup build
        if os.path.exists(WIN_INSTALLER_SCRIPT):
            iscc = shutil.which("iscc.exe") or r"C:\Program Files (x86)\Inno Setup 6\iscc.exe"
            if os.path.exists(iscc):
                logger.info("[Build] Running InnoSetup: %s", iscc)
                result = subprocess.run(
                    [iscc, WIN_INSTALLER_SCRIPT],
                    capture_output=True, text=True, timeout=300
                )
                if result.returncode == 0:
                    possible = glob.glob(os.path.join(out_dir, "OmniAgent-Setup*.exe"))
                    if possible:
                        installer_exe = max(possible, key=os.path.getmtime)
                        logger.info("[Build] InnoSetup success: %s", installer_exe)
                    else:
                        logger.warning("[Build] InnoSetup claimed success but no .exe found")
                else:
                    logger.warning("[Build] InnoSetup failed (%d): %s", result.returncode, result.stderr[:500])
            else:
                logger.warning("[Build] iscc.exe not found at %s", iscc)

        # 3b. NSIS fallback
        if not installer_exe and os.path.exists(NSIS_SCRIPT):
            makensis = shutil.which("makensis")
            if makensis:
                logger.info("[Build] Running makensis (NSIS): %s", makensis)
                result = subprocess.run(
                    [makensis, NSIS_SCRIPT],
                    capture_output=True, text=True, timeout=300
                )
                if result.returncode == 0:
                    nsis_out = os.path.join(PROJECT_ROOT, "agent-install", "OmniAgent-Setup.exe")
                    if os.path.exists(nsis_out):
                        installer_exe = nsis_out
                        logger.info("[Build] NSIS success: %s", installer_exe)
                else:
                    logger.warning("[Build] NSIS failed (%d): %s", result.returncode, result.stderr[:500])
            else:
                logger.warning("[Build] makensis not found on PATH")

        # 4. Copy to backend/static for serving
        if installer_exe and os.path.exists(installer_exe):
            dest = os.path.join(BINARY_STORAGE_PATH, "OmniAgent-Setup.exe")
            os.makedirs(BINARY_STORAGE_PATH, exist_ok=True)
            shutil.copy2(installer_exe, dest)
            BUILD_STATE[task_id] = {"status": "done", "path": dest, "error": None}
            logger.info("[Build] EXE ready at %s", dest)
        else:
            # Fallback: check if a prebuilt exists
            fallback = os.path.join(BINARY_STORAGE_PATH, "OmniAgent-Setup.exe")
            if os.path.exists(fallback):
                BUILD_STATE[task_id] = {"status": "done", "path": fallback, "error": None}
                logger.info("[Build] Using prebuilt EXE at %s", fallback)
            else:
                BUILD_STATE[task_id] = {"status": "failed", "path": None,
                                        "error": "No installer tool found (iscc.exe or makensis). See agent-install/README."}

    except Exception as e:
        BUILD_STATE[task_id] = {"status": "failed", "path": None, "error": str(e)}
        logger.exception("[Build] Build failed: %s", e)

@router.get("/latest")
async def get_latest_version(platform: str = "windows"):
    """
    Get the latest available agent version info.
    """
    # In a real app, this would query a DB or read a manifest.
    # For MVP, we check the backend/static folder naming convention:
    # omni-agent-{version}-{platform}.exe
    
    # Ensure dir exists
    if not os.path.exists(BINARY_STORAGE_PATH):
        os.makedirs(BINARY_STORAGE_PATH, exist_ok=True)
        
    base_url = "http://localhost:5000" # Dynamic in prod
    
    # Check for agent.py updates (Script based)
    agent_script_path = os.path.join("..", "agent", "agent.py")
    script_info = None
    if os.path.exists(agent_script_path):
        import re
        try:
            content = open(agent_script_path, "r", encoding="utf-8").read()
            match = re.search(r'AGENT_VERSION\s*=\s*"([^"]+)"', content)
            if match:
                script_version = match.group(1)
                script_info = {
                    "version": script_version,
                    "filename": "agent.py",
                    "url": f"{base_url}/api/agent-updates/download/agent.py",
                    "release_date": os.path.getmtime(agent_script_path)
                }
        except Exception as e:
            logger.error("Error reading agent version: %s", e)

    # If platform is 'python' or 'script', return script info immediately
    if platform.lower() in ["python", "script"]:
        if script_info:
            return script_info
        return {"version": "0.0.0", "url": None, "message": "No script update available"}

    # Pattern match for binaries
    # Windows: omni-agent-*-windows.exe
    # Linux: omni-agent-*-linux
    
    suffix = ".exe" if platform.lower() == "windows" else ""
    pattern = f"omni-agent-*{suffix}"
    
    files = glob.glob(os.path.join(BINARY_STORAGE_PATH, pattern))
    if not files:
        # Fallback to script if binary not found
        if script_info:
            return script_info
        return {"version": "0.0.0", "url": None, "message": "No updates available"}
        
    # Sort by name (assuming version numbers sort correctly or use creation time)
    # Ideally: omni-agent-2.0.1-windows.exe
    latest_file = max(files, key=os.path.getmtime)
    filename = os.path.basename(latest_file)
    
    # Extract version? 
    # Let's assume filename format: omni-agent-{version}-windows.exe
    try:
        parts = filename.split('-')
        # omni, agent, 2.0.1, windows.exe
        version = parts[2]
    except IndexError:
        version = "unknown"
        
    download_url = f"{base_url}/api/agent-updates/download/{filename}"
    
    return {
        "version": version,
        "filename": filename,
        "url": download_url,
        "release_date": os.path.getmtime(latest_file)
    }

@router.get("/download/{filename}")
async def download_agent_binary(filename: str):
    # Allow downloading specific named files like 'omni-agent.exe' if they exist
    # or map 'omni-agent.exe' to the latest version
    
    # Special handling for Python agent
    if filename == "agent.py":
        agent_path = os.path.join("..", "agent", "agent.py")
        if os.path.exists(agent_path):
            return FileResponse(agent_path, filename="agent.py", media_type="text/plain")
    
    target_path = os.path.join(BINARY_STORAGE_PATH, filename)
    
    # Fallback: if requesting omni-agent.exe but it doesn't exist, try to find the latest version
    if not os.path.exists(target_path) and filename == "omni-agent.exe":
         files = glob.glob(os.path.join(BINARY_STORAGE_PATH, "omni-agent-*-windows.exe"))
         if files:
             target_path = max(files, key=os.path.getmtime)
             filename = os.path.basename(target_path)

    if not os.path.exists(target_path):
        # Auto-trigger build if file doesn't exist and it's the installer
        if filename in ("OmniAgent-Setup.exe", "OmniAgent-2.0.0.msi"):
            task_id = str(uuid.uuid4())
            _executor.submit(_run_build, task_id)
            raise HTTPException(
                status_code=202,
                detail={
                    "message": "Build triggered. Poll status at GET /api/agent-updates/build/" + task_id,
                    "task_id": task_id,
                    "poll_url": f"/api/agent-updates/build/{task_id}"
                }
            )
        raise HTTPException(status_code=404, detail="Binary not found")

    return FileResponse(target_path, filename=filename, media_type="application/octet-stream")


@router.post("/build")
async def trigger_build():
    """
    Trigger an async installer build with Spyglass evidence collection.
    Returns a task_id for polling build status.
    """
    task_id = str(uuid.uuid4())
    _executor.submit(_run_build, task_id)
    return {
        "task_id": task_id,
        "status": "building",
        "poll_url": f"/api/agent-updates/build/{task_id}"
    }


@router.get("/build/{task_id}")
async def get_build_status(task_id: str):
    """Poll the status of an async build."""
    state = BUILD_STATE.get(task_id)
    if not state:
        raise HTTPException(status_code=404, detail="Task not found. It may have expired.")
    resp = {"task_id": task_id, "status": state["status"]}
    if state["status"] == "done":
        resp["download_url"] = "/api/agent-updates/download/OmniAgent-Setup.exe"
    if state["error"]:
        resp["error"] = state["error"]
    return resp

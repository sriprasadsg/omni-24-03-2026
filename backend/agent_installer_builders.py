"""Windows agent installer builders — all ship the standalone Rust agent.

Every installer (EXE via NSIS, ZIP) packages the single
omni-agent.exe built from agent-install/omni-agent-rs. That binary is a native
Windows service (no WinSW/.NET) AND materializes the endpoint tray + chat/ticket
UI itself, so a fresh install needs no Python, no prerequisites, and no
manually-run scripts. The shared Rust packaging (binary + setup_svc.ps1 that
registers the service and the OmniAgentTray logon task) lives in
agent_rust_builder.prepare_rust_pkg; this module owns the ZIP wrappers plus the
shared config helper.
"""
import asyncio, logging, os, shutil, tempfile, uuid
from pathlib import Path
import yaml
from fastapi import BackgroundTasks, HTTPException
from fastapi.responses import Response

logger = logging.getLogger(__name__)


def _config_yaml(api_url: str, registration_key: str, api_key: str = "", is_legacy: bool = False) -> dict:
    return {
        "agent_id": None, "agent_token": None, "api_base_url": api_url,
        "interval_seconds": 30, "max_cpu_percent": 20,
        "agentic_mode_enabled": False, "registration_key": registration_key,
    }


def cleanup_temp_dir(path: str) -> None:
    shutil.rmtree(path, ignore_errors=True)


async def _run(args: list, cwd: str, timeout: int = 300) -> bytes:
    proc = await asyncio.create_subprocess_exec(
        *args, cwd=cwd,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    try:
        _, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except (asyncio.TimeoutError, TimeoutError):
        raise HTTPException(status_code=503, detail=f"{args[0]} timed out after {timeout}s")
    if proc.returncode != 0:
        stderr = (stderr or b"").decode(errors="replace")
        logger.error(f"{args[0]} failed (stderr): {stderr}")
        raise HTTPException(status_code=503, detail=f"{args[0]} failed: {stderr[-500:]}")
    return stderr


async def build_exe(
    tenant_id: str, tenant_name: str, registration_key: str,
    api_url: str, background_tasks: BackgroundTasks, base_dir: Path, api_key: str = "", is_legacy: bool = False
) -> Response:
    makensis = shutil.which("makensis")
    if not makensis:
        raise HTTPException(status_code=503,
            detail="makensis not installed. Run: sudo apt-get install -y nsis")

    from agent_rust_builder import prepare_rust_pkg, _build_nsi_rust, _rust_agent_version, _rust_src
    tenant_safe = tenant_name.replace(" ", "-").lower()
    temp_dir = Path(tempfile.mkdtemp(prefix=f"omni_exe_{tenant_id}_"))
    try:
        pkg_dir = temp_dir / "pkg"
        await prepare_rust_pkg(pkg_dir, base_dir, api_url, registration_key)

        exe_out = temp_dir / f"OmniAgent-{tenant_safe}-Setup.exe"
        nsi_path = temp_dir / "install.nsi"
        version = _rust_agent_version(_rust_src(base_dir))
        nsi_path.write_text(_build_nsi_rust(tenant_name, pkg_dir, str(exe_out), version), encoding="utf-8")
        await _run([makensis, str(nsi_path)], cwd=str(temp_dir), timeout=600)
        if not exe_out.exists():
            raise HTTPException(status_code=503, detail="NSIS produced no output file")

        content = exe_out.read_bytes()
        background_tasks.add_task(cleanup_temp_dir, str(temp_dir))
        return Response(content=content, media_type="application/octet-stream",
            headers={"Content-Disposition": f'attachment; filename="OmniAgent-{tenant_safe}-Setup.exe"'})
    except HTTPException:
        background_tasks.add_task(cleanup_temp_dir, str(temp_dir)); raise
    except Exception as exc:
        logger.error("EXE build failed for %s: %s", tenant_id, exc)
        background_tasks.add_task(cleanup_temp_dir, str(temp_dir))
        raise HTTPException(status_code=500, detail="Failed to build Windows EXE installer")


async def build_windows_zip(
    tenant_id: str, tenant_name: str, registration_key: str,
    api_url: str, background_tasks: BackgroundTasks, base_dir: Path,
) -> Response:
    from agent_rust_builder import prepare_rust_pkg
    tenant_safe = tenant_name.replace(" ", "-").lower()
    temp_dir = Path(tempfile.mkdtemp(prefix=f"omni_win_{tenant_id}_"))
    try:
        agent_dest = temp_dir / "content" / "OmniAgent"
        await prepare_rust_pkg(agent_dest, base_dir, api_url, registration_key)
        (temp_dir / "content" / "README.txt").write_text(
            f"OmniAgent for {tenant_name}\r\n"
            f"Install (elevated PowerShell): cd OmniAgent; powershell -ExecutionPolicy Bypass -File setup_svc.ps1\r\n"
            f"setup_svc.ps1 registers the Windows service and the endpoint tray (Raise Ticket / Chat / Status).\r\n"
            f"Standalone single-exe agent — no Python, no .NET, no prerequisites.\r\n"
            f"API: {api_url}\r\n",
            encoding="utf-8")
        zip_base = str(temp_dir / f"OmniAgent-{tenant_safe}-windows")
        shutil.make_archive(zip_base, "zip", root_dir=str(temp_dir / "content"), base_dir=".")
        content = Path(f"{zip_base}.zip").read_bytes()
        background_tasks.add_task(cleanup_temp_dir, str(temp_dir))
        return Response(content=content, media_type="application/zip",
            headers={"Content-Disposition": f'attachment; filename="OmniAgent-{tenant_safe}-windows.zip"'})
    except HTTPException:
        background_tasks.add_task(cleanup_temp_dir, str(temp_dir)); raise
    except Exception as exc:
        logger.error("Windows ZIP build failed for %s: %s", tenant_id, exc)
        background_tasks.add_task(cleanup_temp_dir, str(temp_dir))
        raise HTTPException(status_code=500, detail="Failed to build Windows ZIP package")

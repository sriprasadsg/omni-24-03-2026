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
from typing import Optional
import yaml
from fastapi import BackgroundTasks, HTTPException
from fastapi.responses import Response

logger = logging.getLogger(__name__)


_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def agent_ca_cert_pem() -> Optional[str]:
    """The certificate agents pin for the platform (PEM), read from
    AGENT_CA_CERT_FILE: the public certificate the platform serves agents
    (on this VM, nginx's /etc/nginx/ssl/omni.crt).

    Installers used to set accept_invalid_certs for self-signed deployments,
    which turned certificate checks off and let anyone on the path pose as the
    server. They now ship this certificate and agents trust it and nothing
    else. Unset: nothing is pinned, and https:// agent URLs are checked against
    the endpoint's OS trust store (right for a CA-signed deployment). A
    misconfigured file fails the build rather than shipping an unpinned agent.
    """
    path = os.getenv("AGENT_CA_CERT_FILE", "").strip()
    if not path:
        return None
    try:
        pem = Path(path).read_text(encoding="ascii").strip()
    except (OSError, UnicodeDecodeError) as exc:
        raise HTTPException(status_code=503, detail=f"AGENT_CA_CERT_FILE could not be read: {exc}")
    if not pem.startswith("-----BEGIN CERTIFICATE-----") or "PRIVATE KEY" in pem:
        raise HTTPException(status_code=503, detail="AGENT_CA_CERT_FILE must contain only a PEM certificate")
    return pem


def _config_yaml(api_url: str, registration_key: str, api_key: str = "", is_legacy: bool = False) -> dict:
    cfg = {
        "agent_id": None, "agent_token": None, "api_base_url": api_url,
        "interval_seconds": 30, "max_cpu_percent": 20,
        "agentic_mode_enabled": False, "registration_key": registration_key,
        "accept_invalid_certs": False,
    }
    pem = agent_ca_cert_pem() if api_url.strip().lower().startswith("https://") else None
    if pem:
        cfg["server_ca_cert"] = pem + "\n"
    return cfg


class _ConfigDumper(yaml.SafeDumper):
    """Writes multi-line strings (the pinned certificate) as literal blocks."""


_ConfigDumper.add_representer(
    str, lambda dumper, data: dumper.represent_scalar(
        "tag:yaml.org,2002:str", data, style="|" if "\n" in data else None))


def config_yaml_text(api_url: str, registration_key: str) -> str:
    """The agent config.yaml every installer ships."""
    return yaml.dump(_config_yaml(api_url, registration_key), Dumper=_ConfigDumper,
                     default_flow_style=False, sort_keys=True)


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

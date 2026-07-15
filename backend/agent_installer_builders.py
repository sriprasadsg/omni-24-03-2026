"""Windows agent installer builders — all ship the standalone Rust agent.

Every installer (EXE via NSIS, MSI via wixl, ZIP) packages the single
omni-agent.exe built from agent-install/omni-agent-rs. That binary is a native
Windows service (no WinSW/.NET) AND materializes the endpoint tray + chat/ticket
UI itself, so a fresh install needs no Python, no prerequisites, and no
manually-run scripts. The shared Rust packaging (binary + setup_svc.ps1 that
registers the service and the OmniAgentTray logon task) lives in
agent_rust_builder.prepare_rust_pkg; this module owns the MSI (wixl) and ZIP
wrappers plus the shared config helper.
"""
import asyncio, logging, os, shutil, tempfile, uuid
from pathlib import Path
import yaml
from fastapi import BackgroundTasks, HTTPException
from fastapi.responses import Response

logger = logging.getLogger(__name__)


def _config_yaml(api_url: str, registration_key: str) -> dict:
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
        snippet = (stderr or b"").decode(errors="replace")[-500:]
        raise HTTPException(status_code=503, detail=f"{args[0]} failed: {snippet}")
    return stderr


def _generate_wxs(tenant_id: str, tenant_name: str, files_root: Path) -> str:
    skip = {"__pycache__", "venv", ".venv", "node_modules", "dist", "build", ".git"}
    entries: list[tuple[Path, Path]] = []
    for root, dirs, files in os.walk(files_root):
        dirs[:] = sorted(d for d in dirs if d not in skip)
        rp = Path(root)
        rel = rp.relative_to(files_root)
        for f in sorted(files):
            if not f.endswith(".pyc") and f != "buffer.db":
                entries.append((rp / f, rel))

    fguid = lambda r: str(uuid.uuid5(uuid.NAMESPACE_URL, f"omni-{tenant_id}-{r}")).upper()
    uguid = str(uuid.uuid5(uuid.NAMESPACE_URL, "omni-agent-upgrade-code")).upper()
    dir_ids: dict[str, str] = {}
    for _, rel in entries:
        for depth in range(len(rel.parts)):
            key = str(Path(*rel.parts[:depth + 1]))
            if key not in dir_ids:
                dir_ids[key] = "Dir_" + key.replace("/","_").replace("\\","_").replace(".","_").replace("-","_")

    # wixl requires <Component> to live inside its <Directory> (a Component as a
    # direct child of <Product> is rejected: "unhandled child Product node
    # Component"). Group components by their owning directory and nest them.
    comps_by_did: dict[str, list[str]] = {}
    refs = []
    for i, (abs_p, rel) in enumerate(entries):
        cid, g = f"Comp{i:05d}", fguid(str(rel / abs_p.name))
        did = dir_ids.get(str(rel)) if rel.parts else "INSTALLDIR"
        did = did or "INSTALLDIR"
        comps_by_did.setdefault(did, []).append(
            f'<Component Id="{cid}" Guid="{{{g}}}">'
            f'<File Id="File{i:05d}" Source="{abs_p}" Name="{abs_p.name}" KeyPath="yes"/>'
            f'</Component>')
        refs.append(f'      <ComponentRef Id="{cid}"/>')

    def dir_xml(parent: str = "", indent: int = 10) -> str:
        depth = len(parent.split("/")) if parent else 0
        out = ""
        for key, did in sorted(dir_ids.items()):
            parts = key.replace("\\","/").split("/")
            if len(parts) != depth + 1 or "/".join(parts[:-1]) != parent:
                continue
            p = " " * indent
            inner = dir_xml(key, indent + 2)
            for c in comps_by_did.get(did, []):
                inner += " " * (indent + 2) + c + "\n"
            out += f'{p}<Directory Id="{did}" Name="{parts[-1]}">\n{inner}{p}</Directory>\n'
        return out

    installdir_comps = "".join(
        " " * 10 + c + "\n" for c in comps_by_did.get("INSTALLDIR", []))

    return f"""<?xml version="1.0" encoding="UTF-8"?>
<Wix xmlns="http://schemas.microsoft.com/wix/2006/wi">
  <Product Id="*" Name="{tenant_name} OmniAgent" Language="1033" Version="2.0.1"
           Manufacturer="Enterprise OmniAgent AI Platform" UpgradeCode="{{{uguid}}}">
    <Package InstallerVersion="300" Compressed="yes" InstallScope="perMachine"/>
    <MediaTemplate EmbedCab="yes"/>
    <Property Id="OMNIPOWERSHELL" Value="C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe"/>
    <Directory Id="TARGETDIR" Name="SourceDir">
      <Directory Id="ProgramFiles64Folder">
        <Directory Id="INSTALLDIR" Name="OmniAgent">
{dir_xml('', 10)}{installdir_comps}        </Directory>
      </Directory>
    </Directory>
    <Feature Id="Complete" Level="1">
{chr(10).join(refs)}
    </Feature>
    <CustomAction Id="RunSetup" Property="OMNIPOWERSHELL"
      ExeCommand="-NoProfile -NonInteractive -ExecutionPolicy Bypass -File &quot;[INSTALLDIR]setup_svc.ps1&quot;"
      Execute="immediate" Return="ignore"/>
    <InstallExecuteSequence>
      <Custom Action="RunSetup" After="InstallFinalize">NOT Installed</Custom>
    </InstallExecuteSequence>
  </Product>
</Wix>
"""


async def build_msi(
    tenant_id: str, tenant_name: str, registration_key: str,
    api_url: str, background_tasks: BackgroundTasks, base_dir: Path,
) -> Response:
    wixl = shutil.which("wixl")
    if not wixl:
        raise HTTPException(status_code=503,
            detail="wixl not installed. Run: sudo apt-get install -y wixl")

    from agent_rust_builder import prepare_rust_pkg
    tenant_safe = tenant_name.replace(" ", "-").lower()
    temp_dir = Path(tempfile.mkdtemp(prefix=f"omni_msi_{tenant_id}_"))
    try:
        pkg_dir = temp_dir / "pkg"
        await prepare_rust_pkg(pkg_dir, base_dir, api_url, registration_key)

        wxs_path = temp_dir / "install.wxs"
        wxs_path.write_text(_generate_wxs(tenant_id, tenant_name, pkg_dir), encoding="utf-8")
        msi_out = temp_dir / f"OmniAgent-{tenant_safe}-Setup.msi"
        await _run([wixl, "-a", "x64", "-o", str(msi_out), str(wxs_path)],
                   cwd=str(temp_dir), timeout=600)
        if not msi_out.exists():
            raise HTTPException(status_code=503, detail="wixl produced no output file")

        content = msi_out.read_bytes()
        background_tasks.add_task(cleanup_temp_dir, str(temp_dir))
        return Response(content=content, media_type="application/octet-stream",
            headers={"Content-Disposition": f'attachment; filename="OmniAgent-{tenant_safe}-Setup.msi"'})
    except HTTPException:
        background_tasks.add_task(cleanup_temp_dir, str(temp_dir)); raise
    except Exception as exc:
        logger.error("MSI build failed for %s: %s", tenant_id, exc)
        background_tasks.add_task(cleanup_temp_dir, str(temp_dir))
        raise HTTPException(status_code=500, detail="Failed to build Windows MSI installer")


async def build_exe(
    tenant_id: str, tenant_name: str, registration_key: str,
    api_url: str, background_tasks: BackgroundTasks, base_dir: Path,
) -> Response:
    makensis = shutil.which("makensis")
    if not makensis:
        raise HTTPException(status_code=503,
            detail="makensis not installed. Run: sudo apt-get install -y nsis")

    from agent_rust_builder import prepare_rust_pkg, _build_nsi_rust
    tenant_safe = tenant_name.replace(" ", "-").lower()
    temp_dir = Path(tempfile.mkdtemp(prefix=f"omni_exe_{tenant_id}_"))
    try:
        pkg_dir = temp_dir / "pkg"
        await prepare_rust_pkg(pkg_dir, base_dir, api_url, registration_key)

        exe_out = temp_dir / f"OmniAgent-{tenant_safe}-Setup.exe"
        nsi_path = temp_dir / "install.nsi"
        nsi_path.write_text(_build_nsi_rust(tenant_name, pkg_dir, str(exe_out)), encoding="utf-8")
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

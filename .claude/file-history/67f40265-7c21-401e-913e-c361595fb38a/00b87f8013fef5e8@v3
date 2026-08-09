"""Build Windows EXE installer using the pre-compiled Rust agent binary.
The Rust exe implements the Windows Service API natively — registered with
sc.exe (built into every Windows release), no WinSW or .NET required.
"""
import asyncio, logging, os, shutil, tempfile
from pathlib import Path
from fastapi import BackgroundTasks, HTTPException
from fastapi.responses import Response

from agent_installer_builders import cleanup_temp_dir, _config_yaml
import yaml

logger = logging.getLogger(__name__)

_RUST_TARGET = "x86_64-pc-windows-gnu"
_CARGO_BIN   = Path.home() / ".cargo" / "bin" / "cargo"


async def _ensure_rust_binary(rust_src: Path) -> Path:
    """Return path to compiled omni-agent.exe, building it if necessary."""
    exe = rust_src / "target" / _RUST_TARGET / "release" / "omni-agent.exe"
    if exe.exists():
        logger.info("Reusing cached Rust binary (%s KB)", exe.stat().st_size // 1024)
        return exe

    cargo = str(_CARGO_BIN) if _CARGO_BIN.exists() else shutil.which("cargo") or ""
    if not cargo:
        raise HTTPException(status_code=503, detail="cargo not found; install Rust via https://rustup.rs")
    mingw = shutil.which("x86_64-w64-mingw32-gcc")
    if not mingw:
        raise HTTPException(status_code=503, detail="x86_64-w64-mingw32-gcc not found; install gcc-mingw-w64-x86-64")

    env = os.environ.copy()
    env["CC_x86_64_pc_windows_gnu"] = mingw
    env["AR_x86_64_pc_windows_gnu"] = shutil.which("x86_64-w64-mingw32-ar") or "x86_64-w64-mingw32-ar"

    logger.info("Compiling Rust agent for %s — first build ~2 min…", _RUST_TARGET)
    proc = await asyncio.create_subprocess_exec(
        cargo, "build", "--release", "--target", _RUST_TARGET,
        cwd=str(rust_src), env=env,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    try:
        _, stderr = await asyncio.wait_for(proc.communicate(), timeout=600)
    except (asyncio.TimeoutError, TimeoutError):
        raise HTTPException(status_code=503, detail="cargo build timed out after 600 s")
    if proc.returncode != 0:
        raise HTTPException(status_code=503, detail=f"cargo build failed: {(stderr or b'').decode(errors='replace')[-500:]}")
    if not exe.exists():
        raise HTTPException(status_code=503, detail="cargo build succeeded but exe not found")
    logger.info("Rust binary compiled (%s KB)", exe.stat().st_size // 1024)
    return exe


def _setup_svc_rust_ps1(api_url: str, reg_key: str) -> str:
    """PowerShell installer script — uses sc.exe (native Windows) to register the service.
    The Rust binary itself implements the Windows Service API (windows-service crate),
    so no WinSW wrapper or .NET Framework is needed."""
    return f"""\
#Requires -RunAsAdministrator
$ErrorActionPreference = 'Stop'
$D = Split-Path -Parent $MyInvocation.MyCommand.Definition
New-Item -ItemType Directory -Force -Path "$D\\logs" | Out-Null

# Write agent config
[IO.File]::WriteAllText("$D\\config.yaml", @"
api_base_url: {api_url}
registration_key: {reg_key}
agent_id: null
agent_token: null
interval_seconds: 30
"@)

$agentExe = "$D\\omni-agent.exe"
$svcName   = "OmniAgentRust"

# Remove any previous installation cleanly
$existing = Get-Service -Name $svcName -ErrorAction SilentlyContinue
if ($existing) {{
    Write-Host "Stopping existing $svcName service..."
    Stop-Service -Name $svcName -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 2
    & sc.exe delete $svcName | Out-Null
    Start-Sleep -Seconds 2
}}

# Register omni-agent.exe as a Windows Service via sc.exe
# The binary handles StartServiceCtrlDispatcher internally — no wrapper needed
Write-Host "Creating Windows Service: $svcName"
& sc.exe create $svcName `
    binPath= "`"$agentExe`"" `
    start=   auto `
    DisplayName= "Enterprise OmniAgent (Rust)" | Out-Null

& sc.exe description $svcName "Lightweight AI security agent — Rust edition v2.0.0" | Out-Null

# Auto-restart: 5 s, 15 s, 30 s, then reset failure count after 24 h
& sc.exe failure $svcName reset= 86400 actions= restart/5000/restart/15000/restart/30000 | Out-Null

# Start the service
Write-Host "Starting $svcName..."
Start-Service -Name $svcName -ErrorAction Stop

$svc = Get-Service -Name $svcName -ErrorAction SilentlyContinue
if ($svc -and $svc.Status -eq 'Running') {{
    Write-Host "SUCCESS: OmniAgent (Rust) is running. Visible in services.msc as 'Enterprise OmniAgent (Rust)'."
}} else {{
    Write-Warning "Service registered but may not be running — check Event Viewer > Windows Logs > Application."
}}
"""


def _build_nsi_rust(tenant_name: str, pkg_dir: Path, outfile: str) -> str:
    esc = lambda s: s.replace('"', '$\\"')
    files = "\n".join(
        f'  File "{pkg_dir / f.name}"'
        for f in sorted(pkg_dir.iterdir(), key=lambda p: p.name)
        if f.is_file()
    )
    # Uninstaller: stop + delete the service via sc.exe, then remove files
    uninstall_ps = (
        'powershell -NoProfile -NonInteractive -Command "'
        'Stop-Service OmniAgentRust -Force -EA SilentlyContinue; '
        'Start-Sleep 2; '
        'sc.exe delete OmniAgentRust | Out-Null'
        '"'
    )
    return f"""; OmniAgent Rust Installer — auto-generated
!include "MUI2.nsh"
Name "OmniAgent Rust 2.0 — {esc(tenant_name)}"
OutFile "{outfile}"
InstallDir "$PROGRAMFILES64\\OmniAgentRust"
RequestExecutionLevel admin
SetCompressor lzma

!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!define MUI_FINISHPAGE_TEXT "OmniAgent (Rust) installed.$\\r$\\nNo Python or .NET required.$\\r$\\nManage via services.msc  →  'Enterprise OmniAgent (Rust)'"
!insertmacro MUI_PAGE_FINISH
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_LANGUAGE "English"
!define UNINST "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\OmniAgentRust"

Section "OmniAgent (Rust)"
  SectionIn RO
  SetOutPath "$INSTDIR"
{files}
  nsExec::ExecToLog 'powershell -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "$INSTDIR\\setup_svc.ps1"'
  WriteRegStr   HKLM "${{UNINST}}" "DisplayName"     "OmniAgent (Rust Edition)"
  WriteRegStr   HKLM "${{UNINST}}" "DisplayVersion"  "2.0.0-rust"
  WriteRegStr   HKLM "${{UNINST}}" "Publisher"       "Enterprise OmniAgent AI Platform"
  WriteRegStr   HKLM "${{UNINST}}" "UninstallString" '"$INSTDIR\\Uninstall.exe"'
  WriteRegDWORD HKLM "${{UNINST}}" "NoModify" 1
  WriteRegDWORD HKLM "${{UNINST}}" "NoRepair" 1
  WriteUninstaller "$INSTDIR\\Uninstall.exe"
SectionEnd

Section "Uninstall"
  ExecWait '{uninstall_ps}' $0
  RMDir /r "$INSTDIR"
  DeleteRegKey HKLM "${{UNINST}}"
SectionEnd
"""


async def build_rust_exe(
    tenant_id: str, tenant_name: str, registration_key: str,
    api_url: str, background_tasks: BackgroundTasks, base_dir: Path,
) -> Response:
    makensis = shutil.which("makensis")
    if not makensis:
        raise HTTPException(status_code=503, detail="makensis not installed (sudo apt-get install nsis)")

    rust_src = base_dir / "agent-rust"
    if not rust_src.is_dir():
        raise HTTPException(status_code=503, detail="agent-rust source directory not found on server")

    tenant_safe = tenant_name.replace(" ", "-").lower()
    temp_dir = Path(tempfile.mkdtemp(prefix=f"omni_rust_{tenant_id}_"))
    try:
        pkg_dir = temp_dir / "pkg"
        pkg_dir.mkdir()

        # Compile (or reuse cached) Rust binary — has native Windows Service API
        binary = await _ensure_rust_binary(rust_src)
        shutil.copy2(binary, pkg_dir / "omni-agent.exe")

        # Write tenant-specific config + registration script
        with open(pkg_dir / "config.yaml", "w", encoding="utf-8") as f:
            yaml.dump(_config_yaml(api_url, registration_key), f, default_flow_style=False, sort_keys=True)
        (pkg_dir / "setup_svc.ps1").write_text(
            _setup_svc_rust_ps1(api_url, registration_key), encoding="utf-8")

        # Build NSIS installer (no WinSW needed — sc.exe registers the service)
        exe_out  = temp_dir / f"OmniAgent-Rust-{tenant_safe}-Setup.exe"
        nsi_path = temp_dir / "install.nsi"
        nsi_path.write_text(_build_nsi_rust(tenant_name, pkg_dir, str(exe_out)), encoding="utf-8")

        proc = await asyncio.create_subprocess_exec(
            makensis, str(nsi_path), cwd=str(temp_dir),
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        try:
            _, stderr = await asyncio.wait_for(proc.communicate(), timeout=300)
        except (asyncio.TimeoutError, TimeoutError):
            raise HTTPException(status_code=503, detail="makensis timed out")
        if proc.returncode != 0:
            raise HTTPException(status_code=503, detail=f"makensis failed: {(stderr or b'').decode()[-400:]}")
        if not exe_out.exists():
            raise HTTPException(status_code=503, detail="NSIS produced no output")

        content = exe_out.read_bytes()
        logger.info("Rust EXE built: %d KB for tenant %s", len(content) // 1024, tenant_id)
        background_tasks.add_task(cleanup_temp_dir, str(temp_dir))
        return Response(
            content=content,
            media_type="application/octet-stream",
            headers={"Content-Disposition": f'attachment; filename="OmniAgent-Rust-{tenant_safe}-Setup.exe"'},
        )
    except HTTPException:
        background_tasks.add_task(cleanup_temp_dir, str(temp_dir))
        raise
    except Exception as exc:
        logger.error("Rust EXE build failed for %s: %s", tenant_id, exc)
        background_tasks.add_task(cleanup_temp_dir, str(temp_dir))
        raise HTTPException(status_code=500, detail="Failed to build Rust Windows installer")

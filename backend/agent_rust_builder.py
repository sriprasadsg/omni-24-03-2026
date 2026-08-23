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


def _sources_newer_than(exe: Path, rust_src: Path) -> bool:
    """True if any .rs source or Cargo.toml is newer than the cached exe."""
    exe_mtime = exe.stat().st_mtime
    candidates = [rust_src / "Cargo.toml", *rust_src.glob("src/**/*.rs")]
    return any(p.stat().st_mtime > exe_mtime for p in candidates if p.exists())


async def _ensure_rust_binary(rust_src: Path) -> Path:
    """Return path to compiled omni-agent.exe, building it if necessary."""
    exe = rust_src / "target" / _RUST_TARGET / "release" / "omni-agent.exe"
    if exe.exists():
        if _sources_newer_than(exe, rust_src):
            if not shutil.which("x86_64-w64-mingw32-gcc"):
                logger.warning("Toolchain missing, reusing old binary despite source changes")
                return exe
            logger.info("Cached Rust binary is older than sources — rebuilding")
        else:
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


def _rust_agent_version(rust_src: Path) -> str:
    """Read [package] version from the shipped agent's Cargo.toml so installer
    version strings track the real binary instead of drifting hardcoded values."""
    import re
    try:
        txt = (rust_src / "Cargo.toml").read_text(encoding="utf-8")
        m = re.search(r'(?m)^\s*version\s*=\s*"([^"]+)"', txt)
        if m:
            return m.group(1)
    except Exception:
        pass
    return "0.0.0"


def _setup_svc_rust_ps1(api_url: str, reg_key: str, version: str) -> str:
    """PowerShell installer script — uses sc.exe (native Windows) to register the service.
    The Rust binary itself implements the Windows Service API (windows-service crate),
    so no WinSW wrapper or .NET Framework is needed."""
    return f"""\
#Requires -RunAsAdministrator
$ErrorActionPreference = 'Stop'
$D = Split-Path -Parent $MyInvocation.MyCommand.Definition
New-Item -ItemType Directory -Force -Path "$D\\logs" | Out-Null
# NSIS runs this hidden via nsExec — keep a transcript so failed installs are diagnosable
Start-Transcript -Path "$D\\logs\\install.log" -Force | Out-Null

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

# Remove any previous installation cleanly, then WAIT for Windows to actually
# release the service name before creating the new one. A flat sleep isn't
# reliable headroom for SCM's async pending-delete teardown — sc.exe create
# fails with 1072 ("marked for deletion") if it runs while the old service is
# still draining, which is exactly what silently left hosts with no
# OmniAgentRust service at all after a reinstall (this poll-loop replaces
# that flat sleep; the retry loop below on sc.exe create is defense in depth
# for the same race).
$existing = Get-Service -Name $svcName -ErrorAction SilentlyContinue
if ($existing) {{
    Write-Host "Stopping existing $svcName service..."
    Stop-Service -Name $svcName -Force -ErrorAction SilentlyContinue
    & sc.exe delete $svcName | Out-Null

    $cleared = $false
    for ($i = 0; $i -lt 15; $i++) {{
        Start-Sleep -Seconds 1
        if (-not (Get-Service -Name $svcName -ErrorAction SilentlyContinue)) {{ $cleared = $true; break }}
    }}
    if (-not $cleared) {{
        Write-Error "Timed out waiting for Windows to release the '$svcName' service after delete (still pending after 15s) — a previous instance may still be shutting down. Re-run this installer, or reboot and retry."
    }}
}}

# Register omni-agent.exe as a Windows Service via sc.exe
# The binary handles StartServiceCtrlDispatcher internally — no wrapper needed
Write-Host "Creating Windows Service: $svcName"
$created = $false
$createOut = $null
$attempt = 0
for ($attempt = 1; $attempt -le 3 -and -not $created; $attempt++) {{
    $createOut = & sc.exe create $svcName `
        binPath= "`"$agentExe`"" `
        start=   auto `
        obj=     LocalSystem `
        DisplayName= "Enterprise OmniAgent (Rust)" 2>&1
    if ($LASTEXITCODE -eq 0) {{
        $created = $true
    }} elseif ($LASTEXITCODE -eq 1072 -and $attempt -lt 3) {{
        # Still marked for deletion despite the wait above — give SCM a bit more time.
        Write-Host "sc.exe create returned 1072 (service still pending deletion) — retrying in 3s (attempt $attempt/3)..."
        Start-Sleep -Seconds 3
    }}
}}
if (-not $created) {{
    # $ErrorActionPreference = 'Stop' (top of script) turns this into a terminating
    # error, so this script — and the nsExec::ExecToLog call that runs it — exits
    # non-zero. The NSIS installer now checks that exit code and aborts instead of
    # reporting success with no service actually created.
    Write-Error "sc.exe create failed after $attempt attempt(s) (exit $LASTEXITCODE): $createOut"
}}

& sc.exe description $svcName "Lightweight AI security agent - Rust edition v{version}" | Out-Null

# Auto-restart: 5 s, 15 s, 30 s, then reset failure count after 24 h
& sc.exe failure $svcName reset= 86400 actions= restart/5000/restart/15000/restart/30000 | Out-Null

# Start the service
Write-Host "Starting $svcName..."
Start-Service -Name $svcName -ErrorAction Stop

$svc = Get-Service -Name $svcName -ErrorAction SilentlyContinue
if ($svc -and $svc.Status -eq 'Running') {{
    Write-Host "SUCCESS: OmniAgent (Rust) is running. Visible in services.msc as 'Enterprise OmniAgent (Rust)'."
}} else {{
    Write-Warning "Service registered but may not be running - check Event Viewer > Windows Logs > Application."
}}

# ── Endpoint tray (Raise Ticket / Chat with IT / Agent Status) ────────────────
# The service runs in session 0 and cannot draw a tray icon; a per-user logon
# task runs the tray script the agent materializes to ProgramData on first
# start. Registering the task is all the installer must do — the agent writes
# tray_icon.ps1 / chat_ui.ps1 / tray-config.json itself once it registers.
try {{
    # Launch the tray through wscript + a hidden-window VBScript, NOT powershell
    # directly: a powershell logon task leaves a console window the user can
    # close (which takes the tray icon down with it). wscript Run(...,0) starts
    # powershell with no window at all. The agent materializes tray_launch.vbs
    # and tray_icon.ps1 to ProgramData on first start.
    $trayLauncher = Join-Path $env:ProgramData 'OmniAgent\\tray_launch.vbs'
    $trayAct  = New-ScheduledTaskAction -Execute 'wscript.exe' -Argument ('"' + $trayLauncher + '"')
    $trayTrg  = New-ScheduledTaskTrigger -AtLogOn
    $traySet  = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
    $trayPrin = New-ScheduledTaskPrincipal -GroupId 'BUILTIN\\Users' -RunLevel Limited
    Register-ScheduledTask -TaskName 'OmniAgentTray' -Action $trayAct -Trigger $trayTrg `
        -Settings $traySet -Principal $trayPrin -Force | Out-Null
    Write-Host "Tray logon task registered (OmniAgentTray)."
    # Best-effort: surface the tray in the current interactive session now, once
    # the agent has written the launcher (it does so right after registering).
    for ($i = 0; $i -lt 8 -and -not (Test-Path $trayLauncher); $i++) {{ Start-Sleep -Seconds 3 }}
    Start-ScheduledTask -TaskName 'OmniAgentTray' -ErrorAction SilentlyContinue
}} catch {{
    Write-Warning "Tray task registration failed (agent still runs): $_"
}}
Stop-Transcript | Out-Null
"""


def _build_nsi_rust(tenant_name: str, pkg_dir: Path, outfile: str, version: str) -> str:
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
!include "LogicLib.nsh"
Name "OmniAgent Rust {version} — {esc(tenant_name)}"
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
  ; Upgrade path: a running OmniAgentRust service holds an exclusive lock on its
  ; own omni-agent.exe, so File (below) cannot overwrite it and the agent would
  ; silently stay on the old binary. Stop + delete the service, stop the tray
  ; task, and kill any stray process FIRST so the binary is unlocked before copy.
  DetailPrint "Stopping any existing OmniAgent (Rust) install for upgrade..."
  nsExec::ExecToLog 'powershell -NoProfile -NonInteractive -ExecutionPolicy Bypass -Command "Stop-Service OmniAgentRust -Force -EA SilentlyContinue; Start-Sleep 2; sc.exe delete OmniAgentRust | Out-Null; Stop-ScheduledTask -TaskName OmniAgentTray -EA SilentlyContinue; Get-Process omni-agent -EA SilentlyContinue | Stop-Process -Force -EA SilentlyContinue; Start-Sleep 2"'
  SetOutPath "$INSTDIR"
  SetOverwrite on
{files}
  ; setup_svc.ps1's exit code is checked, not discarded — it's what previously let a
  ; failed service-creation (e.g. the old service still pending deletion, error 1072)
  ; report install success anyway and leave the host with no OmniAgentRust service at
  ; all. Abort instead of writing success registry keys / showing the finish page.
  nsExec::ExecToLog 'powershell -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "$INSTDIR\\setup_svc.ps1"'
  Pop $0
  ${{If}} $0 != 0
    DetailPrint "setup_svc.ps1 failed (exit code $0) — the Windows service was not created."
    MessageBox MB_OK|MB_ICONSTOP "OmniAgent service setup failed (exit code $0).$\\r$\\nSee $INSTDIR\\logs\\install.log for details, then re-run this installer.$\\r$\\nInstallation will now abort so you are not left without the agent running."
    Abort
  ${{EndIf}}
  WriteRegStr   HKLM "${{UNINST}}" "DisplayName"     "OmniAgent (Rust Edition)"
  WriteRegStr   HKLM "${{UNINST}}" "DisplayVersion"  "{version}"
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


def _rust_src(base_dir: Path) -> Path:
    """The single source of truth for the endpoint agent binary — the
    omni-agent-rs tree, which has the tray + chat/ticket UI. (The legacy
    agent-rust tree is headless and no longer shipped by any installer.)"""
    src = base_dir / "agent-install" / "omni-agent-rs"
    if not src.is_dir():
        raise HTTPException(status_code=503, detail="omni-agent-rs source directory not found on server")
    return src


async def prepare_rust_pkg(pkg_dir: Path, base_dir: Path, api_url: str, registration_key: str) -> None:
    """Populate pkg_dir with the standalone rust agent shared by every installer:
    omni-agent.exe + config.yaml + setup_svc.ps1. The one exe is a native Windows
    service and materializes the tray/chat/ticket UI itself, and setup_svc.ps1
    registers the service + the OmniAgentTray logon task — no Python, no WinSW,
    and nothing to run by hand post-install."""
    pkg_dir.mkdir(parents=True, exist_ok=True)
    rust_src = _rust_src(base_dir)
    binary = await _ensure_rust_binary(rust_src)
    version = _rust_agent_version(rust_src)
    shutil.copy2(binary, pkg_dir / "omni-agent.exe")
    with open(pkg_dir / "config.yaml", "w", encoding="utf-8") as f:
        yaml.dump(_config_yaml(api_url, registration_key), f, default_flow_style=False, sort_keys=True)
    # utf-8-sig: Windows PowerShell 5.1 assumes ANSI without a BOM, which mangles
    # any non-ASCII byte in the script.
    (pkg_dir / "setup_svc.ps1").write_text(
        _setup_svc_rust_ps1(api_url, registration_key, version), encoding="utf-8-sig")


async def build_rust_exe(
    tenant_id: str, tenant_name: str, registration_key: str,
    api_url: str, background_tasks: BackgroundTasks, base_dir: Path,
) -> Response:
    makensis = shutil.which("makensis")
    if not makensis:
        raise HTTPException(status_code=503, detail="makensis not installed (sudo apt-get install nsis)")

    tenant_safe = tenant_name.replace(" ", "-").lower()
    temp_dir = Path(tempfile.mkdtemp(prefix=f"omni_rust_{tenant_id}_"))
    try:
        pkg_dir = temp_dir / "pkg"
        await prepare_rust_pkg(pkg_dir, base_dir, api_url, registration_key)

        # Build NSIS installer (no WinSW needed — sc.exe registers the service)
        exe_out  = temp_dir / f"OmniAgent-Rust-{tenant_safe}-Setup.exe"
        nsi_path = temp_dir / "install.nsi"
        version  = _rust_agent_version(_rust_src(base_dir))
        nsi_path.write_text(_build_nsi_rust(tenant_name, pkg_dir, str(exe_out), version), encoding="utf-8")

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

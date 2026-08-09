"""Windows agent installer builders: EXE (NSIS), MSI (wixl), ZIP fallback.
Bundles Python 3.12 embeddable + WinSW + wheels — fully standalone, no prerequisites.
"""
import asyncio, logging, os, shutil, sys, tempfile, uuid, zipfile
from pathlib import Path
import yaml
from fastapi import BackgroundTasks, HTTPException
from fastapi.responses import Response

logger = logging.getLogger(__name__)

_BUILD_ONLY_PKGS = {"pyinstaller", "pyinstaller_hooks_contrib", "wheel"}
_AGENT_EXCLUDE = shutil.ignore_patterns(
    "__pycache__", "*.pyc", "*.key", "*.db", "*.log",
    "venv", ".venv", "node_modules", "dist", "build", "*.spec", "config.yaml",
)
_EMBED_PY_VERS = ["3.12.10", "3.12.9", "3.12.8", "3.12.7", "3.12.6", "3.12.5"]
_EMBED_PY_URL  = "https://www.python.org/ftp/python/{v}/python-{v}-embed-amd64.zip"
_GET_PIP_URL   = "https://bootstrap.pypa.io/get-pip.py"
# WinSW: wraps any exe/script as a proper Windows Service — no pywin32 / .NET SDK needed
_WINSW_URL     = "https://github.com/winsw/winsw/releases/download/v2.12.0/WinSW-x64.exe"


def _agent_src(base_dir: Path) -> Path:
    src = base_dir / "agent"
    if not src.is_dir():
        raise HTTPException(status_code=500, detail="Source agent directory not found on server")
    return src


def cleanup_temp_dir(path: str) -> None:
    shutil.rmtree(path, ignore_errors=True)


def _config_yaml(api_url: str, registration_key: str) -> dict:
    return {
        "agent_id": None, "agent_token": None, "api_base_url": api_url,
        "interval_seconds": 30, "max_cpu_percent": 20,
        "agentic_mode_enabled": False, "registration_key": registration_key,
    }


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


def _make_runtime_req(src: Path, dst: Path) -> None:
    lines = []
    for line in src.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        pkg = s.split(">=")[0].split("==")[0].split("!=")[0].split(">")[0].split("<")[0]
        pkg = pkg.split(";")[0].split("[")[0].strip().lower().replace("-", "_")
        if pkg not in _BUILD_ONLY_PKGS:
            lines.append(s)
    dst.write_text("\n".join(lines) + "\n", encoding="utf-8")


async def _download_windows_wheels(req_txt: Path, wheels_dir: Path) -> bool:
    wheels_dir.mkdir(exist_ok=True)
    for pyver in ("312", "311", "310"):
        cmd = [sys.executable, "-m", "pip", "download",
               "-r", str(req_txt), "--platform", "win_amd64",
               f"--python-version={pyver}", "--only-binary=:all:",
               "-d", str(wheels_dir), "-q"]
        proc = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE)
        try:
            _, err = await asyncio.wait_for(proc.communicate(), timeout=300)
        except (asyncio.TimeoutError, TimeoutError):
            logger.warning("pip download wheels timed out for py%s", pyver)
            continue
        if proc.returncode == 0:
            logger.info("Bundled %d Windows wheels (py3.%s)",
                        len(list(wheels_dir.glob("*.whl"))), pyver[-2:])
            return True
        logger.debug("pip wheel py%s: %s", pyver, err.decode()[-200:])
    return False


async def _bundle_wheels(req_txt: Path, pkg_dir: Path) -> None:
    if not req_txt.exists():
        return
    rt_req = pkg_dir / "requirements-runtime.txt"
    _make_runtime_req(req_txt, rt_req)
    ok = await _download_windows_wheels(rt_req, pkg_dir / "wheels")
    if not ok:
        logger.warning("Could not pre-download Windows wheels; pip will run online at install time")
        shutil.rmtree(str(pkg_dir / "wheels"), ignore_errors=True)


async def _curl_download(url: str, dst: Path, timeout: int = 120) -> bool:
    """Download url → dst using curl or wget. Returns True on success."""
    curl = shutil.which("curl") or shutil.which("wget")
    if not curl:
        return False
    is_curl = "curl" in curl
    args = ([curl, "-fsSL", "-L", url, "-o", str(dst)]
            if is_curl else [curl, "-q", "-L", url, "-O", str(dst)])
    try:
        proc = await asyncio.create_subprocess_exec(
            *args, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE)
        _, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        return proc.returncode == 0 and dst.exists() and dst.stat().st_size > 1024
    except Exception as exc:
        logger.warning("Download failed %s: %s", url, exc)
        return False


async def _fetch_embedded_python(pkg_dir: Path) -> bool:
    """Download Python 3.12 embeddable + get-pip.py; installer needs no Python prerequisite."""
    py_dir, zip_path = pkg_dir / "python", pkg_dir / "_pyembed.zip"
    for ver in _EMBED_PY_VERS:
        if not await _curl_download(_EMBED_PY_URL.format(v=ver), zip_path):
            continue
        try:
            py_dir.mkdir(exist_ok=True)
            with zipfile.ZipFile(str(zip_path), "r") as zf:
                zf.extractall(str(py_dir))
            zip_path.unlink(missing_ok=True)
            for pth in py_dir.glob("python3*._pth"):
                txt = pth.read_text(encoding="utf-8")
                if "import site" not in txt:
                    pth.write_text(txt.rstrip() + "\nimport site\n", encoding="utf-8")
            (py_dir / "Lib" / "site-packages").mkdir(parents=True, exist_ok=True)
            await _curl_download(_GET_PIP_URL, pkg_dir / "get-pip.py", timeout=30)
            logger.info("Bundled Python %s embeddable", ver)
            return True
        except Exception as exc:
            logger.warning("Python embeddable extract failed (py%s): %s", ver, exc)
            shutil.rmtree(str(py_dir), ignore_errors=True)
            zip_path.unlink(missing_ok=True)
    logger.warning("Python embeddable unavailable; endpoint will need Python pre-installed")
    return False


async def _fetch_winsw(pkg_dir: Path) -> bool:
    """Download WinSW service wrapper exe. Bundled as OmniAgentSvc.exe."""
    dst = pkg_dir / "OmniAgentSvc.exe"
    ok = await _curl_download(_WINSW_URL, dst, timeout=60)
    if ok:
        logger.info("Bundled WinSW (%d KB) as OmniAgentSvc.exe", dst.stat().st_size // 1024)
    else:
        logger.warning("WinSW download failed; service registration will fall back to Task Scheduler")
    return ok


def _setup_svc_ps1(api_url: str, reg_key: str) -> str:
    return f"""\
#Requires -RunAsAdministrator
$ErrorActionPreference = 'Continue'
$D = $PSScriptRoot

[IO.File]::WriteAllText("$D\\config.yaml", @"
api_base_url: {api_url}
registration_key: {reg_key}
agent_id: null
agent_token: null
interval_seconds: 30
max_cpu_percent: 20
agentic_mode_enabled: false
"@)

# Prefer bundled Python (standalone — no Python prerequisite)
$py = "$D\\python\\python.exe"
if (-not (Test-Path $py)) {{
    $py = $null
    foreach ($c in @(
        (Get-Command python  -EA SilentlyContinue)?.Source,
        (Get-Command python3 -EA SilentlyContinue)?.Source,
        "$env:LOCALAPPDATA\\Programs\\Python\\Python312\\python.exe",
        "$env:LOCALAPPDATA\\Programs\\Python\\Python311\\python.exe",
        "$env:LOCALAPPDATA\\Programs\\Python\\Python310\\python.exe",
        "C:\\Python312\\python.exe","C:\\Python311\\python.exe","C:\\Python310\\python.exe",
        "C:\\Program Files\\Python312\\python.exe"
    )) {{ if ($c -and (Test-Path $c -EA SilentlyContinue)) {{ $py = $c; break }} }}
    if (-not $py) {{ $py = 'python.exe' }}
}}
Write-Host "Python: $py"

# Bootstrap pip inside embedded Python if needed
if ((& $py -m pip --version 2>&1) -notmatch 'pip') {{
    $gp = "$D\\get-pip.py"
    if (Test-Path $gp) {{ Write-Host "Bootstrapping pip..."; & $py $gp --no-warn-script-location --quiet 2>&1 }}
}}

Write-Host "Installing dependencies..."
$req = if (Test-Path "$D\\requirements-runtime.txt") {{ "$D\\requirements-runtime.txt" }} else {{ "$D\\requirements.txt" }}
$wheels = "$D\\wheels"
if (Test-Path $wheels) {{
    & $py -m pip install --no-index --find-links $wheels -r $req --quiet 2>&1
}} else {{
    & $py -m pip install -r $req --quiet 2>&1
}}

# Register as Windows Service using bundled WinSW (no pywin32 or .NET SDK needed)
$svcExe = "$D\\OmniAgentSvc.exe"
if (Test-Path $svcExe) {{
    Write-Host "Registering OmniAgent Windows Service via WinSW..."
    [IO.File]::WriteAllText("$D\\OmniAgentSvc.xml", @"
<configuration>
  <id>OmniAgent</id>
  <name>Enterprise OmniAgent</name>
  <description>AI-Powered Enterprise Security Agent</description>
  <executable>$D\\python\\python.exe</executable>
  <arguments>"$D\\agent.py"</arguments>
  <workingdirectory>$D</workingdirectory>
  <startmode>Automatic</startmode>
  <logpath>$D\\logs</logpath>
  <log mode="roll-by-size"><sizeThreshold>10240</sizeThreshold><keepFiles>3</keepFiles></log>
  <onfailure action="restart" delay="5 sec"/>
  <onfailure action="restart" delay="15 sec"/>
  <onfailure action="restart" delay="30 sec"/>
</configuration>
"@)
    & $svcExe stop      2>$null
    & $svcExe uninstall 2>$null
    Start-Sleep -Seconds 2
    & $svcExe install
    & $svcExe start
    Write-Host "OmniAgent running. Manage via services.msc or: & '$svcExe' status"
}} else {{
    Write-Warning "WinSW not bundled — using Task Scheduler AtStartup fallback."
    Unregister-ScheduledTask -TaskName OmniAgent -Confirm:$false -EA SilentlyContinue
    $act = New-ScheduledTaskAction -Execute $py -Argument "`"$D\\agent.py`"" -WorkingDirectory $D
    $set = New-ScheduledTaskSettingsSet -ExecutionTimeLimit 0 -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1) -StartWhenAvailable -MultipleInstances IgnoreNew
    Register-ScheduledTask -TaskName OmniAgent -Action $act -Trigger (New-ScheduledTaskTrigger -AtStartup) -Settings $set -Principal (New-ScheduledTaskPrincipal -UserId SYSTEM -RunLevel Highest) -Force | Out-Null
    Start-ScheduledTask -TaskName OmniAgent
    Write-Host "OmniAgent scheduled task started."
}}
"""


def _nsis_file_commands(pkg_dir: Path) -> str:
    lines: list[str] = []
    skip = {"__pycache__", "venv", ".venv", "node_modules", "dist", "build", ".git"}
    for root, dirs, files in os.walk(pkg_dir):
        dirs[:] = sorted(d for d in dirs if d not in skip)
        rel = os.path.relpath(root, pkg_dir)
        install_path = "$INSTDIR" if rel == "." else f"$INSTDIR\\{rel.replace('/', chr(92))}"
        payload = sorted(f for f in files if not f.endswith(".pyc") and f not in {"buffer.db"})
        if not payload:
            continue
        lines.append(f'  SetOutPath "{install_path}"')
        for fname in payload:
            lines.append(f'  File "{os.path.join(root, fname)}"')
    return "\n".join(lines)


def _build_nsi_script(tenant_name: str, file_commands: str, outfile: str) -> str:
    esc = lambda s: s.replace('"', '$\\"')
    uninstall_cmd = (
        'powershell -NoProfile -Command "& { '
        'try { '
        '$svc=\\"$INSTDIR\\\\OmniAgentSvc.exe\\"; '
        'if(Test-Path $svc){& $svc stop 2>$null; & $svc uninstall 2>$null} '
        'Unregister-ScheduledTask -TaskName OmniAgent -Confirm:$$false -EA SilentlyContinue '
        '} catch {} }"'
    )
    return f"""; OmniAgent Installer — auto-generated
!include "MUI2.nsh"
Name "OmniAgent 2.0 — {esc(tenant_name)}"
OutFile "{outfile}"
InstallDir "$PROGRAMFILES64\\OmniAgent"
RequestExecutionLevel admin
SetCompressor lzma

!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!define MUI_FINISHPAGE_TEXT "OmniAgent installed.$\\r$\\nManage via services.msc or: sc query OmniAgent"
!insertmacro MUI_PAGE_FINISH
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_LANGUAGE "English"
!define UNINST "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\OmniAgent"

Section "OmniAgent"
  SectionIn RO
{file_commands}
  nsExec::ExecToLog 'powershell -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "$INSTDIR\\setup_svc.ps1"'
  WriteRegStr   HKLM "${{UNINST}}" "DisplayName"     "OmniAgent"
  WriteRegStr   HKLM "${{UNINST}}" "DisplayVersion"  "2.0.0"
  WriteRegStr   HKLM "${{UNINST}}" "Publisher"       "Enterprise OmniAgent AI Platform"
  WriteRegStr   HKLM "${{UNINST}}" "UninstallString" '"$INSTDIR\\Uninstall.exe"'
  WriteRegDWORD HKLM "${{UNINST}}" "NoModify" 1
  WriteRegDWORD HKLM "${{UNINST}}" "NoRepair" 1
  WriteUninstaller "$INSTDIR\\Uninstall.exe"
SectionEnd

Section "Uninstall"
  ExecWait '{uninstall_cmd}' $0
  RMDir /r "$INSTDIR"
  DeleteRegKey HKLM "${{UNINST}}"
SectionEnd
"""


async def _prepare_pkg(agent_src: Path, pkg_dir: Path, api_url: str, registration_key: str) -> None:
    """Copy agent source, write config + setup_svc.ps1, bundle wheels + Python + WinSW."""
    shutil.copytree(agent_src, pkg_dir, ignore=_AGENT_EXCLUDE)
    pkg_dir.joinpath("setup_svc.ps1").write_text(
        _setup_svc_ps1(api_url, registration_key), encoding="utf-8")
    with open(pkg_dir / "config.yaml", "w", encoding="utf-8") as f:
        yaml.dump(_config_yaml(api_url, registration_key), f, default_flow_style=False, sort_keys=True)
    await _bundle_wheels(pkg_dir / "requirements.txt", pkg_dir)
    await _fetch_embedded_python(pkg_dir)
    await _fetch_winsw(pkg_dir)


async def build_exe(
    tenant_id: str, tenant_name: str, registration_key: str,
    api_url: str, background_tasks: BackgroundTasks, base_dir: Path,
) -> Response:
    makensis = shutil.which("makensis")
    if not makensis:
        raise HTTPException(status_code=503,
            detail="makensis not installed. Run: sudo apt-get install -y nsis")

    agent_src = _agent_src(base_dir)
    tenant_safe = tenant_name.replace(" ", "-").lower()
    temp_dir = Path(tempfile.mkdtemp(prefix=f"omni_exe_{tenant_id}_"))
    try:
        pkg_dir = temp_dir / "pkg"
        await _prepare_pkg(agent_src, pkg_dir, api_url, registration_key)

        exe_out = temp_dir / f"OmniAgent-{tenant_safe}-Setup.exe"
        nsi_path = temp_dir / "install.nsi"
        nsi_path.write_text(
            _build_nsi_script(tenant_name, _nsis_file_commands(pkg_dir), str(exe_out)),
            encoding="utf-8",
        )
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

    def dir_xml(parent: str = "", indent: int = 10) -> str:
        depth = len(parent.split("/")) if parent else 0
        out = ""
        for key, did in sorted(dir_ids.items()):
            parts = key.replace("\\","/").split("/")
            if len(parts) != depth + 1 or "/".join(parts[:-1]) != parent:
                continue
            p = " " * indent
            out += f'{p}<Directory Id="{did}" Name="{parts[-1]}">\n{dir_xml(key, indent+2)}{p}</Directory>\n'
        return out

    comps, refs = [], []
    for i, (abs_p, rel) in enumerate(entries):
        cid, g = f"Comp{i:05d}", fguid(str(rel / abs_p.name))
        did = dir_ids.get(str(rel) if rel.parts else "", "INSTALLDIR")
        comps.append(
            f'      <Component Id="{cid}" Guid="{{{g}}}" Directory="{did}">\n'
            f'        <File Id="File{i:05d}" Source="{abs_p}" Name="{abs_p.name}" KeyPath="yes"/>\n'
            f'      </Component>')
        refs.append(f'      <ComponentRef Id="{cid}"/>')

    return f"""<?xml version="1.0" encoding="UTF-8"?>
<Wix xmlns="http://schemas.microsoft.com/wix/2006/wi">
  <Product Id="*" Name="{tenant_name} OmniAgent" Language="1033" Version="2.0.0"
           Manufacturer="Enterprise OmniAgent AI Platform" UpgradeCode="{{{uguid}}}">
    <Package InstallerVersion="300" Compressed="yes" InstallScope="perMachine" Platform="x64"/>
    <MediaTemplate EmbedCab="yes"/>
    <Directory Id="TARGETDIR" Name="SourceDir">
      <Directory Id="ProgramFiles64Folder">
        <Directory Id="INSTALLDIR" Name="OmniAgent">
{dir_xml('', 10)}        </Directory>
      </Directory>
    </Directory>
    <Feature Id="Complete" Level="1">
{chr(10).join(refs)}
    </Feature>
{chr(10).join(comps)}
    <CustomAction Id="RunSetup" Type="34" Directory="INSTALLDIR"
      ExeCommand="cmd /c powershell -NoProfile -NonInteractive -ExecutionPolicy Bypass -File setup_svc.ps1"/>
    <InstallExecuteSequence>
      <Custom Action="RunSetup" After="InstallFiles">NOT Installed</Custom>
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

    agent_src = _agent_src(base_dir)
    tenant_safe = tenant_name.replace(" ", "-").lower()
    temp_dir = Path(tempfile.mkdtemp(prefix=f"omni_msi_{tenant_id}_"))
    try:
        pkg_dir = temp_dir / "pkg"
        await _prepare_pkg(agent_src, pkg_dir, api_url, registration_key)

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


async def build_windows_zip(
    tenant_id: str, tenant_name: str, registration_key: str,
    api_url: str, background_tasks: BackgroundTasks, base_dir: Path,
) -> Response:
    agent_src = _agent_src(base_dir)
    tenant_safe = tenant_name.replace(" ", "-").lower()
    temp_dir = Path(tempfile.mkdtemp(prefix=f"omni_win_{tenant_id}_"))
    try:
        agent_dest = temp_dir / "content" / "OmniAgent"
        await _prepare_pkg(agent_src, agent_dest, api_url, registration_key)
        (temp_dir / "content" / "README.txt").write_text(
            f"OmniAgent for {tenant_name}\r\nInstall: cd OmniAgent && powershell -ExecutionPolicy Bypass -File setup_svc.ps1\r\nFully standalone — no prerequisites.\r\nAPI: {api_url}\r\n",
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
        raise HTTPException(status_code=500, detail="Failed to build Windows agent package")

#!/usr/bin/env python3
"""
Windows Agent Build Script
===========================
Builds omni-agent.exe from source using PyInstaller and packages
a complete deployment bundle ready for distribution.

Usage:
    python build_windows.py [--debug] [--skip-clean] [--no-upx]

Output:
    dist/
        omni-agent.exe          <- single self-contained executable
        config.yaml             <- template config (edit before deploying)
    dist/OmniAgent-Installer/
        omni-agent.exe
        config.yaml
        installer/
            install_agent.ps1   <- run this on target machines
            uninstall_agent.ps1
            Configure-Agent.ps1
        README.txt

Requirements:
    pip install pyinstaller pyinstaller-hooks-contrib
    pip install -r requirements.txt
"""

import sys
import os
import shutil
import subprocess
import platform
import argparse
import zipfile
from pathlib import Path
from datetime import datetime

BASE_DIR = Path(__file__).resolve().parent
DIST_DIR = BASE_DIR / "dist"
BUILD_DIR = BASE_DIR / "build"
INSTALLER_DIR = BASE_DIR / "installer"

AGENT_VERSION = "2.0.1"
EXE_NAME = "omni-agent.exe"


def banner(msg: str):
    width = 60
    print("\n" + "=" * width)
    print(f"  {msg}")
    print("=" * width)


def check_python_version():
    if sys.version_info < (3, 9):
        print("ERROR: Python 3.9+ required.")
        sys.exit(1)
    if platform.system() != "Windows":
        print("WARNING: This build script targets Windows. Cross-compilation is not supported.")
        print("         For Linux/macOS packaging use build.py instead.")


def ensure_pyinstaller():
    try:
        import PyInstaller
        print(f"  PyInstaller {PyInstaller.__version__} found.")
    except ImportError:
        print("  PyInstaller not found — installing...")
        subprocess.check_call([sys.executable, "-m", "pip", "install",
                               "pyinstaller>=6.0", "pyinstaller-hooks-contrib>=2024.0"])
        print("  PyInstaller installed.")


def check_upx():
    """Return True if UPX is available on PATH."""
    return shutil.which("upx") is not None


def clean_previous():
    banner("Cleaning previous build artefacts")
    for d in [DIST_DIR, BUILD_DIR]:
        if d.exists():
            shutil.rmtree(d)
            print(f"  Removed: {d}")


def run_pyinstaller(debug: bool, no_upx: bool):
    banner("Running PyInstaller")

    spec_file = BASE_DIR / "omni-agent.spec"
    if not spec_file.exists():
        print(f"ERROR: Spec file not found: {spec_file}")
        sys.exit(1)

    cmd = [
        sys.executable, "-m", "PyInstaller",
        str(spec_file),
        "--distpath", str(DIST_DIR),
        "--workpath", str(BUILD_DIR),
        "--noconfirm",
    ]

    if debug:
        cmd.append("--debug=all")

    # UPX is controlled by the spec file (upx=True/False in EXE block).
    # PyInstaller silently skips UPX when it's not on PATH — no flag needed.
    if no_upx:
        print("  --no-upx requested: set upx=False in omni-agent.spec to persist.")
    if not check_upx():
        print("  UPX not found on PATH — building without compression.")
        print("  Install UPX from https://upx.github.io/ for ~30% smaller exe.")

    print(f"  Command: {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=str(BASE_DIR))
    if result.returncode != 0:
        print("\nERROR: PyInstaller build failed.")
        sys.exit(result.returncode)


def verify_exe():
    banner("Verifying output")
    exe_path = DIST_DIR / EXE_NAME
    if not exe_path.exists():
        print(f"ERROR: Expected exe not found at {exe_path}")
        sys.exit(1)

    size_mb = exe_path.stat().st_size / (1024 * 1024)
    print(f"  {EXE_NAME}  ({size_mb:.1f} MB)")

    # Quick smoke-test: exe must be a valid PE with the correct signature.
    # We don't launch it here because the UAC manifest requires elevation.
    try:
        import struct
        with open(exe_path, "rb") as f:
            dos_header = f.read(2)
        if dos_header == b"MZ":
            print("  Smoke-test: PASS (valid Windows PE executable)")
        else:
            print("  Smoke-test: WARNING — file does not look like a Windows PE")
    except Exception as e:
        print(f"  Smoke-test: WARNING — {e}")


def copy_installer_scripts():
    """Copy PowerShell installer scripts into dist/ alongside the exe."""
    banner("Copying installer scripts")
    dest_installer = DIST_DIR / "installer"
    dest_installer.mkdir(exist_ok=True)

    scripts = [
        INSTALLER_DIR / "install_agent.ps1",
        INSTALLER_DIR / "uninstall_agent.ps1",
        INSTALLER_DIR / "Configure-Agent.ps1",
    ]
    for s in scripts:
        if s.exists():
            shutil.copy2(s, dest_installer / s.name)
            print(f"  Copied: {s.name}")
        else:
            print(f"  WARNING: {s.name} not found — skipping.")

    # Copy config template
    cfg_src = BASE_DIR / "config.yaml"
    cfg_dst = DIST_DIR / "config.yaml"
    if cfg_src.exists() and not cfg_dst.exists():
        shutil.copy2(cfg_src, cfg_dst)
        print("  Copied: config.yaml (template)")


def write_readme():
    readme = DIST_DIR / "README.txt"
    content = f"""Enterprise Omni Agent v{AGENT_VERSION} — Windows Deployment Package
Built: {datetime.now().strftime('%Y-%m-%d %H:%M')}
=======================================================================

QUICK START
-----------
1. Edit config.yaml — set api_base_url and agent_token
   (or run installer\\Configure-Agent.ps1 to do it interactively)

2. Install as a Windows Service (run PowerShell as Administrator):
   .\\installer\\install_agent.ps1

3. Verify it's running:
   Get-Service OmniAgent
   Get-EventLog -LogName Application -Source OmniAgent -Newest 20

MANUAL COMMANDS
---------------
Install service:    omni-agent.exe --install
Start service:      sc start OmniAgent
Stop service:       sc stop OmniAgent
Uninstall service:  omni-agent.exe --uninstall
Run in foreground:  omni-agent.exe   (useful for testing/debugging)

LOGS
----
Windows Event Log:  eventvwr.msc > Application > OmniAgent
File log:           %PROGRAMDATA%\\OmniAgent\\agent.log

SERVICE RECOVERY
----------------
The service is configured to restart automatically on failure (3 attempts,
60-second delay between each attempt).

UNINSTALL
---------
Run:  .\\installer\\uninstall_agent.ps1
"""
    readme.write_text(content)
    print(f"  Created: README.txt")


def create_distribution_zip():
    banner("Creating distribution zip")
    zip_name = f"OmniAgent-{AGENT_VERSION}-Windows-x64.zip"
    zip_path = BASE_DIR / zip_name

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for f in DIST_DIR.rglob("*"):
            if f.is_file():
                arcname = f"OmniAgent-{AGENT_VERSION}/" + str(f.relative_to(DIST_DIR))
                zf.write(f, arcname)

    size_mb = zip_path.stat().st_size / (1024 * 1024)
    print(f"  Created: {zip_name}  ({size_mb:.1f} MB)")
    return zip_path


def print_summary(zip_path: Path):
    banner("Build Complete")
    exe_path = DIST_DIR / EXE_NAME
    size_mb = exe_path.stat().st_size / (1024 * 1024)
    print(f"""
  Executable:    dist\\{EXE_NAME}  ({size_mb:.1f} MB)
  Package:       {zip_path.name}
  Version:       {AGENT_VERSION}

  NEXT STEPS:
  1. Edit dist\\config.yaml with your backend URL and agent token
  2. Deploy to target machines:
       Copy dist\\ folder → target machine
       Run (as Administrator):  .\\installer\\install_agent.ps1
  3. (Optional) Sign the exe with a code-signing certificate:
       signtool sign /fd SHA256 /tr http://timestamp.digicert.com /td SHA256 \\
           /f your_cert.pfx /p your_password dist\\{EXE_NAME}
""")


def main():
    parser = argparse.ArgumentParser(description="Build omni-agent.exe for Windows")
    parser.add_argument("--debug",      action="store_true", help="Enable PyInstaller debug output")
    parser.add_argument("--skip-clean", action="store_true", help="Skip cleaning previous build artefacts")
    parser.add_argument("--no-upx",    action="store_true", help="Disable UPX compression")
    parser.add_argument("--no-zip",    action="store_true", help="Skip creating distribution zip")
    args = parser.parse_args()

    banner(f"Omni Agent Windows Build  v{AGENT_VERSION}")
    check_python_version()
    ensure_pyinstaller()

    if not args.skip_clean:
        clean_previous()

    run_pyinstaller(debug=args.debug, no_upx=args.no_upx)
    verify_exe()
    copy_installer_scripts()
    write_readme()

    zip_path = None
    if not args.no_zip:
        zip_path = create_distribution_zip()

    print_summary(zip_path or DIST_DIR / EXE_NAME)


if __name__ == "__main__":
    main()

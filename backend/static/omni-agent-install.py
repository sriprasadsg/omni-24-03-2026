#!/usr/bin/env python3
"""Cross-platform Omni-Agent installer.

Real installer, not a simulation: resolves the tenant from the registration
key, downloads the actual agent source + capabilities from the platform,
sets up a venv, installs dependencies, and (on Linux, with --as-service)
registers a systemd unit. The agent process registers itself with the
backend on first startup — this script never fabricates a registration.

Mirrors backend/static/linux-install.sh's real install flow so both entry
points end up in the same state; this one is OS-aware (Linux/macOS/Windows)
for users who'd rather `curl | python3` than `curl | bash`.
"""
import argparse
import json
import os
import platform
import shutil
import subprocess
import sys
import tarfile
import urllib.error
import urllib.request

DEFAULT_INSTALL_DIR = {
    "Linux": "/opt/enterprise-omni-agent",
    "Darwin": "/opt/enterprise-omni-agent",
    "Windows": os.path.join(os.environ.get("ProgramFiles", r"C:\Program Files"), "OmniAgent"),
}


def _post_json(url, payload, timeout=30):
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.status, json.loads(resp.read().decode("utf-8"))


def _download(url, dest_path, timeout=60):
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=timeout) as resp, open(dest_path, "wb") as f:
        shutil.copyfileobj(resp, f)


def resolve_tenant(api_url, registration_key, fallback_tenant_id):
    if not registration_key:
        print("  ! No registration key provided — using tenant-id:", fallback_tenant_id)
        return fallback_tenant_id
    try:
        status, body = _post_json(f"{api_url}/api/tenants/lookup-key", {"registrationKey": registration_key})
        if body.get("success"):
            tenant_id = body["tenantId"]
            print(f"  + Key verified — Tenant: {body.get('name', tenant_id)} ({tenant_id})")
            return tenant_id
    except (urllib.error.URLError, KeyError, json.JSONDecodeError) as e:
        print(f"  ! Could not verify registration key ({e}) — using tenant-id: {fallback_tenant_id}")
    return fallback_tenant_id


def fetch_agent_source(api_url, install_dir):
    agent_py = os.path.join(install_dir, "agent.py")
    print(f"  > Downloading agent from {api_url}...")
    _download(f"{api_url}/api/agent-updates/download/agent.py", agent_py)
    print("  + Downloaded agent.py")

    caps_tar = os.path.join(install_dir, "capabilities.tar.gz")
    try:
        _download(f"{api_url}/api/agent-updates/download/capabilities.tar.gz", caps_tar)
        with tarfile.open(caps_tar) as tf:
            tf.extractall(install_dir)
        os.remove(caps_tar)
        print("  + Capabilities extracted")
    except (urllib.error.URLError, tarfile.TarError) as e:
        print(f"  ! Capabilities download failed ({e}) — agent may run in limited mode")


def write_config(install_dir, api_url, tenant_id, registration_key):
    config_path = os.path.join(install_dir, "config.yaml")
    with open(config_path, "w", encoding="utf-8") as f:
        f.write(f'api_base_url: "{api_url}"\n')
        f.write(f'tenant_id: "{tenant_id}"\n')
        f.write(f'registration_key: "{registration_key}"\n')
        f.write("interval_seconds: 5\n")
        f.write("agentic_mode_enabled: true\n")
        f.write("swarm:\n  enabled: true\n")
        f.write("autonomous_actions:\n  enabled: true\n")
    print(f"  + config.yaml written: {config_path}")


def setup_venv(install_dir):
    venv_dir = os.path.join(install_dir, "venv")
    print("  > Creating virtual environment...")
    subprocess.run([sys.executable, "-m", "venv", venv_dir], check=True)
    venv_python = os.path.join(venv_dir, "Scripts" if platform.system() == "Windows" else "bin",
                                "python.exe" if platform.system() == "Windows" else "python")
    subprocess.run([venv_python, "-m", "pip", "install", "--upgrade", "pip", "setuptools", "wheel", "--quiet"],
                    check=True)

    requirements = os.path.join(install_dir, "requirements.txt")
    if os.path.isfile(requirements):
        subprocess.run([venv_python, "-m", "pip", "install", "-r", requirements, "--quiet"], check=True)
        print("  + Dependencies installed from requirements.txt")
    else:
        subprocess.run([venv_python, "-m", "pip", "install", "--quiet",
                         "requests", "PyYAML", "psutil", "py-cpuinfo", "cryptography", "httpx",
                         "watchdog", "websockets>=12.0", "websocket-client>=1.7.0",
                         "python-socketio[client]>=5.10.0"], check=True)
        print("  + Core dependencies installed (requirements.txt not found)")
    return venv_python


def setup_systemd_service(install_dir, venv_python):
    unit_path = "/etc/systemd/system/omni-agent.service"
    unit = f"""[Unit]
Description=Enterprise Omni Platform Agent
After=network.target

[Service]
Type=simple
User={os.environ.get("SUDO_USER") or os.environ.get("USER", "root")}
WorkingDirectory={install_dir}
Environment="PYTHONPATH={install_dir}"
ExecStart={venv_python} agent.py
Restart=always
RestartSec=10
StandardOutput=append:{install_dir}/logs/agent.log
StandardError=append:{install_dir}/logs/agent-error.log

[Install]
WantedBy=multi-user.target
"""
    try:
        with open(unit_path, "w", encoding="utf-8") as f:
            f.write(unit)
        subprocess.run(["systemctl", "daemon-reload"], check=True)
        subprocess.run(["systemctl", "enable", "--now", "omni-agent"], check=True)
        print("  + systemd service 'omni-agent' installed and started")
    except (PermissionError, OSError, subprocess.CalledProcessError) as e:
        print(f"  ! Could not install systemd service ({e}) — run manually via start-agent script")


def write_start_script(install_dir, venv_python):
    if platform.system() == "Windows":
        path = os.path.join(install_dir, "start-agent.bat")
        with open(path, "w", encoding="utf-8") as f:
            f.write(f'@echo off\ncd /d "{install_dir}"\n"{venv_python}" agent.py\n')
    else:
        path = os.path.join(install_dir, "start-agent.sh")
        with open(path, "w", encoding="utf-8") as f:
            f.write(f'#!/bin/bash\ncd "{install_dir}"\n"{venv_python}" agent.py\n')
        os.chmod(path, 0o755)
    print(f"  + Start script created: {path}")


def main():
    parser = argparse.ArgumentParser(description="Omni-Agent installer")
    parser.add_argument("--registration-key", required=True, help="Tenant registration key")
    parser.add_argument("--api-url", required=True, help="Base URL of the Omni-Agent platform")
    parser.add_argument("--tenant-id", default="default-tenant", help="Fallback tenant id if key lookup fails")
    parser.add_argument("--install-dir", default=None, help="Install directory (default: OS-specific)")
    parser.add_argument("--as-service", action="store_true", help="Register a systemd service (Linux only)")
    args = parser.parse_args()

    if sys.version_info < (3, 11):
        print(f"ERROR: Python 3.11+ required, found {sys.version_info.major}.{sys.version_info.minor}",
              file=sys.stderr)
        sys.exit(1)

    api_url = args.api_url.rstrip("/")
    system = platform.system()
    install_dir = args.install_dir or DEFAULT_INSTALL_DIR.get(system, "/opt/enterprise-omni-agent")

    print("Omni-Agent Installer")
    print("=====================")
    print(f"  Platform    : {system}")
    print(f"  Install dir : {install_dir}")
    print(f"  API URL     : {api_url}")

    os.makedirs(install_dir, exist_ok=True)
    os.makedirs(os.path.join(install_dir, "logs"), exist_ok=True)

    print("\n[1/4] Resolving registration key...")
    tenant_id = resolve_tenant(api_url, args.registration_key, args.tenant_id)

    print("\n[2/4] Downloading agent source...")
    fetch_agent_source(api_url, install_dir)

    print("\n[3/4] Writing configuration...")
    write_config(install_dir, api_url, tenant_id, args.registration_key)

    print("\n[4/4] Installing dependencies...")
    venv_python = setup_venv(install_dir)

    if args.as_service and system == "Linux":
        setup_systemd_service(install_dir, venv_python)
    else:
        write_start_script(install_dir, venv_python)

    print(f"\nInstallation complete: {install_dir}")
    print("The agent registers itself with the platform on first startup.")
    if not (args.as_service and system == "Linux"):
        starter = "start-agent.bat" if system == "Windows" else "start-agent.sh"
        print(f"  Run: {os.path.join(install_dir, starter)}")


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as e:
        print(f"\nERROR: command failed: {e}", file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        sys.exit(130)

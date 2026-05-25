"""
Security tools registered with the ToolRegistry for ReAct loop execution.

These are read-only / low-blast-radius tools safe for autonomous execution.
Higher-risk actions (isolate, quarantine, kill) go through the capability
manager's execute_single_instruction() path with safety gating.
"""

import os
import json
import logging
import platform
import socket
import psutil
import subprocess

from .tool_registry import registry

logger = logging.getLogger(__name__)


@registry.register
def get_running_processes() -> str:
    """List all running processes: name, pid, cpu_percent, memory_percent, status."""
    try:
        procs = []
        for p in psutil.process_iter(["name", "pid", "cpu_percent", "memory_percent", "status"]):
            try:
                procs.append(p.info)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        # Sort by CPU descending so highest consumers appear first
        procs.sort(key=lambda x: x.get("cpu_percent") or 0, reverse=True)
        return json.dumps(procs[:50])
    except Exception as e:
        return json.dumps({"error": str(e)})


@registry.register
def get_active_network_connections() -> str:
    """List active TCP/UDP network connections: laddr, raddr, status, pid."""
    try:
        conns = []
        for c in psutil.net_connections(kind="inet"):
            conns.append({
                "fd":     c.fd,
                "laddr":  f"{c.laddr.ip}:{c.laddr.port}" if c.laddr else "",
                "raddr":  f"{c.raddr.ip}:{c.raddr.port}" if c.raddr else "",
                "status": c.status,
                "pid":    c.pid,
            })
        return json.dumps(conns)
    except Exception as e:
        return json.dumps({"error": str(e)})


@registry.register
def get_system_resource_usage() -> str:
    """Return CPU, memory, disk, and swap usage percentages."""
    try:
        disk = psutil.disk_usage("/")
        return json.dumps({
            "cpu_percent":    psutil.cpu_percent(interval=1),
            "memory_percent": psutil.virtual_memory().percent,
            "disk_percent":   disk.percent,
            "swap_percent":   psutil.swap_memory().percent,
            "load_avg":       list(psutil.getloadavg()) if hasattr(psutil, "getloadavg") else [],
        })
    except Exception as e:
        return json.dumps({"error": str(e)})


@registry.register
def find_suspicious_processes(keywords: str) -> str:
    """Search running processes for suspicious name substrings (comma-separated keywords)."""
    try:
        kws = [k.strip().lower() for k in keywords.split(",") if k.strip()]
        matches = []
        for p in psutil.process_iter(["name", "pid", "cmdline", "username"]):
            try:
                name = (p.info.get("name") or "").lower()
                cmd  = " ".join(p.info.get("cmdline") or []).lower()
                if any(kw in name or kw in cmd for kw in kws):
                    matches.append({
                        "pid":      p.info["pid"],
                        "name":     p.info["name"],
                        "cmdline":  (p.info.get("cmdline") or [])[:5],
                        "username": p.info.get("username", ""),
                    })
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        return json.dumps(matches)
    except Exception as e:
        return json.dumps({"error": str(e)})


@registry.register
def get_open_listening_ports() -> str:
    """List all TCP/UDP ports in LISTEN state with owning process."""
    try:
        listening = []
        for c in psutil.net_connections(kind="inet"):
            if c.status == psutil.CONN_LISTEN or c.status == "LISTEN":
                try:
                    proc_name = psutil.Process(c.pid).name() if c.pid else "unknown"
                except Exception:
                    proc_name = "unknown"
                listening.append({
                    "port":    c.laddr.port if c.laddr else None,
                    "ip":      c.laddr.ip   if c.laddr else "",
                    "pid":     c.pid,
                    "process": proc_name,
                })
        return json.dumps(listening)
    except Exception as e:
        return json.dumps({"error": str(e)})


@registry.register
def get_environment_info() -> str:
    """Return OS, hostname, IP address, Python version, and platform details."""
    try:
        return json.dumps({
            "os":             platform.system(),
            "os_release":     platform.release(),
            "os_version":     platform.version()[:120],
            "hostname":       socket.gethostname(),
            "ip_address":     socket.gethostbyname(socket.gethostname()),
            "python_version": platform.python_version(),
            "architecture":   platform.machine(),
            "cpu_count":      psutil.cpu_count(logical=True),
        })
    except Exception as e:
        return json.dumps({"error": str(e)})


@registry.register
def check_file_exists(file_path: str) -> str:
    """Check whether a specific file path exists and return its basic metadata."""
    try:
        import stat as _stat
        p = os.path.realpath(file_path)
        if not os.path.exists(p):
            return json.dumps({"exists": False, "path": p})
        st = os.stat(p)
        return json.dumps({
            "exists":    True,
            "path":      p,
            "size_bytes": st.st_size,
            "is_file":   os.path.isfile(p),
            "is_dir":    os.path.isdir(p),
            "mode":      oct(_stat.S_IMODE(st.st_mode)),
        })
    except Exception as e:
        return json.dumps({"error": str(e)})


@registry.register
def get_recently_modified_files(directory: str, minutes: int) -> str:
    """List files modified within the last N minutes under a directory (max 50 results)."""
    import time
    try:
        cutoff = time.time() - (minutes * 60)
        results = []
        for root, _dirs, files in os.walk(directory):
            for fname in files:
                fpath = os.path.join(root, fname)
                try:
                    mtime = os.path.getmtime(fpath)
                    if mtime >= cutoff:
                        results.append({"path": fpath, "mtime": mtime})
                        if len(results) >= 50:
                            break
                except OSError:
                    pass
            if len(results) >= 50:
                break
        return json.dumps(sorted(results, key=lambda x: x["mtime"], reverse=True))
    except Exception as e:
        return json.dumps({"error": str(e)})


@registry.register
def get_startup_items() -> str:
    """List startup/autorun entries (Windows registry run keys or Linux systemd units)."""
    try:
        items = []
        sys = platform.system()
        if sys == "Windows":
            import winreg
            for hive, path in [
                (winreg.HKEY_CURRENT_USER,  r"Software\Microsoft\Windows\CurrentVersion\Run"),
                (winreg.HKEY_LOCAL_MACHINE, r"Software\Microsoft\Windows\CurrentVersion\Run"),
            ]:
                try:
                    key = winreg.OpenKey(hive, path)
                    i = 0
                    while True:
                        try:
                            name, val, _ = winreg.EnumValue(key, i)
                            items.append({"name": name, "value": val, "source": path})
                            i += 1
                        except OSError:
                            break
                    winreg.CloseKey(key)
                except Exception:
                    pass
        else:
            # Linux: list enabled systemd units
            result = subprocess.run(
                ["systemctl", "list-units", "--type=service", "--state=enabled", "--no-pager", "--plain"],
                capture_output=True, text=True, timeout=10,
            )
            for line in result.stdout.splitlines()[1:]:
                parts = line.split()
                if parts:
                    items.append({"name": parts[0], "source": "systemd"})
        return json.dumps(items[:100])
    except Exception as e:
        return json.dumps({"error": str(e)})


@registry.register
def scan_ip_virustotal(ip_address: str) -> str:
    """Query VirusTotal for the reputation of an IP address. Returns verdict, detection ratio, and malicious/suspicious counts."""
    try:
        import sys, os
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "capabilities"))
        from threat_intel import lookup_ip
        return json.dumps(lookup_ip(ip_address))
    except Exception as e:
        return json.dumps({"error": str(e)})


@registry.register
def scan_domain_virustotal(domain: str) -> str:
    """Query VirusTotal for the reputation of a domain name. Returns verdict, detection ratio, and malicious/suspicious counts."""
    try:
        import sys, os
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "capabilities"))
        from threat_intel import lookup_domain
        return json.dumps(lookup_domain(domain))
    except Exception as e:
        return json.dumps({"error": str(e)})


@registry.register
def scan_url_virustotal(url: str) -> str:
    """Query VirusTotal for the reputation of a URL. Returns verdict, detection ratio, and malicious/suspicious counts."""
    try:
        import sys, os
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "capabilities"))
        from threat_intel import lookup_url
        return json.dumps(lookup_url(url))
    except Exception as e:
        return json.dumps({"error": str(e)})


@registry.register
def scan_file_hash_virustotal(file_hash: str) -> str:
    """Query VirusTotal for the reputation of a file hash (MD5, SHA1, or SHA256). Returns verdict, detection ratio, and antivirus detections."""
    try:
        import sys, os
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "capabilities"))
        from threat_intel import lookup_hash
        return json.dumps(lookup_hash(file_hash))
    except Exception as e:
        return json.dumps({"error": str(e)})


@registry.register
def check_user_accounts() -> str:
    """List local user accounts with enabled/admin status (read-only, no passwords)."""
    try:
        users = []
        sys = platform.system()
        if sys == "Windows":
            result = subprocess.run(
                ["net", "user"],
                capture_output=True, text=True, timeout=10,
            )
            for line in result.stdout.splitlines():
                line = line.strip()
                if line and not line.startswith("User") and not line.startswith("---") and not line.startswith("The"):
                    for name in line.split():
                        if name:
                            users.append({"username": name})
        else:
            with open("/etc/passwd") as f:
                for line in f:
                    parts = line.strip().split(":")
                    if len(parts) >= 7 and parts[6] not in ("/sbin/nologin", "/bin/false", "/usr/sbin/nologin"):
                        users.append({"username": parts[0], "uid": parts[2], "shell": parts[6]})
        return json.dumps(users[:50])
    except Exception as e:
        return json.dumps({"error": str(e)})

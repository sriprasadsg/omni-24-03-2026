"""
Process Monitor Capability
Builds enriched process trees with SHA-256 hashes, parent-child chains,
and IOC cross-referencing for the EDR Process Explorer view.
"""
from .base import BaseCapability
import psutil
import hashlib
import os
import platform
from datetime import datetime
from typing import Dict, Any, List, Optional


class ProcessMonitorCapability(BaseCapability):

    @property
    def capability_id(self) -> str:
        return "process_monitor"

    @property
    def capability_name(self) -> str:
        return "Process Monitor"

    def collect(self) -> Dict[str, Any]:
        """Get enriched process snapshot for Process Explorer UI."""
        raw = list(psutil.process_iter([
            "pid", "name", "ppid", "username", "exe",
            "cmdline", "create_time", "status",
            "cpu_percent", "memory_percent", "num_threads",
            "open_files", "connections"
        ]))

        all_procs: List[Dict] = []
        pid_map: Dict[int, Dict] = {}

        for proc in raw:
            try:
                info = proc.info
                exe = info.get("exe") or ""
                sha256 = self._hash_file(exe) if exe and os.path.isfile(exe) else None
                cmdline = " ".join(info.get("cmdline") or [])

                # Attempt to count open handles (Windows) / file descriptors (Linux)
                try:
                    open_files = len(proc.open_files())
                except Exception:
                    open_files = -1

                try:
                    conn_count = len(proc.connections())
                except Exception:
                    conn_count = 0

                entry = {
                    "pid": info["pid"],
                    "ppid": info.get("ppid"),
                    "name": info.get("name") or "unknown",
                    "username": info.get("username") or "SYSTEM",
                    "exe": exe,
                    "cmdline": cmdline[:300],
                    "sha256": sha256,
                    "create_time": datetime.fromtimestamp(
                        info.get("create_time") or 0
                    ).isoformat(),
                    "status": info.get("status"),
                    "cpu_percent": round(info.get("cpu_percent") or 0, 1),
                    "memory_mb": round((info.get("memory_percent") or 0) * psutil.virtual_memory().total / (100 * 1024 * 1024), 1),
                    "threads": info.get("num_threads") or 0,
                    "open_files": open_files,
                    "connections": conn_count,
                    "children": [],
                }
                all_procs.append(entry)
                pid_map[info["pid"]] = entry
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue

        # Wire up parent-child tree
        roots = []
        for p in all_procs:
            ppid = p.get("ppid")
            if ppid and ppid in pid_map and ppid != p["pid"]:
                pid_map[ppid]["children"].append(p["pid"])
            else:
                roots.append(p["pid"])

        # Build summary statistics
        total_cpu = sum(p["cpu_percent"] for p in all_procs)
        top_cpu = sorted(all_procs, key=lambda x: x["cpu_percent"], reverse=True)[:5]
        top_mem = sorted(all_procs, key=lambda x: x["memory_mb"], reverse=True)[:5]

        return {
            "capability": self.capability_id,
            "timestamp": datetime.utcnow().isoformat(),
            "platform": platform.system(),
            "process_count": len(all_procs),
            "processes": all_procs,      # Full flat list
            "root_pids": roots,          # PIDs with no known parent (for tree rendering)
            "total_cpu_percent": round(total_cpu, 1),
            "top_cpu_processes": [{"pid": p["pid"], "name": p["name"], "cpu": p["cpu_percent"]} for p in top_cpu],
            "top_memory_processes": [{"pid": p["pid"], "name": p["name"], "memory_mb": p["memory_mb"]} for p in top_mem],
        }

    @staticmethod
    def _hash_file(filepath: str) -> Optional[str]:
        """Compute SHA-256 of an executable file."""
        try:
            sha = hashlib.sha256()
            with open(filepath, "rb") as f:
                for chunk in iter(lambda: f.read(65536), b""):
                    sha.update(chunk)
            return sha.hexdigest()
        except Exception:
            return None

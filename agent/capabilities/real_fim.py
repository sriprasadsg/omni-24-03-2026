import time
import logging
import threading
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
import os
import platform

try:
    import socketio as _sio_mod
    _HAS_SOCKETIO = True
except ImportError:
    _HAS_SOCKETIO = False

try:
    from agent.capabilities.base import BaseCapability
except ImportError:
    class BaseCapability:
        pass

logger = logging.getLogger(__name__)

# Platform-specific critical paths to monitor
_WINDOWS_PATHS = [
    r"C:\Windows\System32\drivers\etc\hosts",
    r"C:\Windows\System32\drivers\etc\services",
    r"C:\Windows\System32\config\SAM",
    r"C:\Windows\System32\config\SYSTEM",
    r"C:\Windows\System32\config\SECURITY",
    r"C:\Windows\System32\config\SOFTWARE",
    r"C:\Windows\win.ini",
    r"C:\Windows\System32\GroupPolicy",
]
_LINUX_PATHS = [
    "/etc/passwd",
    "/etc/shadow",
    "/etc/group",
    "/etc/sudoers",
    "/etc/ssh/sshd_config",
    "/etc/crontab",
    "/etc/hosts",
    "/etc/ld.so.preload",
    "/etc/pam.d/common-auth",
    "/root/.ssh/authorized_keys",
]


class FileEventStreamer(FileSystemEventHandler):
    def __init__(self, sio, agent_id: str, backend_url: str, agent_key: str = ""):
        self.sio = sio
        self.agent_id = agent_id
        self._backend_url = backend_url.rstrip("/")
        self._agent_key = agent_key

    def on_modified(self, event):
        if not event.is_directory:
            self._emit_event("modified", event.src_path)

    def on_created(self, event):
        if not event.is_directory:
            self._emit_event("created", event.src_path)

    def on_deleted(self, event):
        if not event.is_directory:
            self._emit_event("deleted", event.src_path)

    def _emit_event(self, event_type: str, path: str):
        logger.info("[FIM] File %s: %s", event_type, path)
        payload = {
            "type": "fim_alert",
            "severity": "high",
            "title": f"Critical File {event_type.title()}",
            "message": f"File {path} was {event_type}.",
            "agent_id": self.agent_id,
            "source": "FileWatcher",
            "path": path,
            "event_type": event_type,
        }

        # Try Socket.IO first
        if self.sio is not None:
            try:
                self.sio.emit("security_event", payload)
                return
            except Exception as e:
                logger.warning("[FIM] Socket.IO emit failed: %s — falling back to HTTP POST", e)

        # HTTP POST fallback
        self._http_post_event(payload)

    def _http_post_event(self, payload: dict):
        try:
            import requests
            headers = {"Content-Type": "application/json"}
            if self._agent_key:
                headers["X-Agent-Key"] = self._agent_key
            url = f"{self._backend_url}/api/agents/{self.agent_id}/fim-events"
            requests.post(url, json=payload, headers=headers, timeout=5)
        except Exception as e:
            logger.debug("[FIM] HTTP POST fallback failed: %s", e)


def _load_backend_url() -> str:
    try:
        import yaml, pathlib
        cfg_path = pathlib.Path(__file__).parent.parent / "config.yaml"
        if cfg_path.exists():
            cfg = yaml.safe_load(cfg_path.read_text()) or {}
            return cfg.get("api_base_url", "http://localhost:5000").rstrip("/")
    except Exception:
        pass
    return "http://localhost:5000"


def _load_agent_key() -> str:
    try:
        import pathlib
        key_path = pathlib.Path(__file__).parent.parent / "agent.key"
        if key_path.exists():
            return key_path.read_text().strip()
    except Exception:
        pass
    return ""


class RealTimeFIMCapability(BaseCapability):
    """Real-time File Integrity Monitoring using Watchdog with Socket.IO + HTTP fallback."""

    def __init__(self, config=None):
        self.config = config or {}
        self.observer = None
        self.sio = None
        self.agent_id = self.config.get("agent_id", "unknown-agent")
        self._backend_url = self.config.get("api_base_url", _load_backend_url())
        self._agent_key = self.config.get("agent_key", _load_agent_key())

    @property
    def capability_id(self) -> str:
        return "real_time_fim"

    @property
    def capability_name(self) -> str:
        return "Real-Time FIM"

    def _get_critical_paths(self):
        sys_platform = platform.system()
        if sys_platform == "Windows":
            candidates = _WINDOWS_PATHS
        else:
            candidates = _LINUX_PATHS
        # Also include any extra paths from config
        candidates = candidates + self.config.get("extra_watch_paths", [])
        return [p for p in candidates if os.path.exists(p) or os.path.isdir(os.path.dirname(p))]

    def collect(self) -> dict:
        monitored = [p for p in self._get_critical_paths() if os.path.exists(p)]
        is_alive = bool(self.observer and self.observer.is_alive())
        return {
            "status": "active" if is_alive else "inactive",
            "watcher_running": is_alive,
            "monitored_files": monitored,
            "watched_directories": list({os.path.dirname(p) for p in monitored}),
            "agent_id": self.agent_id,
            "platform": platform.system(),
            "socket_connected": self.sio is not None,
            "note": "start_watching() activates live event streaming",
        }

    def start_watching(self):
        existing_paths = [p for p in self._get_critical_paths() if os.path.exists(p)]

        if not existing_paths:
            logger.warning("[FIM] No critical files found to watch on this OS.")
            return

        if _HAS_SOCKETIO and hasattr(_sio_mod, "Client"):
            try:
                self.sio = _sio_mod.Client(logger=False, engineio_logger=False)
                self.sio.connect(
                    self._backend_url,
                    auth={"tenant_id": "platform-admin", "agent_id": self.agent_id},
                    wait_timeout=5,
                )
                logger.info("[FIM] Connected to backend WebSocket at %s", self._backend_url)
            except Exception as e:
                logger.warning("[FIM] WebSocket connect failed (%s) — using HTTP POST fallback", e)
                self.sio = None
        else:
            logger.warning("[FIM] python-socketio not available — using HTTP POST fallback")
            self.sio = None

        self.observer = Observer()
        handler = FileEventStreamer(self.sio, self.agent_id, self._backend_url, self._agent_key)

        watched_dirs = set()
        for path in existing_paths:
            d = os.path.dirname(path)
            if d not in watched_dirs:
                self.observer.schedule(handler, d, recursive=False)
                watched_dirs.add(d)

        self.observer.start()
        logger.info("[FIM] Started Real-time FIM on %d paths (%d dirs)", len(existing_paths), len(watched_dirs))

    def stop(self):
        if self.observer:
            self.observer.stop()
            self.observer.join()
        if self.sio:
            try:
                self.sio.disconnect()
            except Exception:
                pass

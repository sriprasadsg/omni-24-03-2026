import socket
from typing import List, Optional
from urllib.parse import urlsplit

def get_local_ip() -> str:
    """Return the machine's LAN IP address (the interface used to reach the network)."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"

def ollama_default_url(port: int = 11434) -> str:
    return f"http://{get_local_ip()}:{port}"


LOOPBACK_HOSTS = ("127.0.0.1", "localhost", "::1")


def ollama_candidate_urls(configured: Optional[str] = None, port: int = 11434) -> List[str]:
    """Where the local model may answer, in order: the configured address, then, when that address is this
    machine (or none is set), its loopback and its LAN address. Ollama listens on 127.0.0.1 unless OLLAMA_HOST
    says otherwise, so a saved LAN address of this machine would otherwise never answer. A remote address is
    tried alone."""
    lan = get_local_ip()
    if configured:
        configured = (configured if "://" in configured else f"http://{configured}").rstrip("/")
        parts = urlsplit(configured)
        if (parts.hostname or "") not in (lan, *LOOPBACK_HOSTS):
            return [configured]
        port = parts.port or port
    urls = [configured, f"http://127.0.0.1:{port}", f"http://{lan}:{port}"]
    return list(dict.fromkeys(u for u in urls if u))

import socket

def get_local_ip() -> str:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"

def ollama_default_url(port: int = 11434) -> str:
    return f"http://{get_local_ip()}:{port}"

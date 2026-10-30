"""The four service checks. Every external effect goes through an injected seam.

Seams (also used by plans 82-03 to 82-05):
    run(argv: list[str], timeout: float) -> (returncode: int, stdout: str)
    http(method: str, url: str, headers: dict, body: bytes | None, timeout: float) -> (status: int, body: bytes)
        (raises on a connection error; a non-2xx answer is returned, not raised)

MongoDB is only ever pinged (PROH-82-12): one OP_MSG ``ping`` to the admin database. The watchdog
never reads or writes MongoDB data and holds no MongoDB credentials.
"""
import json
import socket
import ssl
import struct

from . import DEFAULTS, SERVICE_ORDER, UNITS

OP_MSG = 2013  # MongoDB wire protocol opcode for OP_MSG
MAX_REPLY = 48 * 1024 * 1024


def is_active(run, unit):
    """True when ``systemctl is-active <unit>`` prints ``active``. The unit comes from UNITS only."""
    try:
        _rc, out = run(["systemctl", "is-active", unit], 5)
    except Exception:
        return False
    return (out or "").strip() == "active"


def _bson(items):
    body = b""
    for key, value in items:
        if isinstance(value, int):
            body += b"\x10" + key.encode() + b"\x00" + struct.pack("<i", value)
        else:
            text = value.encode() + b"\x00"
            body += b"\x02" + key.encode() + b"\x00" + struct.pack("<i", len(text)) + text
    return struct.pack("<i", len(body) + 5) + body + b"\x00"


def _recv_exact(sock, size):
    data = b""
    while len(data) < size:
        chunk = sock.recv(size - len(data))
        if not chunk:
            return None
        data += chunk
    return data


def mongo_ping(host="127.0.0.1", port=27017, timeout=3.0):
    """True when the server answers a ``ping`` with a well-formed OP_MSG reply (opcode 2013).

    Any well-formed reply proves the server is alive, even ``Unauthorized`` once auth is on."""
    message = struct.pack("<I", 0) + b"\x00" + _bson([("ping", 1), ("$db", "admin")])
    header = struct.pack("<iiii", 16 + len(message), 1, 0, OP_MSG)
    try:
        with socket.create_connection((host, port), timeout) as sock:
            sock.settimeout(timeout)
            sock.sendall(header + message)
            reply = _recv_exact(sock, 16)
    except (OSError, ValueError):
        return False
    if reply is None:
        return False
    length, _request_id, _response_to, opcode = struct.unpack("<iiii", reply)
    return opcode == OP_MSG and 16 < length <= MAX_REPLY


def backend_ready(http, base_url):
    """(ok, detail) from GET /api/health/ready: 200 is healthy, 503 with demo_mode is its own detail."""
    try:
        status, body = http("GET", base_url.rstrip("/") + "/api/health/ready", {}, None, 5)
    except Exception:
        return False, "unreachable"
    if status == 200:
        return True, ""
    try:
        if json.loads(body or b"{}").get("demo_mode") is True:
            return False, "demo_mode"
    except (ValueError, AttributeError):
        pass
    return False, "http_%d" % status


def nginx_probe(host="127.0.0.1", port=443, timeout=3.0):
    """True when a TLS handshake succeeds and the peer answers with any HTTP reply.

    Liveness only, loopback only: the certificate is deliberately not verified here (its expiry is
    reported by the certificate check, not by this probe)."""
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    try:
        with socket.create_connection((host, port), timeout) as raw:
            raw.settimeout(timeout)
            with context.wrap_socket(raw) as tls:
                tls.sendall(b"HEAD / HTTP/1.0\r\nHost: localhost\r\n\r\n")
                reply = tls.recv(16)
    except (OSError, ValueError):
        return False
    return reply.startswith(b"HTTP/")


def ollama_state(run, http, expected, url=DEFAULTS["ollama_url"]):
    """(ok, detail). Not expected: only ``is-active`` is ever called and the watchdog never starts it."""
    active = is_active(run, UNITS["ollama"])
    if not expected:
        return (False, "unexpected_running") if active else (True, "expected_off")
    if not active:
        return False, "inactive"
    try:
        status, _body = http("GET", url.rstrip("/") + "/", {}, None, 5)
    except Exception:
        return False, "no_reply"
    return (True, "") if status == 200 else (False, "http_%d" % status)


def check_one(sid, run, http, config):
    """(ok, detail) for one service id. ``check_all`` and the restart poll (82-03) both use it."""
    cfg = {**DEFAULTS, **config}
    if sid == "mongod":
        if not is_active(run, UNITS["mongod"]):
            return False, "inactive"
        if not mongo_ping(cfg["mongo_host"], cfg["mongo_port"]):
            return False, "no_reply"
        return True, ""
    if sid == "omni-backend":
        return backend_ready(http, cfg["backend_url"])
    if sid == "nginx":
        if not is_active(run, UNITS["nginx"]):
            return False, "inactive"
        if not nginx_probe(cfg["nginx_host"], cfg["nginx_port"]):
            return False, "no_reply"
        return True, ""
    if sid == "ollama":
        return ollama_state(run, http, bool(cfg["ollama_expected"]), cfg["ollama_url"])
    raise ValueError("unknown service id")


def check_all(run, http, config):
    """One pass over every service: a list of (service id, ok, detail) in SERVICE_ORDER."""
    results = {sid: check_one(sid, run, http, config) for sid in SERVICE_ORDER}
    return [(sid, results[sid][0], results[sid][1]) for sid in SERVICE_ORDER]

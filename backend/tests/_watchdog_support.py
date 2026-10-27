"""Shared support for the watchdog tests (Phase 82, plan 82-02).

The watchdog is a standard-library-only package under deploy/omni-watchdog. These helpers load it
and fake every external effect, so no test touches the host: ``FakeRun`` answers systemctl,
``FakeHttp`` answers the backend, ``FakeClock`` is ``now()``, and two fixtures start throwaway
servers on ephemeral loopback ports that speak just enough MongoDB wire protocol (OP_MSG) and
TLS/HTTP to be probed. Nothing here ever uses port 27017 or 443.
"""
import importlib
import json
import os
import socket
import ssl
import struct
import subprocess
import sys
import threading
import urllib.parse

import pytest

WATCHDOG_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "deploy", "omni-watchdog"))
_MODULES = ("config", "state", "checks", "services", "sync", "run")


def load_watchdog():
    """Put deploy/omni-watchdog on sys.path and return the imported ``omni_watchdog`` package."""
    if WATCHDOG_DIR not in sys.path:
        sys.path.insert(0, WATCHDOG_DIR)
    package = importlib.import_module("omni_watchdog")
    for name in _MODULES:
        if os.path.exists(os.path.join(WATCHDOG_DIR, "omni_watchdog", name + ".py")):
            importlib.import_module("omni_watchdog." + name)
    return package


class FakeRun:
    """Scripted ``run(argv, timeout) -> (returncode, stdout)``; every argv list is recorded."""

    def __init__(self, active=None):
        self.states = {"mongod.service": "active", "omni-backend.service": "active",
                       "nginx.service": "active", "ollama.service": "inactive"}
        self.states.update(active or {})
        self.calls = []
        self.other = {}

    def __call__(self, argv, timeout):
        assert isinstance(argv, list), "subprocess calls must pass an argument list"
        self.calls.append(list(argv))
        if argv[:2] == ["systemctl", "is-active"]:
            word = self.states.get(argv[2], "inactive")
            return (0 if word == "active" else 3), word + "\n"
        return self.other.get(tuple(argv), (0, ""))

    def mutating(self):
        """Calls that are anything other than ``systemctl is-active``."""
        return [c for c in self.calls if c[:2] != ["systemctl", "is-active"]]


class FakeClock:
    """``now()`` in epoch seconds that only moves when told to."""

    def __init__(self, start=1_800_000_000.0):
        self.t = float(start)

    def __call__(self):
        return self.t

    def advance(self, seconds):
        self.t += seconds
        return self.t


class FakeHttp:
    """Scripted ``http(method, url, headers, body, timeout) -> (status, bytes)``.

    ``set(method, path, *responses)``: each response is ``(status, body)`` (body bytes, str or a
    JSON-serialisable object) or an exception instance, which is raised. Responses are used in order
    and the last one repeats. A request with no route raises ConnectionRefusedError."""

    def __init__(self):
        self.routes = {}
        self.requests = []

    def set(self, method, path, *responses):
        self.routes[(method, path)] = list(responses)

    def __call__(self, method, url, headers, body, timeout):
        path = urllib.parse.urlsplit(url).path
        self.requests.append({"method": method, "url": url, "path": path, "headers": dict(headers or {}),
                              "body": body, "timeout": timeout})
        queue = self.routes.get((method, path))
        if not queue:
            raise ConnectionRefusedError("no route for %s %s" % (method, path))
        item = queue.pop(0) if len(queue) > 1 else queue[0]
        if isinstance(item, BaseException):
            raise item
        status, payload = item
        if isinstance(payload, (bytes, bytearray)):
            data = bytes(payload)
        elif isinstance(payload, str):
            data = payload.encode()
        else:
            data = json.dumps(payload).encode()
        return status, data

    def posted(self, path):
        """Parsed JSON bodies of every POST to ``path``."""
        return [json.loads(r["body"]) for r in self.requests if r["method"] == "POST" and r["path"] == path]


# --- fake servers ------------------------------------------------------------------------------

def _bson_ok():
    return struct.pack("<i", 17) + b"\x01ok\x00" + struct.pack("<d", 1.0) + b"\x00"


def mongo_reply():
    """A well-formed OP_MSG reply: header (opcode 2013), flagBits 0, one kind-0 section {ok: 1.0}."""
    body = struct.pack("<I", 0) + b"\x00" + _bson_ok()
    return struct.pack("<iiii", 16 + len(body), 2, 1, 2013) + body


class _Server:
    def __init__(self, handler):
        self.sock = socket.socket()
        self.sock.bind(("127.0.0.1", 0))
        self.sock.listen(8)
        self.sock.settimeout(0.2)
        self.port = self.sock.getsockname()[1]
        self.handler = handler
        self.stop = threading.Event()
        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.thread.start()

    def _loop(self):
        while not self.stop.is_set():
            try:
                conn, _addr = self.sock.accept()
            except socket.timeout:
                continue
            except OSError:
                return
            threading.Thread(target=self._serve, args=(conn,), daemon=True).start()

    def _serve(self, conn):
        try:
            conn.settimeout(2.0)
            self.handler(conn)
        except Exception:
            pass
        finally:
            try:
                conn.close()
            except OSError:
                pass

    def close(self):
        self.stop.set()
        self.sock.close()


def free_port():
    """A loopback port with nothing listening on it."""
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


class MongoFaker:
    """``start(mode)`` returns a port. Modes: ``ok`` (OP_MSG reply), ``close`` (hangs up), ``junk``."""

    def __init__(self):
        self.servers = []

    def start(self, mode="ok"):
        def handle(conn):
            head = conn.recv(16)
            if mode == "ok" and len(head) == 16:
                remaining = struct.unpack("<i", head[:4])[0] - 16
                while remaining > 0:
                    chunk = conn.recv(remaining)
                    if not chunk:
                        break
                    remaining -= len(chunk)
                conn.sendall(mongo_reply())
            elif mode == "junk":
                conn.sendall(b"not mongo at all, sorry")
        server = _Server(handle)
        self.servers.append(server)
        return server.port

    def close(self):
        for server in self.servers:
            server.close()


class TlsFaker:
    """``start(mode)`` returns a port. Modes: ``http`` (TLS, answers ``HTTP/1.1 301``), ``plain``
    (accepts TCP and never speaks), ``tls_junk`` (TLS handshake, then a non-HTTP reply)."""

    def __init__(self, cert, key):
        self.cert, self.key = cert, key
        self.servers = []

    def start(self, mode="http"):
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(self.cert, self.key)

        def handle(conn):
            if mode == "plain":
                threading.Event().wait(2.0)
                return
            with context.wrap_socket(conn, server_side=True) as tls:
                tls.recv(1024)
                if mode == "http":
                    tls.sendall(b"HTTP/1.1 301 Moved Permanently\r\nLocation: /\r\nContent-Length: 0\r\n\r\n")
                else:
                    tls.sendall(b"garbage reply")
        server = _Server(handle)
        self.servers.append(server)
        return server.port

    def close(self):
        for server in self.servers:
            server.close()


@pytest.fixture
def fake_mongo_server():
    faker = MongoFaker()
    yield faker
    faker.close()


@pytest.fixture(scope="session")
def _self_signed_cert(tmp_path_factory):
    directory = tmp_path_factory.mktemp("watchdog-tls")
    cert, key = str(directory / "cert.pem"), str(directory / "key.pem")
    subprocess.run(["openssl", "req", "-x509", "-newkey", "ec", "-pkeyopt", "ec_paramgen_curve:prime256v1",
                    "-nodes", "-keyout", key, "-out", cert, "-days", "2", "-subj", "/CN=localhost"],
                   check=True, capture_output=True, timeout=30)
    return cert, key


@pytest.fixture
def fake_tls_server(_self_signed_cert):
    faker = TlsFaker(*_self_signed_cert)
    yield faker
    faker.close()

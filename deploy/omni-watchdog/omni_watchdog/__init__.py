"""Omni-Agent AI platform watchdog (Phase 82).

Standard library only: this package must keep running when the backend's virtualenv, the backend
or MongoDB is broken, so it imports nothing from backend/ and nothing that needs pip.

One run (``run.run_once``) checks MongoDB, the backend, nginx and Ollama's expected state,
debounces failures, and reports to the backend through ``POST /api/internal/watchdog/sync``
(contract v1, frozen in plan 82-01). The backend renders every user-visible word; the watchdog
sends structured fields only.
"""

CONTRACT_VERSION = 1

# Services are evaluated, stored and reported in this fixed order (MongoDB first: D-09).
SERVICE_ORDER = ("mongod", "omni-backend", "nginx", "ollama")

# systemd unit names come from this constant, never from config or from a backend response.
UNITS = {
    "mongod": "mongod.service",
    "omni-backend": "omni-backend.service",
    "nginx": "nginx.service",
    "ollama": "ollama.service",
}

DISPLAY = {
    "mongod": "MongoDB",
    "omni-backend": "Backend",
    "nginx": "nginx",
    "ollama": "Ollama",
}

DEFAULTS = {
    "backend_url": "http://127.0.0.1:5000",
    "ingest_token_path": "/etc/omni-watchdog/ingest.token",
    "oncall_env_path": "/etc/omni-watchdog/oncall.env",
    "stop_file": "/etc/omni-watchdog/STOP",
    "state_dir": "/var/lib/omni-watchdog",
    "certs": ["/etc/nginx/ssl/omni.crt"],
    "extra_certs": [],
    "disk_paths": ["/", "/var/lib/mongodb"],
    "ollama_expected": False,
    # Loopback probe targets. Not read from watchdog.conf; tests point them at fake servers.
    "mongo_host": "127.0.0.1",
    "mongo_port": 27017,
    "nginx_host": "127.0.0.1",
    "nginx_port": 443,
    "ollama_url": "http://127.0.0.1:11434",
    "host": None,
}

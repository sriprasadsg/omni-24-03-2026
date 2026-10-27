"""Configuration files, read-only to the watchdog.

``/etc/omni-watchdog`` is root-owned: ``watchdog.conf`` (not secret), ``ingest.token`` and
``oncall.env`` (secrets). Missing or unreadable files never raise out of a run: the watchdog uses
the defaults, reports no on-call channel, or (no token) skips the sync and keeps its events spooled.
"""
import configparser

from . import DEFAULTS

_TRUE = ("1", "true", "yes", "on")
_FALSE = ("0", "false", "no", "off")


def _list(value):
    return [item.strip() for item in value.split(",") if item.strip()]


def _boolean(value, fallback=False):
    word = str(value).strip().lower()
    if word in _TRUE:
        return True
    if word in _FALSE:
        return False
    return fallback


def load_config(path):
    """DEFAULTS overlaid with the ``[watchdog]`` section of ``path``. Unknown keys are ignored."""
    config = {key: (list(value) if isinstance(value, list) else value) for key, value in DEFAULTS.items()}
    parser = configparser.ConfigParser(interpolation=None)
    try:
        if not parser.read(path, encoding="utf-8") or not parser.has_section("watchdog"):
            return config
    except (configparser.Error, OSError, UnicodeError):
        return config
    section = parser["watchdog"]
    url = section.get("backend_url", "").strip()
    if url.lower().startswith(("http://", "https://")):
        config["backend_url"] = url.rstrip("/")
    for key in ("ingest_token_path", "oncall_env_path", "stop_file"):
        value = section.get(key, "").strip()
        if value:
            config[key] = value
    extra = _list(section.get("extra_certs", ""))
    if extra:
        config["extra_certs"] = extra
        config["certs"] = list(DEFAULTS["certs"]) + [c for c in extra if c not in DEFAULTS["certs"]]
    disks = _list(section.get("disk_paths", ""))
    if disks:
        config["disk_paths"] = disks
    if "ollama_expected" in section:
        config["ollama_expected"] = _boolean(section.get("ollama_expected"), False)
    return config


class Oncall:
    """The on-call channel from ``oncall.env``. Secrets are attributes but never shown by repr/str."""

    __slots__ = ("type", "routing_key", "webhook_url", "webhook_format", "heartbeat_url")

    def __init__(self, type="none", routing_key="", webhook_url="", webhook_format="json", heartbeat_url=""):
        self.type = type
        self.routing_key = routing_key
        self.webhook_url = webhook_url
        self.webhook_format = webhook_format
        self.heartbeat_url = heartbeat_url

    def __repr__(self):
        return "Oncall(type=%s, routing_key=%s, webhook=%s, heartbeat=%s)" % (
            self.type, bool(self.routing_key), bool(self.webhook_url), bool(self.heartbeat_url))

    __str__ = __repr__


def load_oncall(path):
    """Parse KEY=VALUE lines (comments and blank lines ignored). Never raises; a bad file means type none."""
    values = {}
    try:
        with open(path, "r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _sep, value = line.partition("=")
                value = value.strip()
                if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
                    value = value[1:-1]
                values[key.strip()] = value
    except (OSError, UnicodeError):
        return Oncall()
    kind = values.get("ONCALL_TYPE", "none").lower()
    if kind not in ("pagerduty", "webhook", "none"):
        kind = "none"
    fmt = values.get("WEBHOOK_FORMAT", "json").lower()
    if fmt not in ("json", "slack", "teams"):
        fmt = "json"
    return Oncall(kind, values.get("PAGERDUTY_ROUTING_KEY", ""), values.get("WEBHOOK_URL", ""), fmt,
                  values.get("HEARTBEAT_URL", ""))


def read_token(path):
    """The ingest token with surrounding whitespace removed, or "" when it cannot be read."""
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return handle.read().strip()
    except (OSError, UnicodeError):
        return ""

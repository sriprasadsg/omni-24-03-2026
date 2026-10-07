"""
Agent side of uninstall protection (backend/agent_uninstall_endpoints.py).

The platform sends a salted PBKDF2 hash of this agent's uninstall code with
every heartbeat response; it is kept in config.yaml under `uninstall_protection`.
Uninstallers ask for the code, check it here (works offline), then report the
removal so the platform can record it, alert and rotate the code.

CLI (exit codes are what the Windows and Linux uninstallers act on):
    agent.py --verify-uninstall-code CODE    0 valid, 1 wrong code, 3 agent not protected yet
    agent.py --report-uninstall CODE [--method NAME]
"""
import hashlib
import hmac
import logging
from typing import Optional

logger = logging.getLogger(__name__)

KEY = "uninstall_protection"
_FIELDS = ("version", "salt", "iterations", "hash")

EXIT_VALID, EXIT_INVALID, EXIT_UNPROTECTED = 0, 1, 3


def normalize(code: str) -> str:
    return "".join(ch for ch in (code or "").upper() if ch.isalnum())


def update_from_heartbeat(cfg: dict, body: dict, save_config) -> None:
    """Store new verification data from a heartbeat response (first issue or rotation)."""
    prot = (body or {}).get(KEY) if isinstance(body, dict) else None
    if not isinstance(prot, dict) or not all(k in prot for k in _FIELDS):
        return
    prot = {k: prot[k] for k in _FIELDS}
    if cfg.get(KEY) != prot:
        cfg[KEY] = prot
        save_config(cfg)
        logger.info("Uninstall protection updated (version %s)", prot["version"])


def verify(cfg: dict, code: str) -> Optional[bool]:
    """True/False for a protected agent; None if no code has been issued yet."""
    prot = cfg.get(KEY)
    if not prot:
        return None
    digest = hashlib.pbkdf2_hmac(
        "sha256", normalize(code).encode(), bytes.fromhex(prot["salt"]), int(prot["iterations"])
    ).hex()
    return hmac.compare_digest(digest, prot["hash"])


def verify_exit_code(cfg: dict, code: str) -> int:
    result = verify(cfg, code)
    return EXIT_UNPROTECTED if result is None else (EXIT_VALID if result else EXIT_INVALID)


def report(cfg: dict, code: str, method: str) -> bool:
    """Tell the platform the agent is being removed (best effort: an offline
    endpoint still uninstalls, and the platform sees it go Offline)."""
    import requests

    agent_id, token = cfg.get("agent_id"), cfg.get("agent_token")
    if not agent_id or not token:
        return False
    url = cfg["api_base_url"].rstrip("/") + f"/api/agents/{agent_id}/uninstall-report"
    try:
        r = requests.post(url, json={"code": code or "", "method": method},
                          headers={"Authorization": f"Bearer {token}"}, timeout=10)
        return r.ok
    except Exception as e:
        logger.warning("Could not report the uninstall to the platform: %s", e)
        return False

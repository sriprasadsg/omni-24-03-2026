"""Certificate changes for agents (pin rollover).

Agents trust only the certificates in their config.yaml (server_ca_cert), so the server's
certificate cannot simply be replaced. scripts/tls_rollover.sh writes the list agents should
trust (the served certificate plus the next one) to TRUST_FILE and the rollover state to
STATE_FILE. Heartbeat replies hand that list to agents whose reported trust differs, and ask
them to test the next certificate on the probe port. Platform health shows which agents are
ready, so the switch happens only once they are. Installers ship the same list.
"""
import hashlib
import json
import logging
import os
import re
import ssl
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from cryptography import x509

logger = logging.getLogger(__name__)

TRUST_FILE = Path(os.getenv("AGENT_TRUST_BUNDLE_FILE", "/etc/omni/tls/agent-trust.pem"))
STATE_FILE = Path(os.getenv("AGENT_TLS_ROLLOVER_FILE", "/etc/omni/tls/rollover.json"))
SERVED_CERT_FILE = Path(os.getenv("AGENT_SERVED_CERT_FILE", "/etc/nginx/ssl/omni.crt"))
ACTIVE_DAYS = 7
MAX_CERTS = 8

_CERT_RE = re.compile(r"-----BEGIN CERTIFICATE-----.+?-----END CERTIFICATE-----", re.S)
_FP_RE = re.compile(r"^[0-9a-f]{64}$")
_cache: Dict[str, Any] = {"key": None, "value": None}


def split_pem(text: str) -> List[str]:
    return _CERT_RE.findall(text or "")


def fingerprint(cert_pem: str) -> str:
    """SHA-256 of the certificate's DER, lowercase hex (what agents report)."""
    return hashlib.sha256(ssl.PEM_cert_to_DER_cert(cert_pem)).hexdigest()


def _describe(cert_pem: str) -> Dict[str, Any]:
    cert = x509.load_pem_x509_certificate(cert_pem.encode("ascii"))
    return {"fingerprint": fingerprint(cert_pem), "subject": cert.subject.rfc4514_string(),
            "notAfter": cert.not_valid_after_utc.isoformat()}


def _mtime(path: Path) -> Optional[float]:
    try:
        return path.stat().st_mtime
    except OSError:
        return None


def current() -> Optional[Dict[str, Any]]:
    """The rollover in progress: {bundle, fingerprints, certs, phase, next, probePort}, or None when no
    trust list is published (agents then keep what they have)."""
    key = (_mtime(TRUST_FILE), _mtime(STATE_FILE))
    if key == _cache["key"]:
        return _cache["value"]
    value = None
    if key[0] is not None:
        try:
            certs = split_pem(TRUST_FILE.read_text(encoding="ascii"))
            if not 1 <= len(certs) <= MAX_CERTS:
                raise ValueError(f"{len(certs)} certificates")
            described = [_describe(c) for c in certs]
            state = json.loads(STATE_FILE.read_text(encoding="utf-8")) if key[1] is not None else {}
            fps = [d["fingerprint"] for d in described]
            nxt = [f for f in state.get("next") or [] if isinstance(f, str) and f in fps]
            port = state.get("probePort")
            phase = state.get("phase") if state.get("phase") in ("prepared", "switched", "finished") else "published"
            value = {"bundle": "\n".join(certs) + "\n", "fingerprints": fps, "certs": described, "phase": phase,
                     "next": nxt, "probePort": port if phase == "prepared" and isinstance(port, int) else None}
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            logger.error("Agent trust list %s is unusable (%s); agents keep their certificates", TRUST_FILE, exc)
    _cache.update(key=key, value=value)
    return value


def installer_bundle() -> Optional[str]:
    """The list new installs should trust while a rollover is published, else None."""
    ro = current()
    return ro["bundle"] if ro else None


def _reported(payload: Dict[str, Any]):
    trust = payload.get("tls_trust")
    if not isinstance(trust, list):
        return None
    return [f for f in (str(x).lower() for x in trust[:MAX_CERTS]) if _FP_RE.match(f)]


def heartbeat_reply(payload: Dict[str, Any]) -> Dict[str, Any]:
    """serverTrust for an agent that can take it (it reports tls_trust and pins something) and lacks the
    published list, or has not yet tested the next certificate; {} otherwise."""
    ro = current()
    reported = _reported(payload)
    if not ro or not reported:
        return {}
    probe = payload.get("tls_probe") if isinstance(payload.get("tls_probe"), dict) else {}
    probing = bool(ro["probePort"] and ro["next"])
    probed = sorted(probe.get("fingerprints") or []) == sorted(ro["next"])
    if set(reported) == set(ro["fingerprints"]) and (not probing or probed):
        return {}
    reply: Dict[str, Any] = {"certs": ro["bundle"]}
    if probing:
        reply.update(next=ro["next"], probePort=ro["probePort"])
    return {"serverTrust": reply}


def agent_fields(payload: Dict[str, Any], via_tls: bool = True) -> Dict[str, Any]:
    """What to store on the agent from its heartbeat (only the fields it sent). ``via_tls`` is false for a
    heartbeat that reached the backend without nginx (plain HTTP on this server): no certificate applies."""
    fields: Dict[str, Any] = {"tlsVia": "https" if via_tls else "http"}
    reported = _reported(payload)
    if reported is not None:
        fields["tlsTrust"] = reported
    probe = payload.get("tls_probe")
    if isinstance(probe, dict):
        fields["tlsProbe"] = {
            "ok": probe.get("ok") is True,
            "fingerprints": [f for f in (str(x).lower() for x in (probe.get("fingerprints") or [])[:MAX_CERTS]) if _FP_RE.match(f)],
            "error": str(probe.get("error") or "")[:300] or None,
            "status": probe.get("status") if isinstance(probe.get("status"), int) else None,
            "at": str(probe.get("at") or "")[:40],
        }
    return fields


async def record(db, agent_filter: Dict[str, Any], existing_agent: Optional[Dict[str, Any]], payload: Dict[str, Any],
                 via_tls: bool = True) -> None:
    fields = agent_fields(payload, via_tls)
    if any((existing_agent or {}).get(k) != v for k, v in fields.items()):
        await db.agents.update_one(agent_filter, {"$set": fields})


def _seen_at(agent: Dict[str, Any]) -> Optional[datetime]:
    value = agent.get("lastSeen")
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def agent_status(agent: Dict[str, Any], ro: Dict[str, Any]) -> Dict[str, str]:
    """Where one agent stands: ready, or what it still lacks."""
    trust, probe = agent.get("tlsTrust"), agent.get("tlsProbe") or {}
    if agent.get("tlsVia") == "http":
        return {"status": "ready", "detail": "Connects without TLS on the server itself; no certificate applies"}
    if trust is None:
        return {"status": "update_agent", "detail": "This agent version cannot take a certificate change; update it"}
    if not trust:
        return {"status": "not_pinned", "detail": "The agent pins no certificate (installed before pinning); reinstall it"}
    if not set(ro["next"] or ro["fingerprints"]) <= set(trust):
        return {"status": "waiting", "detail": "It has not taken the new certificate list yet"}
    if ro["probePort"] and ro["next"]:
        if sorted(probe.get("fingerprints") or []) != sorted(ro["next"]):
            return {"status": "probe_pending", "detail": "It has not tested the next certificate yet"}
        if not probe.get("ok"):
            return {"status": "probe_failed", "detail": probe.get("error") or "The test of the next certificate failed"}
    return {"status": "ready", "detail": ""}


async def readiness(db, now: Optional[datetime] = None) -> Dict[str, Any]:
    """Platform-wide: the published list and how many agents seen in the last ACTIVE_DAYS are ready."""
    now = now or datetime.now(timezone.utc)
    served = None
    try:
        served = _describe(split_pem(SERVED_CERT_FILE.read_text(encoding="ascii"))[0])
    except (OSError, IndexError, ValueError):
        pass
    ro = current()
    out: Dict[str, Any] = {"phase": ro["phase"] if ro else "none", "served": served,
                           "trusted": ro["certs"] if ro else [], "next": ro["next"] if ro else [],
                           "probePort": ro["probePort"] if ro else None, "counts": {}, "notReady": []}
    if not ro:
        return out
    raw = getattr(db, "_db", db)  # platform view: every organization's agents
    cursor = raw.agents.find({}, {"_id": 0, "id": 1, "hostname": 1, "tenantId": 1, "platform": 1, "version": 1,
                                  "lastSeen": 1, "tlsTrust": 1, "tlsProbe": 1, "tlsVia": 1})
    counts: Dict[str, int] = {}
    for agent in await cursor.to_list(length=10000):
        seen = _seen_at(agent)
        if not seen or now - seen > timedelta(days=ACTIVE_DAYS):
            continue
        st = agent_status(agent, ro)
        counts[st["status"]] = counts.get(st["status"], 0) + 1
        if agent.get("tlsVia") == "http":
            counts["withoutTls"] = counts.get("withoutTls", 0) + 1
        if st["status"] != "ready" and len(out["notReady"]) < 200:
            out["notReady"].append({"hostname": agent.get("hostname"), "tenantId": agent.get("tenantId"),
                                    "platform": agent.get("platform"), "version": agent.get("version"),
                                    "lastSeen": agent.get("lastSeen"), **st})
    out["counts"] = {"active": sum(v for k, v in counts.items() if k != "withoutTls"), **counts}
    return out

"""Which optional integrations are configured, and a live test of each (Wave 6, Platform health).

Only names, the environment variable that configures each and a configured yes/no leave this module, never a value.
A test makes one harmless call with the configured key (a VirusTotal hash lookup, an NVD single-result query, a
Stripe balance read, a ThreatFox one-day query, a Gemini model list, a Slack message, an email to the person who
asked) and reports ok plus a short reason built here (an HTTP status, never the provider's body, which can echo
the key). Keys stored in the platform's own settings (VirusTotal, NVD on Security Intelligence) count too.
"""
import asyncio
import os
import smtplib
from email.message import EmailMessage
from typing import Any, Dict, List, Optional

import httpx

import self_hosted

TIMEOUT = 15.0
EICAR_SHA256 = "275a021bbfb6489e54d471899f7db9d1663fc695ec2fe2a2c4538aabf651fd0f"

INTEGRATIONS: Dict[str, Dict[str, Any]] = {
    "smtp": {"label": "Email (SMTP)", "env": ["SMTP_HOST", "SMTP_USER", "SMTP_PASS"], "use": "Email alerts, reports, password reset"},
    "slack": {"label": "Slack", "env": ["SLACK_WEBHOOK_URL"], "use": "Slack alerts"},
    "virustotal": {"label": "VirusTotal", "env": ["VIRUSTOTAL_API_KEY"], "use": "File and hash scanning", "setting": "virustotal"},
    "nvd": {"label": "NVD", "env": ["NVD_API_KEY"], "use": "Faster CVE sync (works without a key, throttled)", "setting": "nvd"},
    "abusech": {"label": "abuse.ch ThreatFox", "env": ["ABUSECH_AUTH_KEY"], "use": "Threat-intel indicators"},
    "stripe": {"label": "Stripe", "env": ["STRIPE_SECRET_KEY"], "use": "Payments"},
    "gemini": {"label": "Google Gemini", "env": ["GEMINI_API_KEY"], "use": "Optional cloud AI (the local model needs no key)"},
}


def _env(name: str) -> str:
    return (os.getenv(name) or "").strip()


async def _setting_key(db, provider: Optional[str]) -> str:
    if not provider or db is None:
        return ""
    raw = getattr(db, "_db", db)
    doc = await raw.security_intel_config.find_one({"provider": provider}, {"_id": 0, "api_key": 1}) or {}
    return str(doc.get("api_key") or "").strip()


async def _key(db, name: str) -> str:
    spec = INTEGRATIONS[name]
    return _env(spec["env"][0]) or await _setting_key(db, spec.get("setting"))


async def status(db) -> List[Dict[str, Any]]:
    out = []
    for name, spec in INTEGRATIONS.items():
        present = [v for v in spec["env"] if _env(v)]
        configured = bool(await _key(db, name)) if name != "smtp" else len(present) == len(spec["env"])
        out.append({"name": name, "label": spec["label"], "use": spec["use"], "envVars": spec["env"],
                    "configured": configured, "missing": [v for v in spec["env"] if v not in present] if not configured else []})
    return out


def _http(r: httpx.Response, ok_codes=(200,)) -> Dict[str, Any]:
    if r.status_code in ok_codes:
        return {"ok": True, "detail": f"HTTP {r.status_code}"}
    reason = {401: "the key was refused", 403: "the key lacks access", 429: "rate limited, try later"}.get(r.status_code, "unexpected answer")
    return {"ok": False, "detail": f"HTTP {r.status_code}: {reason}"}


def _send_mail(to: str) -> None:
    host, port = _env("SMTP_HOST"), int(_env("SMTP_PORT") or 587)
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"] = _env("SMTP_FROM") or _env("SMTP_USER"), to, "Omni-Agent AI: test email"
    msg.set_content("This is a test from Platform health. If it arrived, email alerts and password reset can be sent.")
    with smtplib.SMTP(host, port, timeout=TIMEOUT) as s:
        if port != 25:
            s.starttls(context=self_hosted.ssl_context(f"smtp://{host}:{port}"))
        s.login(_env("SMTP_USER"), _env("SMTP_PASS"))
        s.send_message(msg)


async def test(db, name: str, recipient: Optional[str]) -> Dict[str, Any]:
    """One live check of a configured integration: {"ok", "detail"}; never raises for a provider error."""
    if name not in INTEGRATIONS:
        raise KeyError(name)
    key = await _key(db, name) if name != "smtp" else ""
    if name != "smtp" and not key:
        return {"ok": False, "detail": f"Not configured: set {INTEGRATIONS[name]['env'][0]}"}
    try:
        if name == "smtp":
            if not all(_env(v) for v in INTEGRATIONS["smtp"]["env"]):
                return {"ok": False, "detail": "Not configured: set SMTP_HOST, SMTP_USER and SMTP_PASS"}
            if not recipient or "@" not in recipient:
                return {"ok": False, "detail": "Your account has no email address to send the test to"}
            await asyncio.to_thread(_send_mail, recipient)
            return {"ok": True, "detail": f"Test email sent to {recipient}"}
        async with httpx.AsyncClient(timeout=TIMEOUT, follow_redirects=False) as c:
            if name == "slack":
                r = await c.post(key, json={"text": "Omni-Agent AI: test message from Platform health."})
                return _http(r)
            if name == "virustotal":
                return _http(await c.get(f"https://www.virustotal.com/api/v3/files/{EICAR_SHA256}", headers={"x-apikey": key}), (200, 404))
            if name == "nvd":
                return _http(await c.get("https://services.nvd.nist.gov/rest/json/cves/2.0", params={"resultsPerPage": 1}, headers={"apiKey": key}))
            if name == "abusech":
                r = await c.post("https://threatfox-api.abuse.ch/api/v1/", json={"query": "get_iocs", "days": 1}, headers={"Auth-Key": key})
                if r.status_code == 200 and str((r.json() or {}).get("query_status")) in ("ok", "no_result"):
                    return {"ok": True, "detail": "HTTP 200"}
                return _http(r) if r.status_code != 200 else {"ok": False, "detail": "HTTP 200: the key was refused"}
            if name == "stripe":
                return _http(await c.get("https://api.stripe.com/v1/balance", auth=(key, "")))
            if name == "gemini":
                return _http(await c.get("https://generativelanguage.googleapis.com/v1beta/models", params={"pageSize": 1},
                                         headers={"x-goog-api-key": key}))
    except (httpx.HTTPError, OSError, smtplib.SMTPException, ValueError) as exc:
        return {"ok": False, "detail": f"Could not reach it: {type(exc).__name__}"}
    return {"ok": False, "detail": "No test for this integration"}

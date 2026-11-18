"""AI triage of a SOC alert on the platform's own local model (Ollama), never an outside service.

``triage`` sends a trimmed description of the alert (type, severity, title, details, repeats, MITRE
techniques, the program or file it names) with user names in paths and e-mail addresses replaced, after
the platform's AI guardrail scan, and stores the answer on the alert as ``aiTriage``: a short summary,
the likely cause, how serious it looks and why, and next steps. Steps are ids of the console's own
controls (STEP_IDS); anything else the model writes is dropped, and nothing here runs an action. The
answer is advice: the console labels it as an AI suggestion to check before acting.

New critical alerts are triaged automatically in the background (``schedule_auto``), one at a time
because the model shares this server's CPU (about 25 s each); SOC_AUTO_TRIAGE=0 turns that off.
"""
import asyncio
import json
import logging
import os
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import httpx

from database import get_database
from local_ip import ollama_default_url
from soc_service import TECHNIQUE_NAMES, scope_filter, view

logger = logging.getLogger(__name__)

MODEL = os.getenv("SOC_TRIAGE_MODEL", "llama3.2:3b")
TIMEOUT_SECONDS = 120
STEP_IDS = ("acknowledge", "close_false_positive", "close_benign", "isolate_host", "quarantine_file", "block_ip",
            "open_case", "approve_process", "investigate")
SERIOUSNESS = ("low", "medium", "high", "critical")
_ONE_AT_A_TIME = asyncio.Semaphore(1)
_running: set = set()

_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
_WIN_USER = re.compile(r"(?i)([A-Z]:\\Users\\)[^\\'\"]+")
_NIX_USER = re.compile(r"(/home/|/Users/)[^/'\"]+")


class TriageError(ValueError):
    def __init__(self, message: str, status: int = 502):
        super().__init__(message)
        self.status = status


def redact(text: Any) -> str:
    """User names in home-folder paths and e-mail addresses replaced; nothing else is changed."""
    text = _EMAIL.sub("<email>", str(text or ""))
    text = _WIN_USER.sub(r"\1<user>", text)
    return _NIX_USER.sub(r"\1<user>", text)


def prompt_for(alert: Dict[str, Any], os_name: Optional[str] = None) -> str:
    """The question for the model, from a viewed alert (soc_service.view)."""
    ev = alert.get("evidence") or {}
    facts = [
        f"Detection type: {alert['typeLabel']}",
        f"Severity given by the detection: {alert['severity']}",
        f"Title: {redact(alert['title'])[:200]}",
        f"Details: {redact(alert.get('description'))[:600]}",
        f"Seen {alert.get('occurrences', 1)} time(s), first {alert.get('createdAt')}, last {alert.get('lastSeenAt')}",
    ]
    if os_name:
        facts.append(f"Endpoint operating system: {os_name}")
    if alert.get("mitre"):
        facts.append("MITRE ATT&CK: " + ", ".join(f"{t} {TECHNIQUE_NAMES.get(t, ('', ''))[0]}".strip() for t in alert["mitre"]))
    for key in ("process", "exe", "path", "rule", "type"):
        if isinstance(ev.get(key), (str, int)):
            facts.append(f"{key}: {redact(ev[key])[:200]}")
    return (
        "You help a security analyst triage one alert from an endpoint agent. Be concrete and brief. "
        "Call it a likely false positive only when the evidence itself points that way (for example the "
        "flagged file sits in a software build folder); otherwise do not assume one.\n\n"
        + "\n".join(facts)
        + "\n\nAnswer only JSON with these keys: summary (at most 2 sentences), likely_cause (1 sentence), "
        f"seriousness (one of {', '.join(SERIOUSNESS)}), why (1-2 sentences), next_steps (1 to 4 ids from: "
        f"{', '.join(STEP_IDS)}; approve_process only for an AI process the organization uses on purpose)."
    )


def _sentence(value: Any, limit: int) -> str:
    if isinstance(value, list):
        value = " ".join(str(v) for v in value if v)
    return " ".join(str(value or "").split())[:limit]


def parse(raw: str) -> Dict[str, Any]:
    """The model's JSON, checked: known keys, short texts, a known seriousness, known step ids only."""
    try:
        data = json.loads(raw)
    except (TypeError, ValueError):
        match = re.search(r"\{.*\}", str(raw or ""), re.S)
        try:
            data = json.loads(match.group(0)) if match else None
        except ValueError:
            data = None
    if not isinstance(data, dict) or not _sentence(data.get("summary"), 10):
        raise TriageError("The AI model did not give a usable answer; try again.")
    seriousness = str(data.get("seriousness") or "").strip().lower()
    steps: List[str] = []
    for step in data.get("next_steps") if isinstance(data.get("next_steps"), list) else []:
        step = str(step).strip().lower()
        if step in STEP_IDS and step not in steps:
            steps.append(step)
    return {
        "summary": _sentence(data.get("summary"), 600),
        "likelyCause": _sentence(data.get("likely_cause"), 300),
        "seriousness": seriousness if seriousness in SERIOUSNESS else None,
        "why": _sentence(data.get("why"), 500),
        "nextSteps": steps[:4],
    }


def _ollama_urls() -> List[str]:
    """Where the local model may listen: OLLAMA_URL as the platform sets it, this machine, its LAN address."""
    urls = [os.getenv("OLLAMA_URL"), "http://127.0.0.1:11434", ollama_default_url()]
    return list(dict.fromkeys(u.rstrip("/") for u in urls if u))


async def _generate(prompt: str) -> str:
    last: Exception = httpx.ConnectError("no Ollama address")
    async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS) as client:
        for url in _ollama_urls():
            try:
                resp = await client.post(f"{url}/api/generate", json={
                    "model": MODEL, "prompt": prompt, "stream": False, "format": "json",
                    "options": {"temperature": 0.2, "num_predict": 400},
                })
            except httpx.ConnectError as e:  # not listening there: try the next address
                last = e
                continue
            resp.raise_for_status()
            return resp.json().get("response", "")
    raise last


async def triage(scope: Optional[str], alert_id: str, who: str) -> Dict[str, Any]:
    """Ask the local model about one alert and store its answer on the alert."""
    db = get_database()
    doc = await db.security_alerts.find_one({"id": alert_id, **scope_filter(scope)}, {"_id": 0})
    if not doc:
        raise TriageError("Alert not found", 404)
    agent = await db.agents.find_one({"id": doc.get("agent_id")}, {"_id": 0, "platform": 1, "meta.os": 1}) if doc.get("agent_id") else None
    os_name = ((agent or {}).get("meta") or {}).get("os") or (agent or {}).get("platform")
    prompt = prompt_for(view(doc), os_name)
    from guardrail_service import guardrail_service
    scan = await guardrail_service.scan_and_log(prompt, "soc_triage_input")
    if not scan.passed:
        raise TriageError("The AI guardrail stopped this alert's text from being sent: " + ", ".join(scan.findings), 422)
    async with _ONE_AT_A_TIME:
        try:
            raw = await _generate(prompt)
        except (httpx.HTTPError, OSError) as e:
            logger.warning("SOC triage: local model unavailable: %s", e)
            raise TriageError("The local AI model (Ollama) is not answering; try again later.", 503)
    result = {**parse(raw), "model": MODEL, "at": datetime.now(timezone.utc).isoformat(), "by": who}
    if doc.get("type") != "shadow_ai_process":  # approval is only for AI processes
        result["nextSteps"] = [s for s in result["nextSteps"] if s != "approve_process"]
    await db.security_alerts.update_one({"id": alert_id, **scope_filter(scope)}, {"$set": {"aiTriage": result}})
    return result


def schedule_auto(alert: Dict[str, Any]) -> None:
    """Triage a new critical alert in the background; never raises into the writer."""
    if os.getenv("SOC_AUTO_TRIAGE", "1") == "0" or alert.get("severity") != "critical" or not alert.get("id"):
        return
    if alert["id"] in _running:
        return

    async def _run() -> None:
        _running.add(alert["id"])
        try:
            await triage(alert.get("tenantId"), alert["id"], "automatic (critical alert)")
        except Exception as e:  # advice only: a failure leaves the alert as it was
            logger.info("SOC auto-triage of %s skipped: %s", alert["id"], e)
        finally:
            _running.discard(alert["id"])

    try:
        asyncio.get_running_loop().create_task(_run())
    except RuntimeError:
        pass

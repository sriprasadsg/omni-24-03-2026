"""Every user-visible string for platform-health rows (Phase 82, HEAL-07).

The watchdog sends structured fields only (a closed event kind and a closed set of parameters);
this module turns them into the words the Super Admin reads in the platform Activity list, so a
compromised or buggy watchdog can never put free text on screen (82-RESEARCH Pattern 3). The copy
is the UI-SPEC section 8 vocabulary. ACTV-08 scans this file against
shared/autonomous-ops-banned-terms.json: the feature is called Autonomous Ops, and the terms
listed there are never used. A missing value renders as an em dash.
"""
import math
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

DASH = "—"

# What the test-alert route says when it refuses (409): no watchdog has ever reported, or it has gone quiet.
API_DETAIL = {
    "watchdog_not_installed": "Install the watchdog first.",
    "watchdog_silent": "The watchdog is silent, so a test can't be sent until it reports again.",
}

SERVICE_NAMES = {"mongod": "MongoDB", "omni-backend": "Backend", "nginx": "nginx", "ollama": "Ollama"}

# The rule ids shown in font-mono under the reason text.
RULE_IDS = (
    "service-down", "service-recovered", "restart-budget", "service-unexpected",
    "cert-expiry-30d", "cert-expiry-14d", "cert-expiry-7d", "cert-expiry-1d", "cert-unreadable",
    "disk-80", "disk-90", "disk-95", "disk-forecast-14d", "disk-forecast-7d", "disk-forecast-1d",
    "oncall-page", "oncall-test", "watchdog-heartbeat", "state-reset", "retention-run", "retention-confirm",
)

# Mirrors CERT_LADDER in deploy/omni-watchdog/omni_watchdog/warnings.py, which this module may not import:
# (days at most, rule id). The rule is compared on the unrounded daysLeft the watchdog sends, because the rung
# is shared by 14 and 30 days and rounding 1.4 to 1 would name a threshold that did not fire.
_CERT_LADDER = ((1, "cert-expiry-1d"), (7, "cert-expiry-7d"), (14, "cert-expiry-14d"))
_DISK_RULES = ("disk-80", "disk-90", "disk-95")
_FORECAST_RULES = ("disk-forecast-14d", "disk-forecast-7d", "disk-forecast-1d")
_FORECAST_DAYS = (14, 7, 1)

# What ran (the event label), keyed by event kind. "{service}" is filled in by render().
EVENT_LABELS = {
    "service_down": "Service check",
    "service_recovered": "Service check",
    "restart": "Restart {service}",
    "restart_skipped": "Restart {service}",
    "gave_up": "Restart {service}",
    "budget_rearmed": "Restart {service}",
    "unexpected_running": "Service check",
    "cert_warning": "Certificate warning",
    "disk_warning": "Disk warning",
    "disk_forecast": "Disk forecast",
    "page_sent": "On-call page",
    "page_resolved": "On-call page",
    "page_failed": "On-call page",
    "test_alert": "Test alert",
    "state_reset": "Watchdog",
    "watchdog_silent": "Watchdog",
    "watchdog_back": "Watchdog",
    "retention_run": "Retention run",
    "retention_confirmed": "Retention confirmed",
}

_BACKEND_SOURCE = "Platform"
_SOURCES = {"watchdog_silent": _BACKEND_SOURCE, "watchdog_back": _BACKEND_SOURCE, "retention_run": _BACKEND_SOURCE,
            "retention_confirmed": "Super Admin"}


def _text(value: Any) -> str:
    return str(value) if value not in (None, "") else DASH


def _finite(value: Any) -> Optional[Any]:
    """The value when it is a real, finite number (an int, or a float that is not infinity or NaN), else None.
    ``math.isfinite`` runs on floats only: on an integer beyond the float range it raises OverflowError."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def _num(value: Any) -> Optional[int]:
    n = _finite(value)
    return None if n is None else int(round(n))


def _count(value: Any) -> str:
    n = _num(value)
    return f"{n:,}" if n is not None else DASH


def _rung(params: Dict[str, Any]) -> int:
    n = _num(params.get("rung"))
    return n if n is not None and n > 0 else 1


def service_name(target: Any) -> str:
    return SERVICE_NAMES.get(target) or _text(target)


def _date(value: Any) -> str:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return DASH
    return f"{parsed.strftime('%b')} {parsed.day}, {parsed.year}"


def _clock(at: Optional[datetime]) -> str:
    return at.strftime("%H:%M") if isinstance(at, datetime) else DASH


def _channel(value: Any) -> str:
    return {"pagerduty": "PagerDuty", "webhook": "webhook"}.get(value, _text(value))


def _ok(params: Dict[str, Any], default: bool = False) -> bool:
    value = params.get("ok")
    return value if isinstance(value, bool) else default


def chip_for(kind: str, params: Optional[Dict[str, Any]] = None) -> str:
    """The Activity chip of a platform-health row: healthy, notice, warning, critical, paged or skipped."""
    params = params or {}
    if kind in ("service_down", "gave_up", "page_failed", "watchdog_silent"):
        return "critical"
    if kind in ("service_recovered", "budget_rearmed", "watchdog_back"):
        return "healthy"
    if kind in ("restart", "test_alert"):
        return "healthy" if _ok(params) else "critical"
    if kind == "retention_run":
        return "healthy" if _ok(params, True) else "critical"
    if kind == "restart_skipped":
        return "skipped"
    if kind in ("page_sent", "page_resolved"):
        return "paged"
    if kind in ("unexpected_running", "retention_confirmed"):
        return "notice"
    if kind == "state_reset":
        return "warning"
    if kind in ("cert_warning", "disk_warning", "disk_forecast"):
        rung = _rung(params)
        return "notice" if rung <= 1 else "warning" if rung == 2 else "critical"
    return "notice"


def _cert_rule(params: Dict[str, Any]) -> str:
    """The certificate threshold that fired, from daysLeft; a certificate with no readable expiry has its own rule."""
    days = _finite(params.get("daysLeft"))
    if days is None:
        return "cert-unreadable"
    for limit, rule in _CERT_LADDER:
        if days <= limit:
            return rule
    return "cert-expiry-30d"


def _rule_id(kind: str, params: Dict[str, Any]) -> Optional[str]:
    rung = _rung(params)
    if kind == "cert_warning":
        return _cert_rule(params)
    if kind == "disk_warning":
        return _DISK_RULES[min(rung, len(_DISK_RULES)) - 1]
    if kind == "disk_forecast":
        return _FORECAST_RULES[min(rung, len(_FORECAST_RULES)) - 1]
    return {
        "service_down": "service-down", "service_recovered": "service-recovered",
        "restart": "restart-budget", "restart_skipped": "restart-budget", "gave_up": "restart-budget",
        "budget_rearmed": "restart-budget", "unexpected_running": "service-unexpected",
        "page_sent": "oncall-page", "page_resolved": "oncall-page", "page_failed": "oncall-page",
        "test_alert": "oncall-test", "state_reset": "state-reset", "watchdog_silent": "watchdog-heartbeat",
        "watchdog_back": "watchdog-heartbeat", "retention_run": "retention-run",
        "retention_confirmed": "retention-confirm",
    }.get(kind)


def _reason_and_result(kind: str, p: Dict[str, Any], at: Optional[datetime]) -> tuple:
    svc = service_name(p.get("target"))
    if kind == "service_down":
        return "Failed 2 checks in a row.", f"{svc} is down."
    if kind == "service_recovered":
        return "Check passed again.", f"{svc} is healthy."
    if kind == "restart":
        k, secs = _num(p.get("attempt")), _num(p.get("seconds"))
        step = f"Restart {k if k is not None else DASH} of 3: "
        if _ok(p):
            return f"{svc} was down.", step + f"restarted, healthy after {secs if secs is not None else DASH} s."
        return f"{svc} was down.", step + f"failed: {_text(p.get('error'))}."
    if kind == "restart_skipped":
        return "Automatic actions are stopped.", "Skipped. Restarts resume when the stop is cleared."
    if kind == "gave_up":
        return "Restart budget used up: 3 restarts in 30 minutes.", "Not restarting again. On-call paged."
    if kind == "budget_rearmed":
        return "Healthy for 1 hour.", "Restart budget is available again."
    if kind == "unexpected_running":
        return f"{svc} is running but is expected to be off.", "Left as it is. The watchdog never starts or stops it."
    if kind == "cert_warning":
        days = _num(p.get("daysLeft"))
        if days is None:
            return "Can't read this file.", f"{_text(p.get('target'))} could not be read, so its expiry date is unknown."
        if days < 0:
            reason = f"Expired {-days} days ago."
        elif days == 0:
            reason = "Expires today."
        else:
            reason = f"Expires in {days} days."
        verb = "expired" if days < 0 else "expires"
        return reason, (f"{_text(p.get('target'))} {verb} {_date(p.get('notAfter'))}. "
                        "Replacing a pinned certificate needs an agent update.")
    if kind == "disk_warning":
        used = _num(p.get("usedPct"))
        pct = f"{used}%" if used is not None else DASH
        return f"{pct} used.", f"{_text(p.get('target'))} is {pct} full. Nothing is deleted automatically."
    if kind == "disk_forecast":
        window = _FORECAST_DAYS[min(_rung(p), len(_FORECAST_DAYS)) - 1]
        d = _num(p.get("forecastDays"))
        return (f"Forecast to be full within {window} days.",
                f"At the last 7 days of growth, {_text(p.get('target'))} fills in about {d if d is not None else DASH} days.")
    if kind == "page_sent":
        return _text(p.get("incident")), f"Page sent to {_channel(p.get('channel'))}."
    if kind == "page_resolved":
        return _text(p.get("incident")), "Marked resolved."
    if kind == "page_failed":
        return _text(p.get("incident")), f"Not delivered: {_text(p.get('error'))}."
    if kind == "test_alert":
        sent = f"Sent at {_clock(at)}, "
        result = sent + "delivered." if _ok(p) else sent + f"not delivered: {_text(p.get('error'))}"
        return f"Requested by {_text(p.get('by'))}.", result
    if kind == "state_reset":
        return "The saved watchdog state could not be read.", "Started again from a clean state."
    if kind == "watchdog_silent":
        minutes = _num(p.get("minutes"))
        seen = _clock(at - timedelta(minutes=minutes)) if isinstance(at, datetime) and minutes is not None else DASH
        return f"No heartbeat for {minutes if minutes is not None else DASH} minutes.", f"Last seen {seen}."
    if kind == "watchdog_back":
        return "Heartbeat resumed.", "Reporting again."
    if kind == "retention_run":
        n, t = _count(p.get("records")), _count(p.get("tenants"))
        if p.get("mode") == "deleted":
            return "Scheduled nightly run.", f"Deleted {n} records across {t} organizations."
        return "Scheduled nightly run.", f"Counted {n} records across {t} organizations. Deleted nothing."
    if kind == "retention_confirmed":
        n, t = _count(p.get("records")), _count(p.get("tenants"))
        return (f"Confirmed by {_text(p.get('by'))}.",
                f"{n} records across {t} organizations will be deleted from the next nightly run.")
    return DASH, DASH


def render(kind: str, params: Optional[Dict[str, Any]], host: Optional[str], at: Optional[datetime] = None) -> Dict[str, Any]:
    """The words of one platform-health row: {actionLabel, source, reasonText, ruleId, host, target,
    resultText}. ``at`` (the row time) feeds the HH:MM in the test-alert and silent-watchdog lines."""
    p = params if isinstance(params, dict) else {}
    reason, result = _reason_and_result(kind, p, at)
    label = EVENT_LABELS.get(kind, "Platform health").format(service=service_name(p.get("target")))
    target = p.get("target")
    return {"actionLabel": label, "source": _SOURCES.get(kind, "Watchdog"), "reasonText": reason,
            "ruleId": _rule_id(kind, p), "host": host or None, "target": str(target) if target else None,
            "resultText": result}

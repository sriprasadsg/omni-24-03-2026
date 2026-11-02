"""The suggestion stage of the sweep (Phase 83, RESP-01, D-07 / D-08, UI-SPEC section 5 and R14).

A computer can report hundreds of vulnerabilities, so a finding is never a row of its own. For each computer
and kind there is at most ONE open ``suggested`` row, grouped by the server:

* ``vulnerability`` (D-07): every open vulnerability an agent reported, with or without a CVE. The row holds
  the count, the highest severity and at most 10 items (highest severity first, then the id). Nothing is
  patched and there is no approval card: the row is ``suggestionOnly`` and links to patching.
* ``file_change`` (D-08): paths with a ``Changed`` file-integrity event in the last 24 hours (Added and
  Removed are not counted, as in the legacy filter). A path whose hash is flagged as an origin for that
  computer (an ``autonomy_signals`` file signal) is left out: it takes the quarantine path. The change itself
  is never an origin: nothing here writes a signal's origins, only the one refusal memory described below.

A newer sweep updates the row's count, items and time in place (``ledger.refresh_suggestion``: no state
change, so no audit event, and ``createdAt`` becomes the time of the latest sweep). A tick that learned
nothing writes nothing, except that the row's expiry is extended once under 12 hours remain, so the 24 hour
approval clock never ends a suggestion whose findings are still there. When the findings are gone the row
ends ``expired`` with reasonCode ``superseded``.

A suggestion depends on no agent action, so there is no dormancy check. The gate still runs for a new row:
it refuses a never-touch computer (one refused row, remembered for 24 hours on the computer's signal memory)
and records a simulation in shadow (at most one per computer and kind in 24 hours).

Agent-supplied text (CVE ids, package names, paths) is cut to a length and stripped of control characters;
the browser renders it as text (T-83-57). Only structured fields are read; no model is called (PROH-83-01).
Raw Mongo handle with an explicit tenantId; the ambient tenant ContextVar is never used.
"""
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from . import APPROVAL_TTL, gate, ledger, response_dispatch, response_messages as rm, signals, sweep_memory
from .response_views import ID_CAP, ITEM_CAP
from .scope import raw
from .settings import TenantSettings

logger = logging.getLogger(__name__)

RULE_IDS = {"vulnerability": "sweep:suggest_vulnerability", "file_change": "sweep:suggest_file_change"}
_COMMANDS = {"vulnerability": "upgrade_software", "file_change": "restore_file"}
FILE_WINDOW = timedelta(hours=24)         # a changed file counts for this long after the event
FILE_EVENT_LIMIT = 2000
PATH_CAP = 300
_HASH_CHUNK = 500
EXTEND_UNDER = timedelta(hours=12)       # the expiry is pushed out only when less than this remains
VULNERABILITY_LIMIT = 5000               # T-83-56: one pass never reads more than this many findings
PACKAGE_CAP = 200
_SEVERITY_RANK = {"critical": 4, "high": 3, "medium": 2, "low": 1}
_CONTROL = re.compile(r"[\x00-\x1f\x7f]+")


@dataclass
class Group:
    """What one computer reports for one kind: the whole count, the highest severity and the best 10 items."""
    agent: Dict[str, Any]
    count: int = 0
    severity: Optional[str] = None
    rank: int = 0
    found: List[tuple] = field(default_factory=list)       # (sort key, item)

    def add(self, key: tuple, item: Dict[str, str], severity_text: Optional[str] = None, rank: int = 0) -> None:
        self.count += 1
        self.found.append((key, item))
        if rank > self.rank:
            self.rank, self.severity = rank, severity_text
        if len(self.found) > ITEM_CAP * 4:                  # keep the memory of a noisy host small
            self.found = sorted(self.found, key=lambda f: f[0])[:ITEM_CAP]

    def payload(self, kind: str) -> Dict[str, Any]:
        items = [item for _, item in sorted(self.found, key=lambda f: f[0])[:ITEM_CAP]]
        body: Dict[str, Any] = {"kind": kind, "count": self.count, "items": items}
        if kind == "vulnerability":
            body["severity"] = self.severity
        return body


def _clean(value: Any, cap: int) -> Optional[str]:
    """A bounded one-line text from agent data, or None when nothing readable is left."""
    if not isinstance(value, str):
        return None
    text = _CONTROL.sub(" ", value).strip()[:cap].strip()
    return text or None


def _aware(value: Any) -> Any:
    return value.replace(tzinfo=timezone.utc) if isinstance(value, datetime) and value.tzinfo is None else value


# ---------------------------------------------------------------- what the computers report

async def _vulnerability_groups(db, tenant_id: str, index) -> Dict[str, Group]:
    """Open agent vulnerabilities grouped by the one computer each names. An ambiguous hostname is skipped."""
    found = raw(db).vulnerabilities.find(
        {"tenantId": tenant_id, "source": "agent", "status": "Open"},
        {"_id": 0, "agentId": 1, "cveId": 1, "cve_id": 1, "severity": 1, "package": 1}
    ).sort("_id", 1).limit(VULNERABILITY_LIMIT)
    groups: Dict[str, Group] = {}
    total = 0
    async for doc in found:
        total += 1
        agent = signals.resolve(index, doc.get("agentId"))
        if agent is None:
            continue
        severity = _clean(doc.get("severity"), 32)
        rank = _SEVERITY_RANK.get((severity or "").casefold(), 0)
        item = {}
        cve = _clean(doc.get("cveId") or doc.get("cve_id"), ID_CAP)
        package = _clean(doc.get("package"), PACKAGE_CAP)
        if cve:
            item["cve"] = cve
        if package:
            item["package"] = package
        if not item:
            item = {"package": "unknown"}
        group = groups.setdefault(agent["id"], Group(agent))
        group.add((-rank, cve or "", package or ""), item, severity.title() if severity else None, rank)
    if total >= VULNERABILITY_LIMIT:
        logger.warning("autonomous_ops: tenant %s has at least %d open vulnerabilities, counting the first %d",
                       tenant_id, VULNERABILITY_LIMIT, VULNERABILITY_LIMIT)
    return groups


def _hashes_of(doc: Dict[str, Any]) -> List[str]:
    return [h for h in (signals.sha256_of(doc.get("hash_after")), signals.sha256_of(doc.get("sha256"))) if h]


async def _flagged(db, tenant_id: str, hashes: List[str]) -> set:
    """(agent id, sha256) of every file signal of this tenant on one of these hashes."""
    out = set()
    ordered = sorted(set(hashes))
    for i in range(0, len(ordered), _HASH_CHUNK):
        found = raw(db).autonomy_signals.find(
            {"tenantId": tenant_id, "kind": "file", "indicator": {"$in": ordered[i:i + _HASH_CHUNK]}},
            {"_id": 0, "agentId": 1, "indicator": 1})
        out.update([(doc.get("agentId"), doc.get("indicator")) async for doc in found])
    return out


async def _file_change_groups(db, tenant_id: str, index, now: datetime) -> Dict[str, Group]:
    """Distinct changed paths per computer in the last 24 hours, minus paths whose hash is flagged there."""
    cut = (now - FILE_WINDOW).isoformat()
    found = raw(db).fim_events.find(
        {"tenantId": tenant_id, "change_type": "Changed", "received_at": {"$gte": cut}},
        {"_id": 0, "agent_id": 1, "path": 1, "hash_after": 1, "sha256": 1}
    ).sort("received_at", -1).limit(FILE_EVENT_LIMIT)
    paths: Dict[str, Dict[str, set]] = {}
    agents: Dict[str, Dict[str, Any]] = {}
    async for doc in found:
        agent, path = signals.resolve(index, doc.get("agent_id")), _clean(doc.get("path"), PATH_CAP)
        if agent is None or path is None:
            continue
        agents[agent["id"]] = agent
        paths.setdefault(agent["id"], {}).setdefault(path, set()).update(_hashes_of(doc))
    flagged = await _flagged(db, tenant_id, [h for per in paths.values() for hs in per.values() for h in hs])
    groups: Dict[str, Group] = {}
    for agent_id, per_path in paths.items():
        for path, hashes in per_path.items():
            if any((agent_id, h) in flagged for h in hashes):
                continue
            groups.setdefault(agent_id, Group(agents[agent_id])).add((path,), {"path": path})
    return groups


# ---------------------------------------------------------------- one row per computer and kind

def _key(tenant_id: str, kind: str, agent_id: str) -> str:
    return f"{tenant_id}|sweep-suggest|{kind}|{agent_id}"


def _request(tenant_id: str, kind: str, group: Group, suggestion: Dict[str, Any]) -> gate.ActionRequest:
    host = group.agent.get("hostname") or group.agent["id"]
    if kind == "vulnerability":
        text = rm.why_vulnerabilities(group.count, host, suggestion.get("severity") or "unknown")
    else:
        text = rm.why_file_changes(group.count, host)
    return gate.ActionRequest(
        tenant_id=tenant_id, kind="security", origin="sweep", actions=[_COMMANDS[kind]], targets=[group.agent["id"]],
        params={}, dedupe_key=_key(tenant_id, kind, group.agent["id"]),
        reason={"ruleId": RULE_IDS[kind], "inputs": {"suggestionOnly": True, "suggestion": suggestion}},
        reason_text=text, dispatcher=response_dispatch.DISPATCHER_NAME)


def _memory_key(tenant_id: str, kind: str, agent_id: str) -> Dict[str, str]:
    return {"tenantId": tenant_id, "agentId": agent_id, "kind": kind, "indicator": agent_id}


async def _held(db, tenant_id: str, kind: str, agent_id: str, now: datetime) -> bool:
    """A refusal recorded for this computer and kind still holds it quiet (RESP-07)."""
    doc = await raw(db).autonomy_signals.find_one(_memory_key(tenant_id, kind, agent_id), {"_id": 0, "decision": 1})
    decision = (doc or {}).get("decision")
    if not isinstance(decision, dict):
        return False
    decision = {k: _aware(v) for k, v in decision.items()}
    return bool(sweep_memory.skip_reason(decision, await sweep_memory.latest_state(db, tenant_id, decision), [], now))


async def _remember_refusal(db, tenant_id: str, kind: str, agent_id: str, action_id: str, now: datetime) -> None:
    key = _memory_key(tenant_id, kind, agent_id)
    await raw(db).autonomy_signals.update_one(key, {"$setOnInsert": {"origins": {}}, "$max": {"lastSeenAt": now}},
                                              upsert=True)
    await signals.remember(db, key, {"actionId": action_id, "at": now, "outcome": "refused", "origins": []})


async def _refresh(db, tenant_id: str, row: Dict[str, Any], suggestion: Dict[str, Any], now: datetime,
                   counts: Dict[str, int]) -> None:
    """Bring an open suggestion up to date. Nothing is written when nothing changed and the expiry is not
    close; a change also moves the row to the top (createdAt is the time of the latest sweep)."""
    inputs = dict((row.get("reason") or {}).get("inputs") or {})
    fresh = {**inputs, "suggestionOnly": True, "suggestion": suggestion}
    expires = (row.get("approval") or {}).get("expiresAt")
    changed = fresh != inputs
    if not changed and isinstance(expires, datetime) and expires - now >= EXTEND_UNDER:
        return
    if await ledger.refresh_suggestion(db, tenant_id, row["id"], inputs=fresh, expires_at=now + APPROVAL_TTL,
                                       touch_created=changed, now=now):
        counts["refreshed"] += 1


async def _one(db, tenant_id: str, kind: str, group: Group, now: datetime, counts: Dict[str, int]) -> None:
    suggestion = group.payload(kind)
    key = _key(tenant_id, kind, group.agent["id"])
    row = await ledger.open_row(db, tenant_id, key, ("suggested",))
    if row is None:
        if await _held(db, tenant_id, kind, group.agent["id"], now):
            counts["skipped"] += 1
            return
        decision = await gate.suggest(db, _request(tenant_id, kind, group, suggestion), now=now)
        if decision.state == "shadow" and decision.recorded:
            counts["shadow"] += 1
        elif decision.recorded and decision.state == "refused":
            counts["refused"] += 1
            await _remember_refusal(db, tenant_id, kind, group.agent["id"], decision.action_id, now)
        elif decision.recorded:
            counts["suggested"] += 1
        elif decision.reason == "duplicate":
            row = await ledger.open_row(db, tenant_id, key, ("suggested",))      # a second runner won the insert
            if row is not None:
                await _refresh(db, tenant_id, row, suggestion, now, counts)
        return
    await _refresh(db, tenant_id, row, suggestion, now, counts)


async def _close_gone(db, tenant_id: str, kind: str, groups: Dict[str, Group], counts: Dict[str, int]) -> None:
    """An open suggestion of this kind for a computer that reports nothing now ends ``expired``, superseded."""
    found = raw(db).autonomy_actions.find(
        {"tenantId": tenant_id, "state": "suggested", "reason.ruleId": RULE_IDS[kind]}, {"_id": 0, "id": 1, "targets": 1}
    ).limit(1000)
    async for row in found:
        targets = row.get("targets") or [None]
        if targets[0] in groups:
            continue
        done = await ledger.transition(db, tenant_id, row["id"], ("suggested",), "expired", reasonCode="superseded",
                                       reasonText=rm.REASON_TEXT["suggestion_gone"])
        if done is not None:
            counts["closed"] += 1


async def _sync(db, tenant_id: str, kind: str, groups: Dict[str, Group], now: datetime, counts: Dict[str, int]) -> None:
    for agent_id in sorted(groups):
        try:
            await _one(db, tenant_id, kind, groups[agent_id], now, counts)
        except Exception as exc:                                   # one computer never stops the others
            logger.error("autonomous_ops: %s suggestion for %s not written: %s", kind, agent_id, exc)
    await _close_gone(db, tenant_id, kind, groups, counts)


async def run(db, tenant_id: str, tenant: TenantSettings, response, now: datetime) -> Dict[str, int]:
    """One tenant's pass. Returns counts {suggested, refreshed, closed, shadow, refused, skipped}. A kind whose
    findings cannot be read is left exactly as it is: an unreadable list never closes a row."""
    counts = {"suggested": 0, "refreshed": 0, "closed": 0, "shadow": 0, "refused": 0, "skipped": 0}
    index = signals.index_agents(await signals.agents_of(db, tenant_id))
    reads = (("vulnerability", lambda: _vulnerability_groups(db, tenant_id, index)),
             ("file_change", lambda: _file_change_groups(db, tenant_id, index, now)))
    for kind, read in reads:
        try:
            groups = await read()
        except Exception as exc:
            logger.error("autonomous_ops: %s findings of %s unreadable, leaving the rows as they are: %s",
                         kind, tenant_id, exc)
            continue
        await _sync(db, tenant_id, kind, groups, now, counts)
    return counts

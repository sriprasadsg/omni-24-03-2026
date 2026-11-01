"""The signal store, the origin readers and the two-origin rule for the automatic sweep (Phase 83, D-01, D-03, D-23).

``autonomy_signals`` holds one document per (tenantId, agentId, kind, indicator): which origins named an
indicator on a host, when the sweep first and last saw each, and the sweep's memory of what it decided.
``kind`` is ``ip``, ``file`` (a lower-case sha256) or ``range`` (a network, e.g. 45.33.32.0/24).

Origin ids (D-01): ``native`` (a native scan verdict), ``feed:urlhaus`` / ``feed:malwarebazaar`` /
``feed:otx`` (global rows of ``edr_ioc``), ``virustotal`` (a VirusTotal match raised as an alert) and
``onhost`` (any other alert carrying a sha256). One event never reads as two: the alert a native verdict
writes is classified back to ``native``, the one a VirusTotal FIM match writes to ``virustotal``.

Rules this module keeps:
* Only structured fields count (a scan row's ``target`` and ``sha256``, a feed row's ``source_ip`` and
  ``ioc_value``, a process's ``sha256``, a connection's ``remote_address``). No free text from an alert,
  finding or ticket ever names an indicator (PROH-83-01). Tenant-added IOC rows (they carry a tenantId)
  and every other tenant's rows never count (D-23, R7).
* A host reports under a hostname or an id; ``resolve`` maps it to one agent of the same tenant, and to
  nothing when two agents share the name: the failure direction is no action.
* Telemetry (processes, connections, file changes) only says what a host HAS. A candidate exists only
  when some origin names the indicator, and a feed listing counts only for a host that has the thing
  (PROH-83-08).
* Time comparisons use the sweep's own ``firstSeenAt``, never a feed-supplied time. ``evidenceAt`` keeps
  the source's own server-set time (clamped to now); a document is written only when the merge differs.

Raw Mongo handle with an explicit tenantId; the ambient tenant ContextVar is never used. Feed rows are
global (no tenantId) and sit outside the tenant wrapper, so they are read through the raw handle with
tenantId absent. Datetimes are timezone-aware UTC BSON datetimes.
"""
import ipaddress
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Mapping, Optional
from urllib.parse import urlparse

from pymongo.errors import DuplicateKeyError

from .scope import raw

logger = logging.getLogger(__name__)

NATIVE = "native"
VIRUSTOTAL = "virustotal"
ONHOST = "onhost"
KNOWN_FEEDS = ("urlhaus", "malwarebazaar", "otx")
FEED_URLHAUS = "feed:urlhaus"
ORIGIN_IDS = (NATIVE, "feed:urlhaus", "feed:malwarebazaar", "feed:otx", VIRUSTOTAL, ONHOST)
NATIVE_WINDOW = timedelta(hours=25)      # a native verdict, an alert or a file change counts for a little over a day
FEED_WINDOW = timedelta(hours=48)        # a feed row counts while the feed's sync still lists it
CORROBORATION_WINDOW = timedelta(hours=24)       # D-03
NATIVE_LIMIT = 500
CANDIDATE_LIMIT = 500
AGENT_LIMIT = 5000
FEED_CHUNK = 500
_FEED_IP_LIMIT = 1000
_PROCESS_CAP = 2000
_CONNECTION_CAP = 200
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_CIDR_TEXT = "^[0-9a-fA-F:.]+/[0-9]+$"


@dataclass
class Candidate:
    kind: str
    indicator: str
    agent_id: str
    path: Optional[str] = None
    origins: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    decision: Optional[Dict[str, Any]] = None


class Observed(list):
    """The Candidates one ``observe`` call touched, plus ``new_evidence``: one {agentId, kind, indicator,
    origin, evidenceAt} for each origin first seen in this call."""

    def __init__(self, items: Iterable[Candidate] = ()):
        super().__init__(items)
        self.new_evidence: List[Dict[str, Any]] = []


def _aware(value):
    return value.replace(tzinfo=timezone.utc) if isinstance(value, datetime) and value.tzinfo is None else value


def _ms(value: datetime) -> datetime:
    return value.replace(microsecond=value.microsecond // 1000 * 1000)       # BSON datetimes are milliseconds


def _signals(db):
    return raw(db).autonomy_signals


async def ensure_indexes(db) -> None:
    """One signal per (tenant, host, kind, indicator); a signal not seen for 30 days is dropped; the two
    lookups the sweep makes on the shared ``edr_ioc`` collection."""
    await _signals(db).create_index([("tenantId", 1), ("agentId", 1), ("kind", 1), ("indicator", 1)],
                                    unique=True, name="signal_unique")
    await _signals(db).create_index("lastSeenAt", expireAfterSeconds=30 * 86400, name="signal_ttl")
    await raw(db).edr_ioc.create_index([("ioc_type", 1), ("ioc_value", 1)], name="ioc_type_value")
    await raw(db).edr_ioc.create_index([("ioc_type", 1), ("source_ip", 1)], name="ioc_type_source_ip")


# ---------------------------------------------------------------- hosts

async def agents_of(db, tenant_id: str) -> List[Dict[str, Any]]:
    """The tenant's enrolled agents with the fields the sweep needs, telemetry included."""
    found = raw(db).agents.find(
        {"tenantId": tenant_id},
        {"_id": 0, "id": 1, "hostname": 1, "status": 1, "lastSeen": 1, "platform": 1, "ipAddress": 1,
         "meta.response_actions": 1, "meta.process_monitor.processes.sha256": 1,
         "meta.process_monitor.processes.exe": 1, "meta.runtime_security.connections.remote_address": 1}
    ).limit(AGENT_LIMIT)
    return [a async for a in found if a.get("id")]


def index_agents(agents: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    """Agents by id and by casefolded hostname; a key maps to a list so a shared name is visible."""
    index: Dict[str, List[Dict[str, Any]]] = {}
    for agent in agents:
        keys = {str(agent["id"]).casefold()}
        if agent.get("hostname"):
            keys.add(str(agent["hostname"]).strip().casefold())
        for key in keys:
            bucket = index.setdefault(key, [])
            if all(a["id"] != agent["id"] for a in bucket):
                bucket.append(agent)
    return index


def resolve(hosts_by_key: Mapping[str, List[Dict[str, Any]]], name: Any) -> Optional[Dict[str, Any]]:
    """The one agent an id or hostname names, or None when it names none or more than one."""
    if not isinstance(name, str) or not name.strip():
        return None
    matches = hosts_by_key.get(name.strip().casefold()) or []
    return matches[0] if len(matches) == 1 else None


# ---------------------------------------------------------------- indicators

def global_ip(value: Any) -> Optional[str]:
    """The canonical text of a strictly parsed, globally routable address, else None (IPv4-mapped IPv6 is
    unwrapped; private, loopback, link-local, multicast, reserved and documentation ranges never count)."""
    if not isinstance(value, str):
        return None
    try:
        addr = ipaddress.ip_address(value.strip())
    except ValueError:
        return None
    if isinstance(addr, ipaddress.IPv6Address) and addr.ipv4_mapped is not None:
        addr = addr.ipv4_mapped
    return str(addr) if addr.is_global else None


def sha256_of(value: Any) -> Optional[str]:
    """A lower-case sha256 from 64 hex characters, else None."""
    text = value.strip().lower() if isinstance(value, str) else ""
    return text if _SHA256.match(text) else None


def global_range(value: Any) -> Optional[ipaddress._BaseNetwork]:
    """A parsable, globally routable network wider than one host, else None."""
    if not isinstance(value, str) or "/" not in value:
        return None
    try:
        net = ipaddress.ip_network(value.strip(), strict=False)
    except ValueError:
        return None
    return net if net.num_addresses > 1 and net.is_global else None


def remote_host(text: Any) -> Optional[str]:
    """The address of ``host:port`` or ``[v6]:port`` (a bare host too); anything else, including an
    unbracketed IPv6 address with a port, gives None."""
    if not isinstance(text, str):
        return None
    t = text.strip()
    if t.startswith("["):
        end = t.find("]")
        return t[1:end] if end > 1 else None
    if t.count(":") == 1:
        return t.rsplit(":", 1)[0] or None
    return (t or None) if t.count(":") == 0 else None


def _when(value: Any) -> Optional[datetime]:
    """An aware datetime from an ISO string or a datetime, else None."""
    if isinstance(value, datetime):
        return _aware(value)
    if isinstance(value, str) and value:
        try:
            return _aware(datetime.fromisoformat(value.replace("Z", "+00:00")))
        except ValueError:
            return None
    return None


def alert_origin(row: Any) -> str:
    """The origin of a ``security_alerts`` row with a sha256: ``native`` when the native scan wrote it,
    ``virustotal`` when it holds a detection ratio, else ``onhost``. The first two mirror an event another
    reader counts, so they never add a second origin."""
    if not isinstance(row, Mapping):
        return ONHOST
    if row.get("source") == NATIVE:
        return NATIVE
    if row.get("vt_detection_ratio") not in (None, ""):
        return VIRUSTOTAL
    return ONHOST


def feed_origins(row: Mapping[str, Any], now: datetime) -> List[tuple]:
    """(origin id, evidence time) for each known feed that still lists this global ``edr_ioc`` row.
    ``source_feeds`` is every feed that listed it; a feed's last listing is ``feed_seen`` when the sync
    wrote it, else the row's ``updated_at``. A feed not seen for 48 hours no longer counts."""
    names: List[str] = []
    listed = row.get("source_feeds")
    for name in (list(listed) if isinstance(listed, list) else []) + [row.get("source_feed")]:
        if name in KNOWN_FEEDS and name not in names:
            names.append(name)
    seen = row.get("feed_seen") if isinstance(row.get("feed_seen"), dict) else {}
    out = []
    for name in sorted(names):
        stamp = _when(seen.get(name)) or _when(row.get("updated_at"))
        if stamp is not None and now - stamp <= FEED_WINDOW:
            out.append((f"feed:{name}", min(stamp, now)))
    return out


# ---------------------------------------------------------------- reading what the tenant's hosts report

class _Acc:
    """What one observe call gathered: origins per (agent, kind, indicator), and what each host has."""

    def __init__(self, now: datetime):
        self.now = now
        self.obs: Dict[tuple, Dict[str, Dict[str, Any]]] = {}
        self.paths: Dict[tuple, Optional[str]] = {}
        self.hashes: Dict[str, Dict[str, Optional[str]]] = {}      # sha256 -> {agent id: path}
        self.ips: Dict[str, set] = {}                              # address -> {agent id}

    def origin(self, agent_id, kind, indicator, origin, evidence: datetime, ref: str, path: Optional[str] = None):
        key = (agent_id, kind, indicator)
        evidence = _ms(min(evidence, self.now))
        slot = self.obs.setdefault(key, {})
        cur = slot.get(origin)
        if cur is None or evidence > cur["evidenceAt"]:
            slot[origin] = {"evidenceAt": evidence, "ref": ref}
        if path and (self.paths.get(key) is None or path < self.paths[key]):
            self.paths[key] = path

    def has_hash(self, agent_id, sha: str, path: Optional[str] = None):
        have = self.hashes.setdefault(sha, {})
        if agent_id not in have or (path and (have[agent_id] is None or path < have[agent_id])):
            have[agent_id] = path or have.get(agent_id)

    def has_ip(self, agent_id, ip: str):
        self.ips.setdefault(ip, set()).add(agent_id)


async def _read_native(db, tenant_id: str, index, acc: _Acc) -> None:
    """Native Malicious verdicts (an ip, a url whose host is an IP literal, a file or hash with its sha256)
    as the ``native`` origin on the host that posted them."""
    cut = (acc.now - NATIVE_WINDOW).isoformat()
    found = raw(db).security_scan_results.find(
        {"tenantId": tenant_id, "source": NATIVE, "verdict": "Malicious", "created_at": {"$gte": cut}},
        {"_id": 0, "agentId": 1, "target": 1, "type": 1, "sha256": 1, "created_at": 1, "id": 1}
    ).sort("created_at", -1).limit(NATIVE_LIMIT)
    async for row in found:
        agent = resolve(index, row.get("agentId"))
        evidence = _when(row.get("created_at"))
        if agent is None or evidence is None:
            continue
        kind, target, ref = row.get("type"), row.get("target"), str(row.get("id") or "")
        if kind in ("ip", "url"):
            if kind == "url":
                try:
                    target = urlparse(target if "//" in str(target) else f"//{target}").hostname
                except ValueError:
                    target = None
            ip = global_ip(target)
            if ip:
                acc.origin(agent["id"], "ip", ip, NATIVE, evidence, ref)
                acc.has_ip(agent["id"], ip)
        elif kind in ("file", "hash"):
            sha = sha256_of(row.get("sha256")) or (sha256_of(target) if kind == "hash" else None)
            path = target if kind == "file" and isinstance(target, str) and 0 < len(target) <= 1024 else None
            if sha:
                acc.origin(agent["id"], "file", sha, NATIVE, evidence, ref, path)
                acc.has_hash(agent["id"], sha, path)


async def _read_alerts(db, tenant_id: str, index, acc: _Acc) -> None:
    """Alerts that carry a sha256, as the origin ``alert_origin`` gives them."""
    cut = (acc.now - NATIVE_WINDOW).isoformat()
    found = raw(db).security_alerts.find(
        {"tenantId": tenant_id, "sha256": {"$type": "string", "$ne": ""}, "created_at": {"$gte": cut}},
        {"_id": 0, "id": 1, "agent_id": 1, "sha256": 1, "source": 1, "vt_detection_ratio": 1, "created_at": 1}
    ).sort("created_at", -1).limit(NATIVE_LIMIT)
    async for row in found:
        agent = resolve(index, row.get("agent_id"))
        sha, evidence = sha256_of(row.get("sha256")), _when(row.get("created_at"))
        if agent is None or sha is None or evidence is None:
            continue
        acc.origin(agent["id"], "file", sha, alert_origin(row), evidence, str(row.get("id") or ""))
        acc.has_hash(agent["id"], sha)


def _read_telemetry(agents: List[Dict[str, Any]], acc: _Acc) -> None:
    """What each host reports it runs and talks to. Telemetry is never an origin."""
    for agent in agents:
        meta = agent.get("meta") if isinstance(agent.get("meta"), dict) else {}
        monitor = meta.get("process_monitor") if isinstance(meta.get("process_monitor"), dict) else {}
        procs = monitor.get("processes") if isinstance(monitor.get("processes"), list) else []
        for proc in procs[:_PROCESS_CAP]:
            sha = sha256_of(proc.get("sha256")) if isinstance(proc, dict) else None
            if sha:
                exe = proc.get("exe")
                acc.has_hash(agent["id"], sha, exe if isinstance(exe, str) and 0 < len(exe) <= 1024 else None)
        runtime = meta.get("runtime_security") if isinstance(meta.get("runtime_security"), dict) else {}
        conns = runtime.get("connections") if isinstance(runtime.get("connections"), list) else []
        for conn in conns[:_CONNECTION_CAP]:
            ip = global_ip(remote_host(conn.get("remote_address"))) if isinstance(conn, dict) else None
            if ip:
                acc.has_ip(agent["id"], ip)


async def _read_fim(db, tenant_id: str, index, acc: _Acc) -> None:
    cut = (acc.now - NATIVE_WINDOW).isoformat()
    found = raw(db).fim_events.find(
        {"tenantId": tenant_id, "received_at": {"$gte": cut},
         "$or": [{"hash_after": {"$type": "string", "$ne": ""}}, {"sha256": {"$type": "string", "$ne": ""}}]},
        {"_id": 0, "agent_id": 1, "path": 1, "hash_after": 1, "sha256": 1}
    ).sort("received_at", -1).limit(NATIVE_LIMIT)
    async for row in found:
        agent = resolve(index, row.get("agent_id"))
        sha = sha256_of(row.get("hash_after")) or sha256_of(row.get("sha256"))
        path = row.get("path")
        if agent is not None and sha:
            acc.has_hash(agent["id"], sha, path if isinstance(path, str) and 0 < len(path) <= 1024 else None)


def _chunks(values: List[str]):
    return (values[i:i + FEED_CHUNK] for i in range(0, len(values), FEED_CHUNK))


async def _read_feeds(db, acc: _Acc) -> None:
    """Global feed rows (tenantId absent) naming something a host of this tenant has."""
    coll = raw(db).edr_ioc
    shown = {"_id": 0, "ioc_value": 1, "source_ip": 1, "source_feed": 1, "source_feeds": 1, "feed_seen": 1,
             "updated_at": 1}
    glob = {"tenantId": {"$exists": False}}
    for chunk in _chunks(sorted(acc.hashes)):
        async for row in coll.find({**glob, "ioc_type": "hash", "ioc_value": {"$in": chunk}}, shown):
            sha = sha256_of(row.get("ioc_value"))
            for origin, evidence in feed_origins(row, acc.now):
                for agent_id, path in sorted((acc.hashes.get(sha) or {}).items()):
                    acc.origin(agent_id, "file", sha, origin, evidence, origin[5:], path)
    for chunk in _chunks(sorted(acc.ips)):
        async for row in coll.find({**glob, "ioc_type": {"$in": ["ip", "url"]}, "source_ip": {"$in": chunk}}, shown):
            ip = global_ip(row.get("source_ip"))
            for origin, evidence in feed_origins(row, acc.now):
                for agent_id in sorted(acc.ips.get(ip) or ()):
                    acc.origin(agent_id, "ip", ip, origin, evidence, origin[5:])
    if acc.ips:
        async for row in coll.find({**glob, "ioc_type": "ip", "source_ip": {"$regex": _CIDR_TEXT}}, shown).limit(_FEED_IP_LIMIT):
            net = global_range(row.get("source_ip"))
            if net is None:
                continue
            for origin, evidence in feed_origins(row, acc.now):
                for ip in sorted(acc.ips):
                    if ipaddress.ip_address(ip) in net:
                        for agent_id in sorted(acc.ips[ip]):
                            acc.origin(agent_id, "range", str(net), origin, evidence, origin[5:])


# ---------------------------------------------------------------- recording

def _merge(existing: Mapping[str, Any], observed: Mapping[str, Mapping[str, Any]], now: datetime):
    """(merged origins, changed, names new to the document): what the $min / $max update writes."""
    merged = {k: dict(v) for k, v in existing.items() if isinstance(v, dict)}
    changed, new = False, []
    for name in sorted(observed):
        ob, cur = observed[name], merged.get(name)
        if cur is None:
            new.append(name)
            cur = merged[name] = {}
        want = {"firstSeenAt": min(_aware(cur.get("firstSeenAt")) or now, now),
                "lastSeenAt": max(_aware(cur.get("lastSeenAt")) or now, now),
                "evidenceAt": max(_aware(cur.get("evidenceAt")) or ob["evidenceAt"], ob["evidenceAt"]),
                "ref": ob["ref"]}
        if any(cur.get(k) != v for k, v in want.items()):
            changed = True
            cur.update(want)
    return merged, changed, new


async def _record(db, flt: Dict[str, Any], observed, path: Optional[str], now: datetime):
    """Merge one signal's observations. Returns (the document as it now stands, new origin names); no
    write when nothing would change."""
    for attempt in (0, 1):
        doc = await _signals(db).find_one(flt, {"_id": 0}) or {}
        merged, changed, new = _merge(doc.get("origins") or {}, observed, now)
        top_last = max(_aware(doc.get("lastSeenAt")) or now, now)
        if not changed and top_last == _aware(doc.get("lastSeenAt")) and (not path or doc.get("path") == path):
            return doc, new
        sets: Dict[str, Any] = {}
        mins, maxs = {}, {"lastSeenAt": now}
        for name, ob in observed.items():
            mins[f"origins.{name}.firstSeenAt"] = now
            maxs.update({f"origins.{name}.lastSeenAt": now, f"origins.{name}.evidenceAt": ob["evidenceAt"]})
            sets[f"origins.{name}.ref"] = ob["ref"]
        if path:
            sets["path"] = path
        try:
            await _signals(db).update_one(flt, {"$min": mins, "$max": maxs, "$set": sets}, upsert=True)
        except DuplicateKeyError:
            if attempt:
                raise
            continue
        return {**doc, **flt, "origins": merged, "lastSeenAt": top_last, **({"path": path} if path else {})}, new
    return {}, []


async def observe(db, tenant_id: str, agents: List[Dict[str, Any]], now: datetime) -> Observed:
    """Read every origin for this tenant, record each on its signal and return the Candidates touched,
    sorted by (agent, kind, indicator), at most 500. ``new_evidence`` lists the origins first seen now."""
    now = _ms(now)
    index = index_agents(agents)
    acc = _Acc(now)
    await _read_native(db, tenant_id, index, acc)
    await _read_alerts(db, tenant_id, index, acc)
    _read_telemetry(agents, acc)
    await _read_fim(db, tenant_id, index, acc)
    await _read_feeds(db, acc)
    keys = sorted(acc.obs)
    if len(keys) > CANDIDATE_LIMIT:
        logger.warning("autonomous_ops: tenant %s has %d candidates, taking the first %d",
                       tenant_id, len(keys), CANDIDATE_LIMIT)
        keys = keys[:CANDIDATE_LIMIT]
    out = Observed()
    for key in keys:
        agent_id, kind, indicator = key
        flt = {"tenantId": tenant_id, "agentId": agent_id, "kind": kind, "indicator": indicator}
        doc, new = await _record(db, flt, acc.obs[key], acc.paths.get(key), now)
        if doc:
            out.append(_candidate(doc))
            out.new_evidence.extend({"agentId": agent_id, "kind": kind, "indicator": indicator, "origin": name,
                                     "evidenceAt": acc.obs[key][name]["evidenceAt"]} for name in new)
    return out


def _candidate(doc: Dict[str, Any]) -> Candidate:
    origins = {}
    for name, value in (doc.get("origins") or {}).items():
        if isinstance(value, dict):
            origins[name] = {k: _aware(v) for k, v in value.items()}
    decision = doc.get("decision")
    if isinstance(decision, dict):
        decision = {k: _aware(v) for k, v in decision.items()}
    return Candidate(kind=doc.get("kind", "ip"), indicator=doc.get("indicator", ""), agent_id=doc.get("agentId", ""),
                     path=doc.get("path"), origins=origins, decision=decision if isinstance(decision, dict) else None)


# ---------------------------------------------------------------- the rule and the memory

def counting_origins(doc: Any, evidence_after: Optional[datetime] = None) -> Dict[str, Dict[str, Any]]:
    """The origins that count: all, or (D-14) only those with evidence later than ``evidence_after`` (one
    with no evidence time cannot prove it is fresh and is dropped)."""
    origins = doc.origins if isinstance(doc, Candidate) else (doc or {}).get("origins")
    out = {}
    for name, value in (origins or {}).items():
        if not isinstance(value, Mapping):
            continue
        if evidence_after is not None:
            evidence = _aware(value.get("evidenceAt"))
            if not isinstance(evidence, datetime) or evidence <= _aware(evidence_after):
                continue
        out[name] = value
    return out


def corroborated(doc: Any, *, two_signal: bool, evidence_after: Optional[datetime] = None) -> bool:
    """D-03: two different origins whose firstSeenAt are at most 24 hours apart (inclusive, and no matter
    what a third did); with two_signal off (D-04) one is enough. ``doc`` is a Candidate or a mapping holding ``origins``."""
    firsts = sorted(t for t in (_aware(v.get("firstSeenAt")) for v in counting_origins(doc, evidence_after).values())
                    if isinstance(t, datetime))
    if not firsts:
        return False
    if len(firsts) == 1:
        return not two_signal
    return any(b - a <= CORROBORATION_WINDOW for a, b in zip(firsts, firsts[1:])) or not two_signal


async def remember(db, doc_key: Dict[str, Any], decision: Dict[str, Any]) -> None:
    """Write the sweep's memory of what it decided for this signal: {actionId, at, outcome, origins?,
    blockedFrom?, blockedUntil?, holdUntil?}."""
    keep = {k: v for k, v in decision.items() if k in (
        "actionId", "at", "outcome", "origins", "blockedFrom", "blockedUntil", "holdUntil")}
    await _signals(db).update_one(doc_key, {"$set": {"decision": keep}})

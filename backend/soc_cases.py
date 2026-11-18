"""Case work for the SOC console: a case's tasks (its checklist) and its evidence (indicators, notes, files).

Both live in their own collections (``soc_case_tasks``, ``soc_case_evidence``), keyed by the case and its
tenant, not on the case document: PUT /api/security-cases writes the whole case the browser holds, so a
comment added from a stale copy would otherwise wipe newer tasks.

* Tasks: todo / in_progress / done / skipped, with an assignee and a due date. "Standard steps" adds the
  response checklist (confirm, scope, contain, remove, recover, write up) plus steps for the case's alert
  types, once each. Tasks are never deleted; one that no longer applies is skipped.
* Evidence: an indicator (user, process, file, IP, domain, hash), a note, or a file (at most 25 MB, kept on
  disk with its SHA-256, only ever served as a download). Every item keeps a custody log of who added,
  downloaded, excluded or restored it; nothing is deleted.
"""
import os
import pathlib
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from pymongo import ReturnDocument

from soc_service import scope_filter

TASK_STATUSES = ("todo", "in_progress", "done", "skipped")
INDICATOR_KINDS = ("user", "process", "file", "ip", "domain", "hash", "other")
MAX_TASKS = 100
MAX_EVIDENCE = 200
MAX_FILE_BYTES = 25 * 1024 * 1024
EVIDENCE_DIR = os.getenv("SOC_EVIDENCE_DIR", "") or os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "soc_evidence")

STANDARD_STEPS = (
    "Confirm the alerts are real, not a false positive",
    "Find how far it reached: other endpoints and accounts",
    "Contain it: isolate the host, block the IP or quarantine the file if needed",
    "Remove the cause",
    "Restore the endpoint and watch it for a week",
    "Write down what happened and what should change",
)
TYPE_STEPS = {
    "persistence_mechanism": "Find who created the start-up entry, and when",
    "fim_violation": "Compare the changed file with a known-good copy and find who changed it",
    "ueba_anomaly": "Ask the user whether the sign-in was theirs",
    "shadow_ai_process": "Decide whether the AI tool is allowed: approve it or remove it",
    "pii_detected": "Find where the personal data came from and whether it must be moved",
    "malware_detected": "Look the file's hash up in threat intelligence",
    "runtime_security": "Look the process or file up in threat intelligence",
}


class CaseError(ValueError):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _clean(text: Any, limit: int) -> str:
    return " ".join(str(text or "").split())[:limit]


async def get_case(db, scope: Optional[str], case_id: str) -> Dict[str, Any]:
    case = await db.security_cases.find_one({"id": case_id, **scope_filter(scope)}, {"_id": 0})
    if not case:
        raise CaseError("Case not found", 404)
    return case


def _key(case: Dict[str, Any]) -> Dict[str, Any]:
    return {"caseId": case["id"], "tenantId": case.get("tenantId")}


async def _alerts_of(db, case: Dict[str, Any]) -> List[Dict[str, Any]]:
    ids = list(dict.fromkeys([*(case.get("alertIds") or []), *(e.get("id") for e in case.get("relatedEvents") or [] if isinstance(e, dict))]))
    ids = [i for i in ids if isinstance(i, str) and i][:200]
    if not ids:
        return []
    found = []
    for name in ("security_alerts", "alerts"):
        found += await db[name].find({"id": {"$in": ids}, "tenantId": case.get("tenantId")}, {"_id": 0}).to_list(len(ids))
    return found


async def work(db, scope: Optional[str], case_id: str) -> Dict[str, Any]:
    """The case's tasks and evidence, and what the standard steps and its alerts would still add."""
    case = await get_case(db, scope, case_id)
    tasks = await db.soc_case_tasks.find(_key(case), {"_id": 0}).sort("createdAt", 1).to_list(MAX_TASKS)
    evidence = await db.soc_case_evidence.find(_key(case), {"_id": 0, "storedAs": 0}).sort("addedAt", 1).to_list(MAX_EVIDENCE)
    alerts = await _alerts_of(db, case)
    have = {t["title"].lower() for t in tasks}
    held = {(e.get("indicatorKind"), e.get("key")) for e in evidence if e.get("kind") == "indicator"}
    return {
        "caseId": case["id"], "tenantId": case.get("tenantId"), "tasks": tasks, "evidence": evidence,
        "standardSteps": [s for s in _steps(alerts) if s.lower() not in have],
        "alertIndicators": [i for i in _indicators(alerts) if (i["indicatorKind"], i["key"]) not in held],
    }


def _steps(alerts: List[Dict[str, Any]]) -> List[str]:
    extra = list(dict.fromkeys(TYPE_STEPS[a["type"]] for a in alerts if a.get("type") in TYPE_STEPS))
    return [STANDARD_STEPS[0], *extra, *STANDARD_STEPS[1:]]


def _indicators(alerts: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    import soc_graph
    out: Dict[tuple, Dict[str, Any]] = {}
    for a in alerts:
        for kind, key, label in soc_graph.entities(a):
            if kind == "technique":
                continue
            item = out.setdefault((kind, key), {"indicatorKind": kind, "key": key, "value": label,
                                                "detail": soc_graph._file_detail(a) if kind == "file" else None, "alertIds": []})
            if a.get("id") and a["id"] not in item["alertIds"]:
                item["alertIds"].append(a["id"])
    return list(out.values())


async def add_task(db, scope: Optional[str], case_id: str, who: str, title: str, assignee: Optional[str] = None,
                   due_at: Optional[str] = None) -> Dict[str, Any]:
    case = await get_case(db, scope, case_id)
    title = _clean(title, 200)
    if not title:
        raise CaseError("A task needs a title")
    if await db.soc_case_tasks.count_documents(_key(case)) >= MAX_TASKS:
        raise CaseError(f"A case holds at most {MAX_TASKS} tasks", 409)
    task = {"id": f"task-{uuid.uuid4().hex[:12]}", **_key(case), "title": title, "status": "todo",
            "assignee": _clean(assignee, 120) or None, "dueAt": _due(due_at), "createdBy": who, "createdAt": _now()}
    await db.soc_case_tasks.insert_one(dict(task))
    return task


def _due(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    try:
        ts = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        raise CaseError("dueAt must be a date and time (ISO 8601)")
    return (ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc)).isoformat()


async def add_standard_steps(db, scope: Optional[str], case_id: str, who: str) -> Dict[str, Any]:
    """Add the standard steps this case does not have yet, in order."""
    current = await work(db, scope, case_id)
    added = [await add_task(db, scope, case_id, who, step) for step in current["standardSteps"]]
    return {"added": len(added), "tasks": added, "tenantId": current["tenantId"]}


async def update_task(db, scope: Optional[str], case_id: str, task_id: str, who: str, changes: Dict[str, Any]) -> Dict[str, Any]:
    case = await get_case(db, scope, case_id)
    update: Dict[str, Any] = {"updatedBy": who, "updatedAt": _now()}
    unset: Dict[str, str] = {}
    if "status" in changes:
        if changes["status"] not in TASK_STATUSES:
            raise CaseError(f"status must be one of: {', '.join(TASK_STATUSES)}")
        update["status"] = changes["status"]
        if changes["status"] in ("done", "skipped"):
            update.update(closedBy=who, closedAt=update["updatedAt"])
        else:
            unset.update(closedBy="", closedAt="")
    if "assignee" in changes:
        update["assignee"] = _clean(changes["assignee"], 120) or None
    if "dueAt" in changes:
        update["dueAt"] = _due(changes["dueAt"])
    if "note" in changes:
        update["note"] = _clean(changes["note"], 1000) or None
    if changes.get("status") == "skipped" and not update.get("note"):
        raise CaseError("Say why the task is skipped")
    ops: Dict[str, Any] = {"$set": update, **({"$unset": unset} if unset else {})}
    result = await db.soc_case_tasks.find_one_and_update({"id": task_id, **_key(case)}, ops, projection={"_id": 0},
                                                         return_document=ReturnDocument.AFTER)
    if not result:
        raise CaseError("Task not found", 404)
    return result


def _custody(action: str, who: str, note: Optional[str] = None) -> Dict[str, Any]:
    return {"action": action, "by": who, "at": _now(), **({"note": note} if note else {})}


async def _room(db, case: Dict[str, Any]) -> None:
    if await db.soc_case_evidence.count_documents(_key(case)) >= MAX_EVIDENCE:
        raise CaseError(f"A case holds at most {MAX_EVIDENCE} pieces of evidence", 409)


async def add_evidence(db, scope: Optional[str], case_id: str, who: str, kind: str, value: str,
                       indicator_kind: Optional[str] = None, note: Optional[str] = None) -> Dict[str, Any]:
    """An indicator or a note; an indicator already held on the case is refused."""
    case = await get_case(db, scope, case_id)
    if kind not in ("indicator", "note"):
        raise CaseError("kind must be indicator or note (files are uploaded)")
    value = _clean(value, 4000 if kind == "note" else 500)
    if not value:
        raise CaseError("Evidence needs a value")
    item: Dict[str, Any] = {"id": f"ev-{uuid.uuid4().hex[:12]}", **_key(case), "kind": kind, "value": value,
                            "note": _clean(note, 1000) or None, "addedBy": who, "addedAt": _now(), "excluded": False,
                            "custody": [_custody("added", who)]}
    if kind == "indicator":
        if indicator_kind not in INDICATOR_KINDS:
            raise CaseError(f"indicatorKind must be one of: {', '.join(INDICATOR_KINDS)}")
        item.update(indicatorKind=indicator_kind, key=value.lower())
        if await db.soc_case_evidence.find_one({**_key(case), "kind": "indicator", "indicatorKind": indicator_kind, "key": item["key"]}, {"_id": 1}):
            raise CaseError("That indicator is already evidence on this case", 409)
    await _room(db, case)
    await db.soc_case_evidence.insert_one(dict(item))
    return item


async def add_alert_indicators(db, scope: Optional[str], case_id: str, who: str) -> Dict[str, Any]:
    """Every user, process, file and IP the case's alerts name, as indicators linked to those alerts."""
    case = await get_case(db, scope, case_id)
    added = []
    for ind in (await work(db, scope, case_id))["alertIndicators"]:
        if len(added) + await db.soc_case_evidence.count_documents(_key(case)) >= MAX_EVIDENCE:
            break
        item = {"id": f"ev-{uuid.uuid4().hex[:12]}", **_key(case), "kind": "indicator", "indicatorKind": ind["indicatorKind"],
                "key": ind["key"], "value": ind["value"], "note": ind.get("detail"), "alertIds": ind["alertIds"][:50],
                "addedBy": who, "addedAt": _now(), "excluded": False, "custody": [_custody("added", who, "from the case's alerts")]}
        await db.soc_case_evidence.insert_one(dict(item))
        added.append(item)
    return {"added": len(added), "evidence": added, "tenantId": case.get("tenantId")}


def _safe_name(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9._\-]", "_", os.path.basename(name or "evidence"))[:120] or "evidence"


async def add_file(db, scope: Optional[str], case_id: str, who: str, filename: str, contents: bytes,
                   note: Optional[str] = None) -> Dict[str, Any]:
    import hashlib
    case = await get_case(db, scope, case_id)
    if len(contents) > MAX_FILE_BYTES:
        raise CaseError(f"A file can be at most {MAX_FILE_BYTES // (1024 * 1024)} MB", 413)
    if not contents:
        raise CaseError("The file is empty")
    await _room(db, case)
    root = pathlib.Path(EVIDENCE_DIR).resolve()
    root.mkdir(mode=0o750, parents=True, exist_ok=True)
    stored = f"{case['id']}_{uuid.uuid4().hex}"
    path = (root / stored).resolve()
    if not str(path).startswith(str(root) + os.sep):
        raise CaseError("Invalid case id")
    path.write_bytes(contents)
    os.chmod(path, 0o640)
    item = {"id": f"ev-{uuid.uuid4().hex[:12]}", **_key(case), "kind": "file", "value": _safe_name(filename),
            "size": len(contents), "sha256": hashlib.sha256(contents).hexdigest(), "storedAs": stored,
            "note": _clean(note, 1000) or None, "addedBy": who, "addedAt": _now(), "excluded": False,
            "custody": [_custody("added", who)]}
    await db.soc_case_evidence.insert_one(dict(item))
    item.pop("storedAs")
    return item


async def file_for_download(db, scope: Optional[str], case_id: str, evidence_id: str, who: str) -> Dict[str, Any]:
    """The stored file (path, name) of a file evidence item; the download goes on its custody log."""
    case = await get_case(db, scope, case_id)
    item = await db.soc_case_evidence.find_one({"id": evidence_id, **_key(case), "kind": "file"}, {"_id": 0})
    if not item:
        raise CaseError("Evidence file not found", 404)
    root = pathlib.Path(EVIDENCE_DIR).resolve()
    path = (root / str(item.get("storedAs") or "")).resolve()
    if not str(path).startswith(str(root) + os.sep) or not path.is_file():
        raise CaseError("The evidence file is missing on the server", 404)
    await db.soc_case_evidence.update_one({"id": evidence_id, **_key(case)}, {"$push": {"custody": _custody("downloaded", who)}})
    return {"path": str(path), "filename": item["value"], "sha256": item.get("sha256"), "tenantId": case.get("tenantId")}


async def set_excluded(db, scope: Optional[str], case_id: str, evidence_id: str, who: str, excluded: bool,
                       reason: Optional[str]) -> Dict[str, Any]:
    """Mark evidence as not relevant (with a reason) or bring it back; it is never deleted."""
    case = await get_case(db, scope, case_id)
    reason = _clean(reason, 500)
    if excluded and not reason:
        raise CaseError("Say why the evidence is excluded")
    result = await db.soc_case_evidence.find_one_and_update(
        {"id": evidence_id, **_key(case), "excluded": not excluded},
        {"$set": {"excluded": excluded}, "$push": {"custody": _custody("excluded" if excluded else "restored", who, reason or None)}},
        projection={"_id": 0, "storedAs": 0}, return_document=ReturnDocument.AFTER)
    if not result:
        raise CaseError("Evidence not found, or it is already " + ("excluded" if excluded else "included"), 404)
    return result


async def ensure_indexes(db) -> None:
    await db.soc_case_tasks.create_index([("tenantId", 1), ("caseId", 1), ("createdAt", 1)], name="soc_case_task_case")
    await db.soc_case_evidence.create_index([("tenantId", 1), ("caseId", 1), ("addedAt", 1)], name="soc_case_evidence_case")

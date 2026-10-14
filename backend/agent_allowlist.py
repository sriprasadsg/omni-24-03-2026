"""Hardware allowlist (spec C4).

With ``license.allowlistMode == "enforce"`` a new enrollment is admitted only when its
machine matches an entry by BIOS serial, SMBIOS UUID or a physical MAC; otherwise it is
held Pending with reason ``not_allowlisted``. Values are normalized exactly like seat
keys (seat_identity), so "pf3abc12" matches "PF3ABC12". Each value is unique per tenant
(partial unique indexes, migration 013).
"""
import csv
import io
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from pymongo.errors import BulkWriteError, DuplicateKeyError

import seat_identity

MAX_IMPORT_ROWS = 10_000
MAX_NOTE = 200
_FIELDS = ("serialNumber", "smbiosUuid", "macAddress")


def _raw(db):
    return getattr(db, "_db", db)


class EntryError(ValueError):
    pass


def normalize_entry(serial: Any = None, uuid_value: Any = None, mac: Any = None, note: Any = None) -> Dict[str, Any]:
    """The stored identifiers of one entry. Raises EntryError naming what is wrong."""
    entry: Dict[str, Any] = {}
    for field, value, norm in (("serialNumber", serial, seat_identity.normalize_serial),
                               ("smbiosUuid", uuid_value, seat_identity.normalize_uuid),
                               ("macAddress", mac, seat_identity.normalize_mac)):
        if value is None or (isinstance(value, str) and not value.strip()):
            continue
        normalized = norm(value)
        if not normalized:
            raise EntryError(f"invalid {field}: {str(value)[:64]!r}")
        entry[field] = normalized
    if not entry:
        raise EntryError("an entry needs a serial number, SMBIOS UUID or MAC address")
    if note:
        entry["note"] = str(note).strip()[:MAX_NOTE]
    return entry


def _doc(tenant_id: str, entry: Dict[str, Any], actor: str) -> Dict[str, Any]:
    return {"id": f"al-{uuid.uuid4().hex[:16]}", "tenantId": tenant_id, **entry, "addedBy": actor,
            "addedAt": datetime.now(timezone.utc).isoformat()}


async def add(db, tenant_id: str, entry: Dict[str, Any], actor: str) -> Dict[str, Any]:
    """Store one normalized entry. Raises EntryError when a value is already listed."""
    doc = _doc(tenant_id, entry, actor)
    try:
        await _raw(db).agent_allowlist.insert_one(dict(doc))
    except DuplicateKeyError:
        raise EntryError("already on the allowlist")
    return doc


async def remove(db, tenant_id: str, entry_id: str) -> bool:
    res = await _raw(db).agent_allowlist.delete_one({"id": entry_id, "tenantId": tenant_id})
    return res.deleted_count == 1


async def list_entries(db, tenant_id: str, skip: int = 0, limit: int = 200) -> Dict[str, Any]:
    coll = _raw(db).agent_allowlist
    entries = await coll.find({"tenantId": tenant_id}, {"_id": 0}).sort("addedAt", -1) \
        .skip(skip).limit(limit).to_list(length=limit)
    return {"entries": entries, "total": await coll.count_documents({"tenantId": tenant_id})}


async def matches(db, tenant_id: str, hardware: Dict[str, Any]) -> bool:
    """Whether a normalized hardware block matches any entry of the tenant."""
    terms: List[Dict[str, Any]] = []
    if hardware.get("serialNumber"):
        terms.append({"serialNumber": hardware["serialNumber"]})
    if hardware.get("smbiosUuid"):
        terms.append({"smbiosUuid": hardware["smbiosUuid"]})
    if hardware.get("macAddresses"):
        terms.append({"macAddress": {"$in": list(hardware["macAddresses"])}})
    if not terms:
        return False
    return bool(await _raw(db).agent_allowlist.find_one({"tenantId": tenant_id, "$or": terms}, {"_id": 1}))


def parse_csv(text: str) -> Tuple[List[Tuple[int, Dict[str, Any]]], List[Dict[str, Any]]]:
    """Rows of ``serial,uuid,mac,note`` (a header row is optional) -> (valid rows, errors).
    Row numbers are 1-based lines of the file."""
    rows: List[Tuple[int, Dict[str, Any]]] = []
    errors: List[Dict[str, Any]] = []
    seen: Dict[Tuple[str, str], int] = {}
    reader = csv.reader(io.StringIO(text))
    for line_no, cols in enumerate(reader, start=1):
        if not cols or all(not c.strip() for c in cols):
            continue
        if line_no == 1 and cols[0].strip().lower() in ("serial", "serialnumber", "serial_number"):
            continue
        if len(rows) + len(errors) >= MAX_IMPORT_ROWS:
            raise EntryError(f"too many rows: at most {MAX_IMPORT_ROWS} per import")
        cols = (cols + ["", "", "", ""])[:4]
        try:
            entry = normalize_entry(cols[0], cols[1], cols[2], cols[3])
        except EntryError as exc:
            errors.append({"row": line_no, "error": str(exc)})
            continue
        dup = next((seen[(f, entry[f])] for f in _FIELDS if f in entry and (f, entry[f]) in seen), None)
        if dup:
            errors.append({"row": line_no, "error": f"duplicate of row {dup}"})
            continue
        for f in _FIELDS:
            if f in entry:
                seen[(f, entry[f])] = line_no
        rows.append((line_no, entry))
    return rows, errors


async def import_csv(db, tenant_id: str, text: str, actor: str) -> Dict[str, Any]:
    """Insert every valid row; rows that are malformed, repeated in the file or already
    listed are reported and skipped. One unordered bulk insert, so 10,000 rows stay fast."""
    rows, errors = parse_csv(text)
    docs = [_doc(tenant_id, entry, actor) for _, entry in rows]
    imported = len(docs)
    if docs:
        try:
            await _raw(db).agent_allowlist.insert_many(docs, ordered=False)
        except BulkWriteError as exc:
            failed = {e["index"] for e in exc.details.get("writeErrors", [])}
            imported -= len(failed)
            for index in sorted(failed):
                errors.append({"row": rows[index][0], "error": "already on the allowlist"})
    errors.sort(key=lambda e: e["row"])
    return {"imported": imported, "skipped": len(errors), "errors": errors[:1000]}


def entry_from_body(body: Dict[str, Any]) -> Dict[str, Any]:
    return normalize_entry(body.get("serialNumber"), body.get("smbiosUuid"), body.get("macAddress"), body.get("note"))


def describe(entry: Optional[Dict[str, Any]]) -> str:
    entry = entry or {}
    return ", ".join(f"{f}={entry[f]}" for f in _FIELDS if entry.get(f))

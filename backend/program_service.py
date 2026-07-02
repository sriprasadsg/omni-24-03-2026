"""Program Control Grouping — named programs with status rollup."""
import uuid
from datetime import datetime, timezone
from typing import Optional


def _now() -> str: return datetime.now(timezone.utc).isoformat()
def _id() -> str: return f"prog-{uuid.uuid4().hex[:12]}"


async def create_program(db, tenant_id: str, data: dict) -> dict:
    doc = {
        "id": _id(), "tenantId": tenant_id, "name": data.get("name", ""),
        "description": data.get("description", ""), "framework_id": data.get("framework_id", ""),
        "owner": data.get("owner", ""), "control_ids": data.get("control_ids", []),
        "created_at": _now(), "updated_at": _now(),
    }
    await db._db.programs.insert_one(doc)
    doc.pop("_id", None)
    return doc


async def get_program(db, program_id: str, tenant_id: str) -> Optional[dict]:
    doc = await db._db.programs.find_one({"id": program_id, "tenantId": tenant_id}, {"_id": 0})
    if not doc:
        return None
    rollup = await _compute_status_rollup(db, doc.get("control_ids", []), tenant_id)
    doc["status_rollup"] = rollup
    return doc


async def list_programs(db, tenant_id: str) -> list:
    docs = await db._db.programs.find({"tenantId": tenant_id}, {"_id": 0}).sort("created_at", -1).to_list(length=100)
    for doc in docs:
        rollup = await _compute_status_rollup(db, doc.get("control_ids", []), tenant_id)
        doc["status_rollup"] = rollup
    return docs


async def update_controls(db, program_id: str, tenant_id: str, add: list, remove: list) -> Optional[dict]:
    doc = await db._db.programs.find_one({"id": program_id, "tenantId": tenant_id}, {"_id": 0})
    if not doc:
        return None
    current = set(doc.get("control_ids", []))
    if add:
        current.update(add)
    if remove:
        current.difference_update(remove)
    await db._db.programs.update_one(
        {"id": program_id},
        {"$set": {"control_ids": list(current), "updated_at": _now()}},
    )
    doc["control_ids"] = list(current)
    return doc


async def delete_program(db, program_id: str, tenant_id: str) -> bool:
    result = await db._db.programs.delete_one({"id": program_id, "tenantId": tenant_id})
    return result.deleted_count > 0


async def _compute_status_rollup(db, control_ids: list, tenant_id: str) -> dict:
    if not control_ids:
        return {"total": 0, "passing": 0, "failing": 0, "not_assessed": 0, "status": "in_progress"}
    # Sort by lastUpdated descending so, when a control has multiple linked
    # asset results, the first document encountered per controlId below is
    # deterministically the *latest* one (per the plan's "latest compliance
    # check result" requirement), not an arbitrary cursor-order pick.
    results = await db._db.asset_compliance.find(
        {"controlId": {"$in": control_ids}, "tenantId": tenant_id},
        {"_id": 0, "status": 1, "controlId": 1, "lastUpdated": 1},
    ).sort("lastUpdated", -1).to_list(length=1000)
    seen = set()
    passing = 0
    failing = 0
    for r in results:
        cid = r.get("controlId")
        if cid in seen:
            continue
        seen.add(cid)
        if r.get("status") == "Compliant":
            passing += 1
        elif r.get("status") in ("Non-Compliant", "Pending_Evidence"):
            failing += 1
    total = len(set(control_ids))
    not_assessed = total - len(seen)
    if passing >= total * 0.8 and failing == 0:
        status = "compliant"
    elif failing > 0:
        status = "at_risk"
    else:
        status = "in_progress"
    return {"total": total, "passing": passing, "failing": failing, "not_assessed": not_assessed, "status": status}

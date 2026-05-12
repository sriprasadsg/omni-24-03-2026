"""
Compliance Framework Evaluation Endpoints.
Runs NIST CSF, CIS Controls v8, and ISO 27001:2022 automated checks.
"""
from __future__ import annotations
import sys, os
sys.path.insert(0, os.path.dirname(__file__))

from fastapi import APIRouter, Query, Depends
from database import get_database
from auth_utils import get_current_user
from frameworks import nist_rmf, cis_controls, iso27001, hipaa, pci_dss, soc2
from datetime import datetime, timezone
from typing import List, Dict, Any

router = APIRouter(prefix="/api/frameworks", tags=["Compliance Frameworks"])

_REGISTRY = {
    "nist_csf":       nist_rmf,
    "cis_v8":         cis_controls,
    "iso27001_2022":  iso27001,
    "hipaa":          hipaa,
    "pci_dss":        pci_dss,
    "soc2":           soc2,
}


def _score(results: List[Dict[str, Any]]) -> Dict[str, Any]:
    total = len(results)
    passed = sum(1 for r in results if r["status"] == "pass")
    partial = sum(1 for r in results if r["status"] == "partial")
    failed = sum(1 for r in results if r["status"] == "fail")
    na = sum(1 for r in results if r["status"] == "not_applicable")
    coverage = total - na
    score = round((passed + partial * 0.5) / coverage * 100, 1) if coverage else 0
    return {
        "score": score,
        "passed": passed,
        "partial": partial,
        "failed": failed,
        "not_applicable": na,
        "total": total,
    }


@router.get("")
async def list_frameworks(current_user: dict = Depends(get_current_user)):
    """List all available compliance frameworks with metadata."""
    return {
        "frameworks": [
            {
                "id": "nist_csf",
                "name": nist_rmf.FRAMEWORK_NAME,
                "version": nist_rmf.FRAMEWORK_VERSION,
                "control_count": len(nist_rmf.CONTROLS),
                "description": "NIST Cybersecurity Framework 2.0 — Govern, Identify, Protect, Detect, Respond, Recover",
            },
            {
                "id": "cis_v8",
                "name": cis_controls.FRAMEWORK_NAME,
                "version": cis_controls.FRAMEWORK_VERSION,
                "control_count": len(cis_controls.CONTROLS),
                "description": "Center for Internet Security Controls v8 — 18 control groups",
            },
            {
                "id": "iso27001_2022",
                "name": iso27001.FRAMEWORK_NAME,
                "version": iso27001.FRAMEWORK_VERSION,
                "control_count": len(iso27001.CONTROLS),
                "description": "ISO/IEC 27001:2022 — Annex A controls across 4 themes",
            },
            {
                "id": "hipaa",
                "name": hipaa.FRAMEWORK_NAME,
                "version": hipaa.FRAMEWORK_VERSION,
                "control_count": len(hipaa.CONTROLS),
                "description": "HIPAA / HITECH — Administrative, Physical, and Technical Safeguards + Breach Notification",
            },
            {
                "id": "pci_dss",
                "name": pci_dss.FRAMEWORK_NAME,
                "version": pci_dss.FRAMEWORK_VERSION,
                "control_count": len(pci_dss.CONTROLS),
                "description": "PCI-DSS v4.0 — 12 requirements for cardholder data protection",
            },
            {
                "id": "soc2",
                "name": soc2.FRAMEWORK_NAME,
                "version": soc2.FRAMEWORK_VERSION,
                "control_count": len(soc2.CONTROLS),
                "description": "SOC 2 Type II — AICPA Trust Services Criteria (CC1–CC9, Availability)",
            },
        ]
    }


@router.get("/summary")
async def all_frameworks_summary(current_user: dict = Depends(get_current_user)):
    """Quick score for all frameworks without full control detail."""
    db = get_database()
    summary = {}
    for fid, mod in _REGISTRY.items():
        results = await mod.evaluate_controls(db)
        summary[fid] = {
            "name": mod.FRAMEWORK_NAME,
            **_score(results),
            "evaluated_at": datetime.now(timezone.utc).isoformat(),
        }
    return summary


@router.get("/{framework_id}")
async def evaluate_framework(
    framework_id: str,
    function: str = Query(None, description="Filter by function/theme (e.g. IDENTIFY, Technological)"),
    current_user: dict = Depends(get_current_user),
):
    """Run all checks for a specific framework and return results."""
    if framework_id not in _REGISTRY:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail=f"Framework '{framework_id}' not found. Available: {list(_REGISTRY.keys())}")

    db = get_database()
    mod = _REGISTRY[framework_id]
    results = await mod.evaluate_controls(db)

    if function:
        results = [r for r in results if
                   r.get("function", "").lower() == function.lower() or
                   r.get("theme", "").lower() == function.lower()]

    score = _score(results)
    return {
        "framework_id": framework_id,
        "framework_name": mod.FRAMEWORK_NAME,
        "version": mod.FRAMEWORK_VERSION,
        **score,
        "controls": results,
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
    }


@router.post("/{framework_id}/auto-evidence")
async def collect_auto_evidence(
    framework_id: str,
    current_user: dict = Depends(get_current_user),
):
    """
    Auto-collect evidence for a compliance framework by running all controls and
    persisting passing results as evidence records in MongoDB.
    Returns a summary of evidence items created/updated.
    """
    if framework_id not in _REGISTRY:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail=f"Framework '{framework_id}' not found")

    db = get_database()
    mod = _REGISTRY[framework_id]
    results = await mod.evaluate_controls(db)
    now = datetime.now(timezone.utc).isoformat()
    tenant_id = current_user.get("tenant_id", current_user.get("tenantId", "global"))
    import uuid as _uuid

    created = 0
    updated = 0
    for ctrl in results:
        if ctrl["status"] not in ("pass", "partial"):
            continue
        evidence = {
            "id": f"ev-{framework_id}-{ctrl.get('id', _uuid.uuid4().hex[:8])}",
            "framework": framework_id,
            "framework_name": mod.FRAMEWORK_NAME,
            "control_id": ctrl.get("id"),
            "control_name": ctrl.get("name", ""),
            "control_description": ctrl.get("description", ""),
            "status": ctrl["status"],
            "evidence_type": "automated",
            "collected_at": now,
            "tenant_id": tenant_id,
            "source": ctrl.get("evidence_source", "platform_scan"),
            "details": ctrl.get("details", ctrl.get("evidence", "")),
        }
        res = await db.compliance_evidence.update_one(
            {"id": evidence["id"], "tenant_id": tenant_id},
            {"$set": evidence},
            upsert=True,
        )
        if res.upserted_id:
            created += 1
        else:
            updated += 1

    return {
        "framework_id": framework_id,
        "framework_name": mod.FRAMEWORK_NAME,
        "evidence_created": created,
        "evidence_updated": updated,
        "total_controls_evaluated": len(results),
        "passing_controls": sum(1 for r in results if r["status"] in ("pass", "partial")),
        "collected_at": now,
    }


@router.get("/{framework_id}/gaps")
async def framework_gaps(framework_id: str):
    """Return only failing or partial controls — the actionable gap list."""
    if framework_id not in _REGISTRY:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Framework not found")

    db = get_database()
    mod = _REGISTRY[framework_id]
    results = await mod.evaluate_controls(db)
    gaps = [r for r in results if r["status"] in ("fail", "partial")]

    return {
        "framework_id": framework_id,
        "gap_count": len(gaps),
        "gaps": gaps,
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
    }

"""
Compliance reporting: scoring helpers and shared data-fetching utilities.
"""

from database import get_database

# Status vocabulary legend: maps current internal status values to auditor
# standard vocabulary (Pass/Fail/Partial/No-Data) for Wave 2 renderers.
STATUS_LEGEND = {
    "Compliant":           "Pass",
    "Implemented":         "Pass",
    "Non-Compliant":       "Fail",
    "Not Implemented":     "Fail",
    "Warning":             "Partial",
    "Partially Compliant": "Partial",
    "In Progress":         "Partial",
    "—":                   "No-Data",
}


def _score_status(status: str) -> str:
    """Normalise asset_compliance status to Compliant / Warning / Non-Compliant."""
    s = (status or "").strip()
    if s in ("Compliant", "Pass", "Passed", "Implemented", "pass", "passed"):
        return "Compliant"
    if s in ("Non-Compliant", "Fail", "Failed", "Not Implemented", "fail", "failed"):
        return "Non-Compliant"
    return "Warning"


def _compliance_score(counts: dict) -> float:
    total = counts.get("Compliant", 0) + counts.get("Warning", 0) + counts.get("Non-Compliant", 0)
    if total == 0:
        return 0.0
    return round(counts.get("Compliant", 0) / total * 100, 1)


def _overall_verdict(score: float) -> str:
    if score >= 80:
        return "Compliant"
    if score >= 50:
        return "Partially Compliant"
    return "Non-Compliant"


def _flatten_evidence(evidence_list: list) -> dict:
    """
    Extract display fields from a list of evidence/artifact records.
    Returns: names, urls, descriptions, uploaded_ats, statuses, count,
             auto_count, manual_count.

    Classification rule: automated when systemGenerated is True OR source is
    None (absent); otherwise manual (source=='manual' or systemGenerated False).
    Each name is prefixed with [Auto] or [Manual] for auditor readability.
    """
    names, urls, descs, dates, statuses = [], [], [], [], []
    auto_count = 0
    manual_count = 0
    seen_ids: set = set()
    for e in evidence_list:
        eid = e.get("id") or e.get("url") or e.get("name", "")
        if eid in seen_ids:
            continue
        seen_ids.add(eid)
        is_auto = e.get("systemGenerated") is True or e.get("source") is None
        label = "[Auto]" if is_auto else "[Manual]"
        name = e.get("name") or e.get("filename") or ""
        url  = e.get("url") or ""
        desc = e.get("description") or ""
        date = (e.get("uploadedAt") or e.get("uploaded_at") or
                e.get("date") or e.get("lastUpdated") or "")
        if date and "T" in date:
            date = date[:10]
        status = e.get("status") or ""
        if is_auto:
            auto_count += 1
        else:
            manual_count += 1
        if name:
            names.append(f"{label} {name}")
        if url:
            urls.append(url)
        if desc:
            descs.append(desc)
        if date:
            dates.append(date)
        if status:
            statuses.append(status)
    return {
        "names": names, "urls": urls, "descriptions": descs,
        "uploaded_ats": dates, "statuses": statuses, "count": len(seen_ids),
        "auto_count": auto_count, "manual_count": manual_count,
    }


async def _build_report_data(framework_id: str, tenant_id: str = None):
    """
    Returns:
        framework      – the framework document
        asset_summary  – list of {assetId, hostname, counts, score, verdict}
        control_rows   – list of dicts with control + evidence columns
    """
    db = get_database()

    framework = await db.compliance_frameworks.find_one({"id": framework_id})
    if not framework:
        raise ValueError(f"Framework '{framework_id}' not found")

    controls = framework.get("controls", [])
    control_ids = [c["id"] for c in controls]

    ac_docs = await db.asset_compliance.find(
        {"controlId": {"$in": control_ids}}
    ).to_list(length=10000)

    artifact_docs = await db.compliance_artifacts.find(
        {"control_ids": {"$in": control_ids}}
    ).to_list(length=5000)
    artifact_by_ctrl: dict = {}
    for art in artifact_docs:
        for cid in (art.get("control_ids") or []):
            artifact_by_ctrl.setdefault(cid, []).append(art)

    asset_ids = list({d.get("assetId") for d in ac_docs if d.get("assetId")})
    asset_docs = await db.assets.find(
        {"id": {"$in": asset_ids}}, {"id": 1, "hostname": 1, "_id": 0}
    ).to_list(length=1000)
    hostname_map = {a["id"]: a.get("hostname", a["id"]) for a in asset_docs}

    asset_counts: dict = {}
    for doc in ac_docs:
        aid  = doc.get("assetId", "unknown")
        norm = _score_status(doc.get("status", ""))
        if aid not in asset_counts:
            asset_counts[aid] = {"Compliant": 0, "Warning": 0, "Non-Compliant": 0}
        asset_counts[aid][norm] += 1

    asset_summary = []
    for aid, counts in sorted(asset_counts.items()):
        score = _compliance_score(counts)
        asset_summary.append({
            "Asset ID": aid,
            "Hostname": hostname_map.get(aid, aid),
            "Total Controls": sum(counts.values()),
            "Compliant": counts["Compliant"],
            "Warning": counts["Warning"],
            "Non-Compliant": counts["Non-Compliant"],
            "Score (%)": score,
            "Overall Status": _overall_verdict(score),
        })

    ac_by_key: dict = {}
    for doc in ac_docs:
        key = (doc.get("controlId"), doc.get("assetId", "unknown"))
        ac_by_key[key] = doc

    control_rows = []
    for ctrl in controls:
        cid           = ctrl["id"]
        cname         = ctrl.get("name", "")
        ccat          = ctrl.get("category", "")
        ctrl_status   = ctrl.get("status", "Not Implemented")
        last_reviewed = ctrl.get("lastReviewed", "")
        standalone    = artifact_by_ctrl.get(cid, [])
        matching      = [(k[1], v) for k, v in ac_by_key.items() if k[0] == cid]

        if not matching:
            ev = _flatten_evidence(standalone)
            control_rows.append({
                "Control ID": cid, "Control Name": cname, "Category": ccat,
                "Control Status": ctrl_status,
                "Asset ID": "—", "Hostname": "—", "Asset Status": "—",
                "Evidence Count": ev["count"],
                "Auto Evidence": ev["auto_count"],
                "Manual Evidence": ev["manual_count"],
                "Evidence Names": ", ".join(ev["names"]) if ev["names"] else "None",
                "Evidence URLs": ", ".join(ev["urls"]) if ev["urls"] else "—",
                "Evidence Dates": ", ".join(ev["uploaded_ats"]) if ev["uploaded_ats"] else "—",
                "Evidence Desc": "; ".join(ev["descriptions"]) if ev["descriptions"] else "—",
                "Last Reviewed": last_reviewed,
            })
            continue

        for aid, doc in matching:
            asset_ev = doc.get("evidence", [])
            merged   = asset_ev + [
                a for a in standalone
                if not any(ae.get("id") == a.get("id") for ae in asset_ev)
            ]
            ev = _flatten_evidence(merged)
            control_rows.append({
                "Control ID": cid, "Control Name": cname, "Category": ccat,
                "Control Status": ctrl_status,
                "Asset ID": aid,
                "Hostname": hostname_map.get(aid, aid),
                "Asset Status": _score_status(doc.get("status", "")),
                "Evidence Count": ev["count"],
                "Auto Evidence": ev["auto_count"],
                "Manual Evidence": ev["manual_count"],
                "Evidence Names": ", ".join(ev["names"]) if ev["names"] else "None",
                "Evidence URLs": ", ".join(ev["urls"]) if ev["urls"] else "—",
                "Evidence Dates": ", ".join(ev["uploaded_ats"]) if ev["uploaded_ats"] else "—",
                "Evidence Desc": "; ".join(ev["descriptions"]) if ev["descriptions"] else "—",
                "Last Reviewed": last_reviewed,
            })

    return framework, asset_summary, control_rows

"""Phase 39-05 — Tenant-closed control-evidence tool.

`make_get_control_evidence(tenant_id, db)` wraps the existing
`ai_auditor_endpoints.py` evidence-fetch pattern (`db.asset_compliance.find`
scoped to `controlId`) as a tenant-closed `@tool`, so an agent can look up
evidence records for a specific control without a model-supplied tenant
filter (RESEARCH.md Pitfall B). Neither `tenant_id` nor `db` is exposed as a
tool argument — the returned tool's only model-facing parameter is
`control_id`. Every read is scoped by BOTH `controlId` and `tenantId`
explicitly (never an unfiltered find), independent of whatever ambient
tenant-isolation wrapper `db` may or may not carry.
"""
from langchain_core.tools import tool

NO_EVIDENCE_FOUND = "No evidence found for this control in the tenant's evidence store."


def make_get_control_evidence(tenant_id: str, db):
    """Build a tenant-closed `get_control_evidence` @tool bound to `tenant_id`/`db`."""

    @tool
    async def get_control_evidence(control_id: str) -> str:
        """Look up collected evidence records for a specific compliance control ID.

        Returns evidence tagged "[id: <record id> | asset: <asset id> | name:
        <evidence name>]" for citation, scoped to this tenant's own
        asset-compliance evidence, or an explicit "no evidence" message when
        none is found.
        """
        records = await db.asset_compliance.find(
            {"controlId": control_id, "tenantId": tenant_id}
        ).to_list(length=100)

        if not records:
            return NO_EVIDENCE_FOUND

        blocks = []
        for rec in records:
            rec_id = str(rec.get("_id") or rec.get("id") or "")
            asset_id = rec.get("assetId", "unknown-asset")
            for ev in rec.get("evidence", []) or []:
                content = ev.get("content") or ev.get("details") or ""
                if not content:
                    continue
                ev_name = ev.get("name", "evidence")
                blocks.append(
                    f"[id: {rec_id} | asset: {asset_id} | name: {ev_name}]\n{content}"
                )

        if not blocks:
            return NO_EVIDENCE_FOUND
        return "\n\n".join(blocks)

    return get_control_evidence

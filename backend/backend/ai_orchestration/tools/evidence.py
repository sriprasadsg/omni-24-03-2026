"""Evidence lookup tools for LangChain agents (39-05)."""
import logging
from typing import Any

logger = logging.getLogger(__name__)


def make_get_control_evidence(tenant_id: str, raw_db: Any):
    from langchain.tools import tool

    @tool
    async def get_control_evidence(control_id: str) -> str:
        """Retrieve stored compliance evidence for one control_id.
        Input: a control_id string (e.g. 'CIS-5.2').
        Output: the evidence source, content, and date for each record,
        or 'No evidence recorded for this control.' if none exists."""
        try:
            collection = raw_db.control_evidence
            cursor = collection.find(
                {"control_id": control_id, "tenant_id": tenant_id}
            ).sort("collected_at", -1).limit(10)
            records = await cursor.to_list(length=10)
            if not records:
                return "No evidence recorded for this control."
            lines = []
            for r in records:
                source = r.get("source", "unknown")
                content = r.get("content", r.get("description", ""))[:500]
                date = r.get("collected_at", "unknown")
                lines.append(f"[source: {source} | id: {r.get('_id', 'n/a')} | date: {date}]\n{content}")
            return "\n\n".join(lines)
        except Exception as exc:
            logger.error("get_control_evidence error for tenant=%s control=%s: %s",
                         tenant_id, control_id, exc)
            return "No evidence recorded for this control."

    return get_control_evidence

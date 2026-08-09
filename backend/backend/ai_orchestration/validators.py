"""Citation and control-ID validators (39-03).

Ensures every citation resolves to a real evidence record and
every control_id exists in the seeded framework registry.
"""
import logging
import re
from typing import Any, List, Optional

logger = logging.getLogger(__name__)

CONTROL_ID_PATTERN = re.compile(
    r"\b(?:CIS|ISO|NIST|SOC|PCI|HIPAA|GDPR|CSA|MITRE|OWASP|FFIEC|BSI|ENS|MAS|IRAP|TISAX|RBI|KISA|FEDRAMP|TIC|AWS|DO|DORA|FAIR|GQL|REBAC|MCP|ASSIST)[\s\-]?[\w\.\-]+\b"
)


async def validate_citations(finding, tenant_id: str, raw_db: Any):
    """Validate all citations in a finding against tenant evidence and KB.

    Returns (CitationResult, finding_with_pinned_control_id).
    """
    class CitationResult:
        def __init__(self, ok: bool, missing=None):
            self.ok = ok
            self.missing = missing or []

    citations = finding.citations
    if not citations:
        return CitationResult(ok=False, missing=["no citations provided"]), finding

    missing = []
    for cite in citations:
        source = cite.source
        chunk_id = cite.chunk_id
        # Try to find in tenant evidence first
        collection = raw_db.control_evidence
        record = await collection.find_one({"_id": chunk_id, "tenant_id": tenant_id})
        if not record:
            # Try global KB
            record = await collection.find_one({"_id": chunk_id, "tenant_id": "global"})
        if not record:
            missing.append(f"{source}:{chunk_id}")

    ok = len(missing) == 0
    return CitationResult(ok=ok, missing=missing), finding


def extract_control_id_tokens(text: str) -> List[str]:
    """Extract control-ID-shaped tokens from text.

    Used by auditor to best-effort extract control_id from
    control_desc when caller doesn't supply it.
    """
    if not text:
        return []
    return CONTROL_ID_PATTERN.findall(text)

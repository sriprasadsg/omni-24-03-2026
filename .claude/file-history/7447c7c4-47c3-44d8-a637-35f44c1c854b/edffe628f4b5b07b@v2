"""
Compliance Document Validator
==============================
Extracts text from uploaded evidence files and uses the configured AI provider
to assess whether the document is legitimate evidence for a given compliance control.

Supports:
  - PDF  : regex-based text extraction from content streams (no extra library needed)
  - DOCX : stdlib zipfile + xml.etree (DOCX is a ZIP of XML files)
  - XLSX : openpyxl (already in requirements)
  - Images: filename + description only (no OCR)

Returns a ValidationResult dict:
  {
    "verdict":    "RELEVANT" | "IRRELEVANT" | "UNCLEAR" | "SKIPPED",
    "confidence": 0.0 – 1.0,
    "reasoning":  "one-sentence explanation",
    "text_extracted": true/false,
    "text_preview": "first 200 chars of extracted text or ''"
  }

The verdict is advisory — callers decide whether to block or warn.
"""

import io
import re
import logging
import zipfile
import xml.etree.ElementTree as ET
from typing import Optional

logger = logging.getLogger("compliance_doc_validator")

# Controls descriptions — used to give the LLM context about what a control requires.
# These are short human-readable summaries mapped from common control ID prefixes.
_CONTROL_HINTS: dict[str, str] = {
    # ISO 27001
    "A.5": "information security policies, organisation, roles and responsibilities",
    "A.6": "organisation of information security, mobile devices, teleworking",
    "A.7": "human resource security — screening, terms, awareness, disciplinary process",
    "A.8": "asset management — inventory, ownership, acceptable use, media handling",
    "A.9": "access control — business requirements, user management, privileges",
    "A.10": "cryptography — key management, encryption policies",
    "A.11": "physical and environmental security — secure areas, equipment",
    "A.12": "operations security — malware, logging, patch management, backup",
    "A.13": "communications security — network controls, information transfer",
    "A.14": "system acquisition, development and maintenance",
    "A.15": "supplier relationships — security in contracts, monitoring",
    "A.16": "information security incident management",
    "A.17": "business continuity management",
    "A.18": "compliance — legal, regulatory, standards",
    # PCI-DSS
    "PCI-1": "network security controls, firewalls, network segmentation",
    "PCI-2": "apply secure configurations to all system components",
    "PCI-3": "protect stored account data and encryption of cardholder data",
    "PCI-4": "protect cardholder data in transit with strong cryptography",
    "PCI-5": "protect all systems against malware, anti-virus",
    "PCI-6": "develop and maintain secure systems and software",
    "PCI-7": "restrict access by business need to know",
    "PCI-8": "identify users and authenticate access",
    "PCI-9": "restrict physical access to cardholder data",
    "PCI-10": "log and monitor all access to system components",
    "PCI-11": "test security of systems and networks regularly",
    "PCI-12": "support information security with organisational policies and programs",
    # SOX
    "SOX": "financial reporting controls, audit trails, segregation of duties, access to financial systems",
    # NIST CSF
    "ID": "identify — asset management, risk assessment, governance",
    "PR": "protect — access control, awareness, data security, maintenance",
    "DE": "detect — anomalies, security monitoring, detection processes",
    "RS": "respond — response planning, communications, analysis, containment",
    "RC": "recover — recovery planning, improvements, communications",
    # SOC 2 CC
    "CC": "common criteria — logical access, change management, risk management, monitoring",
    # CISSP
    "CISSP": "CISSP domain — access control, cryptography, network, software, operations, physical, disaster recovery",
    # SWIFT
    "SWIFT": "SWIFT customer security programme — network isolation, system hardening, access management",
    # NIS2
    "NIS2": "NIS2 directive — risk management, incident handling, supply chain security, cryptography",
    # DPDP
    "DPDP": "India Digital Personal Data Protection Act — consent, data principal rights, fiduciary obligations",
}


def _control_hint(control_id: str) -> str:
    """Return a human-readable hint for the control, used in the AI prompt."""
    cid = control_id.upper()
    for prefix, hint in _CONTROL_HINTS.items():
        if cid.startswith(prefix.upper()):
            return hint
    return "compliance security control"


# ---------------------------------------------------------------------------
# Text extraction helpers
# ---------------------------------------------------------------------------

def _extract_pdf_text(content: bytes, max_chars: int = 3000) -> str:
    """
    Minimal PDF text extraction using stdlib only.
    Scans for text between BT..ET markers (PDF text objects) and extracts
    parenthesised string literals from Tj / TJ operators.
    Accurate enough for short policy docs; gibberish for encrypted or image-only PDFs.
    """
    try:
        raw = content.decode("latin-1", errors="replace")
        # Extract parenthesised strings (Tj / TJ operators use them)
        strings = re.findall(r'\(([^()\\]{1,200})\)', raw)
        # Filter out binary noise: keep tokens that are mostly printable ASCII
        clean = []
        for s in strings:
            printable = sum(32 <= ord(c) < 127 for c in s)
            if printable / max(len(s), 1) >= 0.7 and len(s.strip()) > 2:
                clean.append(s.strip())
        return " ".join(clean)[:max_chars]
    except Exception as exc:
        logger.debug("PDF extraction failed: %s", exc)
        return ""


def _extract_docx_text(content: bytes, max_chars: int = 3000) -> str:
    """Extract text from a DOCX file using stdlib zipfile + xml.etree."""
    try:
        buf = io.BytesIO(content)
        with zipfile.ZipFile(buf) as zf:
            names = zf.namelist()
            # word/document.xml is the main body; also grab headers/footers
            targets = [n for n in names if re.match(r'word/(document|header|footer)\d*\.xml', n)]
            if not targets:
                targets = [n for n in names if n.endswith(".xml")][:3]
            parts = []
            ns = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
            for target in targets:
                xml_bytes = zf.read(target)
                root = ET.fromstring(xml_bytes)
                for t_elem in root.iter(f"{ns}t"):
                    if t_elem.text:
                        parts.append(t_elem.text)
            return " ".join(parts)[:max_chars]
    except Exception as exc:
        logger.debug("DOCX extraction failed: %s", exc)
        return ""


def _extract_xlsx_text(content: bytes, max_chars: int = 3000) -> str:
    """Extract cell text from an XLSX file using openpyxl."""
    try:
        import openpyxl
        buf = io.BytesIO(content)
        wb = openpyxl.load_workbook(buf, read_only=True, data_only=True)
        parts = []
        for sheet in wb.worksheets:
            for row in sheet.iter_rows(max_row=100, values_only=True):
                for cell in row:
                    if cell is not None and str(cell).strip():
                        parts.append(str(cell).strip())
        wb.close()
        return " ".join(parts)[:max_chars]
    except Exception as exc:
        logger.debug("XLSX extraction failed: %s", exc)
        return ""


def extract_text(file_content: bytes, file_ext: str) -> tuple[str, bool]:
    """
    Extract human-readable text from uploaded file bytes.
    Returns (text, was_extracted).
    was_extracted=False means we fell back to an empty string (e.g. image).
    """
    ext = file_ext.lower()
    text = ""
    if ext == ".pdf":
        text = _extract_pdf_text(file_content)
    elif ext in (".docx",):
        text = _extract_docx_text(file_content)
    elif ext in (".xlsx",):
        text = _extract_xlsx_text(file_content)
    # PNG/JPG: no extraction without OCR
    return text.strip(), bool(text.strip())


# ---------------------------------------------------------------------------
# AI validation
# ---------------------------------------------------------------------------

async def validate_document(
    file_content: bytes,
    file_ext: str,
    filename: str,
    description: str,
    control_id: str,
    department: str,
) -> dict:
    """
    Assess whether the uploaded document is legitimate evidence for the given control.

    Flow:
      1. Extract text from the document (PDF / DOCX / XLSX / image).
      2. Build a short prompt describing the control and the document.
      3. Call ai_service.generate_text() to get RELEVANT / IRRELEVANT / UNCLEAR.
      4. Parse the verdict and return a ValidationResult dict.

    The upload is NEVER blocked by this function — callers use the result
    to display a warning or badge but always allow saving.
    """
    result: dict = {
        "verdict": "SKIPPED",
        "confidence": 0.0,
        "reasoning": "AI not configured — no validation performed.",
        "text_extracted": False,
        "text_preview": "",
    }

    try:
        from ai_service import ai_service  # deferred to avoid circular import at module load

        if not ai_service.is_configured:
            await ai_service.initialize()

        if not ai_service.is_configured:
            result["reasoning"] = "AI provider not configured — skipping validation."
            return result

        text, was_extracted = extract_text(file_content, file_ext)
        result["text_extracted"] = was_extracted

        # Build the evidence description for the LLM
        if was_extracted and text:
            evidence_snippet = text[:1500]
            result["text_preview"] = text[:200]
        else:
            # Fall back to filename + description as the "evidence" the LLM sees
            evidence_snippet = f"Filename: {filename}\nUser description: {description or 'No description provided.'}"
            result["text_preview"] = evidence_snippet[:200]

        hint = _control_hint(control_id)
        prompt = f"""You are a compliance auditor. Assess whether the following document is genuine, relevant evidence for the compliance control described below.

Control ID: {control_id}
Control area: {hint}
Uploaded by: {department} department
User description: {description or 'Not provided'}

Document content (excerpt):
{evidence_snippet}

Respond with EXACTLY two lines:
Line 1: VERDICT: RELEVANT  OR  VERDICT: IRRELEVANT  OR  VERDICT: UNCLEAR
Line 2: REASONING: one sentence explaining your assessment (max 150 chars)

Do not add any other text."""

        raw_response = await ai_service.generate_text(prompt, source="compliance_doc_validator")

        # Parse the two-line response
        lines = [line.strip() for line in raw_response.strip().splitlines() if line.strip()]
        verdict_line = next((l for l in lines if l.upper().startswith("VERDICT:")), "")
        reasoning_line = next((l for l in lines if l.upper().startswith("REASONING:")), "")

        verdict_word = verdict_line.split(":", 1)[-1].strip().upper() if verdict_line else ""
        if verdict_word in ("RELEVANT", "IRRELEVANT", "UNCLEAR"):
            result["verdict"] = verdict_word
        else:
            result["verdict"] = "UNCLEAR"

        result["reasoning"] = reasoning_line.split(":", 1)[-1].strip() if reasoning_line else raw_response[:200]

        # Assign rough confidence: higher when text was actually extracted
        if result["verdict"] == "RELEVANT":
            result["confidence"] = 0.85 if was_extracted else 0.55
        elif result["verdict"] == "IRRELEVANT":
            result["confidence"] = 0.80 if was_extracted else 0.50
        else:
            result["confidence"] = 0.40

        logger.info(
            "[DocValidator] control=%s verdict=%s confidence=%.2f extracted=%s",
            control_id, result["verdict"], result["confidence"], was_extracted,
        )

    except Exception as exc:
        logger.warning("[DocValidator] Validation error: %s", exc)
        result["verdict"] = "SKIPPED"
        result["reasoning"] = f"Validation skipped due to error: {type(exc).__name__}"

    return result

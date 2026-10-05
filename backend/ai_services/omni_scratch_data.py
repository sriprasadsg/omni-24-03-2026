"""
Training data for the from-scratch Omni model (omni_llm_scratch.py).

Sources (per the agreed scope — no live platform or user data):
  1. Project documentation (docs/**/*.md, README.md).
  2. Security knowledge distilled from the local open-source teacher model (Ollama):
     a short explanatory passage plus Q&A pairs for each topic. Generation appends to
     a JSONL file and is resumable — topics already done are skipped.
The tokenizer (byte-level BPE) is trained on this corpus too, so nothing pretrained is used.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

import requests

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = Path(os.getenv("OMNI_SCRATCH_DIR", REPO_ROOT / "backend" / "data" / "omni_scratch"))
GENERATED_PATH = DATA_DIR / "generated.jsonl"
TOKENIZER_PATH = DATA_DIR / "tokenizer.json"
CHECKPOINT_PATH = DATA_DIR / "omni_scratch.pt"
STATUS_PATH = DATA_DIR / "status.json"

EOT, USER, ASSISTANT, PAD = "<|endoftext|>", "<|user|>", "<|assistant|>", "<|pad|>"
SPECIAL_TOKENS = [EOT, USER, ASSISTANT, PAD]

TEACHER_URL = os.getenv("OMNI_TEACHER_URL", "http://127.0.0.1:11434")
TEACHER_MODEL = os.getenv("OMNI_TEACHER_MODEL", "llama3.2:3b")

SECURITY_TOPICS = [
    # Detection & response
    "Endpoint Detection and Response (EDR)", "Extended Detection and Response (XDR)",
    "Security Information and Event Management (SIEM)", "User and Entity Behavior Analytics (UEBA)",
    "Security Orchestration, Automation and Response (SOAR)", "Managed Detection and Response (MDR)",
    "Network Detection and Response (NDR)", "Indicators of Compromise (IOCs)", "Threat hunting",
    "YARA rules", "Sigma detection rules", "File integrity monitoring (FIM)", "Alert triage in a SOC",
    "False positives in security alerting", "Incident response lifecycle", "Digital forensics basics",
    # Attack techniques (MITRE ATT&CK)
    "The MITRE ATT&CK framework", "Phishing", "Spear phishing", "Ransomware", "Credential dumping",
    "Pass-the-Hash attacks", "Kerberoasting", "Lateral movement", "Privilege escalation",
    "Persistence via scheduled tasks", "Persistence via registry Run keys", "Process injection",
    "Command and control (C2) beaconing", "DNS tunneling", "Data exfiltration", "Living off the land binaries",
    "Supply chain attacks", "Brute-force and password spraying attacks", "SQL injection", "Cross-site scripting (XSS)",
    "Server-side request forgery (SSRF)", "Insider threats", "Business email compromise",
    # Vulnerability & exposure management
    "Vulnerability management", "CVE identifiers", "The CVSS scoring system", "Patch management",
    "Zero-day vulnerabilities", "Attack surface management", "Attack path analysis", "Penetration testing",
    "Dynamic application security testing (DAST)", "Static application security testing (SAST)",
    "Software composition analysis (SCA)", "Software bill of materials (SBOM)",
    # Identity & access
    "Multi-factor authentication (MFA)", "Passkeys and WebAuthn", "Privileged access management (PAM)",
    "Just-in-time access", "The principle of least privilege", "Role-based access control (RBAC)",
    "Single sign-on with SAML", "Conditional access policies", "Access reviews", "Zero trust architecture",
    # Cloud, network, data
    "Cloud security posture management (CSPM)", "Data security posture management (DSPM)",
    "Kubernetes security", "Container image scanning", "Infrastructure as code (IaC) security scanning",
    "Network segmentation", "Firewalls", "Intrusion detection and prevention systems (IDS/IPS)",
    "TLS and HTTPS", "Public key infrastructure (PKI) and certificates", "Secrets management",
    "Encryption at rest and in transit", "Data loss prevention (DLP)", "Data classification",
    "Email security (SPF, DKIM and DMARC)", "API security", "Web application firewalls (WAF)",
    "Mobile device management (MDM)", "Configuration drift", "CIS benchmarks",
    # Governance, risk & compliance
    "SOC 2", "ISO 27001", "NIST Cybersecurity Framework", "PCI DSS", "HIPAA security rule", "GDPR",
    "Compliance evidence collection", "Security risk registers", "Third-party vendor risk management",
    "Security awareness training", "Backup and disaster recovery (RPO and RTO)",
    "Business continuity planning", "Security audit logging", "Data retention policies",
    "AI governance and model risk", "Shadow IT and shadow AI",
]


# ── Corpus: project docs ───────────────────────────────────────────────────────

def collect_docs() -> List[str]:
    """Project documentation as plain-ish text (markdown kept; code fences dropped)."""
    paths = sorted((REPO_ROOT / "docs").rglob("*.md")) + [REPO_ROOT / "README.md"]
    texts = []
    for path in paths:
        if path.is_file():
            text = re.sub(r"```.*?```", "", path.read_text(encoding="utf-8", errors="replace"), flags=re.S)
            text = re.sub(r"\n{3,}", "\n\n", text).strip()
            if len(text) > 200:
                texts.append(text)
    return texts


# ── Teacher distillation (Ollama) ──────────────────────────────────────────────

def _ask_teacher(prompt: str, json_mode: bool = False, timeout: int = 300) -> str:
    payload = {"model": TEACHER_MODEL, "prompt": prompt, "stream": False,
               "options": {"temperature": 0.4, "num_predict": 450}}
    if json_mode:
        payload["format"] = "json"
    resp = requests.post(f"{TEACHER_URL}/api/generate", json=payload, timeout=timeout)
    resp.raise_for_status()
    return resp.json().get("response", "").strip()


def _load_generated() -> List[Dict]:
    if not GENERATED_PATH.exists():
        return []
    rows = []
    for line in GENERATED_PATH.read_text(encoding="utf-8").splitlines():
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue  # tolerate a partially written last line
    return rows


def _clean_qa(pairs: Iterable[Dict], seen_q: set) -> List[Tuple[str, str]]:
    out = []
    for pair in pairs:
        if not isinstance(pair, dict):
            continue
        q = str(pair.get("q") or pair.get("question") or "").strip()
        a = str(pair.get("a") or pair.get("answer") or "").strip()
        key = hashlib.sha1(q.lower().encode()).hexdigest()
        if 10 <= len(q) <= 300 and 30 <= len(a) <= 1200 and key not in seen_q:
            seen_q.add(key)
            out.append((q, a))
    return out


def generate_teacher_data(max_topics: int = 0, progress=None) -> int:
    """Distil passages + Q&A from the teacher for each topic not yet done. Returns rows added."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    existing = _load_generated()
    done = {(r["topic"], r["kind"]) for r in existing}
    seen_q = {hashlib.sha1(r["q"].lower().encode()).hexdigest() for r in existing if r["kind"] == "qa"}
    # Curated security topics only: the teacher knows nothing about this project, so asking
    # it about project-specific headings would produce invented answers. Docs are used as-is.
    topics = list(SECURITY_TOPICS)
    if max_topics:
        topics = topics[:max_topics]
    added = 0
    with GENERATED_PATH.open("a", encoding="utf-8") as out:
        for i, topic in enumerate(topics, 1):
            if progress:
                progress(i, len(topics), topic)
            try:
                if (topic, "passage") not in done:
                    text = _ask_teacher(
                        f"Write a clear, factual explanation of '{topic}' for a security analyst in about "
                        "150 words. Plain prose, no headings, no lists, no preamble."
                    )
                    if len(text) > 200:
                        out.write(json.dumps({"topic": topic, "kind": "passage", "text": text}) + "\n")
                        added += 1
                if (topic, "qa") not in done:
                    raw = _ask_teacher(
                        f"Write 3 different question-and-answer pairs a security analyst might ask about "
                        f"'{topic}'. Answers must be accurate and 2-3 sentences long. Respond only as JSON: "
                        '{"pairs": [{"q": "...", "a": "..."}]}',
                        json_mode=True,
                    )
                    try:
                        pairs = json.loads(raw).get("pairs", [])
                    except (json.JSONDecodeError, AttributeError):
                        pairs = []
                    for q, a in _clean_qa(pairs, seen_q):
                        out.write(json.dumps({"topic": topic, "kind": "qa", "q": q, "a": a}) + "\n")
                        added += 1
                out.flush()
            except requests.RequestException as exc:
                logger.warning("[OmniScratch] teacher failed on %r: %s", topic, exc)
    return added


# ── Formatting & tokenizer ─────────────────────────────────────────────────────

def format_qa(question: str, answer: str = "") -> str:
    """Chat template. With an empty answer it is the generation prompt."""
    prompt = f"{USER}{question.strip()}\n{ASSISTANT}"
    return f"{prompt}{answer.strip()}{EOT}" if answer else prompt


def corpus() -> Tuple[List[str], List[Tuple[str, str]]]:
    """(pretraining texts, Q&A pairs)."""
    rows = _load_generated()
    texts = collect_docs() + [r["text"] for r in rows if r["kind"] == "passage"]
    qa = [(r["q"], r["a"]) for r in rows if r["kind"] == "qa"]
    return texts, qa


def train_tokenizer(texts: List[str], vocab_size: int = 8000):
    from tokenizers import Tokenizer, decoders, models, pre_tokenizers, trainers

    tok = Tokenizer(models.BPE())
    tok.pre_tokenizer = pre_tokenizers.ByteLevel(add_prefix_space=False)
    tok.decoder = decoders.ByteLevel()
    trainer = trainers.BpeTrainer(
        vocab_size=vocab_size, min_frequency=2, special_tokens=SPECIAL_TOKENS,
        initial_alphabet=pre_tokenizers.ByteLevel.alphabet(),
    )
    tok.train_from_iterator(texts, trainer=trainer)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    tok.save(str(TOKENIZER_PATH))
    return tok


def load_tokenizer():
    from tokenizers import Tokenizer

    return Tokenizer.from_file(str(TOKENIZER_PATH))

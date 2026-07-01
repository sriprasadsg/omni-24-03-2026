"""
YARA Scanner Helper
Wraps yara-python when available; falls back to string-pattern matching.
Rules are loaded from a `yara_rules/` directory co-located with this file.
"""
import os
import logging
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

# Directory containing .yar rule files (bundled alongside the agent)
_RULES_DIR = os.path.join(os.path.dirname(__file__), "yara_rules")

# ── Inline fallback rules (string patterns only, no byte sequences) ──────────
# Mirrors the intent of the .yar files using simple substring matching.
_INLINE_RULES: List[Dict[str, Any]] = [
    {
        "rule": "MimikatzSignatures",
        "severity": "critical",
        "family": "credential_dumper",
        "mitre": "T1003.001",
        "patterns": ["mimikatz", "mimilib", "sekurlsa::", "privilege::debug",
                     "lsadump::", "kerberos::ptt", "token::elevate", "benjamin delpy", "gentilkiwi"],
        "match_any": True,
    },
    {
        "rule": "LaZagneCredentialDumper",
        "severity": "critical",
        "family": "credential_dumper",
        "mitre": "T1555",
        "patterns": ["lazagne", "aesmodeofoperationcbc", "credentialmanager", "passwordmgr"],
        "match_any": True,
    },
    {
        "rule": "RansomwareGeneric",
        "severity": "critical",
        "family": "ransomware",
        "mitre": "T1486",
        "patterns": [".locked", ".crypted", ".encrypted", ".crypt",
                     "bitcoin", "your files have been encrypted", "send bitcoin",
                     "readme_decrypt", "how_to_decrypt"],
        "match_any": True,
        "match_count": 2,
    },
    {
        "rule": "WannaCryIndicators",
        "severity": "critical",
        "family": "WannaCry",
        "mitre": "T1486",
        "patterns": ["wannacry", "wanacry", "wanacrypt0r", ".wcry", ".wncry",
                     "mswinzonescachecountermutexA"],
        "match_any": True,
    },
    {
        "rule": "ProcessInjectionAPIs",
        "severity": "high",
        "family": "injector",
        "mitre": "T1055",
        "patterns": ["virtualallocex", "writeprocessmemory", "createremotethread",
                     "ntcreatethreadex", "rtlcreateuserthread", "queueuserapc",
                     "setwindowshookex", "ntmapviewofsection", "zwunmapviewofsection"],
        "match_any": False,
        "match_count": 3,
    },
    {
        "rule": "ReflectiveDLLInjection",
        "severity": "critical",
        "family": "injector",
        "mitre": "T1055.001",
        "patterns": ["reflectiveloader"],
        "match_any": True,
    },
]


class YaraScanner:
    """
    Scan file content or process names for malware signatures.

    Priority:
      1. yara-python compiled rules (full accuracy)
      2. Inline string-pattern matching (fallback, no binary sequences)
    """

    def __init__(self):
        self._yara_rules = None
        self._yara_available = False
        self._try_load_yara()

    def _try_load_yara(self) -> None:
        try:
            import yara  # type: ignore
            rule_files = {}
            if os.path.isdir(_RULES_DIR):
                for fname in os.listdir(_RULES_DIR):
                    if fname.endswith(".yar") or fname.endswith(".yara"):
                        ns = os.path.splitext(fname)[0]
                        rule_files[ns] = os.path.join(_RULES_DIR, fname)
            if rule_files:
                self._yara_rules = yara.compile(filepaths=rule_files)
                self._yara_available = True
                logger.info("[YaraScanner] Loaded %d YARA rule files via yara-python", len(rule_files))
            else:
                logger.warning("[YaraScanner] yara-python available but no .yar files found in %s", _RULES_DIR)
        except ImportError:
            logger.info("[YaraScanner] yara-python not installed — using string-pattern fallback")
        except Exception as exc:
            logger.warning("[YaraScanner] Failed to compile YARA rules: %s — using fallback", exc)

    def scan_file(self, filepath: str) -> List[Dict[str, Any]]:
        """Scan a file path and return list of matched rule dicts."""
        try:
            if self._yara_available and self._yara_rules:
                return self._yara_scan_file(filepath)
            return self._fallback_scan_file(filepath)
        except Exception as exc:
            logger.debug("[YaraScanner] scan_file error on %s: %s", filepath, exc)
            return []

    def scan_string(self, data: str) -> List[Dict[str, Any]]:
        """Scan arbitrary text (e.g. process name, command line) against rules."""
        lower = data.lower()
        matches = []
        for rule in _INLINE_RULES:
            hit_count = sum(1 for p in rule["patterns"] if p.lower() in lower)
            required = 1 if rule.get("match_any", True) else rule.get("match_count", 1)
            if hit_count >= required:
                matches.append({
                    "rule": rule["rule"],
                    "severity": rule["severity"],
                    "family": rule["family"],
                    "mitre": rule["mitre"],
                    "scan_type": "string_match",
                })
        return matches

    # ── YARA-python path ──────────────────────────────────────────────────────

    def _yara_scan_file(self, filepath: str) -> List[Dict[str, Any]]:
        import yara  # type: ignore
        matches_raw = self._yara_rules.match(filepath)
        results = []
        for m in matches_raw:
            meta = m.meta or {}
            results.append({
                "rule": m.rule,
                "severity": meta.get("severity", "high"),
                "family": meta.get("family", meta.get("tool", "unknown")),
                "mitre": meta.get("mitre", ""),
                "scan_type": "yara",
            })
        return results

    # ── String-pattern fallback ───────────────────────────────────────────────

    def _fallback_scan_file(self, filepath: str) -> List[Dict[str, Any]]:
        try:
            with open(filepath, "rb") as fh:
                raw = fh.read(512 * 1024)  # first 512 KB
            content = raw.decode("latin-1", errors="replace").lower()
        except OSError:
            return []

        matches = []
        for rule in _INLINE_RULES:
            hit_count = sum(1 for p in rule["patterns"] if p.lower() in content)
            required = 1 if rule.get("match_any", True) else rule.get("match_count", 1)
            if hit_count >= required:
                matches.append({
                    "rule": rule["rule"],
                    "severity": rule["severity"],
                    "family": rule["family"],
                    "mitre": rule["mitre"],
                    "scan_type": "string_match",
                })
        return matches


# Module-level singleton
_scanner: YaraScanner | None = None


def get_yara_scanner() -> YaraScanner:
    global _scanner
    if _scanner is None:
        _scanner = YaraScanner()
    return _scanner

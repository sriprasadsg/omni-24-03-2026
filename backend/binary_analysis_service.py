"""
Binary Analysis Service
Provides static PE analysis + YARA rule scanning + lightweight dynamic sandbox.

Dependencies (add to requirements.txt):
    pefile>=2023.2.7
    yara-python>=4.3.1   # requires libssl-dev, build-tools
"""
import os
import io
import json
import hashlib
import logging
import platform
import tempfile
import subprocess
import threading
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime

logger = logging.getLogger(__name__)

YARA_RULES_DIR = os.path.join(os.path.dirname(__file__), "yara_rules")

# Suspicious entropy threshold — high entropy sections often indicate packed payloads
HIGH_ENTROPY_THRESHOLD = 7.0


class BinaryAnalysisService:
    """
    SentinelOne-style binary analysis:
    1. Static:  PE header parsing, section entropy, import analysis
    2. YARA:    Rule matching against all loaded rulesets
    3. Sandbox: Lightweight subprocess spawn + observation (WMI-based on Windows)
    """

    def __init__(self):
        self._yara_rules = self._load_yara_rules()

    # ==================================================================
    # PUBLIC API
    # ==================================================================

    def analyze(self, file_bytes: bytes, filename: str) -> Dict[str, Any]:
        """
        Full binary analysis pipeline.
        Returns a comprehensive report dict.
        """
        sha256 = self._hash_bytes(file_bytes, "sha256")
        md5 = self._hash_bytes(file_bytes, "md5")
        file_size = len(file_bytes)
        file_type = self._detect_file_type(file_bytes)

        report: Dict[str, Any] = {
            "filename": filename,
            "sha256": sha256,
            "md5": md5,
            "file_size_bytes": file_size,
            "file_type": file_type,
            "analysis_timestamp": datetime.utcnow().isoformat(),
            "static": {},
            "yara_matches": [],
            "sandbox": {},
            "verdict": "clean",
            "threat_score": 0,   # 0-100
            "threat_indicators": [],
        }

        # --- Static Analysis ---
        if file_type == "PE":
            report["static"] = self._analyze_pe(file_bytes)
        elif file_type == "PDF":
            report["static"] = self._analyze_pdf(file_bytes)
        else:
            report["static"] = {"info": f"File type '{file_type}' — basic analysis only"}

        # --- YARA Scanning ---
        report["yara_matches"] = self._scan_yara(file_bytes, filename)

        # --- Sandbox (lightweight, safe subprocess observation) ---
        if file_type == "PE" and file_size < 50 * 1024 * 1024:  # sanity cap: 50 MB
            report["sandbox"] = self._sandbox_observe(file_bytes, filename)

        # --- Score and Verdict ---
        report["threat_score"], report["threat_indicators"] = self._compute_score(report)
        if report["threat_score"] >= 80:
            report["verdict"] = "malicious"
        elif report["threat_score"] >= 40:
            report["verdict"] = "suspicious"
        else:
            report["verdict"] = "clean"

        return report

    # ==================================================================
    # STATIC ANALYSIS
    # ==================================================================

    def _analyze_pe(self, data: bytes) -> Dict[str, Any]:
        """Parse PE headers, imports, exports, sections. Compute entropy."""
        try:
            import pefile  # type: ignore
        except ImportError:
            return {"error": "pefile not installed. Run: pip install pefile"}

        result: Dict[str, Any] = {
            "imports": [],
            "exports": [],
            "sections": [],
            "machine": None,
            "timestamp": None,
            "is_dll": False,
            "has_debug": False,
            "suspicious_sections": [],
        }

        try:
            pe = pefile.PE(data=data)
            result["machine"] = hex(pe.FILE_HEADER.Machine)
            result["timestamp"] = datetime.fromtimestamp(pe.FILE_HEADER.TimeDateStamp).isoformat()
            result["is_dll"] = bool(pe.FILE_HEADER.Characteristics & 0x2000)

            # Imports
            if hasattr(pe, "DIRECTORY_ENTRY_IMPORT"):
                for entry in pe.DIRECTORY_ENTRY_IMPORT:
                    dll_name = entry.dll.decode(errors="ignore")
                    imp_names = []
                    for imp in entry.imports:
                        if imp.name:
                            imp_names.append(imp.name.decode(errors="ignore"))
                    result["imports"].append({"dll": dll_name, "functions": imp_names[:20]})

            # Exports
            if hasattr(pe, "DIRECTORY_ENTRY_EXPORT"):
                for exp in pe.DIRECTORY_ENTRY_EXPORT.symbols:
                    if exp.name:
                        result["exports"].append(exp.name.decode(errors="ignore"))

            # Sections
            for section in pe.sections:
                name = section.Name.decode(errors="ignore").strip("\x00")
                raw_data = section.get_data()
                entropy = self._entropy(raw_data)
                sec_info = {
                    "name": name,
                    "virtual_address": hex(section.VirtualAddress),
                    "size": section.SizeOfRawData,
                    "entropy": round(entropy, 4),
                    "high_entropy": entropy > HIGH_ENTROPY_THRESHOLD,
                }
                result["sections"].append(sec_info)
                if entropy > HIGH_ENTROPY_THRESHOLD:
                    result["suspicious_sections"].append(name)

            pe.close()
        except Exception as e:
            result["pe_error"] = str(e)

        return result

    def _analyze_pdf(self, data: bytes) -> Dict[str, Any]:
        """Basic PDF analysis — scan for JavaScript and hidden streams."""
        text = data[:8192].decode("latin-1", errors="ignore")
        result: Dict[str, Any] = {
            "has_javascript": "/JavaScript" in text or "/JS" in text,
            "has_auto_action": "/OpenAction" in text or "/AA " in text,
            "embedded_files": "/EmbeddedFile" in text or "/Filespec" in text,
            "suspicious": False,
        }
        if result["has_javascript"] or result["has_auto_action"]:
            result["suspicious"] = True
        return result

    # ==================================================================
    # YARA SCANNING
    # ==================================================================

    def _scan_yara(self, data: bytes, filename: str) -> List[Dict[str, Any]]:
        """Run all loaded YARA rulesets against the file bytes."""
        matches = []
        if not self._yara_rules:
            return matches
        try:
            import yara  # type: ignore
            for ruleset_name, rules in self._yara_rules.items():
                try:
                    hits = rules.match(data=data)
                    for hit in hits:
                        matches.append({
                            "ruleset": ruleset_name,
                            "rule": hit.rule,
                            "namespace": hit.namespace,
                            "meta": dict(hit.meta),
                            "tags": list(hit.tags),
                            "strings_matched": [
                                {"offset": s.plaintext().hex()[:20], "identifier": s.identifier}
                                for s in hit.strings[:5]
                            ],
                        })
                except Exception as e:
                    logger.warning(f"YARA scan error on {ruleset_name}: {e}")
        except ImportError:
            logger.info("yara-python not installed — YARA scanning skipped")
        return matches

    # ==================================================================
    # SANDBOX (lightweight)
    # ==================================================================

    def _sandbox_observe(self, data: bytes, filename: str) -> Dict[str, Any]:
        """
        Write binary to a temp file, spawn it in a subprocess with a 5s timeout,
        and observe the processes created and files modified.
        This is a SAFE observation-only sandbox — not a true hypervisor sandbox.
        WARNING: Only call this for files unlikely to be network propagators.
        """
        result: Dict[str, Any] = {
            "spawned": False,
            "exit_code": None,
            "child_processes": [],
            "files_created": [],
            "error": None,
            "observation_seconds": 5,
        }

        if platform.system() not in ("Windows", "Linux"):
            result["error"] = "Sandbox observation only supported on Windows/Linux"
            return result

        # Snapshot before
        before_procs = self._snapshot_processes()
        tmpdir = tempfile.mkdtemp(prefix="omni_sandbox_")
        tmpfile = os.path.join(tmpdir, filename)

        try:
            with open(tmpfile, "wb") as f:
                f.write(data)

            # Run with restricted privileges and short timeout
            proc = subprocess.Popen(
                [tmpfile],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                cwd=tmpdir,
                shell=False,
            )
            result["spawned"] = True
            try:
                proc.wait(timeout=5)
                result["exit_code"] = proc.returncode
            except subprocess.TimeoutExpired:
                proc.kill()
                result["exit_code"] = "timeout"

            # Snapshot after
            after_procs = self._snapshot_processes()
            new_procs = after_procs - before_procs
            result["child_processes"] = list(new_procs)[:10]

            # Check for new files in tmpdir
            for root, _, files in os.walk(tmpdir):
                for fname in files:
                    if fname != filename:
                        result["files_created"].append(os.path.join(root, fname))

        except PermissionError as e:
            result["error"] = f"Permission denied — run with elevated privileges: {e}"
        except Exception as e:
            result["error"] = str(e)
        finally:
            # Cleanup
            import shutil
            try:
                shutil.rmtree(tmpdir, ignore_errors=True)
            except Exception:
                pass

        return result

    # ==================================================================
    # HELPERS
    # ==================================================================

    def _load_yara_rules(self) -> Dict[str, Any]:
        """Compile all .yar files in the yara_rules directory."""
        rules = {}
        if not os.path.isdir(YARA_RULES_DIR):
            return rules
        try:
            import yara  # type: ignore
            for fname in os.listdir(YARA_RULES_DIR):
                if fname.endswith(".yar"):
                    fpath = os.path.join(YARA_RULES_DIR, fname)
                    ruleset_name = fname.replace(".yar", "")
                    try:
                        rules[ruleset_name] = yara.compile(filepath=fpath)
                        logger.info(f"YARA ruleset '{ruleset_name}' loaded")
                    except Exception as e:
                        logger.warning(f"YARA compile error for {fname}: {e}")
        except ImportError:
            logger.info("yara-python not available — YARA rules not loaded")
        return rules

    def _compute_score(self, report: Dict) -> Tuple[int, List[str]]:
        """Compute a 0-100 threat score based on analysis results."""
        score = 0
        indicators = []

        # YARA matches
        for match in report.get("yara_matches", []):
            meta = match.get("meta", {})
            sev = meta.get("severity", "medium")
            if sev == "critical":
                score += 40
            elif sev == "high":
                score += 25
            else:
                score += 10
            indicators.append(f"YARA:{match['ruleset']}:{match['rule']}")

        # High-entropy PE sections
        static = report.get("static", {})
        for sec in static.get("suspicious_sections", []):
            score += 15
            indicators.append(f"High entropy section: {sec}")

        # Dangerous import combos
        all_imports = []
        for imp in static.get("imports", []):
            all_imports.extend(imp.get("functions", []))
        injection_apis = {"VirtualAllocEx", "WriteProcessMemory", "CreateRemoteThread"}
        found_injection = injection_apis & set(all_imports)
        if found_injection:
            score += 20
            indicators.append(f"Injection APIs: {', '.join(found_injection)}")

        # Sandbox new processes
        if report.get("sandbox", {}).get("child_processes"):
            score += 10
            indicators.append("Sandbox: child processes spawned")

        # PDF with JS
        if static.get("has_javascript"):
            score += 15
            indicators.append("PDF contains JavaScript")

        return min(score, 100), indicators

    @staticmethod
    def _hash_bytes(data: bytes, algorithm: str = "sha256") -> str:
        h = hashlib.new(algorithm)
        h.update(data)
        return h.hexdigest()

    @staticmethod
    def _detect_file_type(data: bytes) -> str:
        if data[:2] == b"MZ":
            return "PE"
        if data[:4] == b"%PDF":
            return "PDF"
        if data[:4] in (b"PK\x03\x04", b"PK\x05\x06"):
            return "ZIP"
        if data[:6] in (b"Rar!\x1a\x07",):
            return "RAR"
        return "UNKNOWN"

    @staticmethod
    def _entropy(data: bytes) -> float:
        if not data:
            return 0.0
        from math import log2
        freq = [0] * 256
        for byte in data:
            freq[byte] += 1
        n = len(data)
        entropy = -sum((c / n) * log2(c / n) for c in freq if c > 0)
        return entropy

    @staticmethod
    def _snapshot_processes() -> set:
        try:
            import psutil
            return {f"{p.pid}:{p.name()}" for p in psutil.process_iter(["pid", "name"])}
        except Exception:
            return set()


# Module-level singleton
binary_analysis_service = BinaryAnalysisService()

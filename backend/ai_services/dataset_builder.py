"""
OmniDatasetBuilder — pulls live data from MongoDB and writes instruction-tuning
JSONL files that OmniFineTuner can consume.

Each record is an {"instruction": ..., "input": ..., "output": ...} triplet
following the Alpaca / TinyLlama chat format.
"""

import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

DATASET_PATH = Path(os.getenv("OMNI_DATASET_PATH", "omni_data/dataset.jsonl"))
DATASET_STATS_PATH = Path(os.getenv("OMNI_DATASET_PATH", "omni_data/dataset.jsonl")).with_suffix(".stats.json")


def _rec(instruction: str, inp: str, output: str) -> Dict[str, str]:
    return {"instruction": instruction, "input": inp.strip(), "output": output.strip()}


class OmniDatasetBuilder:
    """Async-aware builder that reads MongoDB collections and emits JSONL triplets."""

    def __init__(self, db=None):
        self._db = db  # motor AsyncIOMotorDatabase; injected or set later

    def set_db(self, db) -> None:
        self._db = db

    # ------------------------------------------------------------------ #
    # Public API                                                           #
    # ------------------------------------------------------------------ #

    async def build(self, output_path: Optional[Path] = None) -> Dict[str, Any]:
        """
        Pull all collections and write a JSONL dataset.
        Returns stats dict: {total, by_source, path, built_at}.
        """
        if self._db is None:
            raise RuntimeError("Database not set. Call set_db(db) first.")

        records: List[Dict[str, str]] = []

        collectors = [
            ("alerts",              self._from_alerts),
            ("compliance",          self._from_compliance),
            ("playbooks",           self._from_playbooks),
            ("incidents",           self._from_incidents),
            ("threat_intel",        self._from_threat_intel),
            ("edr_alerts",          self._from_edr_alerts),
            ("vulnerabilities",     self._from_vulnerabilities),
            ("sboms",               self._from_sboms),
            ("response_tasks",      self._from_response_tasks),
        ]

        by_source: Dict[str, int] = {}
        for name, fn in collectors:
            try:
                batch = await fn()
                by_source[name] = len(batch)
                records.extend(batch)
                logger.info("Dataset builder: %s → %d records", name, len(batch))
            except Exception as exc:
                logger.warning("Dataset builder: %s failed — %s", name, exc)
                by_source[name] = 0

        out = output_path or DATASET_PATH
        out.parent.mkdir(parents=True, exist_ok=True)
        with out.open("w", encoding="utf-8") as fh:
            for r in records:
                fh.write(json.dumps(r, ensure_ascii=False) + "\n")

        stats = {
            "total": len(records),
            "by_source": by_source,
            "path": str(out),
            "built_at": datetime.utcnow().isoformat(),
        }
        DATASET_STATS_PATH.parent.mkdir(parents=True, exist_ok=True)
        with DATASET_STATS_PATH.open("w", encoding="utf-8") as fh:
            json.dump(stats, fh, indent=2)

        logger.info("Dataset built: %d total records → %s", len(records), out)
        return stats

    @staticmethod
    def last_stats() -> Dict[str, Any]:
        """Return the most recent build stats without hitting MongoDB."""
        if DATASET_STATS_PATH.exists():
            try:
                return json.loads(DATASET_STATS_PATH.read_text(encoding="utf-8"))
            except Exception:
                pass
        return {"total": 0, "by_source": {}, "path": str(DATASET_PATH), "built_at": None}

    # ------------------------------------------------------------------ #
    # Per-collection extractors                                            #
    # ------------------------------------------------------------------ #

    async def _from_alerts(self) -> List[Dict[str, str]]:
        out = []
        docs = await self._db.alerts.find({}, {"_id": 0}).limit(500).to_list(length=500)
        for d in docs:
            title = d.get("title") or d.get("name") or "Security Alert"
            severity = d.get("severity", "unknown")
            desc = d.get("description") or d.get("message") or ""
            host = d.get("host") or d.get("source") or ""
            recommendation = d.get("recommendation") or d.get("remediation") or "Investigate and remediate according to security policy."
            out.append(_rec(
                instruction=f"Analyze this {severity} security alert and recommend a response.",
                inp=f"Alert: {title}\nHost: {host}\nDescription: {desc}",
                output=recommendation,
            ))
        return out

    async def _from_compliance(self) -> List[Dict[str, str]]:
        out = []
        docs = await self._db.compliance_frameworks.find({}, {"_id": 0}).limit(50).to_list(length=50)
        for fw in docs:
            name = fw.get("name", "")
            for ctrl in (fw.get("controls") or []):
                cid = ctrl.get("id") or ctrl.get("control_id") or ""
                title = ctrl.get("title") or ctrl.get("name") or ""
                desc = ctrl.get("description") or ""
                guidance = ctrl.get("guidance") or ctrl.get("implementation_guidance") or desc
                if title and guidance:
                    out.append(_rec(
                        instruction=f"How should an organization implement {name} control {cid}?",
                        inp=f"Control: {title}\nDescription: {desc}",
                        output=guidance,
                    ))
        return out

    async def _from_playbooks(self) -> List[Dict[str, str]]:
        out = []
        docs = await self._db.playbooks.find({}, {"_id": 0}).limit(200).to_list(length=200)
        for d in docs:
            name = d.get("name") or d.get("title") or "Playbook"
            trigger = d.get("trigger") or d.get("trigger_condition") or ""
            steps_raw = d.get("steps") or []
            steps_text = "\n".join(
                f"{i+1}. {s.get('name','') if isinstance(s, dict) else s}"
                for i, s in enumerate(steps_raw[:10])
            )
            if steps_text:
                out.append(_rec(
                    instruction=f"What are the response steps for the playbook '{name}'?",
                    inp=f"Trigger: {trigger}",
                    output=steps_text,
                ))
        return out

    async def _from_incidents(self) -> List[Dict[str, str]]:
        out = []
        docs = await self._db.incidents.find({}, {"_id": 0}).limit(300).to_list(length=300)
        for d in docs:
            title = d.get("title") or d.get("name") or "Incident"
            severity = d.get("severity", "")
            summary = d.get("summary") or d.get("description") or ""
            resolution = d.get("resolution") or d.get("resolution_notes") or d.get("remediation") or ""
            if summary and resolution:
                out.append(_rec(
                    instruction=f"How was this {severity} incident resolved?",
                    inp=f"Incident: {title}\nSummary: {summary}",
                    output=resolution,
                ))
        return out

    async def _from_threat_intel(self) -> List[Dict[str, str]]:
        out = []
        docs = await self._db.threat_intel_scans.find({}, {"_id": 0}).limit(300).to_list(length=300)
        for d in docs:
            ioc_type = d.get("ioc_type") or d.get("type") or "indicator"
            ioc_value = d.get("ioc_value") or d.get("value") or ""
            verdict = d.get("verdict") or d.get("result") or ""
            details = d.get("details") or d.get("description") or ""
            if ioc_value and verdict:
                out.append(_rec(
                    instruction=f"What is the threat intelligence verdict for this {ioc_type}?",
                    inp=f"IOC: {ioc_value}\nDetails: {details}",
                    output=f"Verdict: {verdict}. {details}".strip(),
                ))
        return out

    async def _from_edr_alerts(self) -> List[Dict[str, str]]:
        out = []
        docs = await self._db.edr_alerts.find({}, {"_id": 0}).limit(400).to_list(length=400)
        for d in docs:
            process = d.get("process_name") or d.get("process") or ""
            cmd = d.get("command_line") or d.get("cmdline") or ""
            tactic = d.get("mitre_tactic") or d.get("tactic") or ""
            technique = d.get("mitre_technique") or d.get("technique") or ""
            severity = d.get("severity") or ""
            action = d.get("recommended_action") or d.get("action") or "Investigate the process and isolate if malicious."
            out.append(_rec(
                instruction="What action should be taken for this EDR alert?",
                inp=f"Process: {process}\nCmd: {cmd}\nMITRE Tactic: {tactic} / {technique}\nSeverity: {severity}",
                output=action,
            ))
        return out

    async def _from_vulnerabilities(self) -> List[Dict[str, str]]:
        out = []
        docs = await self._db.vulnerabilities.find({}, {"_id": 0}).limit(400).to_list(length=400)
        for d in docs:
            cve = d.get("cve_id") or d.get("cve") or ""
            title = d.get("title") or d.get("name") or cve
            cvss = d.get("cvss_score") or d.get("cvss") or ""
            desc = d.get("description") or ""
            fix = d.get("fix") or d.get("remediation") or d.get("patch") or "Apply vendor patch and follow remediation guidance."
            if title:
                out.append(_rec(
                    instruction="How should we remediate this vulnerability?",
                    inp=f"CVE: {cve}\nTitle: {title}\nCVSS: {cvss}\nDescription: {desc}",
                    output=fix,
                ))
        return out

    async def _from_sboms(self) -> List[Dict[str, str]]:
        out = []
        docs = await self._db.sboms.find({}, {"_id": 0}).limit(200).to_list(length=200)
        for d in docs:
            asset = d.get("asset_name") or d.get("name") or "Asset"
            components = d.get("components") or []
            vuln_count = sum(1 for c in components if c.get("vulnerabilities") or c.get("cve"))
            total = len(components)
            summary = d.get("summary") or f"{total} components, {vuln_count} with known vulnerabilities."
            out.append(_rec(
                instruction="Summarize the software bill of materials (SBOM) risk for this asset.",
                inp=f"Asset: {asset}\nComponents: {total}",
                output=summary,
            ))
        return out

    async def _from_response_tasks(self) -> List[Dict[str, str]]:
        out = []
        docs = await self._db.response_tasks.find({}, {"_id": 0}).limit(300).to_list(length=300)
        for d in docs:
            task_type = d.get("type") or d.get("action_type") or "Response Task"
            target = d.get("target") or d.get("asset") or ""
            status = d.get("status") or ""
            result = d.get("result") or d.get("output") or d.get("notes") or ""
            if result:
                out.append(_rec(
                    instruction=f"What was the outcome of this automated {task_type} response task?",
                    inp=f"Target: {target}\nStatus: {status}",
                    output=result,
                ))
        return out

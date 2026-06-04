import logging
from typing import List, Dict, Any
from google import genai
import json
import os
from database import get_database
from datetime import datetime, timezone
from local_ip import ollama_default_url

_log = logging.getLogger(__name__)

class AgentLogicService:
    def __init__(self):
        self.is_configured = False
        self.model = None
        self.provider_type = None
        self.ollama_url = None
        self.model_name = "gemini-2.0-flash"

    async def initialize(self):
        """Initialize LLM using environment variables or database settings"""
        provider = os.getenv("LLM_PROVIDER", "gemini").lower()
        
        if provider == "ollama":
            self.ollama_url = os.getenv("OLLAMA_URL") or ollama_default_url()
            self.model_name = os.getenv("LLM_MODEL", "llama3.2:3b")
            self.provider_type = "ollama"
            # Simple connectivity check
            try:
                import httpx
                async with httpx.AsyncClient(timeout=2.0) as client:
                    resp = await client.get(f"{self.ollama_url}/api/tags")
                    if resp.status_code == 200:
                        self.is_configured = True
            except Exception as exc:
                _log.debug("Ollama connectivity check failed: %s", exc)
            return

        # Default to Gemini logic
        db = get_database()
        settings = await db.system_settings.find_one({"type": "llm"})
        
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key and settings:
            api_key = settings.get("apiKey")
            
        if api_key:
            try:
                self.model = genai.Client(api_key=api_key)
                self.model_name = settings.get("model", "gemini-2.0-flash") if settings else "gemini-2.0-flash"
                self.is_configured = True
                self.provider_type = "gemini"
            except Exception as e:
                _log.warning("Failed to initialize AgentLogicService (Gemini): %s", e)
        
    async def generate_goals(self, agent_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Use AI or Smart Heuristics to analyze agent state and generate specific goals.
        """
        if not self.is_configured:
            await self.initialize()
            
        if self.is_configured:
            prompt = f"""
            Analyze the following agent telemetry and suggest 2-3 specific, measurable goals.
            The goals should be focused on cybersecurity, compliance, or system stability.
            
            AGENT TELEMETRY:
            {json.dumps(agent_data, indent=2)}
            
            RESPOND ONLY WITH RAW JSON in this format:
            [
                {{"name": "Goal Title", "target": 100.0, "current": 75.0, "status": "active"}},
                ...
            ]
            """
            
            try:
                raw_text = ""
                if self.provider_type == "ollama":
                    import httpx
                    async with httpx.AsyncClient(timeout=30.0) as client:
                        payload = {
                            "model": self.model_name,
                            "prompt": prompt,
                            "stream": False
                        }
                        resp = await client.post(f"{self.ollama_url}/api/generate", json=payload)
                        resp.raise_for_status()
                        raw_text = resp.json().get("response", "")
                else:
                    response = self.model.models.generate_content(
                        model=self.model_name,
                        contents=prompt
                    )
                    raw_text = response.text

                cleaned_text = raw_text.replace("```json", "").replace("```", "").strip()
                goals = json.loads(cleaned_text)
                return goals
            except Exception as e:
                _log.warning("Goal generation failed: %s", e)

        # --- SMART HEURISTIC FALLBACK ---
        goals = []
        meta = agent_data.get("meta", {})

        # 1. Active threats / open alerts take highest priority
        db = get_database()
        agent_id = agent_data.get("id", "")
        tenant_id = agent_data.get("tenantId", "")
        open_alert_count = 0
        try:
            open_alert_count = await db.alerts.count_documents({
                "tenantId": tenant_id,
                "assetId": agent_id,
                "status": {"$in": ["Open", "In Progress"]},
                "severity": {"$in": ["Critical", "High"]},
            })
        except Exception as e:
            _log.debug("Open alert count query failed: %s", e)
        if open_alert_count > 0:
            goals.append({
                "name": "Resolve Active Threats",
                "target": 0.0,
                "current": float(open_alert_count),
                "status": "active",
            })

        # 2. Resource Performance
        cpu = float(meta.get("cpu_percent", meta.get("cpu_usage", 0)))
        mem = float(meta.get("memory_percent", meta.get("ram_usage", 0)))
        if cpu > 70:
            goals.append({"name": "Optimize CPU Load", "target": 50.0, "current": cpu, "status": "active"})
        if mem > 85:
            goals.append({"name": "Reduce Memory Pressure", "target": 75.0, "current": mem, "status": "active"})
        if cpu <= 70 and mem <= 85:
            goals.append({"name": "Resource Efficiency", "target": 95.0, "current": min(cpu, mem) if (cpu > 0 or mem > 0) else 0.0, "status": "active"})

        # 3. Security / Compliance
        compliance = float(meta.get("compliance_score", 100))
        if compliance < 90:
            goals.append({"name": "Remediate Compliance Gaps", "target": 100.0, "current": compliance, "status": "active"})
        else:
            goals.append({"name": "Maintain Zero Trust Baseline", "target": 100.0, "current": compliance, "status": "active"})

        # 4. Connectivity — parse real last-seen timestamp
        import datetime as _dt
        heartbeat_score = 100.0
        last_seen_str = agent_data.get("lastSeen", "")
        if last_seen_str:
            try:
                last_seen_dt = _dt.datetime.fromisoformat(last_seen_str.replace("Z", "+00:00"))
                age_min = (_dt.datetime.now(_dt.timezone.utc) - last_seen_dt).total_seconds() / 60
                if age_min > 5:
                    heartbeat_score = max(0.0, 100.0 - age_min * 2)
            except Exception as e:
                _log.debug("Failed to parse lastSeen timestamp: %s", e)
        goals.append({"name": "Agent Heartbeat Stability", "target": 100.0, "current": heartbeat_score, "status": "active"})

        return goals[:5]

    async def simulate_autonomous_decision(self, agent_id: str, context: str) -> list:
        """
        Evaluate the agent's current goals and dispatch concrete instructions
        back to the agent for any goal that is failing or below target.

        Goal-to-instruction mapping:
            "Resolve Active Threats"     → run_threat_response
            "Optimize CPU Load"          → run_process_snapshot (identify top consumers)
            "Remediate Compliance Gaps"  → run_compliance_scan
            "Maintain Zero Trust ..."    → run_compliance_scan
            "Agent Heartbeat Stability"  → no-op (monitoring only)
            default                      → collect_telemetry
        """
        db = get_database()
        agent = await db.agents.find_one({"id": agent_id})
        if not agent:
            return []

        # Merge caller-supplied context string into agent meta so goal generation
        # can use it (e.g. alert descriptions forwarded from the orchestrator).
        if context:
            agent.setdefault("meta", {})["caller_context"] = context

        goals = await self.generate_goals(agent)
        dispatched = []

        GOAL_INSTRUCTION_MAP = {
            "resolve active threat": "run_threat_response",
            "threat":              "run_threat_response",
            "malware":             "run_threat_response",
            "ransomware":          "run_threat_response",
            "isolat":              "isolate_endpoint",
            "optimize cpu":        "run_process_snapshot",
            "memory pressure":     "run_process_snapshot",
            "compliance":          "run_compliance_scan",
            "zero trust":          "run_compliance_scan",
            "remediate":           "run_compliance_scan",
            "security":            "run_vulnerability_scan",
            "patch":               "run_patch_scan",
            "pii":                 "run_pii_scan",
            "shadow ai":           "run_shadow_ai_scan",
            "persistence":         "run_persistence_scan",
        }

        for goal in goals:
            name_lc = goal.get("name", "").lower()
            current = goal.get("current", 100.0)
            target = goal.get("target", 100.0)

            # Only act on goals that are genuinely behind target
            if current >= target:
                continue

            instruction = "collect_telemetry"  # safe default
            for keyword, instr in GOAL_INSTRUCTION_MAP.items():
                if keyword in name_lc:
                    instruction = instr
                    break

            # Insert instruction for agent to pick up on next poll
            instr_doc = {
                "agent_id": agent_id,
                "instruction": instruction,
                "payload": {
                    "goal_name": goal.get("name"),
                    "current": current,
                    "target": target,
                    "triggered_by": "autonomous_decision_engine",
                },
                "status": "pending",
                "created_at": datetime.now(timezone.utc).isoformat(),
                "source": "agent_logic_service",
            }
            await db.agent_instructions.insert_one(instr_doc)
            dispatched.append({"goal": goal.get("name"), "instruction": instruction})

        if dispatched:
            _log.info("[AgentLogicService] Dispatched %d instructions for agent %s: %s",
                      len(dispatched), agent_id, [d["instruction"] for d in dispatched])
        return dispatched

agent_logic_service = AgentLogicService()

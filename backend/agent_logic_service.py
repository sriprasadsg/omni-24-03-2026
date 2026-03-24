from typing import List, Dict, Any
import google.generativeai as genai
import json
import os
from database import get_database
from datetime import datetime, timezone

class AgentLogicService:
    def __init__(self):
        self.is_configured = False
        self.model = None
        self.provider_type = None
        self.ollama_url = None
        self.model_name = None

    async def initialize(self):
        """Initialize LLM using environment variables or database settings"""
        provider = os.getenv("LLM_PROVIDER", "gemini").lower()
        
        if provider == "ollama":
            self.ollama_url = os.getenv("OLLAMA_URL", "http://localhost:11434")
            self.model_name = os.getenv("LLM_MODEL", "llama3.2:3b")
            self.provider_type = "ollama"
            # Simple connectivity check
            try:
                import httpx
                async with httpx.AsyncClient(timeout=2.0) as client:
                    resp = await client.get(f"{self.ollama_url}/api/tags")
                    if resp.status_code == 200:
                        self.is_configured = True
            except:
                pass
            return

        # Default to Gemini logic
        db = get_database()
        settings = await db.system_settings.find_one({"type": "llm"})
        
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key and settings:
            api_key = settings.get("apiKey")
            
        if api_key:
            try:
                genai.configure(api_key=api_key)
                model_name = settings.get("model", "gemini-2.0-flash") if settings else "gemini-2.0-flash"
                self.model = genai.GenerativeModel(model_name)
                self.is_configured = True
                self.provider_type = "gemini"
            except Exception as e:
                print(f"Failed to initialize AgentLogicService (Gemini): {e}")
        
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
                    response = self.model.generate_content(prompt)
                    raw_text = response.text

                cleaned_text = raw_text.replace("```json", "").replace("```", "").strip()
                goals = json.loads(cleaned_text)
                return goals
            except Exception as e:
                print(f"Goal generation failed: {e}")

        # --- SMART HEURISTIC FALLBACK ---
        goals = []
        meta = agent_data.get("meta", {})
        
        # 1. Resource Performance
        cpu = meta.get("cpu_usage", 0)
        if cpu > 70:
            goals.append({"name": "Optimize CPU Load", "target": 50.0, "current": cpu, "status": "active"})
        else:
            goals.append({"name": "Resource Efficiency", "target": 95.0, "current": 92.0, "status": "active"})
            
        # 2. Security / Compliance
        compliance = meta.get("compliance_score", 100)
        if compliance < 90:
            goals.append({"name": "Remediate Compliance Gaps", "target": 100.0, "current": compliance, "status": "active"})
        else:
            goals.append({"name": "Maintain Zero Trust Baseline", "target": 100.0, "current": 100.0, "status": "active"})
            
        # 3. Connectivity / Uptime
        last_seen = agent_data.get("lastSeen", "")
        # Real implementation would parse date, here we simulate
        goals.append({"name": "Agent Heartbeat Stability", "target": 100.0, "current": 99.8, "status": "active"})
        
        return goals[:3]

    async def simulate_autonomous_decision(self, agent_id: str, context: str):
        """
        Simulate an AI-driven autonomous decision loop.
        In a real system, this would trigger an approval request.
        """
        pass # To be expanded in next steps

agent_logic_service = AgentLogicService()

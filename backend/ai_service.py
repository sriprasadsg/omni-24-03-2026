
import google.generativeai as genai
import json
import os
import httpx
from abc import ABC, abstractmethod
from typing import Optional
from database import get_database
from guardrail_service import guardrail_service

# --- Provider Abstraction ---

class AIProvider(ABC):
    @abstractmethod
    async def configure(self, settings: dict) -> bool:
        """Configure the provider with settings. Return True if successful."""
        pass

    @abstractmethod
    async def generate(self, prompt: str) -> str:
        """Generate text response for a given prompt."""
        pass
    
    @property
    @abstractmethod
    def name(self) -> str:
        pass

class GeminiProvider(AIProvider):
    def __init__(self):
        self.model = None

    @property
    def name(self) -> str:
        return "Gemini"

    async def configure(self, settings: dict) -> bool:
        api_key = settings.get("apiKey")
        if not api_key:
            return False
        try:
            genai.configure(api_key=api_key)
            model_name = settings.get("model", "gemini-2.0-flash")
            self.model = genai.GenerativeModel(model_name)
            return True
        except Exception as e:
            print(f"Gemini Configuration Failed: {e}")
            return False

    async def generate(self, prompt: str) -> str:
        if not self.model:
            raise RuntimeError("Gemini model not initialized")
        response = self.model.generate_content(prompt)
        return response.text

class OllamaProvider(AIProvider):
    def __init__(self):
        self.base_url = "http://127.0.0.1:11434"
        self.model_name = "llama3" # Default, can be overridden

    @property
    def name(self) -> str:
        return "Ollama (Local)"

    async def configure(self, settings: dict) -> bool:
        # Settings might contain custom URL or model
        self.base_url = settings.get("ollamaUrl", "http://127.0.0.1:11434")
        self.model_name = settings.get("ollamaModel", "llama3.2:3b")
        
        # Check connectivity
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(f"{self.base_url}/api/tags")
                if resp.status_code == 200:
                    return True
        except:
            pass
        return False

    async def generate(self, prompt: str) -> str:
        url = f"{self.base_url}/api/generate"
        payload = {
            "model": self.model_name,
            "prompt": prompt,
            "stream": False
        }
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
            return resp.json().get("response", "")

class MockProvider(AIProvider):
    @property
    def name(self) -> str:
        return "Chitti (Mock)"

    async def configure(self, settings: dict) -> bool:
        return True

    async def generate(self, prompt: str) -> str:
        # Simple rule-based mock responses for common queries
        lower_prompt = prompt.lower()
        if "dashboard" in lower_prompt:
            return "The dashboard provides a real-time overview of your enterprise security posture. [NAVIGATE:dashboard]"
        if "agents" in lower_prompt:
            return "I can help you monitor and manage your active agents. [NAVIGATE:agents]"
        return "I am currently operating in limited mode, but I am here to assist with your security operations. [NAVIGATE:home]"

# --- Main Service ---

class IncidentAnalyzer:
    def __init__(self):
        self.provider: Optional[AIProvider] = None
        self.is_configured = False
        self.demo_sessions = {} # userId: {step, state, last_question}

    async def initialize(self):
        """
        Initialize the AI Provider.
        """
        # 1. Try environment variables first
        env_provider = os.getenv("LLM_PROVIDER", "").lower()
        if env_provider == "ollama":
            ollama = OllamaProvider()
            settings = {
                "ollamaUrl": os.getenv("OLLAMA_URL", "http://localhost:11434"),
                "ollamaModel": os.getenv("LLM_MODEL", "llama3.2:3b")
            }
            if await ollama.configure(settings):
                self.provider = ollama
                self.is_configured = True
                return
        elif env_provider == "gemini":
            gemini = GeminiProvider()
            settings = {
                "apiKey": os.getenv("GEMINI_API_KEY"),
                "model": os.getenv("LLM_MODEL", "gemini-2.0-flash")
            }
            if await gemini.configure(settings):
                self.provider = gemini
                self.is_configured = True
                return

        # 2. Fallback to database settings
        db = get_database()
        settings = (await db.system_settings.find_one({"type": "llm"})) if db else {}
        settings = settings or {}
        configured_provider = settings.get("provider")

        if configured_provider == "Gemini":
            gemini = GeminiProvider()
            if await gemini.configure(settings):
                self.provider = gemini
                self.is_configured = True
                return

        if configured_provider == "Ollama (Local)":
            ollama = OllamaProvider()
            if await ollama.configure(settings):
                self.provider = ollama
                self.is_configured = True
                return

        # 3. Final Fallbacks
        ollama = OllamaProvider()
        if await ollama.configure(settings):
            self.provider = ollama
            self.is_configured = True
            return

        gemini = GeminiProvider()
        if await gemini.configure(settings):
            self.provider = gemini
            self.is_configured = True
            return

        self.provider = MockProvider()
        self.is_configured = True

    async def _check_policy(self, text: str):
        """Internal helper to check policy"""
        db = get_database()
        if not db:
            return scan_text(text, True, True)
        settings = await db.ai_settings.find_one({"tenant_id": "global"}) or {}
        policy = settings.get("policy", {})
        return scan_text(text, policy.get("block_pii", True), policy.get("block_injection", True))

    async def generate_text(self, prompt: str, source: str = "generic") -> str:
        """Public generic generation method with guardrails"""
        if not self.is_configured:
            await self.initialize()
        
        # 1. Pre-Generation Scan
        scan = await guardrail_service.scan_and_log(prompt, f"{source}_input")
        if not scan.passed:
            return f"BLOCKED: Security policy violation in prompt. Findings: {', '.join(scan.findings)}"
        
        if self.provider:
            response = await self.provider.generate(prompt)
            
            # 2. Post-Generation Scan (optional, but recommended for PII leakage)
            output_scan = await guardrail_service.scan_and_log(response, f"{source}_output")
            if not output_scan.passed:
                return f"BLOCKED: Security policy violation in AI output. Findings: {', '.join(output_scan.findings)}"
            
            return response
        return ""

    async def analyze_impact(self, context_data: dict):
        """
        Analyze an incident using GenAI.
        """
        if not self.is_configured:
            await self.initialize()

        prompt = f"""
        Analyze the following incident context and provide a structured impact assessment.
        
        INCIDENT CONTEXT:
        {json.dumps(context_data, indent=2)}

        Provide your response in raw JSON format with:
        summary, rootCauseAnalysis, severityAssessment, impactedServices, mitigationSteps, containmentStrategy.
        """
        scan = await self._check_policy(prompt)
        if not scan.passed:
            return {"error": f"Security Policy Violation: {', '.join(scan.findings)}"}

        try:
            raw_text = await self.generate_text(prompt)
            cleaned_text = raw_text.replace("```json", "").replace("```", "").strip()
            return json.loads(cleaned_text)
        except Exception as e:
            return {"error": f"AI Analysis failed: {str(e)}"}

    async def chat(self, message: str, context: dict):
        """Chat with the AI assistant"""
        if not self.is_configured:
            await self.initialize()
        
        user_id = context.get("userId", "default_user")
        session = self.demo_sessions.get(user_id)

        scan = await self._check_policy(message)
        if not scan.passed:
             return f"Message blocked by security policy: {', '.join(scan.findings)}"

        lower_msg = message.lower()

        # --- Demo Start/Trigger ---
        demo_keywords = ["demo", "explain project", "what is this", "tell me about", "overview", "tour", "project details", "how it works", "features", "project features", "usecase", "use case", "capabilities", "present", "presentation"]
        if any(keyword in lower_msg for keyword in demo_keywords):
            self.demo_sessions[user_id] = {"step": 0, "state": "explaining"}
            step = DEMO_STEPS[0]
            return f"Certainly! This platform is a next-gen security operations hub. {step['text']} [NAVIGATE:{step['navigate']}] [AUTO_CONTINUE]"

        # --- Stateful Demo Handling ---
        if session:
            state = session.get("state")
            step_idx = session.get("step", 0)

            if any(kw in lower_msg for kw in ["continue", "next", "satisfied", "yes", "ok", "proceed", "auto_continue"]) and "more" not in lower_msg:
                next_step_idx = step_idx + 1
                if next_step_idx < len(DEMO_STEPS):
                    self.demo_sessions[user_id]["step"] = next_step_idx
                    self.demo_sessions[user_id]["state"] = "explaining"
                    step = DEMO_STEPS[next_step_idx]
                    return f"{step['text']} [NAVIGATE:{step['navigate']}] [AUTO_CONTINUE]"
                else:
                    self.demo_sessions.pop(user_id)
                    return "That concludes our project demo! I hope that was helpful. What else can I do for you today? [NAVIGATE:dashboard]"

            if "more" in lower_msg or ("yes" in lower_msg and state == "awaiting_satisfaction"):
                prompt = f"The user wants more details about: {session.get('last_question', 'their last question')}. Provide a more in-depth but concise explanation."
                answer = await self.generate_text(prompt)
                return f"{answer} Are you satisfied now, or should we continue the project demo?"

            if "?" in message or any(kw in lower_msg for kw in ["how", "what", "why", "can you"]):
                prompt = f"Answer this question concisely: {message}. Then ask if they are satisfied and want to continue the demo."
                answer = await self.generate_text(prompt)
                self.demo_sessions[user_id]["state"] = "awaiting_satisfaction"
                self.demo_sessions[user_id]["last_question"] = message
                return f"{answer} Does that answer satisfy you? If so, should we continue the project demo?"

        # --- Standard Chat ---
        prompt = f"""
        Your name is Chitti. You are a professional AI assistant. 
        Keep responses under 3 sentences and end with a follow-up question.
        Current view: {context.get('currentView', 'unknown')}.
        User query: {message}
        Include EXACTLY ONE navigation tag at the end exactly formatted like [NAVIGATE:dashboard] without spaces.
        """
        try:
            return await self.generate_text(prompt)
        except Exception as e:
            return f"Error: {str(e)}"

ai_service = IncidentAnalyzer()

DEMO_STEPS = [
    {
        "id": "intro",
        "text": "The Enterprise Omni-Agent AI Platform is a comprehensive security and management system. It's designed to act as your digital SecOps assistant.",
        "navigate": "dashboard"
    },
    {
        "id": "agents",
        "text": "First, let's look at Agent Management. We provide real-time telemetry, remote updates, and self-healing for edge devices.",
        "navigate": "agents"
    },
    {
        "id": "secops",
        "text": "Next is the SecOps Hub. This is where incident analysis happens. Chitti performs impact assessments and executes automated playbooks.",
        "navigate": "vulnerabilities"
    },
    {
        "id": "gov_appsec",
        "text": "We also offer Governance & AppSec functionalities. We manage SBOMs, scan for vulnerabilities, and track compliance.",
        "navigate": "compliance"
    },
    {
        "id": "observability",
        "text": "Finally, we have Advanced Observability features. We offer distributed tracing, network analysis, and chaos engineering simulations.",
        "navigate": "insights"
    }
]

PROJECT_OVERVIEW = "Omni-Agent is your unified platform for AI-driven security operations, agent lifecycle management, and enterprise governance. [NAVIGATE:dashboard]"

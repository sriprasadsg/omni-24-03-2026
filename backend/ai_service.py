
from google import genai
import json
import os
import httpx
from abc import ABC, abstractmethod
from typing import Optional
from database import get_database
from guardrail_service import guardrail_service
from ai_guardrails import scan_text
from local_ip import ollama_default_url
from ai_services.omni_local_provider import OmniLocalProvider, OmniLowConfidenceError

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
        self.client = None
        self.model_name = "gemini-2.0-flash"

    @property
    def name(self) -> str:
        return "Gemini"

    async def configure(self, settings: dict) -> bool:
        api_key = settings.get("apiKey")
        if not api_key:
            return False
        try:
            self.client = genai.Client(api_key=api_key)
            self.model_name = settings.get("model", "gemini-2.0-flash")
            return True
        except Exception as e:
            print(f"Gemini Configuration Failed: {e}")
            return False

    async def generate(self, prompt: str) -> str:
        if not self.client:
            raise RuntimeError("Gemini client not initialized")
        response = self.client.models.generate_content(
            model=self.model_name,
            contents=prompt
        )
        return response.text

class OllamaProvider(AIProvider):
    def __init__(self):
        self.base_url = ollama_default_url()
        self.model_name = "llama3"

    @property
    def name(self) -> str:
        return "Ollama (Local)"

    async def configure(self, settings: dict) -> bool:
        # Settings might contain custom URL or model
        self.base_url = settings.get("ollamaUrl") or ollama_default_url()
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

class AnthropicProvider(AIProvider):
    def __init__(self):
        self.api_key: Optional[str] = None
        self.model_name = "claude-sonnet-4-6"

    @property
    def name(self) -> str:
        return "Anthropic Claude"

    async def configure(self, settings: dict) -> bool:
        api_key = settings.get("apiKey") or settings.get("anthropicApiKey")
        if not api_key:
            return False
        self.api_key = api_key
        self.model_name = settings.get("model", "claude-sonnet-4-6")
        return True

    async def generate(self, prompt: str) -> str:
        if not self.api_key:
            raise RuntimeError("Anthropic API key not configured")
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": self.api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": self.model_name,
                    "max_tokens": 1024,
                    "messages": [{"role": "user", "content": prompt}],
                },
            )
            resp.raise_for_status()
            data = resp.json()
            return data["content"][0]["text"]


class MockProvider(AIProvider):
    _DEGRADED_NOTICE = (
        "\n\n⚠️ **AI running in limited mode** — no LLM provider is configured. "
        "Configure an LLM (Anthropic, Gemini, or Ollama) in Settings → AI Configuration for full capabilities."
    )

    @property
    def name(self) -> str:
        return "Limited Mode (No LLM configured)"

    async def configure(self, _settings: dict) -> bool:
        return True

    async def generate(self, prompt: str) -> str:
        lower_prompt = prompt.lower()
        if "dashboard" in lower_prompt:
            base = "The dashboard provides a real-time overview of your enterprise security posture. [NAVIGATE:dashboard]"
        elif "agent" in lower_prompt:
            base = "I can help you monitor and manage your active agents. [NAVIGATE:agents]"
        elif "alert" in lower_prompt or "incident" in lower_prompt:
            base = "Navigate to the Alerts section to review and triage active security incidents. [NAVIGATE:alerts]"
        elif "compliance" in lower_prompt:
            base = "Compliance frameworks (NIST, CIS, ISO 27001, HIPAA, PCI-DSS, SOC 2) are available in the Compliance section. [NAVIGATE:compliance]"
        elif "threat" in lower_prompt:
            base = "Threat hunting and intelligence are available in the Threat Intelligence section. [NAVIGATE:threats]"
        else:
            base = "I can assist with security operations, compliance, threat hunting, and agent management."
        return base + self._DEGRADED_NOTICE

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
        # 0. Priority: Omni-Local fine-tuned model (if trained and enabled)
        if os.getenv("OMNI_LOCAL_ENABLED", "true").lower() in ("1", "true", "yes"):
            omni_local = OmniLocalProvider()
            if await omni_local.configure({}):
                self.provider = omni_local
                self.is_configured = True
                import logging as _logging
                _logging.getLogger(__name__).info(
                    "[AI] Using Omni-Local fine-tuned model (TinyLlama + LoRA adapter)."
                )
                return

        # 1. Try environment variables first
        env_provider = os.getenv("LLM_PROVIDER", "").lower()
        if env_provider == "ollama":
            ollama = OllamaProvider()
            settings = {
                "ollamaUrl": os.getenv("OLLAMA_URL") or ollama_default_url(),
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
        elif env_provider in ("anthropic", "claude"):
            anthropic = AnthropicProvider()
            settings = {
                "apiKey": os.getenv("ANTHROPIC_API_KEY"),
                "model": os.getenv("LLM_MODEL", "claude-sonnet-4-6")
            }
            if await anthropic.configure(settings):
                self.provider = anthropic
                self.is_configured = True
                return

        # Auto-detect from bare env keys when LLM_PROVIDER is not set
        if not env_provider:
            if os.getenv("ANTHROPIC_API_KEY"):
                anthropic = AnthropicProvider()
                if await anthropic.configure({"apiKey": os.getenv("ANTHROPIC_API_KEY")}):
                    self.provider = anthropic
                    self.is_configured = True
                    return
            if os.getenv("GEMINI_API_KEY"):
                gemini = GeminiProvider()
                if await gemini.configure({"apiKey": os.getenv("GEMINI_API_KEY")}):
                    self.provider = gemini
                    self.is_configured = True
                    return

        # 2. Fallback to database settings
        db = get_database()
        settings = (await db.system_settings.find_one({"type": "llm"})) if db else {}
        settings = settings or {}
        configured_provider = settings.get("provider")

        if configured_provider == "Anthropic Claude":
            anthropic = AnthropicProvider()
            if await anthropic.configure(settings):
                self.provider = anthropic
                self.is_configured = True
                return

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

        import logging as _logging
        _logging.warning(
            "[AI] No LLM provider configured. Falling back to MockProvider (limited rule-based responses). "
            "Set LLM_PROVIDER and the corresponding API key environment variable to enable full AI capabilities. "
            "Supported: LLM_PROVIDER=anthropic (ANTHROPIC_API_KEY), gemini (GEMINI_API_KEY), ollama (OLLAMA_URL)."
        )
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

    async def generate_text(self, prompt: str, source: str = "generic", _retries: int = 3) -> str:
        """Public generic generation method with guardrails and exponential-backoff retry."""
        import asyncio as _asyncio
        if not self.is_configured:
            await self.initialize()

        # 1. Pre-Generation Scan
        scan = await guardrail_service.scan_and_log(prompt, f"{source}_input")
        if not scan.passed:
            return f"BLOCKED: Security policy violation in prompt. Findings: {', '.join(scan.findings)}"

        if self.provider:
            last_err: Exception = RuntimeError("provider not ready")
            for attempt in range(_retries):
                try:
                    response = await self.provider.generate(prompt)
                    break
                except OmniLowConfidenceError as low_conf:
                    # Local model not confident - reinitialise with next provider
                    import logging as _logging
                    _logging.getLogger(__name__).info(
                        "[AI] Omni-Local confidence %.3f below threshold - falling back to external LLM.",
                        low_conf.confidence,
                    )
                    old_provider = self.provider
                    self.provider = None
                    self.is_configured = False
                    # Temporarily disable local model so initialize() skips it
                    _prev_env = os.environ.get("OMNI_LOCAL_ENABLED")
                    os.environ["OMNI_LOCAL_ENABLED"] = "false"
                    try:
                        await self.initialize()
                    finally:
                        if _prev_env is None:
                            os.environ.pop("OMNI_LOCAL_ENABLED", None)
                        else:
                            os.environ["OMNI_LOCAL_ENABLED"] = _prev_env
                    if self.provider and self.provider is not old_provider:
                        try:
                            response = await self.provider.generate(prompt)
                            break
                        except Exception as e2:
                            last_err = e2
                    else:
                        last_err = low_conf
                    break
                except Exception as e:
                    last_err = e
                    if attempt < _retries - 1:
                        wait = 2 ** attempt  # 1s, 2s, 4s
                        await _asyncio.sleep(wait)
            else:
                return f"Error: AI generation failed after {_retries} attempts: {last_err}"

            # 2. Post-Generation Scan
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

    async def negotiate_agent_action(self, goal: str, constraints: dict) -> dict:
        """
        [2027 ROADMAP] Negotiator Persona: Evaluates a goal vs. cost/risk constraints.
        """
        if not self.is_configured:
            await self.initialize()

        prompt = f"""
        You are the OmniAgent Negotiator. Evaluate the following goal against the provided constraints.
        
        GOAL: {goal}
        CONSTRAINTS: {json.dumps(constraints, indent=2)}
        
        DECISION LOGIC:
        1. If cost > budget and priority is not CRITICAL, suggest a deferred action.
        2. If risk is HIGH, require manual approval.
        3. Otherwise, authorize and suggest the most cost-effective agent.
        
        Return JSON: {{"authorized": bool, "suggested_action": str, "negotiation_log": str, "estimated_cost": float}}
        """
        try:
            raw_text = await self.generate_text(prompt)
            cleaned_text = raw_text.replace("```json", "").replace("```", "").strip()
            return json.loads(cleaned_text)
        except Exception:
            return {"authorized": False, "suggested_action": "Retry Negotiation", "negotiation_log": "Negotiator logic failure", "estimated_cost": 0.0}

    async def _get_feedback_guidance(self) -> str:
        """
        Read recent ai_feedback records and return a one-line system-prompt
        adjustment so the model learns from past low-rated responses.
        Called once per chat session (result is cached for 5 min).
        """
        try:
            import time as _time
            cache = getattr(self, "_feedback_cache", None)
            if cache and _time.time() - cache["ts"] < 300:
                return cache["text"]

            db = get_database()
            recent = await db.ai_feedback.find(
                {"rating": {"$lte": 2}},
                {"comment": 1, "response_preview": 1},
            ).sort("created_at", -1).limit(10).to_list(length=10)

            if not recent:
                return ""

            patterns = "; ".join(
                f['comment'] for f in recent if f.get('comment')
            )[:400]
            guidance = f"Avoid these patterns from past low-rated responses: {patterns}." if patterns else ""
            self._feedback_cache = {"ts": _time.time(), "text": guidance}
            return guidance
        except Exception:
            return ""

    async def _dispatch_skill(self, message: str, context: dict) -> str:
        from skill_handlers import dispatch_skill
        return await dispatch_skill(message, context, self)

    async def chat(self, message: str, context: dict):
        """Chat with the AI assistant"""
        if not self.is_configured:
            await self.initialize()

        # Skill dispatch — intercept /command messages before everything else
        if message.startswith("/"):
            return await self._dispatch_skill(message, context)

        user_id = context.get("userId", "default_user")
        session = self.demo_sessions.get(user_id)

        scan = await self._check_policy(message)
        if not scan.passed:
             return f"Message blocked by security policy: {', '.join(scan.findings)}"

        lower_msg = message.lower()

        # --- Demo Start/Trigger ---
        demo_keywords = ["demo", "explain project", "what is this", "tell me about", "overview", "tour", "project details", "how it works", "features", "project features", "usecase", "use case", "capabilities", "present", "presentation", "walkthrough", "guide"]
        if any(keyword in lower_msg for keyword in demo_keywords):
            self.demo_sessions[user_id] = {"step": 0, "state": "explaining"}
            step = DEMO_STEPS[0]
            return f"Certainly! Genesis is a state-of-the-art enterprise management and security hub. {step['text']} [NAVIGATE:{step['navigate']}] [AUTO_CONTINUE]"

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
                    return "That concludes our comprehensive platform tour! I hope that provided a clear view of how Genesis can secure and scale your enterprise. What else can I help you with? [NAVIGATE:dashboard]"

            if "more" in lower_msg or ("yes" in lower_msg and state == "awaiting_satisfaction"):
                prompt = f"Using this project context: {PROJECT_DETAILS}\n\nThe user wants more details about: {session.get('last_question', 'their last question')}. Provide a more in-depth but concise explanation."
                answer = await self.generate_text(prompt)
                return f"{answer} Are you satisfied now, or should we continue the platform tour?"

            if "?" in message or any(kw in lower_msg for kw in ["how", "what", "why", "can you"]):
                prompt = f"Using this project context: {PROJECT_DETAILS}\n\nAnswer this question concisely: {message}. Then ask if they are satisfied and want to continue the tour."
                answer = await self.generate_text(prompt)
                self.demo_sessions[user_id]["state"] = "awaiting_satisfaction"
                self.demo_sessions[user_id]["last_question"] = message
                return f"{answer} Does that answer satisfy you? If so, should we continue the platform tour?"

        # --- Standard Chat ---
        feedback_guidance = await self._get_feedback_guidance()
        prompt = f"""
        {PROJECT_DETAILS}
        Your name is Chitti. You are a professional AI security and enterprise assistant.
        Keep responses under 3 sentences and end with a follow-up question.
        Current view: {context.get('currentView', 'unknown')}.
        {feedback_guidance}
        User query: {message}
        Include EXACTLY ONE navigation tag at the end exactly formatted like [NAVIGATE:dashboard] without spaces.
        """
        try:
            return await self.generate_text(prompt)
        except Exception as e:
            return f"Error: {str(e)}"

ai_service = IncidentAnalyzer()

PROJECT_DETAILS = """
The Enterprise Omni-Agent AI Platform (Genesis) is a state-of-the-art security operations and enterprise management hub. 
Key Features & USPs:
1. Unified FutureOps (2030): A futuristic vision for autonomous, self-healing enterprise operations using Digital Twins.
2. CXO Insights: Real-time, executive-level strategic dashboards driven by multi-tenant analytics.
3. Advanced SecOps (XDR/EDR/MDR): Comprehensive threat detection (MITRE ATT&CK), correlation, and automated SOAR response.
4. AI Governance & Policy: A dedicated engine to monitor, govern, and secure enterprise AI models with XAI (Explainability).
5. Autonomous Agent Fleet: Scalable agent management with real-time telemetry, remote control, and self-healing.
6. Zero Trust & Quantum Security: Next-gen encryption and zero-trust access control patterns.
7. Full-Stack Observability: Distributed tracing, network metrics, chaos engineering, and log exploration.
8. Integrated Governance & Compliance: Automated framework assessments (SOC2, ISO27001, etc.) via the Compliance Oracle.
"""

DEMO_STEPS = [
    {
        "id": "intro",
        "text": "Welcome to Genesis. We provide a unified view of your entire organization's health, security, and strategic growth. Let's start with the Global Dashboard.",
        "navigate": "dashboard"
    },
    {
        "id": "cxo",
        "text": "For executive leadership, our CXO Insights dashboard provides high-level strategic data, financial impact analysis, and risk trajectories in real-time.",
        "navigate": "cxo"
    },
    {
        "id": "security",
        "text": "Our Security Operations Hub is the core of your defense. It integrates EDR, XDR, and MDR intelligence to detect and neutralize threats autonomously.",
        "navigate": "security"
    },
    {
        "id": "attack_path",
        "text": "Advanced Threat Defense includes Attack Path Visualization and MITRE ATT&CK mapping, showing exactly how adversaries move through your network.",
        "navigate": "attackPath"
    },
    {
        "id": "agents",
        "text": "The Autonomous Agent Fleet manages thousands of edge and server devices with real-time telemetry and self-healing capabilities.",
        "navigate": "agents"
    },
    {
        "id": "observability",
        "text": "Our Observability suite includes Distributed Tracing and Network Observability to ensure system resilience and performance.",
        "navigate": "distributedTracing"
    },
    {
        "id": "compliance",
        "text": "Governance is automated via our Compliance Oracle, tracking framework adherence (SOC2, ISO) and automating evidence collection.",
        "navigate": "compliance"
    },
    {
        "id": "ai_governance",
        "text": "We provide a dedicated AI Governance engine to monitor model performance, enforce policies, and ensure AI explainability (XAI).",
        "navigate": "aiGovernance"
    },
    {
        "id": "future_ops",
        "text": "Unified FutureOps represents our vision for a fully autonomous operations center using Digital Twins and Predictive AI.",
        "navigate": "unifiedOps"
    },
    {
        "id": "finops",
        "text": "Finally, FinOps & DORA metrics ensure your operations are cost-effective and your engineering pipelines are highly efficient.",
        "navigate": "finops"
    }
]

PROJECT_OVERVIEW = "Genesis is your unified platform for AI-driven security operations, agent lifecycle management, and enterprise governance. [NAVIGATE:dashboard]"

import logging
import json
import os
from typing import AsyncIterator, Optional

from database import get_database
from guardrail_service import guardrail_service
from ai_guardrails import scan_text
from ai_providers import AIProvider, GeminiProvider, OllamaProvider, AnthropicProvider, MockProvider
from ai_service_data import PROJECT_DETAILS, DEMO_STEPS
from ai_services.omni_local_provider import OmniLocalProvider, OmniLowConfidenceError
from local_ip import ollama_default_url
from circuit_breaker import ai_breaker, CircuitBreakerOpen

logger = logging.getLogger(__name__)


class IncidentAnalyzer:
    def __init__(self):
        self.provider: Optional[AIProvider] = None
        self.is_configured = False
        self.demo_sessions: dict = {}

    async def initialize(self):
        """Initialize the AI Provider with fallback chain."""
        if os.getenv("OMNI_LOCAL_ENABLED", "true").lower() in ("1", "true", "yes"):
            omni_local = OmniLocalProvider()
            if await omni_local.configure({}):
                self.provider = omni_local
                self.is_configured = True
                logger.info("[AI] Using Omni-Local fine-tuned model (TinyLlama + LoRA adapter).")
                return

        env_provider = os.getenv("LLM_PROVIDER", "").lower()
        if env_provider == "ollama":
            ollama = OllamaProvider()
            if await ollama.configure({
                "ollamaUrl": os.getenv("OLLAMA_URL") or ollama_default_url(),
                "ollamaModel": os.getenv("LLM_MODEL", "llama3.2:3b"),
            }):
                self.provider = ollama
                self.is_configured = True
                return
        elif env_provider == "gemini":
            gemini = GeminiProvider()
            if await gemini.configure({
                "apiKey": os.getenv("GEMINI_API_KEY"),
                "model": os.getenv("LLM_MODEL", "gemini-2.0-flash"),
            }):
                self.provider = gemini
                self.is_configured = True
                return
        elif env_provider in ("anthropic", "claude"):
            anthropic = AnthropicProvider()
            if await anthropic.configure({
                "apiKey": os.getenv("ANTHROPIC_API_KEY"),
                "model": os.getenv("LLM_MODEL", "claude-sonnet-4-6"),
            }):
                self.provider = anthropic
                self.is_configured = True
                return

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

        logger.warning(
            "[AI] No LLM provider configured. Falling back to MockProvider (limited rule-based responses). "
            "Set LLM_PROVIDER and the corresponding API key environment variable to enable full AI capabilities. "
            "Supported: LLM_PROVIDER=anthropic (ANTHROPIC_API_KEY), gemini (GEMINI_API_KEY), ollama (OLLAMA_URL)."
        )
        self.provider = MockProvider()
        self.is_configured = True

    async def _check_policy(self, text: str):
        """Check text against AI policy guardrails."""
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

        scan = await guardrail_service.scan_and_log(prompt, f"{source}_input")
        if not scan.passed:
            return f"BLOCKED: Security policy violation in prompt. Findings: {', '.join(scan.findings)}"

        if self.provider:
            last_err: Exception = RuntimeError("provider not ready")
            response: str = ""
            for attempt in range(_retries):
                try:
                    async with ai_breaker:
                        response = await self.provider.generate(prompt)
                    break
                except CircuitBreakerOpen as cb_err:
                    last_err = cb_err
                    logger.warning("[AI] Circuit breaker open: %s", cb_err)
                    break  # Do not retry when the circuit is open
                except OmniLowConfidenceError as low_conf:
                    logger.info(
                        "[AI] Omni-Local confidence %.3f below threshold - falling back to external LLM.",
                        low_conf.confidence,
                    )
                    old_provider = self.provider
                    self.provider = None
                    self.is_configured = False
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
                except RuntimeError as load_err:
                    # OmniLocalProvider can't load model — fall back immediately to external LLM
                    if "OmniLocalProvider failed to load" in str(load_err) or attempt == 0:
                        logger.warning("[AI] OmniLocal load failed: %s — falling back to external LLM.", load_err)
                        old_provider = self.provider
                        self.provider = None
                        self.is_configured = False
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
                            last_err = load_err
                        break
                    last_err = load_err
                    if attempt < _retries - 1:
                        await _asyncio.sleep(2 ** attempt)
                except Exception as e:
                    last_err = e
                    if attempt < _retries - 1:
                        await _asyncio.sleep(2 ** attempt)
            else:
                return f"Error: AI generation failed after {_retries} attempts: {last_err}"

            if not response:
                return f"Error: AI generation failed: {last_err}"
            output_scan = await guardrail_service.scan_and_log(response, f"{source}_output")
            if not output_scan.passed:
                return f"BLOCKED: Security policy violation in AI output. Findings: {', '.join(output_scan.findings)}"
            return response
        return ""

    async def analyze_impact(self, context_data: dict):
        """Analyze an incident using GenAI and return structured impact assessment."""
        if not self.is_configured:
            await self.initialize()
        prompt = (
            "Analyze the following incident context and provide a structured impact assessment.\n\n"
            f"INCIDENT CONTEXT:\n{json.dumps(context_data, indent=2)}\n\n"
            "Provide your response in raw JSON format with: "
            "summary, rootCauseAnalysis, severityAssessment, impactedServices, mitigationSteps, containmentStrategy."
        )
        scan = await self._check_policy(prompt)
        if not scan.passed:
            raise ValueError(f"Security Policy Violation: {', '.join(scan.findings)}")
        raw_text = await self.generate_text(prompt)
        return json.loads(raw_text.replace("```json", "").replace("```", "").strip())

    async def negotiate_agent_action(self, goal: str, constraints: dict) -> dict:
        """[2027 ROADMAP] Negotiator Persona: Evaluates a goal vs. cost/risk constraints."""
        if not self.is_configured:
            await self.initialize()
        prompt = (
            "You are the OmniAgent Negotiator. Evaluate the following goal against the provided constraints.\n\n"
            f"GOAL: {goal}\n"
            f"CONSTRAINTS: {json.dumps(constraints, indent=2)}\n\n"
            "DECISION LOGIC:\n"
            "1. If cost > budget and priority is not CRITICAL, suggest a deferred action.\n"
            "2. If risk is HIGH, require manual approval.\n"
            "3. Otherwise, authorize and suggest the most cost-effective agent.\n\n"
            'Return JSON: {"authorized": bool, "suggested_action": str, "negotiation_log": str, "estimated_cost": float}'
        )
        try:
            raw_text = await self.generate_text(prompt)
            return json.loads(raw_text.replace("```json", "").replace("```", "").strip())
        except Exception:
            return {"authorized": False, "suggested_action": "Retry Negotiation", "negotiation_log": "Negotiator logic failure", "estimated_cost": 0.0}

    async def _get_feedback_guidance(self) -> str:
        """Read recent low-rated ai_feedback records and return prompt adjustment guidance."""
        try:
            import time as _time
            cache = getattr(self, "_feedback_cache", None)
            if cache and _time.time() - cache["ts"] < 300:
                return cache["text"]
            db = get_database()
            recent = await db.ai_feedback.find(
                {"rating": {"$lte": 2}}, {"comment": 1, "response_preview": 1},
            ).sort("created_at", -1).limit(10).to_list(length=10)
            if not recent:
                return ""
            patterns = "; ".join(f["comment"] for f in recent if f.get("comment"))[:400]
            guidance = f"Avoid these patterns from past low-rated responses: {patterns}." if patterns else ""
            self._feedback_cache = {"ts": _time.time(), "text": guidance}
            return guidance
        except Exception as e:
            logger.debug("Feedback cache load failed: %s", e)
            return ""

    async def _dispatch_skill(self, message: str, context: dict) -> str:
        from skill_handlers import dispatch_skill
        return await dispatch_skill(message, context, self)

    async def chat(self, message: str, context: dict):
        """Chat with the AI assistant."""
        if not self.is_configured:
            await self.initialize()

        if message.startswith("/"):
            return await self._dispatch_skill(message, context)

        user_id = context.get("userId", "default_user")
        session = self.demo_sessions.get(user_id)

        scan = await self._check_policy(message)
        if not scan.passed:
            return f"Message blocked by security policy: {', '.join(scan.findings)}"

        lower_msg = message.lower()
        demo_keywords = [
            "demo", "explain project", "what is this", "tell me about", "overview", "tour",
            "project details", "how it works", "features", "project features", "usecase",
            "use case", "capabilities", "present", "presentation", "walkthrough", "guide",
        ]
        if any(keyword in lower_msg for keyword in demo_keywords):
            self.demo_sessions[user_id] = {"step": 0, "state": "explaining"}
            step = DEMO_STEPS[0]
            return f"Certainly! Genesis is a state-of-the-art enterprise management and security hub. {step['text']} [NAVIGATE:{step['navigate']}] [AUTO_CONTINUE]"

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

        feedback_guidance = await self._get_feedback_guidance()
        prompt = (
            f"{PROJECT_DETAILS}\n"
            "Your name is Chitti. You are a professional AI security and enterprise assistant.\n"
            "Keep responses under 3 sentences and end with a follow-up question.\n"
            f"Current view: {context.get('currentView', 'unknown')}.\n"
            f"{feedback_guidance}\n"
            f"User query: {message}\n"
            "Include EXACTLY ONE navigation tag at the end exactly formatted like [NAVIGATE:dashboard] without spaces."
        )
        try:
            return await self.generate_text(prompt)
        except Exception as e:
            return f"Error: {str(e)}"


    async def chat_stream(self, message: str, context: dict) -> AsyncIterator[str]:
        """Stream chat response token-by-token via SSE.

        Uses native provider streaming when available. Falls back to
        generate_text (which handles OmniLocal low-confidence and external
        LLM retry) and simulates streaming word-by-word so the UI still
        animates even when the model can't stream natively.
        """
        import asyncio as _asyncio
        if not self.is_configured:
            await self.initialize()

        # Skill commands: dispatch synchronously, yield full result
        if message.startswith("/"):
            result = await self._dispatch_skill(message, context)
            yield result
            return

        scan = await self._check_policy(message)
        if not scan.passed:
            yield f"Message blocked by security policy: {', '.join(scan.findings)}"
            return

        feedback_guidance = await self._get_feedback_guidance()
        prompt = (
            f"{PROJECT_DETAILS}\n"
            "Your name is Chitti. You are a professional AI security and enterprise assistant.\n"
            "Keep responses under 3 sentences and end with a follow-up question.\n"
            f"Current view: {context.get('currentView', 'unknown')}.\n"
            f"{feedback_guidance}\n"
            f"User query: {message}\n"
            "Include EXACTLY ONE navigation tag at the end exactly formatted like [NAVIGATE:dashboard] without spaces."
        )

        if not self.provider:
            yield "AI provider not configured."
            return

        # Try native streaming first
        native_failed = False
        try:
            async for chunk in self.provider.generate_stream(prompt):
                yield chunk
            return
        except OmniLowConfidenceError:
            native_failed = True
        except Exception:
            native_failed = True

        if native_failed:
            # generate_text handles OmniLocal fallback + all retry logic
            try:
                text = await self.generate_text(prompt, source="chat_stream_fallback")
                if text:
                    words = text.split(" ")
                    for i, word in enumerate(words):
                        yield word + (" " if i < len(words) - 1 else "")
                        await _asyncio.sleep(0.03)
            except Exception as e:
                yield f"Error generating response: {str(e)}"


ai_service = IncidentAnalyzer()

import logging
import json

logger = logging.getLogger(__name__)

# Register security tools so the ReAct registry is non-empty at import time
try:
    from . import security_tools  # noqa: F401 — side-effect import, populates registry
except Exception as _e:
    logger.warning("Could not load security_tools: %s", _e)

class AgenticReasoningEngine:
    """
    Core Decision Engine for the Agent.
    Orchestrates the flow between:
    1. Data Collection (Context)
    2. LLM Analysis (Reasoning)
    3. Safety Checks (Guardrails)
    4. Action Recommendation
    """
    
    def __init__(self, llm_engine, safety_guardrails, config=None, memory=None):
        self.llm = llm_engine
        self.safety = safety_guardrails
        self.config = config or {}
        self.memory = memory

        # Threshold for autonomous execution
        self.confidence_threshold = self.config.get("confidence_threshold", 0.8)
        self.require_approval = self.config.get("require_approval", True)

    def decide_action(self, context: dict) -> dict:
        """
        Main entry point for autonomous decision making.
        Enriches context with similar past experiences before querying the LLM.
        """
        # Retrieve relevant past experiences from memory to improve decision quality
        memory = getattr(self, "memory", None)
        if memory:
            try:
                similar = memory.find_similar_situations(context)
                if similar:
                    context = dict(context)
                    context["past_experiences"] = [
                        {
                            "action":  e.get("action"),
                            "success": e.get("outcome", {}).get("success"),
                            "score":   e.get("outcome", {}).get("score", 0),
                        }
                        for e in similar[:3]
                    ]
            except Exception as _me:
                logger.debug("Memory retrieval skipped: %s", _me)

        logger.info("Requesting LLM analysis for current context...")
        analysis = self.llm.analyze_situation(context)
        
        if "error" in analysis:
            return {"action": "none", "is_autonomous": False, "reason": analysis['error']}

        recommended_action = analysis.get("recommended_action", "none")
        confidence = analysis.get("confidence", 0.0)
        
        # Check Safety
        is_safe, safety_reason = self.safety.is_safe_to_act(analysis)
        if not is_safe:
            return {"action": recommended_action, "is_autonomous": False, "reason": f"Unsafe: {safety_reason}"}

        # Check Confidence
        if confidence < self.confidence_threshold:
            decision = {"action": recommended_action, "is_autonomous": False, "reason": "Low Confidence"}
            self._store_decision(context, recommended_action, success=False)
            return decision

        decision = {
            "action": recommended_action,
            "is_autonomous": True,
            "reason": "Autonomous execution criteria met",
            "plan": analysis,
        }
        # Pre-execution memory record (outcome will be updated later by agent.py)
        self._store_decision(context, recommended_action, success=None)
        return decision

    def _store_decision(self, context: dict, action: str, success=None):
        """Persist decision to memory for future recall and learning."""
        memory = getattr(self, "memory", None)
        if not memory:
            return
        try:
            memory.store_experience(
                context=str(context),
                action=action,
                outcome={"success": success, "score": 0.5 if success is None else (1.0 if success else 0.0)},
            )
        except Exception as _me:
            logger.debug("Memory store skipped: %s", _me)

    def run_react_loop(self, task: str, max_steps=5) -> dict:
        """
        Execute an iterative ReAct (Reason-Act-Observe) loop.
        Routes through the LLM engine's provider-agnostic interface so it works
        with backend, ollama, and openai providers.
        """
        from .tool_registry import registry
        import json

        history = []
        for i in range(max_steps):
            logger.info(f"ReAct Step {i+1}/{max_steps}")

            # 1. Build prompt and ask LLM for raw text (not pre-parsed JSON)
            prompt = self._construct_react_prompt(task, history, registry.get_all_schemas())
            raw = self.llm.query_raw(prompt)

            # 2. Extract structured decision from raw LLM text
            import re
            try:
                json_match = re.search(r'\{.*\}', raw, re.DOTALL)
                if json_match:
                    thought = json.loads(json_match.group())
                else:
                    thought = {"action": "final_answer", "action_input": "No JSON in LLM response"}
            except Exception:
                thought = {"action": "final_answer", "action_input": "Failed to parse LLM response"}

            action_name = thought.get("action", "final_answer")
            action_input = thought.get("action_input", {})
            reasoning = thought.get("thought", "")

            history.append(f"Thought: {reasoning}")

            # 2. Act
            if action_name == "final_answer":
                return {"status": "success", "result": action_input}

            tool = registry.get_tool(action_name)
            if not tool:
                available = [s['name'] for s in registry.get_all_schemas()]
                observation = f"Error: Tool '{action_name}' not found. Available: {available}"
            else:
                try:
                    result = registry.execute(action_name, action_input)
                    observation = f"Observation: {result}"
                except Exception as e:
                    observation = f"Error executing {action_name}: {e}"

            history.append(f"Action: {action_name}({action_input})")
            history.append(observation)
            logger.info(observation)

        return {"status": "max_steps_reached", "history": history}

    def _construct_react_prompt(self, task, history, tools):
        history_str = "\n".join(history)
        tools_str = json.dumps(tools, indent=2)
        return f"""You are an Agentic AI. Solve the TASK using the available TOOLS.
        
TOOLS:
{tools_str}

FORMAT:
{{
    "thought": "<reasoning>",
    "action": "<tool_name> or final_answer",
    "action_input": <dict args> or <string final answer>
}}

TASK: {task}

HISTORY:
{history_str}
"""

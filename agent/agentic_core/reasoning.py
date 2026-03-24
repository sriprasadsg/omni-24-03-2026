import logging
import json

logger = logging.getLogger(__name__)

class AgenticReasoningEngine:
    """
    Core Decision Engine for the Agent.
    Orchestrates the flow between:
    1. Data Collection (Context)
    2. LLM Analysis (Reasoning)
    3. Safety Checks (Guardrails)
    4. Action Recommendation
    """
    
    def __init__(self, llm_engine, safety_guardrails, config=None):
        self.llm = llm_engine
        self.safety = safety_guardrails
        self.config = config or {}
        
        # Threshold for autonomous execution
        self.confidence_threshold = self.config.get("confidence_threshold", 0.8)
        self.require_approval = self.config.get("require_approval", True)

    def decide_action(self, context: dict) -> dict:
        """
        Main entry point for autonomous decision making.
        """
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
             return {"action": recommended_action, "is_autonomous": False, "reason": "Low Confidence"}
             
        return {
            "action": recommended_action,
            "is_autonomous": True,
            "reason": "Autonomous execution criteria met",
            "plan": analysis
        }

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

            # 1. Build context and ask LLM to reason + pick action
            context = {
                "task": task,
                "history": history,
                "available_tools": registry.get_all_schemas(),
                "instruction": (
                    "You are an Agentic AI executing a ReAct loop. "
                    "Choose a tool to call or return final_answer. "
                    "Reply ONLY with JSON matching the format: "
                    '{"thought": "<reasoning>", "action": "<tool_name or final_answer>", '
                    '"action_input": <dict args or string answer>}'
                )
            }

            analysis = self.llm.analyze_situation(context)

            # Extract structured decision from analysis
            try:
                # analyze_situation may return {"recommended_action": ..., "reasoning": ..., "raw": ...}
                raw = analysis.get("raw", "") or analysis.get("reasoning", "") or ""
                # Attempt to parse embedded JSON from the raw LLM response
                import re
                json_match = re.search(r'\{.*\}', raw, re.DOTALL)
                if json_match:
                    thought = json.loads(json_match.group())
                else:
                    # Fallback: treat recommended_action as the action
                    thought = {
                        "thought": analysis.get("reasoning", ""),
                        "action": analysis.get("recommended_action", "final_answer"),
                        "action_input": {}
                    }
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
                observation = f"Error: Tool '{action_name}' not found. Choose from: {list(registry.get_all_schemas().keys())}"
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

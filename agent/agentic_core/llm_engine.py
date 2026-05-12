import requests
import json
import logging
import os
import time

logger = logging.getLogger(__name__)

_TUNING_FILE = os.path.join(os.path.dirname(__file__), "..", "data", "llm_tuning.json")

class AgenticLLM:
    """
    Local LLM Engine for Agentic AI Reasoning.
    Connects to a local Ollama instance to provide intelligent analysis.
    """

    def __init__(self, config=None):
        self.config = config or {}
        self.provider = self.config.get("provider", "ollama")

        # Local Ollama Config
        self.base_url = self.config.get("base_url", "http://localhost:11434")
        self.model = self.config.get("model", "llama3.2:3b")

        # Backend API Config
        self.api_base_url = self.config.get("api_base_url", "http://localhost:5000")
        self.api_key = self.config.get("api_key", "")

        self.temperature = self.config.get("temperature", 0.7)
        self.timeout = self.config.get("timeout", 30)

        # Self-tuning state: track recent LLM outcomes to adjust temperature
        self._performance_history: list = []
        self._load_tuning_state()

    def record_outcome(self, success: bool, reasoning: str = "") -> None:
        """Record an action outcome so self_tune() can adjust parameters."""
        self._performance_history.append({
            "success": success,
            "reasoning": reasoning[:200],
            "temperature": self.temperature,
            "timestamp": time.time(),
        })
        # Keep only the last 100 entries
        if len(self._performance_history) > 100:
            self._performance_history = self._performance_history[-100:]
        # Auto-tune every 20 new data points
        if len(self._performance_history) % 20 == 0:
            self.self_tune()

    def self_tune(self) -> None:
        """
        Adjust temperature based on recent success rate.
        High success → lower temperature (more deterministic).
        Low success → raise temperature (more creative).
        """
        recent = self._performance_history[-50:]
        if not recent:
            return
        success_rate = sum(1 for r in recent if r["success"]) / len(recent)
        old_temp = self.temperature
        if success_rate > 0.80:
            self.temperature = max(0.3, round(self.temperature - 0.05, 2))
        elif success_rate < 0.50:
            self.temperature = min(1.0, round(self.temperature + 0.05, 2))
        if self.temperature != old_temp:
            logger.info(
                "SELF-TUNE: temperature %.2f → %.2f (success_rate=%.0f%%, n=%d)",
                old_temp, self.temperature, success_rate * 100, len(recent),
            )
        self._save_tuning_state()

    def _load_tuning_state(self) -> None:
        """Restore persisted temperature and performance history from disk."""
        try:
            with open(_TUNING_FILE) as f:
                state = json.load(f)
            self.temperature = float(state.get("temperature", self.temperature))
            self._performance_history = state.get("history", [])[-100:]
            logger.debug("Loaded LLM tuning state: temp=%.2f, history=%d entries",
                         self.temperature, len(self._performance_history))
        except (FileNotFoundError, json.JSONDecodeError):
            pass

    def _save_tuning_state(self) -> None:
        """Persist current temperature and performance history to disk."""
        try:
            os.makedirs(os.path.dirname(_TUNING_FILE), exist_ok=True)
            with open(_TUNING_FILE, "w") as f:
                json.dump({
                    "temperature": self.temperature,
                    "history": self._performance_history[-100:],
                }, f)
        except Exception as e:
            logger.debug("Could not save LLM tuning state: %s", e)

    def query_raw(self, prompt: str) -> str:
        """Return raw LLM text without JSON parsing — used by the ReAct loop."""
        if not self.is_available():
            return '{"thought": "LLM unavailable", "action": "final_answer", "action_input": "LLM provider not reachable"}'
        try:
            if self.provider == "backend":
                return self._query_backend(prompt)
            return self._query_ollama(prompt)
        except Exception as e:
            logger.error("query_raw failed: %s", e)
            return '{"action": "final_answer", "action_input": "query failed"}'

    def is_available(self) -> bool:
        """Check if the configured LLM provider is running and accessible"""
        if self.provider == "backend":
            try:
                url = f"{self.api_base_url.rstrip('/')}/health"
                resp = requests.get(url, timeout=2)
                return resp.status_code == 200
            except:
                return False
        elif self.provider == "omni-llm-scratch":
            try:
                # Check if training is complete
                url = f"{self.api_base_url.rstrip('/')}/api/ai/train/status"
                resp = requests.get(url, timeout=2)
                if resp.status_code == 200:
                    data = resp.json()
                    return data.get("current_job", {}) is not None and \
                           data.get("current_job", {}).get("status") == "Completed"
                return False
            except:
                return False
        else:
            # Default to Ollama
            try:
                response = requests.get(f"{self.base_url}/api/tags", timeout=2)
                return response.status_code == 200
            except Exception:
                return False

    def analyze_situation(self, context: dict) -> dict:
        """
        Analyze the current system state and security context.
        Returns a structured dictionary with analysis results.
        """
        if not self.is_available():
            logger.warning(f"Agentic LLM ({self.provider}) is not available. Skipping analysis.")
            return {"error": "LLM_UNAVAILABLE", "confidence": 0.0}

        # Sanitize Context for PII
        from agentic_core.pii_security import PIISecurityMiddleware
        clean_context = PIISecurityMiddleware.sanitize(context)

        # Construct the prompt
        prompt = self._construct_analysis_prompt(clean_context)
        
        try:
            if self.provider == "backend":
                response_text = self._query_backend(prompt)
            else:
                response_text = self._query_ollama(prompt)
                
            return self._parse_response(response_text)
        except Exception as e:
            logger.error(f"Error during LLM analysis: {e}")
            return {"error": str(e), "confidence": 0.0}

    def _query_backend(self, prompt: str) -> str:
        """Send query to Backend API"""
        url = f"{self.api_base_url.rstrip('/')}/api/ai/chat"
        payload = {
            "message": prompt,
            "context": {"source": "agent_reasoning_engine"}
        }
        headers = {}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
            
        response = requests.post(url, json=payload, headers=headers, timeout=self.timeout)
        response.raise_for_status()
        data = response.json()
        return data.get("response", "")

    def _query_ollama(self, prompt: str) -> str:
        """Send query to Ollama API"""
        url = f"{self.base_url}/api/generate"
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": self.temperature
            }
        }
        
        response = requests.post(url, json=payload, timeout=self.timeout)
        response.raise_for_status()
        return response.json().get("response", "")

    def _construct_analysis_prompt(self, context: dict) -> str:
        """Create a structured prompt for the LLM"""
        system_info = json.dumps(context.get('system_info', {}), indent=2)
        alerts = json.dumps(context.get('alerts', []), indent=2)
        history = json.dumps(context.get('history', []), indent=2)
        
        return f"""You are an expert autonomous cybersecurity agent. 
Analyze the following system state and provide a JSON response.

CONTEXT:
System Info: {system_info}
Active Alerts: {alerts}
Recent Logic: {history}

TASK:
1. Assess the threat level (0-10)
2. Identify the root cause
3. Recommend an immediate action
4. Determine if autonomous action is safe (true/false)
5. Provide a confidence score (0.0-1.0)

RESPONSE FORMAT (Valid JSON only):
{{
    "threat_level": <int>,
    "root_cause": "<string>",
    "recommended_action": "<string>",
    "is_autonomous_safe": <bool>,
    "confidence": <float>,
    "reasoning": "<string>"
}}
"""

    def plan_remediation(self, issue: dict) -> dict:
        """
        Generate a structured remediation plan for a specific issue using the
        dedicated remediation prompt (includes AVAILABLE_ACTIONS schema).
        """
        if not self.is_available():
            logger.warning("Agentic LLM is not available. Cannot plan remediation.")
            return {"error": "LLM_UNAVAILABLE"}

        prompt = self._construct_remediation_prompt(issue)
        try:
            raw = self.query_raw(prompt)
            return self._parse_response(raw)
        except Exception as e:
            logger.error("Error during LLM remediation planning: %s", e)
            return {"error": str(e)}

    def _construct_remediation_prompt(self, issue: dict) -> str:
        """Create a prompt for generating a remediation plan"""
        issue_json = json.dumps(issue, indent=2)
        
        return f"""You are an expert autonomous remediation engine.
Generate a structured, multi-step remediation plan for the following issue.

ISSUE:
{issue_json}

TASK:
1. Define a clear name for the plan.
2. List affected services or files.
3. Provide a sequence of atomic steps to resolve the issue.

AVAILABLE ACTIONS:
- restart_service (target: service_name)
- kill_process (target: process_name or pid)
- delete_file (target: file_path)
- run_command (target: shell_command)
- rollback_checkpoint (target: checkpoint_id)

RESPONSE FORMAT (Valid JSON only):
{{
    "name": "<plan_name>",
    "affected_services": ["<service1>", ...],
    "affected_files": ["<file1>", ...],
    "steps": [
        {{
            "action": "<action_type>",
            "target": "<target_value>",
            "description": "<step_description>"
        }},
        ...
    ]
}}
"""

    def _parse_response(self, text: str) -> dict:
        """Parse the LLM response, handling potential JSON formatting issues"""
        try:
            # simple cleanup to find the first '{' and last '}'
            start = text.find('{')
            end = text.rfind('}') + 1
            if start != -1 and end != -1:
                json_str = text[start:end]
                return json.loads(json_str)
            else:
                raise ValueError("No JSON found in response")
        except Exception:
            logger.warning(f"Failed to parse LLM response as JSON. Raw: {text[:100]}...")
            return {
                "error": "PARSE_ERROR", 
                "raw_response": text,
                "confidence": 0.0
            }

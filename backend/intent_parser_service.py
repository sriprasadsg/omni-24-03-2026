from typing import Dict, Any, Optional
import json
from agent_logic_service import agent_logic_service
from celery_app import celery_app
from database import get_database
from datetime import datetime, timezone
import uuid

class IntentParserService:
    """Parses ticket descriptions and dispatches agent tasks."""

    async def parse_and_dispatch(self, ticket_data: Dict[str, Any], platform: str) -> Dict[str, Any]:
        """
        Main entry point for inbound webhooks.
        Parses ticket, dispatches task if intent found, and returns status.
        """
        # 1. Extract raw text based on platform
        title = ""
        description = ""
        ticket_id = ""

        if platform == "jira":
            issue = ticket_data.get("issue", {})
            fields = issue.get("fields", {})
            title = fields.get("summary", "")
            description = fields.get("description", "")
            ticket_id = issue.get("key", "unknown")
        elif platform == "zohodesk":
            # Simplify for mock/demo
            title = ticket_data.get("subject", "")
            description = ticket_data.get("description", "")
            ticket_id = ticket_data.get("id", "unknown")
        
        if not title and not description:
            return {"success": False, "error": "No content to parse"}

        # 2. Use LLM to detect intent
        intent = await self._detect_intent(title, description)
        
        if not intent or intent.get("action") == "none":
            return {"success": True, "message": "No actionable intent detected", "intent": intent}

        # 3. Dispatch Task
        target_agent = intent.get("target_agent", "default")
        action = intent.get("action")
        params = intent.get("params", {})
        
        task_description = self._build_task_description(action, params)
        
        print(f"[IntentParser] Dispatching task: {task_description} to {target_agent}")
        
        task = celery_app.send_task(
            "tasks.run_agent_task_async",
            args=[task_description, target_agent],
            queue="default"
        )
        
        # 4. Record as a job in DB for UI visibility
        db = get_database()
        job_id = f"job-{uuid.uuid4().hex[:8]}"
        await db.jobs.insert_one({
            "id": job_id,
            "task_id": job_id,
            "type": "ticket_automation",
            "status": "processing",
            "progress": 50, # Initial progress
            "created_at": datetime.now(timezone.utc).isoformat(),
            "created_by": "system",
            "details": {
                "ticket_id": ticket_id,
                "platform": platform,
                "action": action,
                "task_description": task_description,
                "agent_id": target_agent,
                "celery_task_id": task.id
            },
            "result": None
        })
        
        return {
            "success": True,
            "intent": intent,
            "task_id": task.id,
            "ticket_id": ticket_id
        }

    async def _detect_intent(self, title: str, description: str) -> Dict[str, Any]:
        """Uses AgentLogicService (Gemini) to parse intent from text."""
        if not agent_logic_service.is_configured:
            await agent_logic_service.initialize()

        prompt = f"""
        Act as a Cybersecurity Automation Dispatcher. Parse the following IT ticket and identify if it requires an automated agent action.
        
        TICKET TITLE: {title}
        TICKET DESCRIPTION: {description}
        
        AVAILABLE ACTIONS:
        - install_software: (params: package_name) e.g. "Install VS Code"
        - set_env_variable: (params: name, value) e.g. "Set JAVA_HOME to C:\\Java"
        - run_security_scan: (params: type) e.g. "Run a full scan"
        - isolate_host: (params: none)
        - none: If no specific action is requested.
        
        TARGET AGENT: Try to find a hostname or agent ID. If not found, use "default".
        
        RESPOND ONLY WITH RAW JSON in this format:
        {{
            "action": "action_name",
            "params": {{ ... }},
            "target_agent": "hostname_or_default",
            "confidence": 0.0-1.0
        }}
        """

        try:
            if agent_logic_service.model:
                response = agent_logic_service.model.generate_content(prompt)
                cleaned_text = response.text.replace("```json", "").replace("```", "").strip()
                return json.loads(cleaned_text)
        except Exception as e:
            print(f"[IntentParser] LLM Detection failed: {e}")

        # Basic heuristic fallback
        low_text = (title + " " + description).lower()
        if "install" in low_text:
            return {"action": "install_software", "params": {"package_name": "requested_app"}, "target_agent": "default", "confidence": 0.5}
        
        return {"action": "none", "params": {}, "target_agent": "default", "confidence": 0.0}

    def _build_task_description(self, action: str, params: Dict[str, Any]) -> str:
        """Translates action/params to agent-consumable string."""
        if action == "install_software":
            return f"install_software:{params.get('package_name', 'unknown')}"
        elif action == "set_env_variable":
            return f"set_env:{params.get('name')}={params.get('value')}"
        elif action == "run_security_scan":
            return f"run_scan:{params.get('type', 'quick')}"
        elif action == "isolate_host":
            return "isolate_host"
        return f"custom_action:{action}"

intent_parser_service = IntentParserService()

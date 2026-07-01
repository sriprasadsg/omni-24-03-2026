import logging
import time

logger = logging.getLogger(__name__)

class SafetyGuardrails:
    """
    Enforces safety constraints on autonomous actions.
    Acts as the final gatekeeper before any AI decision is executed.
    Supports dynamic rule loading from the backend so operators can adjust
    autonomy policies at runtime without restarting the agent.
    """

    # Default hardcoded rules (used when backend is unreachable)
    FORBIDDEN_ACTIONS = [
        "delete_critical_files",
        "shutdown_production",
        "modify_firewall_allow_all",
        "disable_antivirus",
        "wipe_disk",
        "uninstall_agent",
    ]

    APPROVAL_REQUIRED = [
        "restart_service",
        "modify_configuration",
        "deploy_patch",
        "update_application",
        "isolate_host",
    ]

    SAFE_ACTIONS = [
        "scan_system",
        "collect_logs",
        "check_status",
        "kill_process_low_priority",
    ]

    def __init__(self, config=None):
        self.config = config or {}
        self.enabled = self.config.get("enabled", True)
        # Dynamic rules fetched from the backend (overrides defaults when present)
        self._dynamic_forbidden: list = []
        self._dynamic_approval_required: list = []
        self._dynamic_safe: list = []
        self._rules_fetched_at: float = 0.0
        self._rules_ttl: float = 300.0  # refresh every 5 minutes

    def load_remote_rules(self, api_base_url: str = "", api_key: str = "", agent_id: str = "") -> None:
        """
        Fetch tenant-specific safety rules from the backend.
        Falls back to hardcoded defaults silently if the backend is unavailable.
        Rules are cached for `_rules_ttl` seconds to avoid per-decision HTTP overhead.
        """
        now = time.time()
        if now - self._rules_fetched_at < self._rules_ttl:
            return  # cache is still warm
        try:
            import requests
            url = f"{api_base_url.rstrip('/')}/api/agents/{agent_id}/safety-rules"
            headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
            resp = requests.get(url, headers=headers, timeout=3)
            if resp.status_code == 200:
                data = resp.json()
                self._dynamic_forbidden = data.get("forbidden_actions", [])
                self._dynamic_approval_required = data.get("approval_required", [])
                self._dynamic_safe = data.get("safe_actions", [])
                self._rules_fetched_at = now
                logger.info("Safety rules refreshed from backend (%d forbidden, %d approval, %d safe)",
                            len(self._dynamic_forbidden), len(self._dynamic_approval_required),
                            len(self._dynamic_safe))
        except Exception as _e:
            logger.debug("Could not load remote safety rules, using defaults: %s", _e)

    @property
    def _forbidden(self) -> list:
        return self._dynamic_forbidden or self.FORBIDDEN_ACTIONS

    @property
    def _approval_required(self) -> list:
        return self._dynamic_approval_required or self.APPROVAL_REQUIRED

    @property
    def _safe(self) -> list:
        return self._dynamic_safe or self.SAFE_ACTIONS

    def is_safe_to_act(self, action_plan: dict) -> tuple[bool, str]:
        """
        Validate if an action plan is safe to execute autonomously.
        Checks dynamic rules from backend first, falls back to hardcoded defaults.
        Returns: (is_safe: bool, reason: str)
        """
        if not self.enabled:
            return False, "Safety guardrails disabled (fail-safe)"

        action = action_plan.get("recommended_action", "").lower()
        confidence = action_plan.get("confidence", 0.0)

        # 1. Check Confidence
        if confidence < 0.8:
            return False, f"Confidence too low ({confidence:.2f} < 0.8)"

        # 2. Check Forbidden Actions (dynamic + default)
        if any(forbidden in action for forbidden in self._forbidden):
            return False, f"Action '{action}' is FORBIDDEN"

        # 3. Check Approval Required (dynamic + default)
        if any(req in action for req in self._approval_required):
            return False, f"Action '{action}' requires HUMAN APPROVAL"

        # 4. Check Blast Radius
        affected = action_plan.get("affected_entities", [])
        if isinstance(affected, list) and len(affected) > 5:
            return False, "Blast radius too high (>5 entities affected)"

        return True, "Action is safe and within autonomy limits"

    def validate_action_syntax(self, action: str) -> bool:
        """Basic validation to prevent command injection characters if generating shell commands"""
        dangerous_chars = [";", "&&", "|", ">", "`", "$("]
        if any(char in action for char in dangerous_chars):
            return False
        return True

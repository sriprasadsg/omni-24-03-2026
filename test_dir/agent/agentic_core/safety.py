import logging

logger = logging.getLogger(__name__)

class SafetyGuardrails:
    """
    Enforces safety constraints on autonomous actions.
    Acts as the final gatekeeper before any AI decision is executed.
    """
    
    # Actions that are NEVER allowed autonomously
    FORBIDDEN_ACTIONS = [
        "delete_critical_files",
        "shutdown_production", 
        "modify_firewall_allow_all",
        "disable_antivirus",
        "wipe_disk",
        "uninstall_agent"
    ]
    
    # Actions that ALWAYS require human approval (via backend)
    APPROVAL_REQUIRED = [
        "restart_service",
        "modify_configuration",
        "deploy_patch",
        "update_application",
        "isolate_host"
    ]
    
    # Actions that are strictly "Safe" / Read-only or Low impact
    SAFE_ACTIONS = [
        "scan_system",
        "collect_logs",
        "check_status",
        "kill_process_low_priority" 
    ]

    def __init__(self, config=None):
        self.config = config or {}
        self.enabled = self.config.get("enabled", True)

    def is_safe_to_act(self, action_plan: dict) -> tuple[bool, str]:
        """
        Validate if an action plan is safe to execute autonomously.
        Returns: (is_safe: bool, reason: str)
        """
        if not self.enabled:
            return False, "Safety guardrails disabled (fail-safe)"

        action = action_plan.get("recommended_action", "").lower()
        confidence = action_plan.get("confidence", 0.0)
        
        # 1. Check Confidence
        if confidence < 0.8:
            return False, f"Confidence too low ({confidence:.2f} < 0.8)"

        # 2. Check Forbidden Actions
        if any(forbidden in action for forbidden in self.FORBIDDEN_ACTIONS):
            return False, f"Action '{action}' is FORBIDDEN"

        # 3. Check Approval Required
        if any(req in action for req in self.APPROVAL_REQUIRED):
            return False, f"Action '{action}' requires HUMAN APPROVAL"

        # 4. Explicit Safe List check (Optionally strict mode)
        # For now, we allow if not forbidden/approval, but ideally should be whitelist based
        # if not any(safe in action for safe in self.SAFE_ACTIONS):
        #    return False, "Action not in explicit safe list"

        # 5. Check Blast Radius (Simulated)
        if hasattr(action_plan, 'affected_entities') and len(action_plan['affected_entities']) > 5:
             return False, "Blast radius too high (>5 entities affected)"

        return True, "Action is safe and within autonomy limits"

    def validate_action_syntax(self, action: str) -> bool:
        """Basic validation to prevent command injection characters if generating shell commands"""
        dangerous_chars = [";", "&&", "|", ">", "`", "$("]
        if any(char in action for char in dangerous_chars):
            return False
        return True

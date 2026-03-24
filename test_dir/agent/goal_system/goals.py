from dataclasses import dataclass

@dataclass
class AgentGoal:
    """
    Represents a high-level goal the agent should strive to achieve.
    """
    name: str
    target: float
    priority: int
    unit: str = ""
    description: str = ""
    
    # State
    current_value: float = 0.0
    status: str = "pending" # pending, active, achieved, failed

    def calculate_achievement(self) -> float:
        """Calculate percentage achievement (0-100)"""
        if self.target == 0:
            return 100.0 if self.current_value == 0 else 0.0
        
        # Simple ratio for now, can be complex logic later
        ratio = (self.current_value / self.target) * 100.0
        return min(max(ratio, 0.0), 100.0)

    def is_achieved(self) -> bool:
        """Check if goal is met"""
        # Assuming 'higher is better' for now, or use specific logic per goal type
        return self.current_value >= self.target

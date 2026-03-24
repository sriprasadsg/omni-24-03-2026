import logging
import json
from typing import List, Dict
from .goals import AgentGoal

logger = logging.getLogger(__name__)

class GoalManager:
    """
    Manages agent goals, tracks progress, and generates strategic plans.
    """
    
    def __init__(self, llm_engine, config=None):
        self.llm = llm_engine
        self.config = config or {}
        self.goals: Dict[str, AgentGoal] = {}
        
        # Load default goals from config
        self._load_goals_from_config(self.config.get('goals', []))

    def _load_goals_from_config(self, goals_cfg: List[dict]):
        """Initialize goals from configuration"""
        for g_cfg in goals_cfg:
            goal = AgentGoal(
                name=g_cfg.get('name', 'unknown'),
                target=float(g_cfg.get('target', 0.0)),
                priority=int(g_cfg.get('priority', 5)),
                unit=g_cfg.get('unit', ''),
                description=g_cfg.get('description', '')
            )
            self.goals[goal.name] = goal
            logger.info(f"Initialized Goal: {goal.name} (Target: {goal.target})")

    def update_goal_progress(self, goal_name: str, current_value: float):
        """Update the current status of a goal"""
        if goal_name in self.goals:
            self.goals[goal_name].current_value = current_value
            # logger.debug(f"Updated goal {goal_name}: {current_value}")

    def evaluate_goals(self) -> List[AgentGoal]:
        """Return list of goals that are failing (underperforming)"""
        underperforming = []
        for goal in self.goals.values():
            if not goal.is_achieved():
                underperforming.append(goal)
        return sorted(underperforming, key=lambda x: x.priority)

    def generate_strategic_plan(self, failed_goal: AgentGoal, context: dict) -> dict:
        """
        Use LLM to generate a high-level strategy to achieve a specific goal.
        """
        if not self.llm:
            return {"error": "No LLM available for planning"}
        
        logger.info(f"Generating strategy for failing goal: {failed_goal.name}")
        
        prompt = self._construct_planning_prompt(failed_goal, context)
        response = self.llm._query_ollama(prompt)
        
        try:
            return self.llm._parse_response(response)
        except Exception as e:
            logger.error(f"Failed to parse strategic plan: {e}")
            return {"error": "Planning Failed"}

    def _construct_planning_prompt(self, goal: AgentGoal, context: dict) -> str:
        return f"""You are a strategic AI planner.
The system is failing to meet a high-level goal.
        
GOAL: {goal.name}
TARGET: {goal.target} {goal.unit}
CURRENT: {goal.current_value} {goal.unit}
DESC: {goal.description}

SYSTEM CONTEXT:
{json.dumps(context, indent=2)}

TASK:
Generate a strategic plan to bridge the gap between Current and Target.
Return a JSON object with:
1. "strategy": High level approach
2. "actions": List of specific steps (e.g. "deploy_patch", "optimize_config")
3. "estimated_impact": Expected improvement
        
RESPONSE JSON:
"""

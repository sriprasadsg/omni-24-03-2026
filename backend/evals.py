import logging
import asyncio
from typing import List, Dict, Any, Optional
from pydantic import BaseModel

logger = logging.getLogger("EvalFramework")

class TestCase(BaseModel):
    name: str
    instruction: str
    expected_action: Optional[str] = None
    expected_phrases: List[str] = []
    
class TestResult(BaseModel):
    test_case: str
    passed: bool
    actual_action: str
    score: float
    details: str

class Evaluator:
    def __init__(self, agent_manager):
        self.agent = agent_manager
        
    def evaluate_test_case(self, test: TestCase) -> TestResult:
        """Run a single test case against the agent logic."""
        logger.info(f"Running Eval: {test.name}")
        
        try:
            # Execute Agent Logic (Synchronously for eval simplicity, or await if async)
            # agent_manager.execute_single_instruction is synchronous in our current implementation
            result = self.agent.execute_single_instruction(test.instruction)
            
            decision = result.get("decision", {})
            action = decision.get("action", "none")
            plan = result.get("plan", {})
            plan_str = str(plan)
            
            # Scoring Logic
            score = 0.0
            passed = False
            details = []
            
            # 1. Action Match
            if test.expected_action:
                if test.expected_action.lower() in action.lower():
                    score += 0.5
                    details.append(f"✅ Action matched '{test.expected_action}'")
                else:
                    details.append(f"❌ Action mismatch. Expected '{test.expected_action}', got '{action}'")
            else:
                score += 0.5 # Free points if no action expectation
            
            # 2. Phrase Match in Plan
            phrase_hits = 0
            if test.expected_phrases:
                for phrase in test.expected_phrases:
                    if phrase.lower() in plan_str.lower() or phrase.lower() in str(result).lower():
                        phrase_hits += 1
                
                phrase_score = (phrase_hits / len(test.expected_phrases)) * 0.5
                score += phrase_score
                details.append(f"Found {phrase_hits}/{len(test.expected_phrases)} expected phrases")
            else:
                score += 0.5
                
            passed = score >= 0.8
            
            return TestResult(
                test_case=test.name,
                passed=passed,
                actual_action=action,
                score=score,
                details="; ".join(details)
            )
            
        except Exception as e:
            logger.error(f"Eval Error: {e}")
            return TestResult(
                test_case=test.name,
                passed=False,
                actual_action="error",
                score=0.0,
                details=str(e)
            )

    def run_suite(self, suite: List[TestCase]) -> Dict[str, Any]:
        results = [self.evaluate_test_case(test) for test in suite]
        
        total_score = sum(r.score for r in results)
        avg_score = total_score / len(results) if results else 0
        
        return {
            "total_tests": len(results),
            "passed": sum(1 for r in results if r.passed),
            "average_score": avg_score,
            "results": [r.dict() for r in results]
        }

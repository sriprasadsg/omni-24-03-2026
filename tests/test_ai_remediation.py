import logging
import sys
import os
from unittest.mock import MagicMock

# Add the project root to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from agent.autonomous_actions.remediation import AutonomousRemediationEngine

def test_ai_remediation():
    logging.basicConfig(level=logging.INFO)
    
    # Mock Reasoning Engine and LLM
    mock_reasoning = MagicMock()
    mock_llm = MagicMock()
    mock_reasoning.llm = mock_llm
    
    # Mock LLM plan_remediation response
    mock_llm.plan_remediation.return_value = {
        "name": "Test Remediation Plan",
        "affected_services": ["test-service"],
        "affected_files": ["C:\\temp\\test.txt"],
        "steps": [
            {
                "action": "restart_service",
                "target": "test-service",
                "description": "Restarting test service"
            },
            {
                "action": "run_command",
                "target": "echo 'Hello World'",
                "description": "Running test command"
            }
        ]
    }
    
    # Mock Reasoning decide_action response (Autonomous allowed)
    mock_reasoning.decide_action.return_value = {
        "is_autonomous": True,
        "action": "Test Remediation Plan"
    }
    
    engine = AutonomousRemediationEngine(mock_reasoning)
    
    issue = {
        "title": "Test Issue",
        "recommended_action": "Restart test-service"
    }
    
    print("Starting AI-driven remediation test...")
    success = engine.execute_remediation(issue)
    
    if success:
        print("✅ AI-driven remediation test passed!")
    else:
        print("❌ AI-driven remediation test failed!")

if __name__ == "__main__":
    test_ai_remediation()

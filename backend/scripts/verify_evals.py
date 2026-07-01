import sys
from pathlib import Path

# Add 'agent' directory to sys.path
agent_dir = str(Path(__file__).parent.parent / "agent")
if agent_dir not in sys.path:
    sys.path.append(agent_dir)

from evals import Evaluator, TestCase
try:
    from agent import AgentCapabilityManager, load_config
except ImportError:
    # If running from backend dir, agent might not be found without sys.path
    pass
import logging

# Setup basic logging
logging.basicConfig(level=logging.INFO)

def run_verification():
    print("🚀 Verifying Evaluation Framework...")
    
    # 1. Init Agent
    print("... Initializing Agent (This might take a moment to load LLM/Chroma) ...")
    try:
        cfg = load_config()
        # Mocking or using real? Let's try real for end-to-end confidence
        agent = AgentCapabilityManager(cfg)
        agent.fetch_configuration()
    except Exception as e:
        print(f"❌ Failed to init agent: {e}")
        return

    # 2. Define Test Suite
    suite = [
        TestCase(
            name="RAG Knowledge Retrieval",
            instruction="What is the code for the server room?", 
            expected_phrases=["998877", "server room"],
            expected_action="none" # Retrieval usually just returns text plan
        ),
        TestCase(
            name="System Health Check",
            instruction="Check system health status",
            expected_action="execute_tool",
            expected_phrases=["health", "status"]
        )
    ]
    
    # 3. Run Evaluator
    evaluator = Evaluator(agent)
    results = evaluator.run_suite(suite)
    
    # 4. Report
    print(f"\n📊 Eval Results: {results['passed']}/{results['total_tests']} Passed")
    print(f"Average Score: {results['average_score']:.2f}")
    
    for r in results['results']:
        status = "✅" if r['passed'] else "❌"
        print(f"{status} {r['test_case']}: Score {r['score']} - {r['details']}")

if __name__ == "__main__":
    run_verification()

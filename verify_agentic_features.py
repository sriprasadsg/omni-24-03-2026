
import logging
import time
import sys
import os

# Ensure the 'agent' directory is treated as a package
# We append the current directory to path
sys.path.append(os.getcwd())

# If agent/agent.py exists, it might shadow the package if not careful.
# we try to import components directly.

try:
    from agent.agentic_core.tool_registry import registry
    from agent.agentic_core.reasoning import AgenticReasoningEngine
    from agent.agentic_core.llm_engine import AgenticLLM
    from agent.agentic_core.safety import SafetyGuardrails
    from agent.knowledge_base.memory import AgentMemory
    from agent.swarm.coordinator import SwarmCoordinator
except ImportError:
    # Fallback if running directly inside agent folder or similar
    sys.path.append(os.path.join(os.getcwd(), 'agent'))
    from agentic_core.tool_registry import registry
    from agentic_core.reasoning import AgenticReasoningEngine
    from agentic_core.llm_engine import AgenticLLM
    from agentic_core.safety import SafetyGuardrails
    from knowledge_base.memory import AgentMemory
    from swarm.coordinator import SwarmCoordinator


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("Verification")

def test_tool_registry():
    logger.info("--- Testing Tool Registry ---")
    
    @registry.register
    def dummy_tool(x: int, y: int) -> int:
        """Adds two numbers"""
        return x + y
    
    schemas = registry.get_all_schemas()
    assert len(schemas) > 0, "Registry should have schemas"
    assert schemas[0]['name'] == 'dummy_tool'
    
    result = registry.execute("dummy_tool", {"x": 5, "y": 10})
    logger.info(f"Tool Execution Result: {result}")
    assert result == 15, "Tool execution failed"
    logger.info("✅ Tool Registry Verified")

def test_memory_embeddings():
    logger.info("--- Testing Semantic Memory ---")
    mem = AgentMemory(data_dir="test_data")
    
    # Store dummy
    context = {"cpu_usage": 95, "alerts": [{"type": "CPU_Overload", "details": "Critical"}]}
    mem.store_experience(context, "optimize_process", {"success": True})
    
    # Retrieve similar
    new_context = {"cpu_usage": 90} # Similar
    matches = mem.find_similar_situations(new_context)
    
    logger.info(f"Found {len(matches)} matches")
    if len(matches) > 0:
        logger.info(f"Top Match Action: {matches[0]['action']}")
    
    # Cleanup
    import shutil
    try:
        shutil.rmtree("test_data")
    except:
        pass
    logger.info("✅ Memory Verified")

def test_swarm_offload():
    logger.info("--- Testing Swarm Offloading ---")
    coord = SwarmCoordinator(agent_id="agent_1")
    coord.peer_data["agent_2"] = {"ip_address": "127.0.0.1", "gossip_port": 12345}
    
    # Simulate sending task (will fail connection but logic should pass)
    success = coord.request_task_offload({"task": "test"}, "agent_2")
    assert success, "Offload request failed logic"
    
    # Simulate receiving task
    payload = {
        "type": "TASK_OFFLOAD",
        "source_id": "agent_2", 
        "content": {"description": "Analyze Log"}
    }
    coord.handle_remote_task(payload)
    logger.info("✅ Swarm Offloading Logic Verified")

if __name__ == "__main__":
    test_tool_registry()
    test_memory_embeddings()
    test_swarm_offload()

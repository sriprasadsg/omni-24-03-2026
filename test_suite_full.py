
import unittest
import sys
import os
import subprocess

# Add agent path
sys.path.append(os.path.join(os.getcwd(), 'agent'))

class AgentTestSuite(unittest.TestCase):
    def test_agentic_features(self):
        print("\n=== Testing Agentic AI Core ===")
        import verify_agentic_features
        verify_agentic_features.test_tool_registry()
        verify_agentic_features.test_memory_embeddings()
        verify_agentic_features.test_swarm_offload()
        print("✅ Agentic Features Passed")

    def test_self_healing(self):
        print("\n=== Testing Self-Healing Capability ===")
        # Run the unittest executable for the existing file
        result = subprocess.run([sys.executable, "agent/test_self_healing.py"], capture_output=True, text=True)
        if result.returncode != 0:
            print(result.stderr)
            self.fail("Self-Healing Tests Failed")
        print("✅ Self-Healing Tests Passed")

    def test_update_capability(self):
        print("\n=== Testing Auto-Update Capability ===")
        if os.path.exists("agent/test_update_capability.py"):
            result = subprocess.run([sys.executable, "agent/test_update_capability.py"], capture_output=True, text=True)
            if result.returncode != 0:
                 print(result.stderr)
                 self.fail("Update Capability Tests Failed")
            print("✅ Update Capability Tests Passed")
        else:
            print("⚠️ Update test file not found, skipping.")

if __name__ == '__main__':
    unittest.main()

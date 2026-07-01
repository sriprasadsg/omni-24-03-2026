
import sys
import os

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from agent.capabilities.system_patching import SystemPatchingCapability

def test_capability():
    print("Initializing Capability...")
    cap = SystemPatchingCapability()
    print("Collecting Data (PowerShell based)...")
    data = cap.collect()
    
    print("\n--- Collection Result ---")
    print(f"Pending Updates: {len(data['pending_updates'])}")
    print(f"BIOS: {data['bios_info']}")
    print(f"Uptime: {data['uptime']}")

if __name__ == "__main__":
    test_capability()

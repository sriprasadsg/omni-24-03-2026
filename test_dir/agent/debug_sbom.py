
import sys
import os

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from agent.capabilities.sbom import SBOMAnalysisCapability

def test_sbom():
    print("Testing SBOM Collection...")
    cap = SBOMAnalysisCapability()
    data = cap.collect()
    print("Collection Complete.")
    print(f"Total Components: {data['total_components']}")
    updates = [c for c in data['components'] if c.get('updateAvailable')]
    print(f"Updates Found: {len(updates)}")
    for u in updates:
        print(f" - {u['name']} (Latest: {u['latestVersion']})")

if __name__ == "__main__":
    test_sbom()

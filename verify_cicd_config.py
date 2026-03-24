import os
import yaml

WORKFLOW_DIR = ".github/workflows"

def verify_workflows():
    print("Verifying GitHub Actions Workflows...")
    
    if not os.path.exists(WORKFLOW_DIR):
        print(f"FAIL: Directory '{WORKFLOW_DIR}' does not exist.")
        return

    files = [f for f in os.listdir(WORKFLOW_DIR) if f.endswith(".yml") or f.endswith(".yaml")]
    if not files:
        print("FAIL: No workflow files found.")
        return

    print(f"Found {len(files)} workflows: {files}\n")

    required_workflows = ["ci.yml", "cd.yml"]
    found_workflows = []

    for filename in files:
        filepath = os.path.join(WORKFLOW_DIR, filename)
        print(f"Checking {filename}...")
        
        try:
            with open(filepath, 'r') as f:
                data = yaml.safe_load(f)
                
                if not data:
                    print(f"  WARN: Empty file {filename}")
                    continue
                    
                name = data.get("name")
                on = data.get("on")
                jobs = data.get("jobs")
                
                if name and on and jobs:
                    print(f"  OK: Workflow '{name}' has valid structure (Triggers: {list(on.keys())}, Jobs: {len(jobs)})")
                    found_workflows.append(filename)
                else:
                    print(f"  FAIL: Missing required top-level keys in {filename} (name, on, jobs)")

        except Exception as e:
            print(f"  FAIL: Error parsing {filename}: {e}")

    # Verify coverage
    missing = [w for w in required_workflows if w not in found_workflows]
    if missing:
        print(f"\nFAIL: Missing critical workflows: {missing}")
    else:
        print("\nPASS: All expected workflows found and valid.")

if __name__ == "__main__":
    verify_workflows()

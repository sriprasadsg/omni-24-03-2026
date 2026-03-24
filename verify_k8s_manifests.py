import os
import yaml

MANIFEST_DIR = "kubernetes"

def verify_manifests():
    print("Verifying Kubernetes Manifests...")
    
    if not os.path.exists(MANIFEST_DIR):
        print(f"FAIL: Directory '{MANIFEST_DIR}' does not exist.")
        return

    files = [f for f in os.listdir(MANIFEST_DIR) if f.endswith(".yaml")]
    if not files:
        print("FAIL: No YAML files found.")
        return

    print(f"Found {len(files)} manifests: {files}\n")

    required_kinds = ["Namespace", "StatefulSet", "Deployment", "Service", "Ingress"]
    found_kinds = []

    for filename in files:
        filepath = os.path.join(MANIFEST_DIR, filename)
        print(f"Checking {filename}...")
        
        try:
            with open(filepath, 'r') as f:
                # yaml.safe_load_all supports multi-doc files (separated by ---)
                docs = list(yaml.safe_load_all(f))
                
                for doc in docs:
                    if not doc: continue
                    
                    kind = doc.get("kind")
                    name = doc.get("metadata", {}).get("name")
                    namespace = doc.get("metadata", {}).get("namespace")
                    
                    if kind and name:
                        print(f"  OK: Found {kind} '{name}'")
                        found_kinds.append(kind)
                    else:
                        print(f"  WARN: Missing kind or metadata.name in {filename}")

                    # Basic check: Namespace consistency
                    if kind != "Namespace" and namespace != "omni-platform":
                         print(f"  WARN: Resource {kind}/{name} not in 'omni-platform' namespace")
                         
        except Exception as e:
            print(f"  FAIL: Error parsing {filename}: {e}")

    # Verify coverage
    missing = [k for k in required_kinds if k not in found_kinds]
    if missing:
        print(f"\nFAIL: Missing critical resource kinds: {missing}")
    else:
        print("\nPASS: All expected resource types found.")

if __name__ == "__main__":
    verify_manifests()

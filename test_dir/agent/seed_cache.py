
import subprocess
import json
import re

def seed_cache():
    print("Seeding SBOM cache via Winget...")
    upgrades = []
    try:
        cmd = ["winget", "upgrade", "--include-unknown"]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60, encoding='utf-8', errors='ignore')
        
        if result.returncode == 0:
            lines = result.stdout.splitlines()
            start_idx = -1
            for i, line in enumerate(lines):
                if line.strip().startswith("Name") and "Id" in line:
                    start_idx = i + 2
                    break
            
            if start_idx != -1:
                for line in lines[start_idx:]:
                    if not line.strip(): continue
                    parts = re.split(r'\s{2,}', line.strip())
                    if len(parts) >= 4:
                        upgrades.append({
                            "name": parts[0],
                            "id": parts[1],
                            "current_version": parts[2],
                            "available_version": parts[3]
                        })
        
        # Write to cache
        # Note: The agent runs from d:/Downloads/enterprise-omni-agent-ai-platform
        # so we write to that CWD
        import os
        cwd = os.getcwd()
        cache_path = os.path.join(cwd, "sbom_upgrades_cache.json")
        with open(cache_path, "w") as f:
            json.dump(upgrades, f, indent=2)
            
        print(f"Success: Wrote {len(upgrades)} upgrades to {cache_path}")
        
    except Exception as e:
        print(f"Error seeding cache: {e}")

if __name__ == "__main__":
    seed_cache()

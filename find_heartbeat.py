
import os

target_dir = r"d:\Downloads\enterprise-omni-agent-ai-platform\backend"
term = "heartbeat"

for root, dirs, files in os.walk(target_dir):
    for file in files:
        if file.endswith(".py"):
            path = os.path.join(root, file)
            try:
                with open(path, "r", encoding="utf-8") as f:
                    content = f.read()
                    if term in content:
                        print(f"MATCH: {file}")
                        # Print context
                        lines = content.splitlines()
                        for i, line in enumerate(lines):
                            if term in line:
                                print(f"  {i+1}: {line.strip()[:100]}")
            except:
                pass

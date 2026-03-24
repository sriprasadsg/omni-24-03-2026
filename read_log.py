

import re

try:
    with open("agent_comp_retry.log", "r", encoding="utf-16") as f:
        content = f.read()
except:
    try:
        with open("agent_comp_retry.log", "r", encoding="utf-8") as f:
            content = f.read()
    except Exception as e:
        print(f"Error: {e}")
        content = ""

# Find "compliance" related logs
matches = list(re.finditer("compliance", content, re.IGNORECASE))
if matches:
    print(f"Found {len(matches)} compliance mentions.")
    for m in matches:
        start = max(0, m.start() - 50)
        end = min(len(content), m.end() + 150)
        print(content[start:end])
        print("-" * 80)
else:
    print("No 'compliance' keyword found.")
    print(f"Content length: {len(content)}")
    # Show last 500 chars
    print("\nLast 500 chars:")
    print(content[-500:])

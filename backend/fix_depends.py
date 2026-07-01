"""Add Depends to existing fastapi imports"""
import re

files = [
    "threat_endpoints.py",
    "notification_endpoints.py",
    "maintenance_endpoints.py",
    "kpi_endpoints.py",
    "deployment_endpoints.py",
    "ai_endpoints.py",
]

for filename in files:
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Pattern to find "from fastapi import ..." without Depends
        pattern = r'from fastapi import ([^D\n]+?)(\n|$)'
        
        def replacer(match):
            imports = match.group(1)
            if 'Depends' in imports:
                return match.group(0)  # Already has Depends
            return f"from fastapi import {imports}, Depends{match.group(2)}"
        
        new_content = re.sub(pattern, replacer, content)
        
        if new_content != content:
            with open(filename, 'w', encoding='utf-8') as f:
                f.write(new_content)
            print(f"✅ Added Depends to {filename}")
        else:
            print(f"✓  {filename} already OK")
    except Exception as e:
        print(f"❌ Error with {filename}: {e}")

print("\n✅ Done!")

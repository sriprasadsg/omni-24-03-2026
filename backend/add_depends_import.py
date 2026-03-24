"""Add missing Depends import to all endpoint files"""
import os

endpoint_files = [
    "vuln_endpoints.py",
    "threat_endpoints.py",
    "notification_endpoints.py",
    "maintenance_endpoints.py",
    "kpi_endpoints.py",
    "deployment_endpoints.py",
    "audit_endpoints.py",
    "ai_endpoints.py",
]

for filename in endpoint_files:
    if not os.path.exists(filename):
        continue
    
    with open(filename, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Check if Depends is already imported
    if 'from fastapi import' in content and 'Depends' not in content:
        # Need to add Depends to the imports
        lines = content.split('\n')
        for i, line in enumerate(lines):
            if 'from fastAPI import' in line or 'from fastapi import' in line:
                if 'Depends' not in line:
                    # Add Depends to this import
                    line = line.rstrip()
                    if line.endswith(')'):
                        # Multi-line import
                        line = line[:-1] + ', Depends)'
                    else:
                        # Single line import
                        line = line + ', Depends'
                    lines[i] = line
                    print(f"✅ Added Depends to {filename}")
                    break
        
        content = '\n'.join(lines)
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(content)
    elif 'Depends' not in content:
        # No fastapi import, add it after other imports
        lines = content.split('\n')
        insert_idx = 0
        for i, line in enumerate(lines):
            if line.startswith('from ') or line.startswith('import '):
                insert_idx = i + 1
        
        lines.insert(insert_idx, 'from fastapi import Depends')
        content = '\n'.join(lines)
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"✅ Added fastapi Depends import to {filename}")
    else:
        print(f"✓  {filename} already has Depends import")

print("\n✅ All files checked!")

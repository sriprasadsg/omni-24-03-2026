import re
import os
import subprocess

with open('backend/compliance_endpoints.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Find MAPPINGS dictionary
match = re.search(r'MAPPINGS\s*=\s*({.*?})\s*timestamp', content, re.DOTALL)
if match:
    mappings_str = match.group(1)
    
    with open('inject_mongo.py', 'r', encoding='utf-8') as f:
        inject_code = f.read()
        
    # Replace the import with the actual dict definition
    inject_code = inject_code.replace('from compliance_endpoints import MAPPINGS', f'MAPPINGS = {mappings_str}')
    
    with open('inject_mongo.py', 'w', encoding='utf-8') as f:
        f.write(inject_code)
        
    print("MAPPINGS injected! Running inject_mongo.py...")
    subprocess.run(["python", "inject_mongo.py"])

else:
    print("Could not find MAPPINGS")

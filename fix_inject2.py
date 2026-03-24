import json
import subprocess

with open('missing_controls.json', 'r') as f:
    missing = json.load(f)

with open('inject_mongo.py', 'r', encoding='utf-8') as f:
    inject_code = f.read()

# Just append the key to the MAPPINGS dictionary in inject_mongo.py
# The string looks like "Data Leakage Prevention Simulation": ["PCI-12.1", "PR.DS-5", "A.8.12"],
#     }
new_mapping = f',\n        "Universal Non-Tech Controls Simulation": {json.dumps(missing)}\n    }}'
inject_code = inject_code.replace('        "Data Leakage Prevention Simulation": ["PCI-12.1", "PR.DS-5", "A.8.12"],\n    }', f'        "Data Leakage Prevention Simulation": ["PCI-12.1", "PR.DS-5", "A.8.12"]{new_mapping}')

with open('inject_mongo.py', 'w', encoding='utf-8') as f:
    f.write(inject_code)

print("Injected into MAPPINGS in inject_mongo.py! Running...")
subprocess.run(["python", "inject_mongo.py"])


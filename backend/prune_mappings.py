import re
import os

def clean_mappings():
    path = os.path.join(os.path.dirname(__file__), "compliance_endpoints.py")
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    # We need to remove the "Universal Non-Tech Controls Simulation" entry entirely 
    # since all of its mappings are administrative policies.
    content = re.sub(
        r'"Universal Non-Tech Controls Simulation":\s*\[.*?\],\n?', 
        '', 
        content, 
        flags=re.DOTALL
    )

    # We need to selectively remove "CISSP-1.3" from all technical admin checks
    # since technical checks don't prove enterprise risk management processes.
    content = re.sub(r'"CISSP-1\.3",\s*', '', content)
    content = re.sub(r',\s*"CISSP-1\.3"', '', content)
    content = re.sub(r'"CISSP-1\.3"', '', content)
    
    # Same for CISSP-1.5, CISSP-1.6, CISSP-2.2, CISSP-2.3, etc. mapped to simple technical tests
    # CISSP-1.5 (Security Policy & Standards - Min Password Length doesn't prove policy)
    content = re.sub(r'"CISSP-1\.5",\s*', '', content)
    # CISSP-1.4 (BCP/DR - Data Backup alone doesn't prove full formal BCP process)
    content = re.sub(r'"CISSP-1\.4",\s*', '', content)
    # CISSP-2.2 (Data Privacy & Protection - Bitlocker alone doesn't prove DPIA/Data Flow adherence)
    content = re.sub(r'"CISSP-2\.2",\s*', '', content)

    # Remove empty brackets that might be left behind: "Key": [], -> remove line
    content = re.sub(r'\s*"[^"]+":\s*\[\],\n?', '\n', content)

    with open(path, "w", encoding="utf-8") as f:
        f.write(content)

    print("Successfully cleaned compliance_endpoints.py")

if __name__ == "__main__":
    clean_mappings()

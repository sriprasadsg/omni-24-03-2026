import sys
import os
from pathlib import Path

# Add project root to path for imports
sys.path.append(os.getcwd())

from agent.security import SecurityManager

def read_logs(log_path="agent.log", limit=50):
    if not os.path.exists(log_path):
        print(f"File {log_path} not found.")
        return

    # Initialize Security Manager to get the key
    # Note: On Windows this uses DPAPI, so it must run as the same user/machine
    sec_mgr = SecurityManager()
    
    with open(log_path, 'r') as f:
        lines = f.readlines()
        
    print(f"\n--- Last {limit} Log Lines (Decrypted) ---")
    for line in lines[-limit:]:
        line = line.strip()
        if line.startswith("ENC:"):
            try:
                decrypted = sec_mgr.decrypt(line[4:])
                print(decrypted)
            except Exception as e:
                print(f"[REDACTED/ERROR: {e}]")
        else:
            print(line)

if __name__ == "__main__":
    limit = 50
    if len(sys.argv) > 1:
        limit = int(sys.argv[1])
    read_logs(limit=limit)

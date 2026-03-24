import subprocess
import sys
import os
import time

SCRIPTS = [
    "verify_mlops.py",
    "verify_xai.py",
    "verify_ab_testing.py",
    "verify_ueba_shadow.py",
    "verify_integrations_phase5.py"
]

LOG_FILE = "backend_verification_log.txt"

def run_script(script_name):
    print(f"--- Running {script_name} ---")
    with open(LOG_FILE, "a") as f:
        f.write(f"\n\n{'='*30}\nRUNNING: {script_name}\n{'='*30}\n")
        f.flush()
        
    try:
        # Run process and capture output
        result = subprocess.run(
            [sys.executable, script_name],
            cwd=os.getcwd(),
            capture_output=True,
            text=True
        )
        
        output = result.stdout + "\n" + result.stderr
        print(output)
        
        with open(LOG_FILE, "a") as f:
            f.write(output)
            f.write(f"\nEXIT CODE: {result.returncode}\n")
            if result.returncode == 0:
                f.write("STATUS: PASSED\n")
            else:
                f.write("STATUS: FAILED\n")
                
        return result.returncode == 0
    except Exception as e:
        print(f"Error running {script_name}: {e}")
        with open(LOG_FILE, "a") as f:
            f.write(f"EXECUTION ERROR: {e}\nSTATUS: CRASHED\n")
        return False

def main():
    # Clear log file
    with open(LOG_FILE, "w") as f:
        f.write("ENTERPRISE OMNI-AGENT AI PLATFORM - COMPREHENSIVE TEST LOG\n")
        f.write(f"Date: {time.ctime()}\n")
        
    passed = 0
    failed = 0
    
    for script in SCRIPTS:
        if os.path.exists(script):
            if run_script(script):
                passed += 1
            else:
                failed += 1
        else:
            print(f"Warning: {script} not found.")
            with open(LOG_FILE, "a") as f:
                f.write(f"\n\n--- SKIP: {script} NOT FOUND ---\n")
                
    summary = f"\n\n{'='*30}\nSUMMARY\n{'='*30}\nPASSED: {passed}\nFAILED: {failed}\nTotal: {len(SCRIPTS)}\n"
    print(summary)
    with open(LOG_FILE, "a") as f:
        f.write(summary)

if __name__ == "__main__":
    main()

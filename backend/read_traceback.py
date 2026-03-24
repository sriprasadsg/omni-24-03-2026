
import os

def read_log():
    log_file = "captured_output.txt"
    if not os.path.exists(log_file):
        print(f"File {log_file} does not exist.")
        return

    with open(log_file, "rb") as f:
        content_bytes = f.read()

    # Try decoding
    content = content_bytes.decode("utf-8", errors="replace")

    lines = content.splitlines()
    printing = False
    for i, line in enumerate(lines):
        if "Traceback" in line:
            printing = True
            print(f"--- START TRACEBACK (Line {i}) ---")
        
        if printing:
            print(line)
            if "Internal Server Error" in line: # End of interesting part usually
                pass 
    
    if not printing:
        print("No traceback found. Printing last 50 lines:")
        for line in lines[-50:]:
            print(line)

if __name__ == "__main__":
    read_log()

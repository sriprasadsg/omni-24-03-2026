
import sys

def check_exe(path):
    try:
        with open(path, 'rb') as f:
            header = f.read(2)
            print(f"Header: {header}")
            if header == b'MZ':
                print("Valid DOS/PE header found.")
            else:
                print("INVALID header. Not a Windows executable.")
    except Exception as e:
        print(f"Error: {e}")

check_exe(r'd:/Downloads/enterprise-omni-agent-ai-platform/backend/static/omni-agent.exe')

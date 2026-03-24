import os
import subprocess
import signal
import sys
import time
import psutil

def kill_existing_agent():
    print("Searching for existing agent instances...")
    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            cmdline = proc.info.get('cmdline')
            if cmdline and 'agent.py' in ' '.join(cmdline):
                print(f"Killing process {proc.info['pid']}...")
                proc.kill()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

def start_agent():
    print("Starting secure agent...")
    agent_path = os.path.join(os.getcwd(), 'agent', 'agent.py')
    # Run in background
    # We use a log file to capture startup errors
    with open('agent_startup.log', 'w') as f:
        subprocess.Popen([sys.executable, agent_path], 
                         stdout=f, stderr=f, 
                         cwd=os.getcwd(),
                         creationflags=subprocess.CREATE_NEW_CONSOLE if os.name == 'nt' else 0)
    print("Agent started in new console.")

if __name__ == "__main__":
    kill_existing_agent()
    time.sleep(2)
    start_agent()
    print("Restart sequence complete.")

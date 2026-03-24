import psutil
import os

def kill_project_processes():
    targets = ['agent.py', 'app.py', 'vite', 'node']
    print(f"Targeting processes related to: {targets}")
    
    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            cmdline = proc.info.get('cmdline')
            if not cmdline:
                continue
                
            cmd_str = ' '.join(cmdline).lower()
            
            # Kill python scripts
            if 'python' in cmd_str and any(t in cmd_str for t in ['agent.py', 'app.py']):
                print(f"Killing Python process: PID {proc.info['pid']} - {cmd_str}")
                proc.kill()
                
            # Kill node/vite
            if any(t in cmd_str for t in ['vite', 'node_modules']):
                print(f"Killing Frontend process: PID {proc.info['pid']} - {cmd_str}")
                proc.kill()
                
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

if __name__ == "__main__":
    kill_project_processes()
    print("Cleanup complete.")

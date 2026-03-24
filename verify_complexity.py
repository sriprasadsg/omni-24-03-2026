
import subprocess
import os

def check_complexity():
    secedit_path = "secedit_test.cfg" # Use local dir to avoid perm issues for test
    # But real agent uses C:\Windows\Temp - let's try local first
    
    print(f"Running secedit export to {secedit_path}...")
    try:
        cmd = ['secedit', '/export', '/cfg', secedit_path]
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        print("STDOUT:", res.stdout)
        print("STDERR:", res.stderr)
        
        if os.path.exists(secedit_path):
            print("File created successfully.")
            try:
                # secedit uses UTF-16LE usually
                with open(secedit_path, 'r', encoding='utf-16') as f:
                    content = f.read()
                    print(f"Content length: {len(content)}")
                    if "PasswordComplexity = 1" in content:
                        print("✅ Found 'PasswordComplexity = 1'")
                    elif "PasswordComplexity = 0" in content:
                        print("⚠️ Found 'PasswordComplexity = 0' (Disabled)")
                    else:
                        print("❌ 'PasswordComplexity' key not found in file.")
                        print("Partial Content Preview:\n" + content[:500])
            except Exception as e:
                print(f"Error reading file: {e}")
        else:
            print("❌ File was NOT created.")
            
    except Exception as e:
        print(f"Error running secedit: {e}")

if __name__ == "__main__":
    check_complexity()

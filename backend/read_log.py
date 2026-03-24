
import os

def read_crash_log():
    try:
        # Try different encodings
        for enc in ['utf-16', 'utf-16-le', 'utf-8', 'latin-1']:
            try:
                with open('backend/backend_crash.log', 'r', encoding=enc) as f:
                    content = f.read()
                    if content:
                        print(f"--- CONTENT ({enc}) ---")
                        print(content[-2000:]) # Last 2000 chars
                        return
            except:
                continue
        print("Could not read file with any encoding")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    read_crash_log()


import sys

def search_log():
    try:
        # Try UTF-16LE first as per previous error hints
        with open("backend_no_auth.log", "r", encoding="utf-16le") as f:
            content = f.readlines()
    except Exception:
        # Fallback to UTF-8
        try:
            with open("backend_no_auth.log", "r", encoding="utf-8") as f:
                content = f.readlines()
        except Exception as e:
            print(f"Failed to read file: {e}")
            return

    found = False
    for i, line in enumerate(content):
        if "TypeError" in line and "vars()" in line:
            print(f"MATCH LINE {i}: {line.strip()}")
            start = max(0, i - 20)
            end = i + 1
            for j in range(start, end):
                print(f"{j}: {content[j].strip()}")
            found = True
            print("=" * 40)
    
    if not found:
        print("No TypeError found.")

    print("\nLAST 50 LINES:")
    for line in content[-50:]:
        print(line.strip())

if __name__ == "__main__":
    search_log()

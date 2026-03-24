
import subprocess
import os

def test_winget():
    print("Testing Winget...")
    try:
        # Check if winget is in path
        cmd = ["winget", "--version"]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        print(f"Winget Version: {result.stdout.strip()}")

        # Try to list upgrades
        print("\nChecking for upgrades (this might take a moment)...")
        # winget upgrade --include-unknown returns JSON-like output only if --json is passed? 
        # Actually `winget export` is json, but `upgrade` is text table usually.
        # Let's try `winget upgrade --include-unknown`
        cmd = ["winget", "upgrade", "--include-unknown"]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode == 0:
            print("Winget Upgrade Output (Sample):")
            print("\n".join(result.stdout.splitlines()[:20])) # First 20 lines
        else:
            print(f"Winget Upgrade Failed: {result.stderr}")

    except FileNotFoundError:
        print("Winget executable not found in PATH.")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test_winget()

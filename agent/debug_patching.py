
import subprocess
import json

def run_wmic():
    print("--- WMIC BIOS ---")
    try:
        cmd = ["wmic", "bios", "get", "Manufacturer,SMBIOSBIOSVersion,ReleaseDate", "/format:csv"]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
        print(f"Return Code: {result.returncode}")
        print(f"Stdout:\n{result.stdout}")
        print(f"Stderr:\n{result.stderr}")
    except Exception as e:
        print(f"Error: {e}")

    print("\n--- WMIC Uptime ---")
    try:
        cmd = ["wmic", "os", "get", "LastBootUpTime", "/format:csv"]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
        print(f"Return Code: {result.returncode}")
        print(f"Stdout:\n{result.stdout}")
    except Exception as e:
        print(f"Error: {e}")

def run_powershell():
    print("\n--- PowerShell BIOS (Proposed) ---")
    ps = "Get-CimInstance Win32_BIOS | Select-Object Manufacturer, SMBIOSBIOSVersion, ReleaseDate | ConvertTo-Json"
    try:
        cmd = ["powershell", "-Command", ps]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        print(f"Stdout:\n{result.stdout}")
    except Exception as e:
        print(f"Error: {e}")

    print("\n--- PowerShell Uptime (Proposed) ---")
    ps = "Get-CimInstance Win32_OperatingSystem | Select-Object LastBootUpTime | ConvertTo-Json"
    try:
        cmd = ["powershell", "-Command", ps]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        print(f"Stdout:\n{result.stdout}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    run_wmic()
    run_powershell()

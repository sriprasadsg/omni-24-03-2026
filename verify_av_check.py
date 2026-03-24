
import subprocess
import json

def check_av():
    print("--- Checking Defender Status ---")
    try:
        cmd = ['powershell', '-Command', 'Get-MpComputerStatus | Select-Object AntivirusEnabled, RealTimeProtectionEnabled | ConvertTo-Json']
        res = subprocess.run(cmd, capture_output=True, text=True)
        print("STDOUT:", res.stdout)
        print("STDERR:", res.stderr)
    except Exception as e:
        print("Error:", e)

    print("\n--- Checking WMI SecurityCenter2 ---")
    try:
        cmd = ['powershell', '-Command', 'Get-CimInstance -Namespace root/SecurityCenter2 -ClassName AntivirusProduct | Select-Object displayName, productState | ConvertTo-Json']
        res = subprocess.run(cmd, capture_output=True, text=True)
        print("STDOUT:", res.stdout)
        print("STDERR:", res.stderr)
    except Exception as e:
        print("Error:", e)

if __name__ == "__main__":
    check_av()


import subprocess
import json

def check_bitlocker():
    print("--- Checking BitLocker Status (Current Method) ---")
    try:
        # Replicating existing check: 
        # Get-BitLockerVolume -MountPoint C: | Select-Object -ExpandProperty ProtectionStatus
        cmd = ["powershell", "-Command", "Get-BitLockerVolume -MountPoint C: | Select-Object -ExpandProperty ProtectionStatus"]
        res = subprocess.run(cmd, capture_output=True, text=True)
        print("STDOUT (Raw):", repr(res.stdout))
        print("STDERR:", res.stderr)
        
        status_out = res.stdout.strip()
        print(f"Parsed Output: '{status_out}'")
        
        if "On" in status_out or "1" in status_out:
            print("✅ PASS: Logic sees 'On' or '1'")
        else:
            print("❌ FAIL: Logic does not see 'On' or '1'")

    except Exception as e:
        print("Error:", e)

    print("\n--- Checking BitLocker Status (Detailed) ---")
    try:
        # Get full object
        cmd = ["powershell", "-Command", "Get-BitLockerVolume -MountPoint C: | Select-Object * | ConvertTo-Json"]
        res = subprocess.run(cmd, capture_output=True, text=True)
        print("STDOUT:", res.stdout)
    except Exception as e:
        print("Error:", e)
        
    print("\n--- Checking specific C: Drive status via WMI (Fallback idea) ---")
    try:
        cmd = ["powershell", "-Command", "Get-CimInstance -Namespace root/cimv2/security/microsoftvolumeencryption -ClassName Win32_EncryptableVolume | ConvertTo-Json"]
        res = subprocess.run(cmd, capture_output=True, text=True)
        print("STDOUT:", res.stdout)
    except Exception as e:
        print("Error:", e)

    print("\n--- Checking manage-bde (Fallback) ---")
    try:
        # manage-bde -status C:
        cmd = ["manage-bde", "-status", "C:"]
        res = subprocess.run(cmd, capture_output=True, text=True)
        print("STDOUT:", res.stdout)
        if "Protection On" in res.stdout:
            print("✅ manage-bde sees Protection On")
        elif "Protection Off" in res.stdout:
             print("⚠️ manage-bde sees Protection Off")
        else:
             print("❌ manage-bde output unclear")
    except Exception as e:
        print("Error:", e)

if __name__ == "__main__":
    check_bitlocker()


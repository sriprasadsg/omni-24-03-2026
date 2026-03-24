
import subprocess
import json
import platform

def test_ps():
    if platform.system() == "Windows":
        ps_cmd = (
            "$os = Get-WmiObject Win32_OperatingSystem -ErrorAction SilentlyContinue; "
            "$reg = Get-ItemProperty 'HKLM:\\SOFTWARE\\Microsoft\\Windows NT\\CurrentVersion' -ErrorAction SilentlyContinue; "
            "$installDate = [Management.ManagementDateTimeConverter]::ToDateTime($os.InstallDate).ToString('dd-MM-yyyy'); "
            "$buildStr = $reg.CurrentBuild + '.' + $reg.UBR; "
            "$spec = @{ "
            "edition = $os.Caption; "
            "version = $reg.DisplayVersion; "
            "installedOn = $installDate; "
            "osBuild = $buildStr; "
            "serialNumber = (Get-WmiObject Win32_BIOS).SerialNumber; "
            "experience = 'Windows Feature Experience Pack'; "
            "}; "
            "$spec | ConvertTo-Json"
        )
        cmd = f'powershell -ExecutionPolicy Bypass -Command "{ps_cmd}"'
        try:
            print(f"Running command: {cmd}")
            result = subprocess.check_output(cmd, shell=True, timeout=15).decode(errors='ignore')
            print(f"Result: {result}")
            data = json.loads(result)
            print(f"Parsed Data: {data}")
        except Exception as e:
            print(f"Error: {e}")

if __name__ == "__main__":
    test_ps()

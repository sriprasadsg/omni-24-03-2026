
import subprocess
import json
import os

def get_windows_specifications():
    """Extract Windows specifications using PowerShell"""
    try:
        if os.name == 'nt':
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
            result = subprocess.check_output(cmd, shell=True, timeout=15).decode(errors='ignore')
            return json.loads(result)
        return {}
    except Exception as e:
        print(f"Error: {e}")
        return {}

if __name__ == "__main__":
    print(json.dumps(get_windows_specifications(), indent=2))

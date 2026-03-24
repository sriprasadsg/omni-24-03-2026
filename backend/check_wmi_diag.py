import platform
import psutil
import socket
import subprocess
import json

def get_cpu_model():
    try:
        if platform.system() == "Windows":
            cmd = 'powershell "Get-WmiObject -Class Win32_Processor | Select-Object -ExpandProperty Name"'
            result = subprocess.check_output(cmd, shell=True, timeout=10).decode(errors='ignore')
            return result.strip()
    except Exception as e:
        return f"Error: {e}"
    return "Not Windows"

def get_os_version_details():
    try:
        if platform.system() == "Windows":
            cmd = 'powershell "Get-WmiObject -Class Win32_OperatingSystem | Select-Object -ExpandProperty Version"'
            result = subprocess.check_output(cmd, shell=True, timeout=10).decode(errors='ignore')
            return result.strip()
    except Exception as e:
        return f"Error: {e}"
    return "Not Windows"

def get_os_caption():
    try:
        if platform.system() == "Windows":
            cmd = 'powershell "Get-WmiObject -Class Win32_OperatingSystem | Select-Object -ExpandProperty Caption"'
            result = subprocess.check_output(cmd, shell=True, timeout=10).decode(errors='ignore')
            return result.strip()
    except Exception as e:
        return f"Error: {e}"
    return "Not Windows"

print("--- DIAGNOSTICS ---")
print(f"CPU Model: {get_cpu_model()}")
print(f"OS Caption: {get_os_caption()}")
print(f"OS Version: {get_os_version_details()}")
print(f"Platform Release: {platform.release()}")
print(f"Platform Version: {platform.version()}")
print(f"Platform System: {platform.system()}")

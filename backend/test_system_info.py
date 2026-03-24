"""
Test script to verify system information collection
"""
import platform
import psutil
import socket
import subprocess

print("=" * 60)
print("SYSTEM INFORMATION TEST")
print("=" * 60)

# Test CPU
print("\n1. CPU DETECTION:")
try:
    result = subprocess.check_output("wmic cpu get name", shell=True, timeout=5).decode(errors='ignore')
    print(f"Raw output: {repr(result)}")
    lines = [line.strip() for line in result.split('\n') if line.strip()]
    print(f"All lines: {lines}")
    lines = [line for line in lines if 'Name' not in line]
    print(f"Filtered lines: {lines}")
    if lines:
        print(f"CPU Model: {lines[0]}")
except Exception as e:
    print(f"Error: {e}")

# Test OS Version
print("\n2. OS VERSION:")
print(f"platform.system(): {platform.system()}")
print(f"platform.release(): {platform.release()}")
print(f"platform.version(): {platform.version()}")
print(f"platform.platform(): {platform.platform()}")

try:
    result = subprocess.check_output("wmic os get caption,version", shell=True, timeout=5).decode(errors='ignore')
    print(f"\nWMIC OS output:")
    print(result)
except Exception as e:
    print(f"Error: {e}")

# Test Serial
print("\n3. SERIAL NUMBER:")
try:
    result = subprocess.check_output("wmic bios get serialnumber", shell=True, timeout=5).decode(errors='ignore')
    print(f"Raw output: {repr(result)}")
    lines = [line.strip() for line in result.split('\n') if line.strip() and 'SerialNumber' not in line]
    print(f"Filtered: {lines}")
    if lines:
        print(f"Serial: {lines[0]}")
except Exception as e:
    print(f"Error: {e}")

# Test MAC
print("\n4. MAC ADDRESS:")
addrs = psutil.net_if_addrs()
for interface, addr_list in addrs.items():
    for addr in addr_list:
        if addr.family == psutil.AF_LINK:
            print(f"{interface}: {addr.address}")

import asyncio
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend'))

import requests
from datetime import datetime, timezone
import time
import socket
import platform
import psutil
import uuid
import json

# Configuration
BACKEND_URL = "http://localhost:5000"
REGISTRATION_KEY = "reg_62a4b18a91ec461b"  # Exafluence tenant key
HEARTBEAT_INTERVAL = 30  # Send heartbeat every 30 seconds
COMPLIANCE_SCAN_INTERVAL = 300 # Run compliance scan every 5 minutes

# Import Capabilities
try:
    # Add parent directory to path to find agent module
    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from agent.capabilities.compliance import ComplianceEnforcementCapability
except ImportError as e:
    print(f"Warning: Could not import ComplianceCapability: {e}")
    ComplianceEnforcementCapability = None

def get_mac_address():
    """Get MAC address of primary network interface"""
    try:
        # Get all network interfaces
        addrs = psutil.net_if_addrs()
        for interface, addr_list in addrs.items():
            for addr in addr_list:
                if addr.family == psutil.AF_LINK and not interface.startswith('lo'):
                    # Return first non-loopback MAC address
                    return addr.address
        return "00:00:00:00:00:00"
    except:
        return "00:00:00:00:00:00"

def get_cpu_model():
    """Get CPU model information using PowerShell WMI"""
    try:
        if platform.system() == "Windows":
            import subprocess
            # Use PowerShell Get-WmiObject instead of wmic
            cmd = 'powershell "Get-WmiObject -Class Win32_Processor | Select-Object -ExpandProperty Name"'
            result = subprocess.check_output(cmd, shell=True, timeout=10).decode(errors='ignore')
            cpu_name = result.strip()
            if cpu_name:
                return cpu_name
        elif platform.system() == "Linux":
            with open('/proc/cpuinfo', 'r') as f:
                for line in f:
                    if 'model name' in line:
                        return line.split(':')[1].strip()
        # Fallback
        proc = platform.processor()
        if proc and proc.strip():
            return f"{proc} ({psutil.cpu_count()} cores)"
        return f"{psutil.cpu_count()}-Core Processor"
    except Exception as e:
        print(f"CPU detection error: {e}")
        return f"{psutil.cpu_count()}-Core Processor"

def get_kernel_version():
    """Get OS kernel version"""
    try:
        if platform.system() == "Windows":
            return platform.version()
        else:
            return platform.release()
    except:
        return "Unknown"

def get_serial_number():
    """Get system serial number using PowerShell WMI"""
    try:
        if platform.system() == "Windows":
            import subprocess
            cmd = 'powershell "Get-WmiObject -Class Win32_BIOS | Select-Object -ExpandProperty SerialNumber"'
            result = subprocess.check_output(cmd, shell=True, timeout=10).decode(errors='ignore')
            serial = result.strip()
            if serial:
                return serial
        elif platform.system() == "Linux":
            result = subprocess.check_output("dmidecode -s system-serial-number", shell=True, timeout=5).decode(errors='ignore')
            return result.strip()
        return "Not Available"
    except Exception as e:
        print(f"Serial number detection error: {e}")
        return "Not Available"

def get_os_caption():
    """Get OS detailed name using PowerShell WMI"""
    try:
        if platform.system() == "Windows":
            import subprocess
            cmd = 'powershell "Get-WmiObject -Class Win32_OperatingSystem | Select-Object -ExpandProperty Caption"'
            result = subprocess.check_output(cmd, shell=True, timeout=10).decode(errors='ignore')
            return result.strip()
    except Exception as e:
        print(f"OS caption detection error: {e}")
    return platform.system()

def get_os_version_details():
    """Get detailed OS version string using PowerShell WMI"""
    try:
        if platform.system() == "Windows":
            import subprocess
            cmd = 'powershell "Get-WmiObject -Class Win32_OperatingSystem | Select-Object -ExpandProperty Version"'
            result = subprocess.check_output(cmd, shell=True, timeout=10).decode(errors='ignore')
            return result.strip()
    except Exception as e:
        print(f"OS version detection error: {e}")
    return platform.version()

def get_windows_specifications():
    """Get detailed Windows specifications matching system settings UI"""
    try:
        if platform.system() == "Windows":
            import subprocess
            import json
            # Combined PowerShell command for efficiency
            ps_cmd = (
                "$os = Get-WmiObject Win32_OperatingSystem -ErrorAction SilentlyContinue; "
                "$reg = Get-ItemProperty 'HKLM:\\SOFTWARE\\Microsoft\\Windows NT\\CurrentVersion' -ErrorAction SilentlyContinue; "
                "$installDate = [Management.ManagementDateTimeConverter]::ToDateTime($os.InstallDate).ToString('dd-MM-yyyy'); "
                "$buildStr = $reg.CurrentBuild + '.' + $reg.UBR; "
                "$spec = @{ "
                "edition = $os.Caption; "
                "version = $reg.DisplayVersion; "
                "osVersion = $os.Version; "  # Added this line
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
    except Exception as e:
        print(f"Windows specifications detection error: {e}")
    return {}

def get_disk_information():
    """Get detailed disk/drive information"""
    try:
        disks = []
        partitions = psutil.disk_partitions()
        for partition in partitions:
            try:
                usage = psutil.disk_usage(partition.mountpoint)
                disk_info = {
                    "device": partition.device,
                    "mountpoint": partition.mountpoint,
                    "fstype": partition.fstype,
                    "total_gb": round(usage.total / (1024**3), 2),
                    "used_gb": round(usage.used / (1024**3), 2),
                    "free_gb": round(usage.free / (1024**3), 2),
                    "percent": round(usage.percent, 2),
                    # Add formatted label for UI
                    "label": f"{partition.device} ({partition.fstype}, {round(usage.total / (1024**3), 2)} GB)"
                }
                disks.append(disk_info)
            except PermissionError:
                continue
        return disks
    except:
        return []

def get_installed_software():
    """Get list of installed software (simplified)"""
    try:
        software = []
        if platform.system() == "Windows":
            import subprocess
            # Get a sample of installed software via wmic
            result = subprocess.check_output(
                "wmic product get name,version /format:csv", 
                shell=True, 
                timeout=10
            ).decode(errors='ignore')
            lines = [line.strip() for line in result.split('\n') if line.strip() and ',' in line]
            for line in lines[1:11]:  # Limit to first 10 for performance
                parts = line.split(',')
                if len(parts) >= 3:
                    software.append({
                        "name": parts[1],
                        "version": parts[2]
                    })
        # For Linux/Mac, we'd use dpkg, rpm, or brew
        return software[:10]  # Limit to 10 items
    except:
        return []

def get_comprehensive_system_info():
    """Get complete system information for asset creation"""
    hostname = socket.gethostname()
    
    # Get primary IP address
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip_address = s.getsockname()[0]
        s.close()
    except:
        ip_address = "127.0.0.1"
    
    # Get platform information
    system = platform.system()
    if system == "Windows":
        # Get detailed OS version and Caption from WMI
        os_version = get_os_version_details()  # e.g., "10.0.26200"
        platform_name = get_os_caption()        # e.g., "Microsoft Windows 11 Pro"
    elif system == "Linux":
        platform_name = "Linux"
        os_version = platform.release()
    elif system == "Darwin":
        platform_name = "macOS"
        os_version = platform.mac_ver()[0]
    else:
        platform_name = system
        os_version = platform.release()
    
    # Get memory information
    memory = psutil.virtual_memory()
    
    # Get disk information
    disks = get_disk_information()
    
    # Get kernel and serial
    kernel = get_kernel_version()
    serial = get_serial_number()
    
    # Get OS specifications (Edition, Version, Installed on, etc.)
    win_spec = get_windows_specifications()
    
    # Prefer win_spec for all OS related fields on Windows
    if system == "Windows" and win_spec:
        os_version = win_spec.get("osVersion", os_version)
        platform_name = win_spec.get("edition", platform_name)
    
    return {
        "hostname": hostname,
        "platform": platform_name,
        "version": "2.0.0",  # Agent version
        "ipAddress": ip_address,
        "macAddress": get_mac_address(),
        "osVersion": os_version,
        "kernel": kernel,
        "serialNumber": win_spec.get("serialNumber", serial),
        # New Windows specific fields
        "osEdition": win_spec.get("edition", platform_name),
        "osDisplayVersion": win_spec.get("version", ""),
        "osInstalledOn": win_spec.get("installedOn", ""),
        "osBuild": win_spec.get("osBuild", os_version),
        "osExperience": win_spec.get("experience", ""),
        "cpuModel": get_cpu_model(),
        "cpuCores": psutil.cpu_count(),
        "ram": f"{round(memory.total / (1024**3), 2)} GB",
        "totalMemoryGB": round(memory.total / (1024**3), 2),
        "disks": disks,
        "installedSoftware": get_installed_software()
    }

def get_real_metrics():
    """Get real-time system metrics"""
    cpu_percent = psutil.cpu_percent(interval=1)
    memory = psutil.virtual_memory()
    disk = psutil.disk_usage('/')
    
    system_name = platform.system()
    if system_name == "Windows":
        try:
            os_ver = get_os_version_details()
        except:
            os_ver = platform.release()
    else:
        os_ver = platform.release()

    return {
        "current_cpu": round(cpu_percent, 2),
        "current_memory": round(memory.percent, 2),
        "disk_usage": round(disk.percent, 2),
        "os_info": {
            "name": system_name,
            "version": os_ver
        },
        "total_memory_gb": round(memory.total / (1024**3), 2),
        "available_memory_gb": round(memory.available / (1024**3), 2),
        "disk_total_gb": round(disk.total / (1024**3), 2),
        "disk_used_gb": round(disk.used / (1024**3), 2)
    }

def register_agent(agent_config):
    """Register this host as an agent with comprehensive system info"""
    try:
        payload = {
            **agent_config,
            "registrationKey": REGISTRATION_KEY
        }
        
        response = requests.post(
            f"{BACKEND_URL}/api/agents/register",
            json=payload,
            timeout=10
        )
        
        if response.status_code == 200:
            result = response.json()
            print(f"✓ Registered {agent_config['hostname']} - Agent ID: {result.get('agentId')}")
            print(f"  CPU: {agent_config.get('cpuModel', 'Unknown')}")
            print(f"  RAM: {agent_config.get('ram', 'Unknown')}")
            print(f"  Disks: {len(agent_config.get('disks', []))}")
            print(f"  Software: {len(agent_config.get('installedSoftware', []))} packages")
            return result.get('agentId')
        else:
            print(f"✗ Failed to register {agent_config['hostname']}: {response.status_code} - {response.text}")
            return None
            
    except Exception as e:
        print(f"✗ Error registering {agent_config['hostname']}: {e}")
        return None

def send_heartbeat(agent_id, agent_config):
    """Send heartbeat with real system metrics"""
    try:
        # Get real-time metrics
        metrics = get_real_metrics()
        
        payload = {
            "hostname": agent_config["hostname"],
            "platform": agent_config["platform"],
            "version": agent_config["version"],
            "ipAddress": agent_config["ipAddress"],
            "meta": metrics
        }
        
        headers = {
            "X-Tenant-Key": REGISTRATION_KEY
        }
        
        response = requests.post(
            f"{BACKEND_URL}/api/agents/{agent_id}/heartbeat",
            json=payload,
            headers=headers,
            timeout=10
        )
        
        if response.status_code == 200:
            print(f"  ♥ Heartbeat sent | CPU: {metrics['current_cpu']}% | Memory: {metrics['current_memory']}% | Disk: {metrics['disk_usage']}%")
            return True
        else:
            print(f"  ✗ Heartbeat failed: {response.status_code}")
            return False
            
    except Exception as e:
        print(f"  ✗ Heartbeat error: {e}")
        return False

def run_compliance_scan(agent_id, hostname):
    """Run compliance checks and report results"""
    if not ComplianceEnforcementCapability:
        print("  ⚠️ Compliance capability not available")
        return

    print("  🔍 Starting Compliance Scan...")
    try:
        compliance = ComplianceEnforcementCapability()
        results = compliance.collect()
        
        # Report results to backend
        payload = {
            "compliance_checks": results.get("compliance_checks", []),
            "total_checks": results.get("total_checks", 0),
            "passed": results.get("passed", 0),
            "failed": results.get("failed", 0),
            "compliance_score": results.get("compliance_score", 0),
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
        headers = {
            "X-Tenant-Key": REGISTRATION_KEY
        }
        
        # Determine strict or normal endpoint? 
        # Using instructions/result as it processes evidence
        response = requests.post(
            f"{BACKEND_URL}/api/agents/{hostname}/instructions/result",
            json=payload,
            headers=headers,
            timeout=30
        )
        
        if response.status_code == 200:
             print(f"  ✅ Compliance report sent: {results.get('passed')}/{results.get('total_checks')} Passed ({results.get('compliance_score')}%)")
        else:
             print(f"  ❌ Failed to send compliance report: {response.status_code}")

    except Exception as e:
        import traceback
        print(f"  ❌ Compliance scan error: {e}")
        traceback.print_exc()

async def main():
    """Main daemon loop"""
    print("=" * 60)
    print("LIVE AGENT DAEMON - COMPREHENSIVE SYSTEM MONITORING")
    print("=" * 60)
    print(f"Backend: {BACKEND_URL}")
    print(f"Heartbeat Interval: {HEARTBEAT_INTERVAL}s")
    print(f"Compliance Scan: Every {COMPLIANCE_SCAN_INTERVAL}s")
    print()
    
    # Get comprehensive system info
    print("Collecting comprehensive system information...")
    system_info = get_comprehensive_system_info()
    print(f"  Hostname: {system_info['hostname']}")
    print(f"  Platform: {system_info['platform']} ({system_info['osVersion']})")
    print(f"  IP Address: {system_info['ipAddress']}")
    print(f"  MAC Address: {system_info['macAddress']}")
    print(f"  CPU: {system_info['cpuModel']}")
    print(f"  RAM: {system_info['ram']}")
    print(f"  Disks: {len(system_info['disks'])} drive(s)")
    print(f"  Installed Software: {len(system_info['installedSoftware'])} package(s) detected")
    print()
    
    # Register this host
    print("Registering agent with comprehensive data...")
    agent_id = register_agent(system_info)
    
    if not agent_id:
        print("❌ Failed to register agent. Exiting.")
        return
    
    print(f"✓ Agent registered successfully!")
    print()
    
    # Initial Compliance Scan
    print("Running initial compliance scan...")
    run_compliance_scan(agent_id, system_info['hostname'])
    last_compliance_scan = time.time()
    print()
    
    # Continuous heartbeat loop with real metrics
    print("Starting heartbeat loop with real system metrics (Ctrl+C to stop)...")
    print()
    
    try:
        while True:
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Sending heartbeat...")
            send_heartbeat(agent_id, system_info)
            
            # periodic compliance scan
            if time.time() - last_compliance_scan > COMPLIANCE_SCAN_INTERVAL:
                print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Running scheduled compliance scan...")
                run_compliance_scan(agent_id, system_info['hostname'])
                last_compliance_scan = time.time()
            
            print(f"  Next heartbeat in {HEARTBEAT_INTERVAL}s")
            print()
            await asyncio.sleep(HEARTBEAT_INTERVAL)
            
    except KeyboardInterrupt:
        print("\n\n✓ Live Agent Daemon stopped by user")
    except Exception as e:
        print(f"\n\n✗ Fatal error: {e}")

if __name__ == "__main__":
    asyncio.run(main())

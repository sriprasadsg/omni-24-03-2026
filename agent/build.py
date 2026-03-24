#!/usr/bin/env python3
"""
Cross-Platform Agent Build Script
Builds executables for Windows and Linux using PyInstaller
"""

import subprocess
import sys
import platform
import os
from pathlib import Path

def build_windows():
    """Build Windows executable"""
    print("=" * 50)
    print("Building Windows Executable...")
    print("=" * 50)
    
    cmd = [
        "pyinstaller",
        "--onefile",
        "--hidden-import=win32timezone",
        "--name=omni-agent",
        "agent.py"
    ]
    
    try:
        subprocess.run(cmd, check=True)
        print("✅ Windows build successful: dist/omni-agent.exe")
    except subprocess.CalledProcessError as e:
        print(f"❌ Windows build failed: {e}")
        return False
    return True

def build_linux():
    """Build Linux executable"""
    print("=" * 50)
    print("Building Linux Executable...")
    print("=" * 50)
    
    cmd = [
        "pyinstaller",
        "--onefile",
        "--name=omni-agent",
        "agent.py"
    ]
    
    try:
        subprocess.run(cmd, check=True)
        print("✅ Linux build successful: dist/omni-agent")
    except subprocess.CalledProcessError as e:
        print(f"❌ Linux build failed: {e}")
        return False
    return True

def package_python_version():
    """Package Python version with dependencies"""
    print("=" * 50)
    print("Packaging Python Version...")
    print("=" * 50)
    
    output_dir = Path("dist/python-agent")
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Copy agent files
    import shutil
    shutil.copy("agent.py", output_dir / "agent.py")
    shutil.copy("config.yaml", output_dir / "config.yaml")
    shutil.copy("requirements.txt", output_dir / "requirements.txt")
    
    # Copy capabilities directory
    if Path("capabilities").exists():
        shutil.copytree("capabilities", output_dir / "capabilities", dirs_exist_ok=True)
    
    print("✅ Python package created: dist/python-agent/")
    return True

def main():
    current_os = platform.system()
    
    print(f"Current OS: {current_os}")
    print(f"Python Version: {sys.version}")
    print()
    
    # Change to agent directory
    agent_dir = Path(__file__).parent
    os.chdir(agent_dir)
    
    if len(sys.argv) > 1:
        target = sys.argv[1].lower()
    else:
        target = "all"
    
    results = {}
    
    if target in ["all", "windows"] and current_os == "Windows":
        results["Windows"] = build_windows()
    
    if target in ["all", "linux"] and current_os == "Linux":
        results["Linux"] = build_linux()
    
    if target in ["all", "python"]:
        results["Python"] = package_python_version()
    
    print("\n" + "=" * 50)
    print("Build Summary:")
    print("=" * 50)
    for name, success in results.items():
        status = "✅ SUCCESS" if success else "❌ FAILED"
        print(f"{name}: {status}")
    
    return all(results.values())

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)

import PyInstaller.__main__
import shutil
import os
import platform

# Define base directory (d:\Downloads\enterprise-omni-agent-ai-platform\agent)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DIST_DIR = os.path.join(BASE_DIR, 'dist')
BUILD_DIR = os.path.join(BASE_DIR, 'build')

# Cleanup previous builds
if os.path.exists(DIST_DIR):
    shutil.rmtree(DIST_DIR)
if os.path.exists(BUILD_DIR):
    shutil.rmtree(BUILD_DIR)

print(f"Building Agent from {BASE_DIR}...")
print(f"Target OS: {platform.system()}")

# Define PyInstaller args
args = [
    os.path.join(BASE_DIR, 'agent.py'),
    '--onefile',                   # Single executable
    '--name=omni-agent',           # Executable name
    '--clean',                     # Clean cache
    f'--distpath={DIST_DIR}',
    f'--workpath={BUILD_DIR}',
    '--hidden-import=engineio.async_drivers.aiohttp', # Fix for socketio/aiohttp sometimes missing
    # Include config.yaml (we'll copy it manually too, but if we want it embedded...)
    # Actually, config.yaml should be external so user can edit it. 
    # But for a single-file exe, resources are tricky.
    # We will assume config.yaml is alongside the binary.
]

# Run PyInstaller
PyInstaller.__main__.run(args)

# Post-build: Copy config.yaml to dist for testing
src_config = os.path.join(BASE_DIR, 'config.yaml')
dst_config = os.path.join(DIST_DIR, 'config.yaml')
if os.path.exists(src_config):
    shutil.copy(src_config, dst_config)
    print(f"Copied config.yaml to {DIST_DIR}")

print("Build Complete.")
print(f"Executable located at: {os.path.join(DIST_DIR, 'omni-agent' + ('.exe' if platform.system() == 'Windows' else ''))}")


import sys
import os
import json
import logging

# Add agent directory to path
sys.path.append(os.path.join(os.getcwd(), 'agent'))

# Configure logging
logging.basicConfig(level=logging.INFO)

try:
    from platform_utils import PlatformUtils
    print("Gathering software...")
    software = PlatformUtils.get_installed_software()
    print(f"Found {len(software)} items.")
    if len(software) > 0:
        print("First 3 items:")
        print(json.dumps(software[:3], indent=2))
    else:
        print("No items found.")
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()

import os
import sys

# Add agent directory to path
agent_dir = os.path.join(os.getcwd(), 'agent')
if agent_dir not in sys.path:
    sys.path.append(agent_dir)

from platform_utils import PlatformUtils

def test_storage_info():
    print("Testing PlatformUtils.get_storage_info()...")
    disks = PlatformUtils.get_storage_info()
    
    if not disks:
        print("❌ No disks found!")
        return

    print(f"✅ Found {len(disks)} disk(s):")
    for disk in disks:
        print(f"--- Device: {disk['device']} ---")
        print(f"  Mountpoint: {disk['mountpoint']}")
        print(f"  FSType: {disk['fstype']}")
        print(f"  Total: {disk['total']}")
        print(f"  Used: {disk['used']}")
        print(f"  Free: {disk['free']}")
        print(f"  UsedPercent: {disk['usedPercent']}%")
        print(f"  IsRemovable: {disk['isRemovable']}")
        
        # Validate fields
        assert 'free' in disk, f"Missing 'free' in disk {disk['device']}"
        assert 'isRemovable' in disk, f"Missing 'isRemovable' in disk {disk['device']}"
        print(f"  ✅ Validation passed for {disk['device']}")

if __name__ == "__main__":
    try:
        test_storage_info()
        print("\n✨ All tests passed!")
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        sys.exit(1)

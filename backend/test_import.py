import sys
import os
sys.path.append(os.getcwd())
try:
    import dr_endpoints
    print("SUCCESS: dr_endpoints imported")
    print("Router prefix:", dr_endpoints.router.prefix)
except Exception as e:
    print(f"FAILURE: {e}")
    import traceback
    traceback.print_exc()

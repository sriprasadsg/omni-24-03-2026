
import sys
import os
print(f"CWD: {os.getcwd()}")
sys.path.append('backend')
try:
    import backend.app
    print(f"Loaded backend.app from: {backend.app.__file__}")
except ImportError:
    print("Could not import backend.app")

try:
    import app
    print(f"Loaded app (top level) from: {app.__file__}")
except ImportError:
    print("Could not import app (top level)")

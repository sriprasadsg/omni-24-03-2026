import sys
import os
import logging

logging.basicConfig(level=logging.INFO)
print(f"CWD: {os.getcwd()}")
print(f"sys.path: {sys.path}")

try:
    import google.generativeai
    print("SUCCESS: 'google.generativeai' imported.")
    print(f"File: {google.generativeai.__file__}")
except ImportError as e:
    print(f"FAILED: 'google.generativeai' import: {e}")

try:
    import database
    print("SUCCESS: 'database' imported directly.")
except ImportError as e:
    print(f"FAILED: 'database' import direct: {e}")

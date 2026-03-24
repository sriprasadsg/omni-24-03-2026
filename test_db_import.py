import sys
import os
# Add backend to path
sys.path.append(os.path.join(os.path.dirname(__file__), "backend"))
try:
    from database import get_database
    print("Success importing from database")
except Exception as e:
    print(f"Error: {e}")

try:
    import backend.database as db
    print("Success importing backend.database")
except Exception as e:
    print(f"Error backend.database: {e}")

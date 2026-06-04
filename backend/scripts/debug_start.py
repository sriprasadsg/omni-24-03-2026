
import sys
import traceback

print("DEBUG: Starting import of app...")
try:
    from app import app
    print("DEBUG: Import successful!")
except Exception:
    traceback.print_exc()
    sys.exit(1)

print("DEBUG: Starting uvicorn...")
import uvicorn
try:
    uvicorn.run(app, host="0.0.0.0", port=5000)
except Exception:
    traceback.print_exc()

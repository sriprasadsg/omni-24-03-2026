import sys
import os
import uvicorn
sys.path.append('backend')
from backend.app import app

if __name__ == "__main__":
    print("Starting TEST backend on port 5001...")
    uvicorn.run(app, host="0.0.0.0", port=5001)

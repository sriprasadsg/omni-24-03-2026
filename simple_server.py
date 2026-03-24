
import sys
sys.path.append('backend')
from backend.app import app
import uvicorn

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=5001)

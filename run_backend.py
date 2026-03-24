
import sys
import os
from fastapi.responses import FileResponse
import uvicorn

# Ensure backend can import its dependencies
sys.path.append('backend')
from backend.app import app
import backend.authentication_endpoints
print(f"DEBUG: Loaded authentication_endpoints from {backend.authentication_endpoints.__file__}")

# Explicitly define the route here to ensure it is registered
@app.get("/api/install-script")
async def serve_install_script_wrapper():
    file_path = r"D:\Downloads\enterprise-omni-agent-ai-platform\backend\static\win-install.ps1"
    print(f"DEBUG: Serving win-install.ps1 (Wrapper) from {file_path}")
    if os.path.exists(file_path):
        return FileResponse(file_path, media_type="text/plain")
    return {"error": "File not found"}, 404



if __name__ == "__main__":
    print("Starting backend on port 5000 with installer patch...")
    # Use the socket_app object (FastAPI + Socket.IO)
    uvicorn.run("backend.app:socket_app", host="0.0.0.0", port=5000, reload=False)

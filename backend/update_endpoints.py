from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
import os
import glob

router = APIRouter(
    prefix="/api/agent-updates",
    tags=["Agent Update"]
)

# Configuration for where binaries are stored
BINARY_STORAGE_PATH = os.path.join(os.path.dirname(__file__), "static")

@router.get("/latest")
async def get_latest_version(platform: str = "windows"):
    """
    Get the latest available agent version info.
    """
    # In a real app, this would query a DB or read a manifest.
    # For MVP, we check the backend/static folder naming convention:
    # omni-agent-{version}-{platform}.exe
    
    # Ensure dir exists
    if not os.path.exists(BINARY_STORAGE_PATH):
        os.makedirs(BINARY_STORAGE_PATH, exist_ok=True)
        
    base_url = "http://localhost:5000" # Dynamic in prod
    
    # Check for agent.py updates (Script based)
    agent_script_path = os.path.join("..", "agent", "agent.py")
    script_info = None
    if os.path.exists(agent_script_path):
        import re
        try:
            content = open(agent_script_path, "r", encoding="utf-8").read()
            match = re.search(r'AGENT_VERSION\s*=\s*"([^"]+)"', content)
            if match:
                script_version = match.group(1)
                script_info = {
                    "version": script_version,
                    "filename": "agent.py",
                    "url": f"{base_url}/api/agent-updates/download/agent.py",
                    "release_date": os.path.getmtime(agent_script_path)
                }
        except Exception as e:
            print(f"Error reading agent version: {e}")

    # If platform is 'python' or 'script', return script info immediately
    if platform.lower() in ["python", "script"]:
        if script_info:
            return script_info
        return {"version": "0.0.0", "url": None, "message": "No script update available"}

    # Pattern match for binaries
    # Windows: omni-agent-*-windows.exe
    # Linux: omni-agent-*-linux
    
    suffix = ".exe" if platform.lower() == "windows" else ""
    pattern = f"omni-agent-*{suffix}"
    
    files = glob.glob(os.path.join(BINARY_STORAGE_PATH, pattern))
    if not files:
        # Fallback to script if binary not found
        if script_info:
            return script_info
        return {"version": "0.0.0", "url": None, "message": "No updates available"}
        
    # Sort by name (assuming version numbers sort correctly or use creation time)
    # Ideally: omni-agent-2.0.1-windows.exe
    latest_file = max(files, key=os.path.getmtime)
    filename = os.path.basename(latest_file)
    
    # Extract version? 
    # Let's assume filename format: omni-agent-{version}-windows.exe
    try:
        parts = filename.split('-')
        # omni, agent, 2.0.1, windows.exe
        version = parts[2]
    except:
        version = "unknown"
        
    download_url = f"{base_url}/api/agent-updates/download/{filename}"
    
    return {
        "version": version,
        "filename": filename,
        "url": download_url,
        "release_date": os.path.getmtime(latest_file)
    }

@router.get("/download/{filename}")
async def download_agent_binary(filename: str):
    # Allow downloading specific named files like 'omni-agent.exe' if they exist
    # or map 'omni-agent.exe' to the latest version
    
    # Special handling for Python agent
    if filename == "agent.py":
        agent_path = os.path.join("..", "agent", "agent.py")
        if os.path.exists(agent_path):
            return FileResponse(agent_path, filename="agent.py", media_type="text/plain")
    
    target_path = os.path.join(BINARY_STORAGE_PATH, filename)
    
    # Fallback: if requesting omni-agent.exe but it doesn't exist, try to find the latest version
    if not os.path.exists(target_path) and filename == "omni-agent.exe":
         files = glob.glob(os.path.join(BINARY_STORAGE_PATH, "omni-agent-*-windows.exe"))
         if files:
             target_path = max(files, key=os.path.getmtime)
             filename = os.path.basename(target_path)

    if not os.path.exists(target_path):
        raise HTTPException(status_code=404, detail="Binary not found")
        
    return FileResponse(target_path, filename=filename, media_type="application/octet-stream")

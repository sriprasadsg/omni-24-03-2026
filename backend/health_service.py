import shutil
import os
import httpx
import logging

logger = logging.getLogger(__name__)

async def check_binary(binary_name: str) -> bool:
    """Checks if a binary is available in the system PATH."""
    return shutil.which(binary_name) is not None

async def check_vt_connectivity(api_key: str) -> bool:
    """Checks if VirusTotal API is reachable with the provided key."""
    if not api_key:
        return False
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                "https://www.virustotal.com/api/v3/users/validate",
                headers={"x-apikey": api_key}
            )
            return response.status_code == 200
    except Exception as e:
        logger.error(f"VirusTotal connectivity check failed: {e}")
        return False

async def get_system_health():
    """Runs a suite of health checks for the backend."""
    return {
        "binaries": {
            "nmap": await check_binary("nmap"),
            "nikto": await check_binary("nikto")
        },
        "integrations": {
            "virustotal": await check_vt_connectivity(os.getenv("VT_API_KEY", ""))
        }
    }

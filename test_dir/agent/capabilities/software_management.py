
from .base import BaseCapability
import platform
import subprocess
import logging
from typing import Dict, Any, List

logger = logging.getLogger(__name__)

class SoftwareManagementCapability(BaseCapability):
    """
    Capability to manage software installation and upgrades.
    Supports verify-install-upgrade lifecycle.
    """
    
    @property
    def capability_id(self) -> str:
        return "software_management"
    
    @property
    def capability_name(self) -> str:
        return "Software Management"
    
    def collect(self) -> Dict[str, Any]:
        """
        Passive collection isn't the primary goal here, 
        but we can return status of last operations.
        """
        return {"status": "ready"}

    def install_software(self, package_id: str) -> Dict[str, Any]:
        """
        Install a software package.
        """
        system = platform.system()
        logger.info(f"Attempting to install '{package_id}' on {system}")
        
        if system == "Windows":
            return self._install_windows(package_id)
        elif system == "Linux":
            return self._install_linux(package_id)
        else:
            return {"status": "error", "error": f"Unsupported platform: {system}"}

    def upgrade_software(self, package_id: str) -> Dict[str, Any]:
        """
        Upgrade a software package.
        """
        system = platform.system()
        logger.info(f"Attempting to upgrade '{package_id}' on {system}")
        
        if system == "Windows":
            return self._upgrade_windows(package_id)
        elif system == "Linux":
            return self._upgrade_linux(package_id)
        else:
            return {"status": "error", "error": f"Unsupported platform: {system}"}

    def _install_windows(self, package_id: str) -> Dict[str, Any]:
        """
        Install via Winget.
        Command: winget install <id> -e --silent --accept-package-agreements --accept-source-agreements
        """
        cmd = [
            "winget", "install", 
            "--id", package_id, 
            "-e", 
            "--silent", 
            "--accept-package-agreements", 
            "--accept-source-agreements"
        ]
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=600) # 10 min timeout for installs
            if result.returncode == 0:
                return {"status": "success", "message": f"Successfully installed {package_id}", "details": result.stdout}
            else:
                return {"status": "error", "error": f"Winget failed with code {result.returncode}", "details": result.stderr or result.stdout}
        except Exception as e:
            return {"status": "error", "error": str(e)}

    def _upgrade_windows(self, package_id: str) -> Dict[str, Any]:
        """
        Upgrade via Winget.
        Command: winget upgrade <id> -e --silent --accept-package-agreements
        """
        cmd = [
            "winget", "upgrade", 
            "--id", package_id, 
            "-e", 
            "--silent", 
            "--accept-package-agreements", 
            "--accept-source-agreements"
        ]
        
        try:
            # First check if upgrade is available to avoid error noise?
            # Winget upgrade <id> will fail if no upgrade found, which is fine.
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
            if result.returncode == 0:
                return {"status": "success", "message": f"Successfully upgraded {package_id}", "details": result.stdout}
            # Winget specific codes: 
            # 2316632065 (0x8A150001) -> No upgrade available
            elif result.returncode == 2316632065 or "No available upgrade" in result.stdout:
                 return {"status": "skipped", "message": "No upgrade available (already latest)", "details": result.stdout}
            else:
                return {"status": "error", "error": f"Winget failed with code {result.returncode}", "details": result.stderr or result.stdout}
        except Exception as e:
            return {"status": "error", "error": str(e)}

    def _install_linux(self, package_id: str) -> Dict[str, Any]:
        """
        Install via apt-get (Debian/Ubuntu) or yum (RHEL/CentOS).
        """
        # Detect package manager
        pm = "apt-get"
        install_cmd = ["apt-get", "install", "-y", package_id]
        
        # Simple check for yum/dnf
        import shutil
        if shutil.which("dnf"):
            pm = "dnf"
            install_cmd = ["dnf", "install", "-y", package_id]
        elif shutil.which("yum"):
            pm = "yum"
            install_cmd = ["yum", "install", "-y", package_id]
            
        try:
            # Might need sudo? Agent usually runs as root or has specific perms.
            # For now assume permissions are sufficient or rely on sudoers.
            # If running as user, prepend sudo
            if shutil.which("sudo"):
                install_cmd.insert(0, "sudo")
                
            result = subprocess.run(install_cmd, capture_output=True, text=True, timeout=600)
            if result.returncode == 0:
                return {"status": "success", "message": f"Successfully installed {package_id}", "details": result.stdout}
            else:
                return {"status": "error", "error": f"{pm} failed", "details": result.stderr}
        except Exception as e:
            return {"status": "error", "error": str(e)}

    def _upgrade_linux(self, package_id: str) -> Dict[str, Any]:
        """
        Upgrade via apt-get or yum.
        """
        # Detect package manager
        import shutil
        cmd = []
        if shutil.which("apt-get"):
            cmd = ["apt-get", "install", "--only-upgrade", "-y", package_id]
        elif shutil.which("dnf"):
            cmd = ["dnf", "upgrade", "-y", package_id]
        
        if shutil.which("sudo"):
            cmd.insert(0, "sudo")
            
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
            if result.returncode == 0:
                return {"status": "success", "message": f"Successfully upgraded {package_id}", "details": result.stdout}
            else:
                return {"status": "error", "error": "Upgrade failed", "details": result.stderr}
        except Exception as e:
            return {"status": "error", "error": str(e)}

    # ── Uninstall ──────────────────────────────────────────────────────────────

    def uninstall_software(self, package_id: str) -> Dict[str, Any]:
        """
        Uninstall a software package.
        Windows: winget uninstall --id <id> -e --silent
        Linux:   apt-get remove / dnf remove / yum remove
        """
        system = platform.system()
        logger.info(f"Attempting to uninstall '{package_id}' on {system}")

        if system == "Windows":
            return self._uninstall_windows(package_id)
        elif system == "Linux":
            return self._uninstall_linux(package_id)
        else:
            return {"status": "error", "error": f"Unsupported platform: {system}"}

    def _uninstall_windows(self, package_id: str) -> Dict[str, Any]:
        """
        Uninstall via Winget.
        Command: winget uninstall --id <id> -e --silent
        """
        cmd = [
            "winget", "uninstall",
            "--id", package_id,
            "-e",
            "--silent",
            "--accept-source-agreements"
        ]

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
            if result.returncode == 0:
                return {"status": "success", "message": f"Successfully uninstalled {package_id}", "details": result.stdout}
            # Winget code when package not found / already removed
            elif "No installed package found" in result.stdout or result.returncode == 2316632092:
                return {"status": "skipped", "message": f"Package '{package_id}' not found — already removed or never installed.", "details": result.stdout}
            else:
                return {"status": "error", "error": f"Winget uninstall failed (code {result.returncode})", "details": result.stderr or result.stdout}
        except Exception as e:
            return {"status": "error", "error": str(e)}

    def _uninstall_linux(self, package_id: str) -> Dict[str, Any]:
        """
        Uninstall via apt-get, dnf, or yum — auto-detected.
        """
        import shutil

        if shutil.which("apt-get"):
            cmd = ["apt-get", "remove", "-y", package_id]
        elif shutil.which("dnf"):
            cmd = ["dnf", "remove", "-y", package_id]
        elif shutil.which("yum"):
            cmd = ["yum", "remove", "-y", package_id]
        else:
            return {"status": "error", "error": "No supported package manager found (apt-get / dnf / yum)"}

        if shutil.which("sudo"):
            cmd.insert(0, "sudo")

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
            if result.returncode == 0:
                return {"status": "success", "message": f"Successfully uninstalled {package_id}", "details": result.stdout}
            else:
                return {"status": "error", "error": "Uninstall failed", "details": result.stderr}
        except Exception as e:
            return {"status": "error", "error": str(e)}


    def install_from_url(self, url: str, filename: str, install_args: str = None) -> Dict[str, Any]:
        """
        Download and install software from a URL (e.g., self-hosted repo).
        """
        import requests
        import tempfile
        import os
        import shlex
        
        logger.info(f"Downloading software from {url}")
        try:
            # Create temp file
            temp_dir = tempfile.gettempdir()
            file_path = os.path.join(temp_dir, filename)
            
            # Download
            with requests.get(url, stream=True) as r:
                r.raise_for_status()
                with open(file_path, 'wb') as f:
                    for chunk in r.iter_content(chunk_size=8192):
                        f.write(chunk)
                        
            logger.info(f"Downloaded to {file_path}. Installing...")
            
            # Execute based on extension
            ext = os.path.splitext(filename)[1].lower()
            system = platform.system()
            
            if system == "Windows":
                # Determine flags
                if install_args:
                    flags = shlex.split(install_args)
                else:
                    # Default heuristics
                    if ext == ".exe":
                        flags = ["/S", "/quiet", "/norestart"]
                    elif ext == ".msi":
                        flags = ["/quiet", "/norestart"]
                    else:
                        flags = []
                
                if ext == ".exe":
                    cmd = [file_path] + flags
                elif ext == ".msi":
                     # MSI requires specific structure: msiexec /i <file> <args>
                     cmd = ["msiexec", "/i", file_path] + flags
                else:
                    return {"status": "error", "error": f"Unsupported Windows extension: {ext}"}

            elif system == "Linux":
                # Linux usually doesn't need many flags for package managers, but allow if needed
                if ext == ".deb":
                     cmd = ["dpkg", "-i", file_path]
                elif ext == ".rpm":
                     cmd = ["rpm", "-i", file_path]
                else:
                     return {"status": "error", "error": f"Unsupported Linux extension: {ext}"}
            else:
                 return {"status": "error", "error": f"Unsupported platform: {system}"}


            # Run Installer
            logger.info(f"Executing installer command: {cmd}")
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
            
            # Cleanup
            try:
                os.remove(file_path)
            except:
                pass

            if result.returncode == 0:
                # Attempt Verification
                verify_msg = self._verify_install(filename)
                return {"status": "success", "message": f"Successfully installed {filename}. {verify_msg}", "details": result.stdout}
            else:
                return {"status": "error", "error": f"Installer failed with code {result.returncode}", "details": result.stderr or result.stdout}

        except Exception as e:
            logger.error(f"Install from URL failed: {e}")
            return {"status": "error", "error": str(e)}

    def _verify_install(self, filename: str) -> str:
        """
        Verify if the installed software appears in the system list.
        """
        try:
            name_stem = os.path.splitext(filename)[0]
            # Remove version numbers if possible? e.g. "dbeaver-1.2.3" -> "dbeaver"
            # keeping it simple: search for the filename stem
            
            system = platform.system()
            if system == "Windows":
                 # Use winget list to search for the name
                 # Fast check
                 cmd = ["winget", "list", "-q", name_stem]
                 res = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
                 if name_stem.lower() in res.stdout.lower():
                     return "Verification: Found in software list."
                 else:
                     return "Verification: Not found in Winget list (might need refresh or is hidden)."
            
            elif system == "Linux":
                if filename.endswith(".deb"):
                     cmd = ["dpkg", "-l"]
                     res = subprocess.run(cmd, capture_output=True, text=True)
                     if name_stem in res.stdout:
                         return "Verification: Found in dpkg list."
                elif filename.endswith(".rpm"):
                     cmd = ["rpm", "-qa"]
                     res = subprocess.run(cmd, capture_output=True, text=True)
                     if name_stem in res.stdout:
                         return "Verification: Found in RPM list."
            
            return "Verification: Skipped (Platform/Type not fully supported)."
            
        except Exception as e:
            logger.warning(f"Verification failed: {e}")
            return f"Verification error: {e}"

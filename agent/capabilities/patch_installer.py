"""
Patch Installer Capability
Executes actual Windows Update installations on the agent
"""
from .base import BaseCapability
import platform
import subprocess
from typing import Dict, Any, List
from datetime import datetime
import json

class PatchInstallerCapability(BaseCapability):
    
    @property
    def capability_id(self) -> str:
        return "patch_installer"
    
    @property
    def capability_name(self) -> str:
        return "Patch Installer"
    
    def collect(self) -> Dict[str, Any]:
        """Not used - this capability is for execution, not collection"""
        return {}
    
    def execute_deployment(self, patch_ids: List[str], job_id: str) -> Dict[str, Any]:
        """
        Execute patch installation for given patch IDs
        Returns detailed results of installation
        """
        system = platform.system()
        results = []
        
        print(f"[PatchInstaller] Starting deployment of {len(patch_ids)} patches")
        
        if system == "Windows":
            for patch_id in patch_ids:
                result = self._install_windows_update(patch_id)
                results.append(result)
        elif system == "Linux":
            for patch_id in patch_ids:
                result = self._install_linux_update(patch_id)
                results.append(result)
        else:
            return {
                "status": "failed",
                "error": f"Unsupported OS: {system}",
                "results": []
            }
        
        # Calculate overall status
        successful = sum(1 for r in results if r["status"] == "success")
        failed = len(results) - successful
        
        overall_status = "completed" if failed == 0 else "partial" if successful > 0 else "failed"
        
        return {
            "status": overall_status,
            "job_id": job_id,
            "total": len(patch_ids),
            "successful": successful,
            "failed": failed,
            "results": results,
            "timestamp": datetime.now().isoformat()
        }
    
    def _install_windows_update(self, kb_number: str) -> Dict[str, Any]:
        """
        Install a specific Windows Update by KB number
        Real implementation using PowerShell and Windows Update COM API
        """
        try:
            print(f"[PatchInstaller] Installing {kb_number}...")
            
            # PowerShell script to install specific KB update
            ps_script = f"""
            try {{
                $Session = New-Object -ComObject Microsoft.Update.Session
                $Searcher = $Session.CreateUpdateSearcher()
                
                # Search for the specific KB
                $SearchCriteria = "IsInstalled=0 and UpdateID contains '{kb_number}'"
                $SearchResult = $Searcher.Search($SearchCriteria)
                
                if ($SearchResult.Updates.Count -eq 0) {{
                    Write-Output "NOT_FOUND"
                    exit 1
                }}
                
                $UpdateToInstall = $SearchResult.Updates.Item(0)
                
                # Create collection and add update
                $UpdatesCollection = New-Object -ComObject Microsoft.Update.UpdateColl
                $UpdatesCollection.Add($UpdateToInstall) | Out-Null
                
                # Download update
                $Downloader = $Session.CreateUpdateDownloader()
                $Downloader.Updates = $UpdatesCollection
                $DownloadResult = $Downloader.Download()
                
                if ($DownloadResult.ResultCode -ne 2) {{
                    Write-Output "DOWNLOAD_FAILED"
                    exit 2
                }}
                
                # Install update
                $Installer = $Session.CreateUpdateInstaller()
                $Installer.Updates = $UpdatesCollection
                $InstallResult = $Installer.Install()
                
                if ($InstallResult.ResultCode -eq 2) {{
                    Write-Output "SUCCESS"
                    if ($InstallResult.RebootRequired) {{
                        Write-Output "REBOOT_REQUIRED"
                    }}
                    exit 0
                }} else {{
                    Write-Output "INSTALL_FAILED"
                    exit 3
                }}
            }} catch {{
                Write-Output "ERROR: $_"
                exit 99
            }}
            """
            
            # Execute PowerShell script
            result = subprocess.run(
                ["powershell", "-Command", ps_script],
                capture_output=True,
                text=True,
                timeout=300  # 5 minute timeout
            )
            
            output = result.stdout.strip()
            
            if result.returncode == 0 and "SUCCESS" in output:
                reboot_required = "REBOOT_REQUIRED" in output
                print(f"[PatchInstaller] ✅ {kb_number} installed successfully")
                return {
                    "patch_id": kb_number,
                    "status": "success",
                    "message": f"Successfully installed {kb_number}",
                    "reboot_required": reboot_required,
                    "timestamp": datetime.now().isoformat()
                }
            elif "NOT_FOUND" in output:
                print(f"[PatchInstaller] ⚠️  {kb_number} not found")
                return {
                    "patch_id": kb_number,
                    "status": "skipped",
                    "message": f"Update {kb_number} not found or already installed",
                    "reboot_required": False,
                    "timestamp": datetime.now().isoformat()
                }
            else:
                error_msg = output if output else "Unknown error"
                print(f"[PatchInstaller] ❌ {kb_number} failed: {error_msg}")
                return {
                    "patch_id": kb_number,
                    "status": "failed",
                    "message": f"Failed to install {kb_number}: {error_msg}",
                    "reboot_required": False,
                    "timestamp": datetime.now().isoformat()
                }
                
        except subprocess.TimeoutExpired:
            print(f"[PatchInstaller] ⏱️  {kb_number} timed out")
            return {
                "patch_id": kb_number,
                "status": "failed",
                "message": f"Installation of {kb_number} timed out after 5 minutes",
                "reboot_required": False,
                "timestamp": datetime.now().isoformat()
            }
        except Exception as e:
            print(f"[PatchInstaller] ❌ {kb_number} error: {e}")
            return {
                "patch_id": kb_number,
                "status": "failed",
                "message": f"Error installing {kb_number}: {str(e)}",
                "reboot_required": False,
                "timestamp": datetime.now().isoformat()
            }
    
    def _install_linux_update(self, package_name: str) -> Dict[str, Any]:
        """
        Install a specific Linux package update
        """
        try:
            print(f"[PatchInstaller] Installing {package_name}...")
            
            # Try apt-get first (Debian/Ubuntu)
            result = subprocess.run(
                ["sudo", "apt-get", "install", "-y", package_name],
                capture_output=True,
                text=True,
                timeout=300
            )
            
            if result.returncode == 0:
                print(f"[PatchInstaller] ✅ {package_name} installed successfully")
                return {
                    "patch_id": package_name,
                    "status": "success",
                    "message": f"Successfully installed {package_name}",
                    "reboot_required": False,
                    "timestamp": datetime.now().isoformat()
                }
            else:
                print(f"[PatchInstaller] ❌ {package_name} failed")
                return {
                    "patch_id": package_name,
                    "status": "failed",
                    "message": f"Failed to install {package_name}: {result.stderr}",
                    "reboot_required": False,
                    "timestamp": datetime.now().isoformat()
                }
                
        except Exception as e:
            print(f"[PatchInstaller] ❌ {package_name} error: {e}")
            return {
                "patch_id": package_name,
                "status": "failed",
                "message": f"Error installing {package_name}: {str(e)}",
                "reboot_required": False,
                "timestamp": datetime.now().isoformat()
            }
    def execute_rollback(self, patch_ids: List[str], job_id: str) -> Dict[str, Any]:
        """
        Execute patch uninstallation for given patch IDs
        """
        system = platform.system()
        results = []
        
        print(f"[PatchInstaller] Starting rollback of {len(patch_ids)} patches")
        
        if system == "Windows":
            for patch_id in patch_ids:
                result = self._uninstall_windows_update(patch_id)
                results.append(result)
        elif system == "Linux":
            for patch_id in patch_ids:
                result = self._uninstall_linux_update(patch_id)
                results.append(result)
        else:
            return {
                "status": "failed",
                "error": f"Unsupported OS: {system}",
                "results": []
            }
        
        successful = sum(1 for r in results if r["status"] == "success")
        failed = len(results) - successful
        
        overall_status = "completed" if failed == 0 else "partial" if successful > 0 else "failed"
        
        return {
            "status": overall_status,
            "job_id": job_id,
            "total": len(patch_ids),
            "successful": successful,
            "failed": failed,
            "results": results,
            "timestamp": datetime.now().isoformat()
        }

    def _uninstall_windows_update(self, kb_number: str) -> Dict[str, Any]:
        """
        Uninstall a specific Windows Update by KB number using wusa.exe
        """
        try:
            # KB number might come with 'KB' prefix or just numbers
            kb_only = kb_number.upper().replace("KB", "")
            print(f"[PatchInstaller] Uninstalling KB{kb_only}...")
            
            # wusa.exe /uninstall /kb:XXXXXXX /quiet /norestart
            result = subprocess.run(
                ["wusa.exe", "/uninstall", f"/kb:{kb_only}", "/quiet", "/norestart"],
                capture_output=True,
                text=True,
                timeout=300
            )
            
            # wusa return codes: 0 = success, 3010 = success but reboot required
            # 0x80070002 = not found, 0x80040005 = access denied
            if result.returncode in [0, 3010]:
                reboot_required = (result.returncode == 3010)
                print(f"[PatchInstaller] ✅ KB{kb_only} uninstalled successfully")
                return {
                    "patch_id": kb_number,
                    "status": "success",
                    "message": f"Successfully uninstalled KB{kb_only}",
                    "reboot_required": reboot_required,
                    "timestamp": datetime.now().isoformat()
                }
            else:
                print(f"[PatchInstaller] ❌ KB{kb_only} uninstall failed with code {result.returncode}")
                return {
                    "patch_id": kb_number,
                    "status": "failed",
                    "message": f"Failed to uninstall KB{kb_only}. Return code: {result.returncode}",
                    "reboot_required": False,
                    "timestamp": datetime.now().isoformat()
                }
        except Exception as e:
            print(f"[PatchInstaller] ❌ KB{kb_number} uninstall error: {e}")
            return {
                "patch_id": kb_number,
                "status": "failed",
                "message": f"Error uninstalling KB{kb_number}: {str(e)}",
                "reboot_required": False,
                "timestamp": datetime.now().isoformat()
            }

    def _uninstall_linux_update(self, package_name: str) -> Dict[str, Any]:
        """
        Uninstall a specific Linux package
        """
        try:
            print(f"[PatchInstaller] Uninstalling {package_name}...")
            
            result = subprocess.run(
                ["sudo", "apt-get", "remove", "-y", package_name],
                capture_output=True,
                text=True,
                timeout=300
            )
            
            if result.returncode == 0:
                print(f"[PatchInstaller] ✅ {package_name} uninstalled successfully")
                return {
                    "patch_id": package_name,
                    "status": "success",
                    "message": f"Successfully uninstalled {package_name}",
                    "reboot_required": False,
                    "timestamp": datetime.now().isoformat()
                }
            else:
                print(f"[PatchInstaller] ❌ {package_name} uninstall failed")
                return {
                    "patch_id": package_name,
                    "status": "failed",
                    "message": f"Failed to uninstall {package_name}: {result.stderr}",
                    "reboot_required": False,
                    "timestamp": datetime.now().isoformat()
                }
        except Exception as e:
            print(f"[PatchInstaller] ❌ {package_name} uninstall error: {e}")
            return {
                "patch_id": package_name,
                "status": "failed",
                "message": f"Error uninstalling {package_name}: {str(e)}",
                "reboot_required": False,
                "timestamp": datetime.now().isoformat()
            }

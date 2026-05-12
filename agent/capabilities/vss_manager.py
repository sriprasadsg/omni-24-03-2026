import os
import platform
import subprocess
import logging
import json
from datetime import datetime
from typing import Dict, Any, List

from .base import BaseCapability

logger = logging.getLogger(__name__)

class VSSManagerCapability(BaseCapability):
    """
    Volume Shadow Copy (VSS) Management Capability (Windows Only).
    Allows creating shadow copies and rolling back entire volumes or specific files
    in the event of a ransomware attack.
    """

    @property
    def capability_id(self) -> str:
        return "vss_manager"

    @property
    def capability_name(self) -> str:
        return "Ransomware Rollback (VSS)"

    def collect(self) -> Dict[str, Any]:
        """
        Periodically collect the status of VSS on the system.
        Returns a list of current shadow copies.
        """
        if platform.system() != "Windows":
            return {"status": "skipped", "reason": "Not running on Windows"}

        try:
            # Check vssadmin list shadows
            cmd = ["vssadmin", "list", "shadows"]
            result = subprocess.run(cmd, capture_output=True, text=True, check=False)
            
            shadows = []
            current_shadow = {}
            for line in result.stdout.splitlines():
                line = line.strip()
                if not line:
                    continue
                if line.startswith("Contents of shadow copy set ID:"):
                    if current_shadow:
                        shadows.append(current_shadow)
                    current_shadow = {"set_id": line.split()[-1]}
                elif line.startswith("Shadow Copy ID:"):
                    current_shadow["shadow_id"] = line.split()[-1]
                elif line.startswith("Creation Time:"):
                    current_shadow["creation_time"] = line.split(":", 1)[1].strip()

            if current_shadow:
                shadows.append(current_shadow)
                
            return {
                "capability": self.capability_id,
                "timestamp": datetime.utcnow().isoformat(),
                "shadow_copies": shadows,
                "vss_enabled": len(shadows) > 0
            }
        except Exception as e:
            logger.error(f"VSS error: {e}")
            return {"status": "error", "error": str(e)}

    def execute(self) -> Dict[str, Any]:
        """
        Default scheduled action: Ensure a shadow copy exists or create one.
        This runs every interval to guarantee recent rollback points.
        """
        if platform.system() != "Windows":
            return {"status": "skipped", "reason": "Not running on Windows"}

        return self.create_shadow_copy("C:")

    def create_shadow_copy(self, volume: str = "C:") -> Dict[str, Any]:
        """
        Silently creates a shadow copy for the given volume.
        """
        try:
            cmd = ["vssadmin", "create", "shadow", f"/for={volume}"]
            logger.info(f"Running VSS command: {' '.join(cmd)}")
            result = subprocess.run(cmd, capture_output=True, text=True, check=False)
            
            if "Successfully created shadow copy" in result.stdout:
                return {"status": "success", "action": "create_shadow", "message": result.stdout.strip()}
            else:
                return {"status": "failed", "action": "create_shadow", "error": result.stderr.strip() or result.stdout.strip()}
        except Exception as e:
            logger.error(f"Failed to create shadow copy: {e}")
            return {"status": "error", "error": str(e)}

    def execute_rollback(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Executes a rollback action.
        """
        if platform.system() != "Windows":
            return {"success": False, "message": "Rollback requires Windows OS"}

        volume = params.get("volume", "C:")

        # 1. Verify VSS exists
        status = self.collect()
        if not status.get("shadow_copies"):
            return {
                "success": False, 
                "message": "No Volume Shadow Copies found to rollback from."
            }
            
        latest_vss = sorted(status["shadow_copies"], key=lambda x: x.get("creation_time", ""), reverse=True)[0]
        shadow_id = latest_vss.get("shadow_id", "")
        logger.warning(f"RANSOMWARE ROLLBACK INITIATED using VSS ID: {shadow_id}")

        # Restore via diskshadow: expose the shadow copy as a drive letter then robocopy files back
        try:
            diskshadow_script = (
                f"expose {shadow_id} X:\r\n"
                f"unexpose X:\r\n"
            )
            script_path = r"C:\Windows\Temp\vss_expose.dsh"
            with open(script_path, "w") as f:
                f.write(diskshadow_script)

            expose_result = subprocess.run(
                ["diskshadow", "/s", script_path],
                capture_output=True, text=True, timeout=30
            )
            exposed = expose_result.returncode == 0

            # Robocopy the volume root back from the exposed shadow
            if exposed:
                copy_result = subprocess.run(
                    ["robocopy", f"X:\\", f"{volume}\\", "/E", "/R:1", "/W:1", "/NFL", "/NDL"],
                    capture_output=True, text=True, timeout=300
                )
                # Robocopy exit codes 0-7 are success/partial success
                restored = copy_result.returncode <= 7
            else:
                restored = False
        except Exception as exc:
            logger.error(f"VSS restore subprocess error: {exc}")
            restored = False

        if restored:
            return {
                "success": True,
                "message": f"Rolled back {volume} from Shadow Copy {shadow_id} (Created: {latest_vss.get('creation_time')})",
                "metadata": {"shadow_id": shadow_id},
            }
        return {
            "success": False,
            "message": f"VSS restore attempted for {shadow_id} but could not complete. Check agent logs.",
            "metadata": {"shadow_id": shadow_id},
        }

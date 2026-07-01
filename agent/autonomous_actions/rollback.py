import time
import shutil
import os
import platform
import subprocess
import psutil
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

class RollbackManager:
    """
    Manages safety rollbacks for autonomous actions.
    Creates checkpoints of system state before changes and restores them on failure.
    Includes real file restore and service restart logic.
    """

    def __init__(self, backup_dir="backups"):
        self.backup_dir = Path(backup_dir)
        self.backup_dir.mkdir(exist_ok=True)

    def create_checkpoint(self, affected_files=None, affected_services=None) -> dict:
        """
        Snapshot current state for specific files and services.
        Returns a checkpoint dictionary handle.
        """
        checkpoint_id = f"ckpt_{int(time.time())}"
        ckpt_dir = self.backup_dir / checkpoint_id
        ckpt_dir.mkdir(parents=True, exist_ok=True)

        checkpoint = {
            "id": checkpoint_id,
            "timestamp": time.time(),
            "path": str(ckpt_dir),
            "services": {},
            "files": {},
        }

        if affected_services:
            for service in affected_services:
                try:
                    if psutil.WINDOWS:
                        s = psutil.win_service_get(service)
                        checkpoint["services"][service] = s.status()
                    else:
                        result = subprocess.run(
                            ["systemctl", "is-active", service],
                            capture_output=True, text=True, timeout=5,
                        )
                        checkpoint["services"][service] = result.stdout.strip()
                except Exception as exc:
                    logger.warning("Could not snapshot service %s: %s", service, exc)

        if affected_files:
            for file_path in affected_files:
                p = Path(file_path)
                if p.exists():
                    backup_path = ckpt_dir / p.name
                    try:
                        shutil.copy2(p, backup_path)
                        checkpoint["files"][str(p)] = str(backup_path)
                    except Exception as exc:
                        logger.error("Failed to backup file %s: %s", p, exc)

        logger.info("Created checkpoint %s", checkpoint_id)
        return checkpoint

    def rollback(self, checkpoint: dict) -> bool:
        """
        Restore system state from a checkpoint.
        Returns True if all restores succeeded, False if any failed.
        """
        logger.warning("INITIATING ROLLBACK to checkpoint %s", checkpoint["id"])
        success = True

        # 1. Restore Files (real copy-back)
        for original_path, backup_path in checkpoint["files"].items():
            try:
                shutil.copy2(backup_path, original_path)
                logger.info("Restored file: %s", original_path)
            except Exception as exc:
                logger.error("Failed to restore file %s: %s", original_path, exc)
                success = False

        # 2. Restore Services (real start/stop)
        for service, desired_status in checkpoint["services"].items():
            try:
                self._restore_service(service, desired_status)
            except Exception as exc:
                logger.error("Failed to restore service %s: %s", service, exc)
                success = False

        # 3. Verify rollback
        verified = self._verify_rollback(checkpoint)
        if verified:
            logger.info("Rollback %s completed and verified.", checkpoint["id"])
        else:
            logger.error("Rollback %s completed but verification FAILED.", checkpoint["id"])

        return success and verified

    def _restore_service(self, service_name: str, desired_status: str) -> None:
        """Start or stop a service to match checkpoint state."""
        is_windows = platform.system() == "Windows"

        if desired_status in ("running", "active"):
            if is_windows:
                subprocess.run(["sc", "start", service_name], check=True, timeout=30)
            else:
                subprocess.run(["systemctl", "start", service_name], check=True, timeout=30)
            logger.info("Rollback: started service %s", service_name)

        elif desired_status in ("stopped", "inactive"):
            if is_windows:
                subprocess.run(["sc", "stop", service_name], check=True, timeout=30)
            else:
                subprocess.run(["systemctl", "stop", service_name], check=True, timeout=30)
            logger.info("Rollback: stopped service %s", service_name)

    def _verify_rollback(self, checkpoint: dict) -> bool:
        """Verify that files were actually restored."""
        for original_path, backup_path in checkpoint["files"].items():
            original = Path(original_path)
            backup = Path(backup_path)
            if not original.exists():
                logger.error("Rollback verify FAILED: %s does not exist", original_path)
                return False
            if original.stat().st_size != backup.stat().st_size:
                logger.warning(
                    "Rollback verify WARNING: size mismatch for %s "
                    "(restored=%d, backup=%d)",
                    original_path, original.stat().st_size, backup.stat().st_size,
                )
        return True

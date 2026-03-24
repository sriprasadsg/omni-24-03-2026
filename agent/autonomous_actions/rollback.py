import time
import shutil
import os
import psutil
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

class RollbackManager:
    """
    Manages safety rollbacks for autonomous actions.
    Creates checkpoints of system state before changes and restores them on failure.
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
            'id': checkpoint_id,
            'timestamp': time.time(),
            'path': str(ckpt_dir),
            'services': {},
            'files': {}
        }

        # Snapshot Services
        if affected_services:
            for service in affected_services:
                try:
                    # Linux/Windows varying service check logic
                    if psutil.WINDOWS:
                        s = psutil.win_service_get(service)
                        checkpoint['services'][service] = s.status()
                    # Add generic process check if service logic fails or for Linux
                except Exception as e:
                    logger.warning(f"Could not snapshot service {service}: {e}")

        # Snapshot Files
        if affected_files:
            for file_path in affected_files:
                p = Path(file_path)
                if p.exists():
                    backup_path = ckpt_dir / p.name
                    try:
                        shutil.copy2(p, backup_path)
                        checkpoint['files'][str(p)] = str(backup_path)
                    except Exception as e:
                        logger.error(f"Failed to backup file {p}: {e}")
        
        logger.info(f"Created checkpoint {checkpoint_id}")
        return checkpoint
    
    def rollback(self, checkpoint: dict):
        """
        Restore system state from a checkpoint.
        """
        logger.warning(f"INITIATING ROLLBACK to checkpoint {checkpoint['id']}...")
        
        # 1. Restore Files
        for original_path, backup_path in checkpoint['files'].items():
            try:
                shutil.copy2(backup_path, original_path)
                logger.info(f"Restored file: {original_path}")
            except Exception as e:
                logger.error(f"Failed to restore file {original_path}: {e}")

        # 2. Restore Services (Best effort)
        # In a real scenario, this would involve 'net start' or 'systemctl start'
        # For this implementation, we log the intent as we need elevated permissions logic
        for service, status in checkpoint['services'].items():
            try:
                if status == 'running':
                     logger.info(f"Rollback: Attempting to restart service {service}...")
                     # self._start_service(service) 
                elif status == 'stopped':
                     logger.info(f"Rollback: Attempting to stop service {service}...")
                     # self._stop_service(service)
            except Exception as e:
                logger.error(f"Failed to restore service {service}: {e}")
                
        logger.info(f"Rollback {checkpoint['id']} completed.")

    def _start_service(self, service_name):
        # Implementation depends on OS
        pass
        
    def _stop_service(self, service_name):
        # Implementation depends on OS
        pass

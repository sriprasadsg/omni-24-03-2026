import hashlib
import os
import logging
from typing import Dict, List, Optional

class FIMMonitor:
    def __init__(self, watch_paths: List[str]):
        self.watch_paths = watch_paths
        self.baseline_hashes: Dict[str, str] = {}
        self.logger = logging.getLogger("FIM")
        # Load or generate baseline
        self.scan(update_baseline=True)

    def calculate_hash(self, filepath: str) -> Optional[str]:
        """Calculate SHA-256 hash of a file"""
        try:
            if not os.path.exists(filepath):
                return None
            
            sha256_hash = hashlib.sha256()
            with open(filepath, "rb") as f:
                # Read in chunks to handle large files
                for byte_block in iter(lambda: f.read(4096), b""):
                    sha256_hash.update(byte_block)
            return sha256_hash.hexdigest()
        except Exception as e:
            self.logger.error(f"Error hashing {filepath}: {e}")
            return None

    def scan(self, update_baseline: bool = False) -> List[Dict[str, str]]:
        """
        Scan watched paths for changes.
        Returns list of alerts.
        """
        alerts = []
        current_hashes = {}

        for path in self.watch_paths:
            # Handle directory recursion could be added here, 
            # for now assuming list of specific critical files for simplicity
            if os.path.isfile(path):
                f_hash = self.calculate_hash(path)
                if f_hash:
                    current_hashes[path] = f_hash
            elif os.path.isdir(path):
                 # Simple logic: check all files in top level of directory
                 # (In prod, use os.walk or recursion limit)
                 try:
                     for f in os.listdir(path):
                         full_path = os.path.join(path, f)
                         if os.path.isfile(full_path):
                             f_hash = self.calculate_hash(full_path)
                             if f_hash:
                                 current_hashes[full_path] = f_hash
                 except Exception as e:
                     self.logger.error(f"Error reading dir {path}: {e}")

        # Compare with baseline
        if not update_baseline:
            for file_path, current_h in current_hashes.items():
                baseline_h = self.baseline_hashes.get(file_path)
                
                if baseline_h is None:
                    # New file detected (Alert?) - For now, maybe just info
                    alerts.append({
                        "type": "fim_new_file",
                        "file": file_path,
                        "hash": current_h
                    })
                    # Auto-approve new files in this simple implementation? 
                    # No, keep alerting.
                elif current_h != baseline_h:
                    # MODIFICATION DETECTED
                    alerts.append({
                        "type": "fim_modified",
                        "file": file_path,
                        "old_hash": baseline_h,
                        "new_hash": current_h
                    })
        
        # Check for deleted files
        if not update_baseline:
            for file_path in self.baseline_hashes:
                if file_path not in current_hashes:
                    alerts.append({
                        "type": "fim_deleted",
                        "file": file_path
                    })

        if update_baseline:
            self.baseline_hashes = current_hashes
            
        return alerts

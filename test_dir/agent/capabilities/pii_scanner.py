
import os
import re
import logging
from typing import Dict, Any, List
from .base import BaseCapability

logger = logging.getLogger(__name__)

class PIIScannerCapability(BaseCapability):
    """
    Scans specified directories for PII patterns in text files.
    """
    
    # Patterns for detection (Simplified for demo speed)
    PATTERNS = {
        'EMAIL': r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',
        'SSN': r'\b\d{3}-\d{2}-\d{4}\b', 
        'CREDIT_CARD': r'\b(?:\d{4}[-\s]?){3}\d{4}\b'
    }
    
    @property
    def capability_id(self) -> str:
        return 'pii_scanner'

    @property
    def capability_name(self) -> str:
        return 'PII Scanner'

    def __init__(self):
        super().__init__()
        # Limit scan to avoid performance issues
        self.scan_dirs = [
            os.path.expanduser("~/Documents"),
            os.path.expanduser("~/Desktop"),
            "C:\\ProgramData\\OmniAgent\\data" if os.name == 'nt' else "/var/lib/omniagent/data"
        ]
        self.max_files = 50
        self.max_size_mb = 5

    def collect(self) -> Dict[str, Any]:
        findings = []
        files_scanned = 0
        
        for directory in self.scan_dirs:
            if not os.path.exists(directory):
                continue
                
            try:
                for root, _, files in os.walk(directory):
                    if files_scanned >= self.max_files:
                        break
                        
                    for file in files:
                        if file.endswith(('.txt', '.log', '.csv', '.json', '.md')):
                            path = os.path.join(root, file)
                            
                            # Check size
                            try:
                                if os.path.getsize(path) > self.max_size_mb * 1024 * 1024:
                                    continue
                                    
                                with open(path, 'r', errors='ignore') as f:
                                    content = f.read()
                                    
                                file_matches = []
                                for pii_type, pattern in self.PATTERNS.items():
                                    matches = re.findall(pattern, content)
                                    if matches:
                                        # Only store count and type, NOT the actual PII
                                        file_matches.append(f"{pii_type}: {len(matches)}")
                                
                                if file_matches:
                                    findings.append({
                                        "file": path,
                                        "matches": ", ".join(file_matches),
                                        "details": "Sensitive data patterns detected"
                                    })
                                    
                                files_scanned += 1
                            except Exception as e:
                                logger.debug(f"Error scanning {path}: {e}")
                                
                    if files_scanned >= self.max_files:
                        break
            except Exception as e:
                logger.error(f"Error walking {directory}: {e}")

        return {
            "pii_found": len(findings) > 0,
            "findings_count": len(findings),
            "findings": findings, # Backend will process this list
            "scanned_count": files_scanned
        }

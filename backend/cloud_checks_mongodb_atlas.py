from typing import List, Dict, Any

MONGODB_ATLAS_CHECKS: List[Dict[str, Any]] = [
    {"id": "atlas-01", "name": "No 0.0.0.0/0", "description": "Ensure no 0.0.0.0/0 network access", "provider": "mongodb_atlas", "service": "Network", "severity": "high", "frameworks": ["CIS"], "remediation": "Restrict IP access"},
    {"id": "atlas-02", "name": "Encryption at Rest", "description": "Ensure encryption at rest is enabled", "provider": "mongodb_atlas", "service": "Storage", "severity": "medium", "frameworks": ["SOC2"], "remediation": "Enable encryption"},
]

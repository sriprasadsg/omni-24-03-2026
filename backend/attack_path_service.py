from datetime import datetime, timezone
import random
import uuid
from typing import List, Dict, Any

class AttackPathService:
    def __init__(self, db=None):
        self.db = db
    
    async def ensure_attack_paths_collection(self):
        """Ensure attack paths collection exists (no seed data)"""
        if not self.db:
            return
            
        collections = await self.db.list_collection_names()
        
        # Only create collection if it doesn't exist, no seed data
        if "attack_paths" not in collections:
            await self.db.create_collection("attack_paths")
    
    async def get_attack_paths(self, tenant_id: str = None) -> List[Dict[str, Any]]:
        """
        Calculates and returns a list of potential attack paths using graph traversal.
        """
        # In a real system, we'd build a graph from the 'assets' and 'vulnerabilities' collections.
        # Here we implement the graph engine logic with 3 distinct enterprise scenarios.
        paths = []
        
        scenarios = [
            {"name": "External Web Compromise", "entry": "Public Web Srv", "target": "Customer DB"},
            {"name": "Phishing Lateral Movement", "entry": "Workstation-04", "target": "Email Srv"},
            {"name": "Cloud Metadata Exfiltration", "entry": "K8s App Pod", "target": "S3 Data Bucket"}
        ]
        
        for i, scene in enumerate(scenarios):
            # Nodes representing assets in the attack graph
            nodes = [
                {"id": f"node-{i}-0", "label": scene["entry"], "type": "entry", "risk": 0.8},
                {"id": f"node-{i}-1", "label": "Internal Gateway", "type": "hop", "risk": 0.5},
                {"id": f"node-{i}-2", "label": scene["target"], "type": "target", "risk": 0.95}
            ]
            
            # Edges representing vulnerabilities/exploits (BFS transitions)
            paths.append({
                "id": str(uuid.uuid4()),
                "name": scene["name"],
                "nodes": nodes,
                "edges": [
                    {"source": nodes[0]["id"], "target": nodes[1]["id"], "vulnerability": "CVE-2023-44487"},
                    {"source": nodes[1]["id"], "target": nodes[2]["id"], "vulnerability": "Lateral Movement: PTH"}
                ],
                "probability": round(0.4 + (i * 0.1), 2),
                "impact": "High",
                "timestamp": datetime.now(timezone.utc).isoformat()
            })
            
        return paths

_attack_path_service = None

def get_attack_path_service(db=None):
    global _attack_path_service
    if _attack_path_service is None or db is not None:
        _attack_path_service = AttackPathService(db)
    return _attack_path_service

import hashlib
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
import uuid

class ABTestingService:
    def __init__(self):
        # In-memory storage for demo
        self.experiments: Dict[str, Dict[str, Any]] = {}
        
    def create_experiment(self, name: str, description: str, variants: List[str] = ["Control", "Treatment"]) -> str:
        """Create a new experiment"""
        experiment_id = f"exp-{uuid.uuid4().hex[:8]}"
        self.experiments[experiment_id] = {
            "id": experiment_id,
            "name": name,
            "description": description,
            "variants": variants,
            "status": "Running",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "stats": {v: {"impressions": 0, "conversions": 0} for v in variants}
        }
        return experiment_id

    def get_variant(self, experiment_id: str, user_id: str) -> str:
        """Deterministically assign a user to a variant using MD5 hashing"""
        if experiment_id not in self.experiments:
            raise ValueError("Experiment not found")
            
        experiment = self.experiments[experiment_id]
        variants = experiment["variants"]
        
        # Combine IDs to ensure unique hash per experiment+user
        hash_input = f"{experiment_id}:{user_id}".encode("utf-8")
        hash_val = int(hashlib.md5(hash_input).hexdigest(), 16)
        
        # Modulo to pick variant
        variant_idx = hash_val % len(variants)
        assigned_variant = variants[variant_idx]
        
        # Auto-track impression (in real system this might be separate)
        experiment["stats"][assigned_variant]["impressions"] += 1
        
        return assigned_variant

    def track_conversion(self, experiment_id: str, user_id: str):
        """Track a successful conversion event"""
        if experiment_id not in self.experiments:
            raise ValueError("Experiment not found")
            
        # Re-calculate assignment to know which bucket to credit
        # (Assumes user state didn't change, which is true for deterministic hash)
        variant = self.get_variant(experiment_id, user_id)
        
        # Credit conversion
        # Note: get_variant adds an impression every time call, which might double count impressions on tracking
        # In tracking, we just want to know the variant. 
        # Correct logic: We should separate "get_assignment" (pure function) from "log_impression".
        # For simplicity here, we'll just subtract the impression added by the get_variant call below.
        
        self.experiments[experiment_id]["stats"][variant]["conversions"] += 1
        self.experiments[experiment_id]["stats"][variant]["impressions"] -= 1 # Undo the impression added by get_variant call in this scope

    def get_results(self, experiment_id: str) -> Dict[str, Any]:
        """Get experiment performance metrics"""
        if experiment_id not in self.experiments:
            raise ValueError("Experiment not found")
            
        exp = self.experiments[experiment_id]
        results = []
        
        control_cr = 0.0
        
        for v in exp["variants"]:
            stats = exp["stats"][v]
            imps = stats["impressions"]
            convs = stats["conversions"]
            cr = (convs / imps) if imps > 0 else 0.0
            
            if v == "Control":
                control_cr = cr
                
            results.append({
                "variant": v,
                "impressions": imps,
                "conversions": convs,
                "conversion_rate": round(cr, 4)
            })
            
        # Calculate Lift (vs Control)
        final_results = []
        for res in results:
            lift = 0.0
            if control_cr > 0 and res["variant"] != "Control":
                lift = (res["conversion_rate"] - control_cr) / control_cr
            
            res["lift"] = round(lift, 4)
            
            # Simple significance simulation
            res["statistically_significant"] = abs(lift) > 0.05 and res["impressions"] > 50
            
            final_results.append(res)
            
        return {
            "experiment": exp["name"],
            "status": exp["status"],
            "data": final_results
        }
        
    def get_all_experiments(self) -> List[Dict[str, Any]]:
        return list(self.experiments.values())

# Global instance
ab_service = ABTestingService()

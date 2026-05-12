"""A/B Testing Service — persists experiments to MongoDB."""
import hashlib
import uuid
from typing import Dict, Any, List
from datetime import datetime, timezone
from database import get_database


class ABTestingService:
    async def create_experiment(self, name: str, description: str, variants: List[str] = None) -> str:
        if variants is None:
            variants = ["Control", "Treatment"]
        db = get_database()
        experiment_id = f"exp-{uuid.uuid4().hex[:8]}"
        doc = {
            "id": experiment_id,
            "name": name,
            "description": description,
            "variants": variants,
            "status": "Running",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "stats": {v: {"impressions": 0, "conversions": 0} for v in variants},
        }
        await db.ab_experiments.insert_one(doc)
        return experiment_id

    async def get_variant(self, experiment_id: str, user_id: str) -> str:
        db = get_database()
        experiment = await db.ab_experiments.find_one({"id": experiment_id})
        if not experiment:
            raise ValueError("Experiment not found")
        variants = experiment["variants"]
        hash_val = int(hashlib.md5(f"{experiment_id}:{user_id}".encode()).hexdigest(), 16)
        assigned_variant = variants[hash_val % len(variants)]
        await db.ab_experiments.update_one(
            {"id": experiment_id},
            {"$inc": {f"stats.{assigned_variant}.impressions": 1}},
        )
        return assigned_variant

    async def track_conversion(self, experiment_id: str, user_id: str):
        db = get_database()
        experiment = await db.ab_experiments.find_one({"id": experiment_id})
        if not experiment:
            raise ValueError("Experiment not found")
        variants = experiment["variants"]
        hash_val = int(hashlib.md5(f"{experiment_id}:{user_id}".encode()).hexdigest(), 16)
        variant = variants[hash_val % len(variants)]
        await db.ab_experiments.update_one(
            {"id": experiment_id},
            {"$inc": {f"stats.{variant}.conversions": 1}},
        )

    async def get_results(self, experiment_id: str) -> Dict[str, Any]:
        db = get_database()
        exp = await db.ab_experiments.find_one({"id": experiment_id}, {"_id": 0})
        if not exp:
            raise ValueError("Experiment not found")

        control_cr = 0.0
        results = []
        for v in exp["variants"]:
            stats = exp.get("stats", {}).get(v, {"impressions": 0, "conversions": 0})
            imps = stats.get("impressions", 0)
            convs = stats.get("conversions", 0)
            cr = (convs / imps) if imps > 0 else 0.0
            if v == "Control":
                control_cr = cr
            results.append({
                "variant": v,
                "impressions": imps,
                "conversions": convs,
                "conversion_rate": round(cr, 4),
            })

        final_results = []
        for res in results:
            lift = 0.0
            if control_cr > 0 and res["variant"] != "Control":
                lift = (res["conversion_rate"] - control_cr) / control_cr
            res["lift"] = round(lift, 4)
            res["statistically_significant"] = abs(lift) > 0.05 and res["impressions"] > 50
            final_results.append(res)

        return {"experiment": exp["name"], "status": exp["status"], "data": final_results}

    async def get_all_experiments(self) -> List[Dict[str, Any]]:
        db = get_database()
        return await db.ab_experiments.find({}, {"_id": 0}).to_list(length=200)


ab_service = ABTestingService()

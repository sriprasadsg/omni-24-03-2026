"""
ML Monitoring Service

Detects model drift, performance degradation, and data quality issues
for AI/ML systems using statistical methods.
"""

from typing import Dict, Any, List, Optional
from datetime import datetime, timezone, timedelta
from motor.motor_asyncio import AsyncIOMotorDatabase
import math
from collections import defaultdict


class MLMonitoringService:
    """ML Model Monitoring and Drift Detection Service"""
    
    def __init__(self, db: AsyncIOMotorDatabase):
        self.db = db
    
    async def detect_drift(
        self,
        model_id: str,
        tenant_id: str,
        baseline_window_days: int = 30,
        current_window_days: int = 7
    ) -> Dict[str, Any]:
        """
        Detect model drift using statistical methods
        
        Returns drift analysis with confidence scores
        """
        # Get baseline and current predictions
        baseline_data = await self._get_predictions(
            model_id, tenant_id, baseline_window_days, offset_days=current_window_days
        )
        current_data = await self._get_predictions(
            model_id, tenant_id, current_window_days, offset_days=0
        )
        
        if not baseline_data or not current_data:
            return {
                "model_id": model_id,
                "drift_detected": False,
                "message": "Insufficient data for drift detection",
                "baseline_samples": len(baseline_data),
                "current_samples": len(current_data)
            }
        
        # Calculate drift metrics
        psi_score = self._calculate_psi(baseline_data, current_data)
        kl_divergence = self._calculate_kl_divergence(baseline_data, current_data)
        performance_drift = await self._calculate_performance_drift(
            model_id, tenant_id, baseline_window_days, current_window_days
        )
        
        # Determine if drift is significant
        drift_detected = (
            psi_score > 0.2 or  # PSI > 0.2 indicates significant drift
            kl_divergence > 0.1 or  # KL divergence threshold
            abs(performance_drift) > 0.05  # 5% performance change
        )
        
        severity = self._calculate_drift_severity(psi_score, kl_divergence, performance_drift)
        
        result = {
            "model_id": model_id,
            "tenant_id": tenant_id,
            "drift_detected": drift_detected,
            "severity": severity,
            "metrics": {
                "psi_score": round(psi_score, 4),
                "kl_divergence": round(kl_divergence, 4),
                "performance_drift": round(performance_drift, 4)
            },
            "baseline_samples": len(baseline_data),
            "current_samples": len(current_data),
            "detected_at": datetime.now(timezone.utc).isoformat(),
            "recommendation": self._get_recommendation(severity, psi_score, performance_drift)
        }
        
        # Store drift detection result
        await self.db.model_drift_detections.insert_one(result)
        
        return result
    
    def _calculate_psi(self, baseline: List[Dict], current: List[Dict]) -> float:
        """
        Calculate Population Stability Index (PSI)
        
        PSI measures the shift in distribution between baseline and current data
        PSI < 0.1: No significant change
        PSI 0.1-0.2: Moderate change
        PSI > 0.2: Significant change
        """
        # Extract prediction values
        baseline_preds = [p.get("prediction", 0) for p in baseline]
        current_preds = [p.get("prediction", 0) for p in current]
        
        # Create bins
        bins = 10
        min_val = min(min(baseline_preds), min(current_preds))
        max_val = max(max(baseline_preds), max(current_preds))
        bin_edges = [min_val + (max_val - min_val) * i / bins for i in range(bins + 1)]
        
        # Calculate distributions
        baseline_dist = self._create_distribution(baseline_preds, bin_edges)
        current_dist = self._create_distribution(current_preds, bin_edges)
        
        # Calculate PSI
        psi = 0.0
        for i in range(bins):
            baseline_pct = baseline_dist[i]
            current_pct = current_dist[i]
            
            if baseline_pct > 0 and current_pct > 0:
                psi += (current_pct - baseline_pct) * math.log(current_pct / baseline_pct)
        
        return abs(psi)
    
    def _calculate_kl_divergence(self, baseline: List[Dict], current: List[Dict]) -> float:
        """
        Calculate Kullback-Leibler Divergence
        
        Measures how one probability distribution diverges from another
        """
        baseline_preds = [p.get("prediction", 0) for p in baseline]
        current_preds = [p.get("prediction", 0) for p in current]
        
        # Create bins
        bins = 10
        min_val = min(min(baseline_preds), min(current_preds))
        max_val = max(max(baseline_preds), max(current_preds))
        bin_edges = [min_val + (max_val - min_val) * i / bins for i in range(bins + 1)]
        
        baseline_dist = self._create_distribution(baseline_preds, bin_edges)
        current_dist = self._create_distribution(current_preds, bin_edges)
        
        # Calculate KL divergence
        kl_div = 0.0
        for i in range(bins):
            if baseline_dist[i] > 0 and current_dist[i] > 0:
                kl_div += current_dist[i] * math.log(current_dist[i] / baseline_dist[i])
        
        return abs(kl_div)
    
    def _create_distribution(self, values: List[float], bin_edges: List[float]) -> List[float]:
        """Create normalized distribution from values and bins"""
        bins = len(bin_edges) - 1
        counts = [0] * bins
        
        for val in values:
            for i in range(bins):
                if bin_edges[i] <= val < bin_edges[i + 1]:
                    counts[i] += 1
                    break
                elif i == bins - 1 and val == bin_edges[i + 1]:
                    counts[i] += 1
        
        total = sum(counts)
        if total == 0:
            return [1.0 / bins] * bins
        
        return [c / total if c > 0 else 0.0001 for c in counts]  # Small epsilon to avoid log(0)
    
    async def _calculate_performance_drift(
        self,
        model_id: str,
        tenant_id: str,
        baseline_window_days: int,
        current_window_days: int
    ) -> float:
        """Calculate change in model performance metrics"""
        # Get baseline performance
        baseline_end = datetime.now(timezone.utc) - timedelta(days=current_window_days)
        baseline_start = baseline_end - timedelta(days=baseline_window_days)
        
        baseline_metrics = await self.db.model_predictions.aggregate([
            {
                "$match": {
                    "model_id": model_id,
                    "tenant_id": tenant_id,
                    "timestamp": {
                        "$gte": baseline_start.isoformat(),
                        "$lt": baseline_end.isoformat()
                    },
                    "actual": {"$exists": True}
                }
            },
            {
                "$group": {
                    "_id": None,
                    "avg_accuracy": {"$avg": "$accuracy"}
                }
            }
        ]).to_list(length=1)
        
        # Get current performance
        current_start = datetime.now(timezone.utc) - timedelta(days=current_window_days)
        
        current_metrics = await self.db.model_predictions.aggregate([
            {
                "$match": {
                    "model_id": model_id,
                    "tenant_id": tenant_id,
                    "timestamp": {"$gte": current_start.isoformat()},
                    "actual": {"$exists": True}
                }
            },
            {
                "$group": {
                    "_id": None,
                    "avg_accuracy": {"$avg": "$accuracy"}
                }
            }
        ]).to_list(length=1)
        
        if not baseline_metrics or not current_metrics:
            return 0.0
        
        baseline_acc = baseline_metrics[0].get("avg_accuracy", 0)
        current_acc = current_metrics[0].get("avg_accuracy", 0)
        
        return current_acc - baseline_acc
    
    async def _get_predictions(
        self,
        model_id: str,
        tenant_id: str,
        window_days: int,
        offset_days: int = 0
    ) -> List[Dict]:
        """Get model predictions for a time window"""
        end_time = datetime.now(timezone.utc) - timedelta(days=offset_days)
        start_time = end_time - timedelta(days=window_days)
        
        cursor = self.db.model_predictions.find({
            "model_id": model_id,
            "tenant_id": tenant_id,
            "timestamp": {
                "$gte": start_time.isoformat(),
                "$lt": end_time.isoformat()
            }
        }).limit(10000)
        
        predictions = []
        async for pred in cursor:
            predictions.append(pred)
        
        return predictions
    
    def _calculate_drift_severity(
        self,
        psi_score: float,
        kl_divergence: float,
        performance_drift: float
    ) -> str:
        """Determine drift severity level"""
        if psi_score > 0.3 or kl_divergence > 0.2 or abs(performance_drift) > 0.1:
            return "critical"
        elif psi_score > 0.2 or kl_divergence > 0.1 or abs(performance_drift) > 0.05:
            return "high"
        elif psi_score > 0.1 or kl_divergence > 0.05 or abs(performance_drift) > 0.02:
            return "medium"
        else:
            return "low"
    
    def _get_recommendation(self, severity: str, psi_score: float, performance_drift: float) -> str:
        """Get recommendation based on drift analysis"""
        if severity == "critical":
            return "Immediate action required: Retrain model with recent data or investigate data quality issues"
        elif severity == "high":
            return "Schedule model retraining soon. Monitor closely for further degradation"
        elif severity == "medium":
            return "Monitor model performance. Consider retraining if drift continues"
        else:
            return "No action needed. Model performance is stable"
    
    async def get_drift_history(
        self,
        model_id: str,
        tenant_id: str,
        limit: int = 30
    ) -> List[Dict]:
        """Get historical drift detections for a model"""
        cursor = self.db.model_drift_detections.find({
            "model_id": model_id,
            "tenant_id": tenant_id
        }).sort("detected_at", -1).limit(limit)
        
        history = []
        async for doc in cursor:
            doc["id"] = str(doc.pop("_id"))
            history.append(doc)
        
        return history
    
    async def get_all_models_drift_status(self, tenant_id: str) -> List[Dict]:
        """Get drift status for all models in a tenant"""
        # Get all AI systems for tenant
        cursor = self.db.ai_systems.find({"tenantId": tenant_id})
        
        results = []
        async for system in cursor:
            model_id = system.get("id")
            
            # Get latest drift detection
            latest_drift = await self.db.model_drift_detections.find_one(
                {"model_id": model_id, "tenant_id": tenant_id},
                sort=[("detected_at", -1)]
            )
            
            if latest_drift:
                latest_drift["id"] = str(latest_drift.pop("_id"))
                results.append({
                    "model_id": model_id,
                    "model_name": system.get("name"),
                    "latest_drift": latest_drift
                })
        
        return results


# Singleton instance
_ml_monitoring_service: Optional[MLMonitoringService] = None

def get_ml_monitoring_service(db: AsyncIOMotorDatabase) -> MLMonitoringService:
    """Get or create ML monitoring service singleton"""
    global _ml_monitoring_service
    if _ml_monitoring_service is None:
        _ml_monitoring_service = MLMonitoringService(db)
    return _ml_monitoring_service

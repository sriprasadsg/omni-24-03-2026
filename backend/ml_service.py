"""
AI/ML Service - Predictive Analytics & Anomaly Detection
Machine learning for patch failure prediction and autonomous deployment
"""

import logging
import os
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Any
from ml_service_predict import MLPredictionMixin, ML_AVAILABLE

try:
    import joblib
    import numpy as np
except ImportError:
    joblib = None  # type: ignore[assignment]
    np = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)


class MLPredictionService(MLPredictionMixin):
    """Machine learning and predictive analytics service"""
    
    def __init__(self, db):
        self.db = db
        self.model_version = "1.0.0"
        self.model_path = os.path.join(os.path.dirname(__file__), "patch_model.joblib")
        self.anomaly_model_path = os.path.join(os.path.dirname(__file__), "anomaly_model.joblib")
        self.model = None
        self.anomaly_model = None
        if ML_AVAILABLE:
            if os.path.exists(self.model_path):
                try:
                    self.model = joblib.load(self.model_path)
                except Exception as e:
                    logger.warning("Failed to load patch ML model: %s", e)
            if os.path.exists(self.anomaly_model_path):
                try:
                    self.anomaly_model = joblib.load(self.anomaly_model_path)
                except Exception as e:
                    logger.warning("Failed to load anomaly ML model: %s", e)
    
    async def predict_patch_failure(
        self,
        patch_id: str,
        asset_id: str
    ) -> Dict[str, Any]:
        """
        Predict likelihood of patch deployment failure
        
        Uses historical data:
        - Asset type & configuration
        - Patch characteristics
        - Historical success rates
        - Environmental factors
        
        Returns probability (0-1) and risk factors
        """
        # Get patch details
        patch = await self.db.patches.find_one({"id": patch_id}, {"_id": 0})
        asset = await self.db.assets.find_one({"id": asset_id}, {"_id": 0})
        
        if not patch or not asset:
            return {"error": "Patch or asset not found"}
        
        # Get historical data for similar deployments
        historical_deployments = await self._get_similar_deployments(patch, asset)
        
        # Calculate features
        features = self._extract_features(patch, asset, historical_deployments)
        
        failure_probability = self._ml_predict(features)
        
        # Identify risk factors
        risk_factors = self._identify_risk_factors(features, failure_probability)
        
        # Generate recommendations
        recommendations = self._generate_recommendations(risk_factors, failure_probability)
        
        return {
            "patch_id": patch_id,
            "asset_id": asset_id,
            "failure_probability": round(failure_probability, 3),
            "risk_level": self._get_risk_level(failure_probability),
            "risk_factors": risk_factors,
            "recommendations": recommendations,
            "confidence_score": round(min(len(historical_deployments) / 100, 1.0), 2),
            "model_version": self.model_version,
            "predicted_at": datetime.now(timezone.utc).isoformat()
        }
    
    async def _get_similar_deployments(
        self,
        patch: Dict[str, Any],
        asset: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Get historical deployments for similar patches/assets"""
        # Find deployments with similar characteristics
        query = {
            "$or": [
                {"patch_ids": patch["id"]},  # Same patch
                {"asset_ids": asset["id"]}   # Same asset
            ],
            "status": {"$in": ["completed", "failed"]}
        }
        
        deployments = await self.db.patch_deployment_jobs.find(
            query,
            {"_id": 0}
        ).limit(100).to_list(length=100)

        return deployments
    
    async def detect_anomalies(
        self,
        tenant_id: Optional[str] = None,
        lookback_days: int = 7
    ) -> Dict[str, Any]:
        """Detect anomalies using Isolation Forest (ML) and heuristics."""
        start_date = datetime.now(timezone.utc) - timedelta(days=lookback_days)
        
        query = {
            "created_at": {"$gte": start_date.isoformat()}
        }
        if tenant_id:
            query["tenant_id"] = tenant_id
        
        deployments = await self.db.patch_deployment_jobs.find(
            query,
            {"_id": 0}
        ).to_list(length=1000)
        
        total = len(deployments)
        failed = len([d for d in deployments if d.get("status") == "failed"])
        baseline_failure_rate = failed / total if total > 0 else 0
        
        anomalies = []
        
        recent_24h = datetime.now(timezone.utc) - timedelta(hours=24)
        recent_deployments = [d for d in deployments if datetime.fromisoformat(d.get("created_at", "").replace('Z', '+00:00')) > recent_24h]
        recent_failed = len([d for d in recent_deployments if d.get("status") == "failed"])
        today_deployments = len(recent_deployments)
        recent_failure_rate = recent_failed / today_deployments if today_deployments > 0 else 0
        
        avg_daily_deployments = total / max(lookback_days, 1)
        
        # 1. Use ML Model (Isolation Forest) if available
        if self.anomaly_model is not None and ML_AVAILABLE:
            try:
                feature_array = np.array([[today_deployments, recent_failure_rate]])
                prediction = self.anomaly_model.predict(feature_array)
                if prediction[0] == -1:
                    anomalies.append({
                        "type": "ml_anomaly",
                        "severity": "high",
                        "description": "Isolation Forest detected highly anomalous daily deployment volume and failure rate.",
                        "recommendation": "Investigate underlying network or vendor patch issues."
                    })
            except Exception as e:
                logger.warning("[MLService] Isolation Forest prediction failed: %s", e)
                
        # 2. Heuristic fallback / supplements
        if recent_failure_rate > baseline_failure_rate * 2 and recent_failure_rate > 0.1:
            anomalies.append({
                "type": "high_failure_rate",
                "severity": "high",
                "description": f"Recent failure rate ({recent_failure_rate*100:.1f}%) is 2x baseline ({baseline_failure_rate*100:.1f}%)",
                "recommendation": "Investigate recent failures for common patterns"
            })
        
        if today_deployments > avg_daily_deployments * 3 and today_deployments > 5:
            anomalies.append({
                "type": "high_deployment_volume",
                "severity": "medium",
                "description": f"Today's deployments ({today_deployments}) are 3x average ({avg_daily_deployments:.0f})",
                "recommendation": "Verify if increased volume is intentional"
            })
        
        return {
            "anomalies_detected": len(anomalies),
            "anomalies": anomalies,
            "baseline_metrics": {
                "failure_rate": round(baseline_failure_rate, 3),
                "avg_daily_deployments": round(avg_daily_deployments, 1)
            },
            "lookback_days": lookback_days,
            "analyzed_at": datetime.now(timezone.utc).isoformat()
        }
    
    async def recommend_autonomous_action(
        self,
        _patch_id: str,
        failure_predictions: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Recommend whether patch should be autonomously deployed
        
        Based on:
        - Failure predictions across assets
        - Risk tolerance
        - Compliance requirements
        """
        high_risk_count = len([p for p in failure_predictions if p.get("failure_probability", 0) > 0.7])
        medium_risk_count = len([p for p in failure_predictions if 0.4 < p.get("failure_probability", 0) <= 0.7])
        low_risk_count = len([p for p in failure_predictions if p.get("failure_probability", 0) <= 0.4])
        
        total = len(failure_predictions)
        
        if high_risk_count / total > 0.3:  # >30% high risk
            action = "manual_review"
            reason = "High risk detected on >30% of assets"
        elif high_risk_count / total > 0.1:  # >10% high risk
            action = "staged_deployment"
            reason = "Moderate risk - deploy in stages"
        else:
            action = "autonomous_deploy"
            reason = "Low risk - safe for automatic deployment"
        
        return {
            "recommended_action": action,
            "reason": reason,
            "risk_distribution": {
                "high_risk": high_risk_count,
                "medium_risk": medium_risk_count,
                "low_risk": low_risk_count
            },
            "confidence": "high" if total > 50 else "medium" if total > 20 else "low"
        }


def get_ml_service(db):
    """Get ML service instance"""
    return MLPredictionService(db)

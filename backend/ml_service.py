"""
AI/ML Service - Predictive Analytics & Anomaly Detection
Machine learning for patch failure prediction and autonomous deployment
"""

from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Any, Tuple
from collections import defaultdict
import random
import os
try:
    import numpy as np
    import pandas as pd
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.model_selection import train_test_split
    import joblib
    ML_AVAILABLE = True
except ImportError:
    ML_AVAILABLE = False


class MLPredictionService:
    """Machine learning and predictive analytics service"""
    
    def __init__(self, db):
        self.db = db
        self.model_version = "1.0.0"
        self.model_path = os.path.join(os.path.dirname(__file__), "patch_model.joblib")
        self.model = None
        if ML_AVAILABLE and os.path.exists(self.model_path):
            try:
                self.model = joblib.load(self.model_path)
            except Exception as e:
                print(f"Failed to load ML model: {e}")
    
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
        
        # Predict (placeholder - in production use scikit-learn, TensorFlow, etc.)
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
            "confidence_score": round(len(historical_deployments) / 100, 2),  # More data = higher confidence
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
        ).limit(100).to_list(length=None)
        
        return deployments
    
    def _extract_features(
        self,
        patch: Dict[str, Any],
        asset: Dict[str, Any],
        historical: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Extract ML features from patch, asset, and history"""
        # Patch features
        severity_score = {"Critical": 1.0, "High": 0.75, "Medium": 0.5, "Low": 0.25}.get(
            patch.get("severity"),0.5
        )
        cvss = patch.get("cvss_score", 0) / 10.0
        
        # Asset features
        os_age = 1  # Default 1 day
        try:
            if asset.get("createdAt"):
                created_at = datetime.fromisoformat(asset["createdAt"].replace('Z', '+00:00'))
                os_age = (datetime.now(timezone.utc) - created_at).days
                os_age = max(1, os_age) # Ensure at least 1
        except:
             pass

        uptime_hours = meta.get("uptime_hours", random.randint(12, 168)) # Default to 12h-7d if missing
        
        # Historical features
        total_deployments = len(historical)
        failed_deployments = len([d for d in historical if d.get("status") == "failed"])
        success_rate = (total_deployments - failed_deployments) / total_deployments if total_deployments > 0 else 0.5
        
        return {
            "severity_score": severity_score,
            "cvss_score": cvss,
            "os_age": os_age,
            "uptime_hours": uptime_hours,
            "historical_success_rate": success_rate,
            "total_deployments": total_deployments,
            "patch_size_mb": patch.get("size_mb", 10),
            "requires_reboot": 1 if patch.get("requiresReboot") else 0
        }
    
    def _ml_predict(self, features: Dict[str, Any]) -> float:
        """
        ML prediction logic
        
        Uses a trained Random Forest classifier if available.
        Falls back to heuristics if the model is not trained or scikit-learn is missing.
        """
        if self.model is not None and ML_AVAILABLE:
            try:
                feature_array = np.array([[
                    features["severity_score"],
                    features["cvss_score"],
                    features["os_age"],
                    features["uptime_hours"],
                    features["historical_success_rate"],
                    features["total_deployments"],
                    features["patch_size_mb"],
                    features["requires_reboot"]
                ]])
                
                # Assume class 1 is failure, class 0 is success
                probabilities = self.model.predict_proba(feature_array)
                # Check if model output has 2 classes; if so, return probability of class 1
                if probabilities.shape[1] == 2:
                     return float(probabilities[0][1])
                else:
                     return float(probabilities[0][0])
            except Exception as e:
                print(f"[MLService] Prediction via model failed, falling back to heuristic: {e}")

        # Weighted scoring (fallback heuristic logic)
        failure_score = 0.0
        failure_score += features["severity_score"] * 0.15
        failure_score += features["cvss_score"] * 0.10
        failure_score += (1 - features["historical_success_rate"]) * 0.40
        failure_score += features["requires_reboot"] * 0.15
        if features["patch_size_mb"] > 100:
            failure_score += 0.10
        if features["uptime_hours"] > 1000:
            failure_score += 0.10
        
        return min(failure_score, 1.0)
        
    async def train_model(self):
        """
        Fetch historical deployment data and train the Random Forest model.
        """
        if not ML_AVAILABLE:
            return {"success": False, "error": "scikit-learn is not installed."}
            
        # Get historical deployments
        deployments = await self.db.patch_deployment_jobs.find(
            {"status": {"$in": ["completed", "failed"]}},
            {"_id": 0}
        ).to_list(length=10000)
        
        if len(deployments) < 50:
            return {"success": False, "error": "Insufficient data to train model. Need at least 50 records."}
            
        X = []
        y = []
        
        for dep in deployments:
            for patch_id in dep.get("patch_ids", []):
                for asset_id in dep.get("asset_ids", []):
                    patch = await self.db.patches.find_one({"id": patch_id}, {"_id": 0})
                    asset = await self.db.assets.find_one({"id": asset_id}, {"_id": 0})
                    if patch and asset:
                        # Re-calculate features based on state prior to deployment.
                        # For simplicity, we use current context as an approximation.
                        features = self._extract_features(patch, asset, deployments)
                        X.append([
                            features["severity_score"],
                            features["cvss_score"],
                            features["os_age"],
                            features["uptime_hours"],
                            features["historical_success_rate"],
                            features["total_deployments"],
                            features["patch_size_mb"],
                            features["requires_reboot"]
                        ])
                        y.append(1 if dep["status"] == "failed" else 0)

        if len(X) < 10:
             return {"success": False, "error": "Insufficient valid feature records to train model."}

        X_array = np.array(X)
        y_array = np.array(y)
        
        # Check if we have both classes
        if len(np.unique(y_array)) < 2:
             return {"success": False, "error": "Need both successful and failed deployments to train."}
        
        X_train, X_test, y_train, y_test = train_test_split(X_array, y_array, test_size=0.2, random_state=42)
        
        clf = RandomForestClassifier(n_estimators=100, max_depth=10, random_state=42)
        clf.fit(X_train, y_train)
        
        accuracy = clf.score(X_test, y_test)
        
        # Save model
        joblib.dump(clf, self.model_path)
        self.model = clf
        
        return {"success": True, "accuracy": accuracy, "samples": len(X)}
    
    def _identify_risk_factors(
        self,
        features: Dict[str, Any],
        failure_prob: float
    ) -> List[Dict[str, Any]]:
        """Identify key risk factors contributing to failure probability"""
        risk_factors = []
        
        if features["severity_score"] > 0.7:
            risk_factors.append({
                "factor": "High Severity Patch",
                "impact": "high",
                "description": "Critical/High severity patches have higher failure rates"
            })
        
        if features["historical_success_rate"] < 0.7:
            risk_factors.append({
                "factor": "Low Historical Success Rate",
                "impact": "high",
                "description": f"Only {features['historical_success_rate']*100:.0f}% success rate historically"
            })
        
        if features["requires_reboot"]:
            risk_factors.append({
                "factor": "Reboot Required",
                "impact": "medium",
                "description": "Patches requiring reboot have higher risk of issues"
            })
        
        if features["uptime_hours"] > 1000:
            risk_factors.append({
                "factor": "High System Uptime",
                "impact": "medium",
                "description": "Long uptime may indicate dependency conflicts"
            })
        
        if features["patch_size_mb"] > 100:
            risk_factors.append({
                "factor": "Large Patch Size",
                "impact": "low",
                "description": "Large patches may encounter network/storage issues"
            })
        
        return risk_factors
    
    def _generate_recommendations(
        self,
        risk_factors: List[Dict[str, Any]],
        failure_prob: float
    ) -> List[str]:
        """Generate actionable recommendations based on risk"""
        recommendations = []
        
        if failure_prob > 0.7:
            recommendations.append("Deploy to test environment first")
            recommendations.append("Schedule deployment during maintenance window")
            recommendations.append("Ensure backup/rollback plan is ready")
        elif failure_prob > 0.4:
            recommendations.append("Monitor deployment closely")
            recommendations.append("Have rollback plan prepared")
        else:
            recommendations.append("Proceed with standard deployment")
        
        for factor in risk_factors:
            if "uptime" in factor["factor"].lower():
                recommendations.append("Consider rebooting asset before deployment")
            if "historical" in factor["factor"].lower():
                recommendations.append("Review previous failure logs for this patch/asset combination")
        
        return recommendations
    
    def _get_risk_level(self, failure_prob: float) -> str:
        """Convert probability to risk level"""
        if failure_prob > 0.7:
            return "high"
        elif failure_prob > 0.4:
            return "medium"
        else:
            return "low"
    
    async def detect_anomalies(
        self,
        tenant_id: Optional[str] = None,
        lookback_days: int = 7
    ) -> Dict[str, Any]:
        """
        Detect anomalies in patch deployment patterns
        
        Detects:
        - Unusual failure rates
        - Unexpected deployment volumes
        - Asset behavior changes
        """
        start_date = datetime.now(timezone.utc) - timedelta(days=lookback_days)
        
        query = {
            "created_at": {"$gte": start_date.isoformat()}
        }
        if tenant_id:
            query["tenant_id"] = tenant_id
        
        deployments = await self.db.patch_deployment_jobs.find(
            query,
            {"_id": 0}
        ).to_list(length=None)
        
        # Calculate baselines
        total = len(deployments)
        failed = len([d for d in deployments if d.get("status") == "failed"])
        baseline_failure_rate = failed / total if total > 0 else 0
        
        # Detect anomalies
        anomalies = []
        
        # Check recent 24h failure rate
        recent_24h = datetime.now(timezone.utc) - timedelta(hours=24)
        recent_deployments = [d for d in deployments if datetime.fromisoformat(d.get("created_at", "")) > recent_24h]
        recent_failed = len([d for d in recent_deployments if d.get("status") == "failed"])
        recent_failure_rate = recent_failed / len(recent_deployments) if recent_deployments else 0
        
        if recent_failure_rate > baseline_failure_rate * 2:
            anomalies.append({
                "type": "high_failure_rate",
                "severity": "high",
                "description": f"Recent failure rate ({recent_failure_rate*100:.1f}%) is 2x baseline ({baseline_failure_rate*100:.1f}%)",
                "recommendation": "Investigate recent failures for common patterns"
            })
        
        # Check deployment volume
        avg_daily_deployments = total / lookback_days
        today_deployments = len([d for d in recent_deployments])
        
        if today_deployments > avg_daily_deployments * 3:
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
        patch_id: str,
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

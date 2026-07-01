"""MLPredictionMixin: ML feature extraction, training, and prediction for MLPredictionService."""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

try:
    import numpy as np
    from sklearn.ensemble import RandomForestClassifier, IsolationForest
    from sklearn.model_selection import train_test_split
    import joblib
    ML_AVAILABLE = True
except ImportError:
    ML_AVAILABLE = False


class MLPredictionMixin:
    """Mixin providing ML feature extraction, model training, and prediction."""

    def _extract_features(
        self,
        patch: Dict[str, Any],
        asset: Dict[str, Any],
        historical: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        severity_score = {"Critical": 1.0, "High": 0.75, "Medium": 0.5, "Low": 0.25}.get(
            patch.get("severity"), 0.5
        )
        cvss = patch.get("cvss_score", 0) / 10.0

        os_age = 1
        try:
            if asset.get("createdAt"):
                created_at = datetime.fromisoformat(asset["createdAt"].replace("Z", "+00:00"))
                os_age = max(1, (datetime.now(timezone.utc) - created_at).days)
        except (ValueError, TypeError):
            pass

        uptime_hours = asset.get("uptime_hours", 72)
        total_deployments = len(historical)
        failed_deployments = len([d for d in historical if d.get("status") == "failed"])
        success_rate = (
            (total_deployments - failed_deployments) / total_deployments
            if total_deployments > 0 else 0.5
        )

        return {
            "severity_score": severity_score,
            "cvss_score": cvss,
            "os_age": os_age,
            "uptime_hours": uptime_hours,
            "historical_success_rate": success_rate,
            "total_deployments": total_deployments,
            "patch_size_mb": patch.get("size_mb", 10),
            "requires_reboot": 1 if patch.get("requiresReboot") else 0,
        }

    def _ml_predict(self, features: Dict[str, Any]) -> float:
        """Use trained Random Forest if available; fall back to weighted heuristics."""
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
                    features["requires_reboot"],
                ]])
                probabilities = self.model.predict_proba(feature_array)
                if probabilities.shape[1] == 2:
                    return float(probabilities[0][1])
                return float(probabilities[0][0])
            except Exception as e:
                logger.warning("[MLService] Model prediction failed, falling back to heuristic: %s", e)

        failure_score = 0.0
        failure_score += features["severity_score"] * 0.15
        failure_score += features["cvss_score"] * 0.10
        failure_score += (1 - features["historical_success_rate"]) * 0.35
        failure_score += features["requires_reboot"] * 0.15
        failure_score += min(features["os_age"] / 1095, 1.0) * 0.10
        if features["patch_size_mb"] > 100:
            failure_score += 0.08
        if features["uptime_hours"] > 1000:
            failure_score += 0.07
        return min(failure_score, 1.0)

    async def ensure_model_trained(self):
        """Guarantee a usable model is in memory; bootstrap with synthetic data if needed."""
        if self.model is not None or not ML_AVAILABLE:
            return

        result = await self.train_model()
        if result.get("success"):
            return

        try:
            from sklearn.datasets import make_classification
            X, y = make_classification(
                n_samples=800, n_features=8, n_informative=6, n_redundant=1,
                weights=[0.8, 0.2], random_state=42,
            )
            X_train, X_test, y_train, _ = train_test_split(X, y, test_size=0.2, random_state=42)
            clf = RandomForestClassifier(n_estimators=100, max_depth=10, random_state=42)
            clf.fit(X_train, y_train)
            joblib.dump(clf, self.model_path)
            self.model = clf
        except Exception as exc:
            logger.warning("[MLService] Bootstrap training failed: %s", exc)

    async def train_model(self):
        """Fetch historical deployment data and train the Random Forest classifier."""
        if not ML_AVAILABLE:
            return {"success": False, "error": "scikit-learn is not installed."}

        deployments = await self.db.patch_deployment_jobs.find(
            {"status": {"$in": ["completed", "failed"]}}, {"_id": 0}
        ).to_list(length=10000)

        if len(deployments) < 50:
            return {"success": False, "error": "Insufficient data. Need at least 50 records."}

        X, y = [], []
        for dep in deployments:
            for patch_id in dep.get("patch_ids", []):
                for asset_id in dep.get("asset_ids", []):
                    patch = await self.db.patches.find_one({"id": patch_id}, {"_id": 0})
                    asset = await self.db.assets.find_one({"id": asset_id}, {"_id": 0})
                    if patch and asset:
                        features = self._extract_features(patch, asset, deployments)
                        X.append([
                            features["severity_score"], features["cvss_score"],
                            features["os_age"], features["uptime_hours"],
                            features["historical_success_rate"], features["total_deployments"],
                            features["patch_size_mb"], features["requires_reboot"],
                        ])
                        y.append(1 if dep["status"] == "failed" else 0)

        if len(X) < 10:
            return {"success": False, "error": "Insufficient valid feature records."}

        X_array, y_array = np.array(X), np.array(y)
        if len(np.unique(y_array)) < 2:
            return {"success": False, "error": "Need both successful and failed deployments."}

        X_train, X_test, y_train, y_test = train_test_split(X_array, y_array, test_size=0.2, random_state=42)
        clf = RandomForestClassifier(n_estimators=100, max_depth=10, random_state=42)
        clf.fit(X_train, y_train)
        accuracy = clf.score(X_test, y_test)
        joblib.dump(clf, self.model_path)
        self.model = clf
        return {"success": True, "accuracy": accuracy, "samples": len(X)}

    async def train_anomaly_model(self):
        """Train Isolation Forest for deployment anomaly detection."""
        if not ML_AVAILABLE:
            return {"success": False, "error": "scikit-learn is not installed."}

        deployments = await self.db.patch_deployment_jobs.find(
            {"status": {"$in": ["completed", "failed"]}}, {"_id": 0}
        ).to_list(length=10000)

        if len(deployments) < 20:
            return {"success": False, "error": "Insufficient data (need 20)."}

        from collections import defaultdict
        daily_stats = defaultdict(lambda: {"total": 0, "failed": 0})
        for dep in deployments:
            day = dep.get("created_at", "")[:10]
            if not day:
                continue
            daily_stats[day]["total"] += 1
            if dep.get("status") == "failed":
                daily_stats[day]["failed"] += 1

        X = [
            [s["total"], s["failed"] / s["total"] if s["total"] > 0 else 0]
            for s in daily_stats.values()
        ]
        if len(X) < 5:
            return {"success": False, "error": "Insufficient daily data."}

        X_array = np.array(X)
        iso = IsolationForest(contamination=0.1, random_state=42)
        iso.fit(X_array)
        joblib.dump(iso, self.anomaly_model_path)
        self.anomaly_model = iso
        return {"success": True, "samples": len(X_array)}

    def _identify_risk_factors(
        self,
        features: Dict[str, Any],
        _failure_prob: float,
    ) -> List[Dict[str, Any]]:
        risk_factors = []
        checks = [
            (features["severity_score"] > 0.7,
             "High Severity Patch", "high", "Critical/High severity patches have higher failure rates"),
            (features["historical_success_rate"] < 0.7,
             "Low Historical Success Rate", "high",
             f"Only {features['historical_success_rate']*100:.0f}% success rate historically"),
            (bool(features["requires_reboot"]),
             "Reboot Required", "medium", "Patches requiring reboot have higher risk"),
            (features["uptime_hours"] > 1000,
             "High System Uptime", "medium", "Long uptime may indicate dependency conflicts"),
            (features["patch_size_mb"] > 100,
             "Large Patch Size", "low", "Large patches may encounter network/storage issues"),
            (features["cvss_score"] >= 0.9,
             "Critical CVSS Score", "high",
             f"CVSS score {features['cvss_score']*10:.1f} indicates severe exploitability"),
            (features["os_age"] > 730,
             "Aged Asset", "medium",
             f"Asset is {features['os_age']} days old; legacy systems have higher patch failure rates"),
        ]
        for condition, factor, impact, description in checks:
            if condition:
                risk_factors.append({"factor": factor, "impact": impact, "description": description})
        return risk_factors

    def _generate_recommendations(
        self,
        risk_factors: List[Dict[str, Any]],
        failure_prob: float,
    ) -> List[str]:
        if failure_prob > 0.7:
            recs = [
                "Deploy to test environment first",
                "Schedule deployment during maintenance window",
                "Ensure backup/rollback plan is ready",
            ]
        elif failure_prob > 0.4:
            recs = ["Monitor deployment closely", "Have rollback plan prepared"]
        else:
            recs = ["Proceed with standard deployment"]

        for factor in risk_factors:
            if "uptime" in factor["factor"].lower():
                recs.append("Consider rebooting asset before deployment")
            if "historical" in factor["factor"].lower():
                recs.append("Review previous failure logs for this patch/asset combination")
        return recs

    def _get_risk_level(self, failure_prob: float) -> str:
        if failure_prob > 0.7:
            return "high"
        if failure_prob > 0.4:
            return "medium"
        return "low"

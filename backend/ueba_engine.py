import os
import asyncio
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Any, Optional
import uuid

# Machine Learning & Statstics imports
try:
    from sklearn.ensemble import IsolationForest
    from sklearn.preprocessing import StandardScaler
    import numpy as np
    ML_AVAILABLE = True
except ImportError:
    ML_AVAILABLE = False
    print("[WARN] scikit-learn or numpy not installed. UEBA Engine will use basic thresholding instead of IsolationForest.")

from database import get_database

class UEBAEngine:
    def __init__(self):
        self._db = None
        # Fallback basic thresholds if ML is missing
        self.thresholds = {
            "max_daily_bytes": 5 * 1024 * 1024 * 1024, # 5 GB
            "max_distinct_ips": 3,
            "max_failed_logins": 5
        }

    @property
    def db(self):
        if self._db is None:
            self._db = get_database()
        return self._db
        
    async def get_user_activity_vector(self, user_id: str, tenant_id: str, days_back: int = 7) -> Dict[str, float]:
        """
        Calculates a feature vector for a single user over the given timeframe.
        Features:
        - login_count
        - failed_login_count
        - distinct_ips
        - bytes_downloaded (from proxy/dlp logs if available)
        - alerts_triggered
        """
        threshold = datetime.now(timezone.utc) - timedelta(days=days_back)
        threshold_iso = threshold.isoformat()
        
        # In a real system, we'd aggregate from `audit_logs`, `itdr_alerts`, `network_logs`, etc.
        # For this prototype, we'll query the `audit_logs` and `itdr_alerts` collections.
        
        audit_logs = await self.db.audit_logs.find({
            "tenantId": tenant_id,
            "userId": user_id,
            "timestamp": {"$gte": threshold_iso}
        }).to_list(None)
        
        itdr_alerts = await self.db.itdr_alerts.find({
            "tenantId": tenant_id,
            "user_id": user_id,
            "timestamp": {"$gte": threshold_iso}
        }).to_list(None)
        
        # Calculate features
        login_count = sum(1 for log in audit_logs if log.get("action") == "user.login" and log.get("status") == "success")
        failed_login_count = sum(1 for log in audit_logs if log.get("action") == "user.login" and log.get("status") == "failure")
        
        distinct_ips = set()
        for log in audit_logs:
            if ip := log.get("details", {}).get("ipAddress"):
                distinct_ips.add(ip)
        
        # Simulate bytes downloaded (DLP or Network proxy data)
        # For the demo, we'll calculate a proxy based on access frequency if real data is missing
        bytes_downloaded = 0
        file_access_logs = [log for log in audit_logs if log.get("action") in ["file.download", "file.export"]]
        for log in file_access_logs:
            bytes_downloaded += log.get("details", {}).get("fileSize", 0)
            
        alerts_triggered = len(itdr_alerts)
        
        return {
            "login_count": float(login_count),
            "failed_login_count": float(failed_login_count),
            "distinct_ips": float(len(distinct_ips)),
            "bytes_downloaded": float(bytes_downloaded),
            "alerts_triggered": float(alerts_triggered)
        }

    async def train_isolation_forest(self, user_vectors: List[Dict[str, float]]) -> Optional[Any]:
        """Trains an Isolation Forest model on the provided user vectors."""
        if not ML_AVAILABLE or len(user_vectors) < 5:
            return None # Need more data for meaningful ML
            
        features = ["login_count", "failed_login_count", "distinct_ips", "bytes_downloaded", "alerts_triggered"]
        
        # Extract data matrix
        X = []
        for vec in user_vectors:
            row = [vec.get(f, 0.0) for f in features]
            X.append(row)
            
        X = np.array(X)
        
        # Scale features
        scaler = StandardScaler()
        X_scaled = scaler.fit_transform(X)
        
        # Train Isolation Forest
        model = IsolationForest(contamination=0.1, random_state=42) # Expect ~10% anomalies
        model.fit(X_scaled)
        
        return {"model": model, "scaler": scaler, "features": features}

    async def calculate_risk_score(self, tenant_id: str, user_id: str) -> Dict[str, Any]:
        """
        Calculates the current risk score (0-100) for a user.
        Combines deterministic rules with ML anomaly detection (if available).
        """
        vector = await self.get_user_activity_vector(user_id, tenant_id, days_back=1) # Last 24 hours
        
        score = 0
        reasons = []
        
        # 1. Deterministic Rule-Based Scoring
        if vector["failed_login_count"] > self.thresholds["max_failed_logins"]:
            score += 30
            reasons.append(f"High number of failed logins ({int(vector['failed_login_count'])})")
            
        if vector["distinct_ips"] > self.thresholds["max_distinct_ips"]:
            score += 25
            reasons.append(f"Accessed from too many distinct IPs ({int(vector['distinct_ips'])})")
            
        if vector["bytes_downloaded"] > self.thresholds["max_daily_bytes"]:
            score += 40
            reasons.append(f"Massive data download volume ({vector['bytes_downloaded'] / (1024**3):.2f} GB)")
            
        if vector["alerts_triggered"] > 0:
            score += min(50, vector["alerts_triggered"] * 20)
            reasons.append(f"Triggered {int(vector['alerts_triggered'])} ITDR alerts")

        # 2. ML Anomaly Detection (Isolation Forest against Peer Group)
        ml_score = 0
        if ML_AVAILABLE:
            # Get peer behavior (all users in tenant)
            # In a real app, you'd filter by department or Azure AD Group
            all_users = await self.db.users.find({"tenantId": tenant_id}).to_list(None)
            peer_user_ids = [u.get("id") for u in all_users if u.get("id") != user_id]
            
            if len(peer_user_ids) >= 5: # Need enough peers
                peer_vectors = []
                for pid in peer_user_ids:
                    # Calculate their 24h vector
                    p_vec = await self.get_user_activity_vector(pid, tenant_id, days_back=1)
                    peer_vectors.append(p_vec)
                    
                # Train model on peers
                ml_result = await self.train_isolation_forest(peer_vectors)
                
                if ml_result:
                    model = ml_result["model"]
                    scaler = ml_result["scaler"]
                    features = ml_result["features"]
                    
                    # Predict this user
                    X_user = np.array([[vector.get(f, 0.0) for f in features]])
                    X_user_scaled = scaler.transform(X_user)
                    
                    # prediction: 1 for inlier, -1 for outlier
                    # score_samples: anomalous observations have lower scores (usually negative)
                    prediction = model.predict(X_user_scaled)[0]
                    anomaly_score = model.score_samples(X_user_scaled)[0]
                    
                    if prediction == -1:
                        # Map anomaly_score (typically -0.5 to -1.0) to a 0-40 boost
                        ml_boost = min(40, max(10, abs(anomaly_score) * 40))
                        score += ml_boost
                        ml_score = ml_boost
                        reasons.append(f"Behavior deviates significantly from peer group baseline (ML Isolation Forest)")
                        
        # Normalize to 0-100
        final_score = min(100, max(0, int(score)))
        
        # 3. Store the calculation
        # Risk scores decay over time, this represents the *current* point-in-time calculation
        risk_record = {
            "id": f"risk_{uuid.uuid4().hex[:12]}",
            "tenantId": tenant_id,
            "userId": user_id,
            "score": final_score,
            "ruleScore": score - ml_score,
            "mlScore": ml_score,
            "reasons": reasons,
            "vector": vector,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
        # Upsert the user's current risk state
        await self.db.ueba_risk_scores.update_one(
            {"userId": user_id, "tenantId": tenant_id},
            {"$set": risk_record},
            upsert=True
        )
        
        # Also store historical tracking
        await self.db.ueba_risk_history.insert_one(risk_record)
        
        # 4. Generate Alert if > 80
        if final_score >= 80:
            await self._generate_ueba_alert(tenant_id, user_id, final_score, reasons)
            
        return risk_record

    async def _generate_ueba_alert(self, tenant_id: str, user_id: str, score: int, reasons: List[str]):
        """Generates a high-severity UEBA alert if the risk score crosses the threshold."""
        # Check if we recently alerted for this user to avoid spam
        recent_threshold = (datetime.now(timezone.utc) - timedelta(hours=4)).isoformat()
        recent_alert = await self.db.ueba_alerts.find_one({
            "tenantId": tenant_id,
            "user_id": user_id,
            "timestamp": {"$gte": recent_threshold}
        })
        
        if recent_alert:
            return # Already alerted recently
            
        user = await self.db.users.find_one({"id": user_id})
        
        alert_doc = {
            "id": f"ueba_alert_{uuid.uuid4().hex[:12]}",
            "tenantId": tenant_id,
            "user_id": user_id,
            "user_email": user.get("email") if user else "Unknown",
            "score": score,
            "reasons": reasons,
            "status": "New",
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
        await self.db.ueba_alerts.insert_one(alert_doc)
        print(f"[UEBA] Generated High-Risk Alert for user {user_id} (Score: {score})")

# Singleton instance
ueba_engine = UEBAEngine()

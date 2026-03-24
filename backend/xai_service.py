from typing import Dict, Any, List, Optional
import random

class XAIService:
    def __init__(self):
        # Simulated Feature Importance (Global)
        self.global_importance = [
            {"feature": "failed_logins_count", "importance": 0.35},
            {"feature": "ip_reputation_score", "importance": 0.25},
            {"feature": "access_time_hour", "importance": 0.15},
            {"feature": "device_trust_score", "importance": 0.10},
            {"feature": "resource_sensitivity", "importance": 0.08},
            {"feature": "location_distance_km", "importance": 0.07}
        ]
        
    def get_global_importance(self, model_id: str) -> List[Dict[str, Any]]:
        """Return global feature importance rankings"""
        # In real app, this would load the model/explainer and calculate
        return self.global_importance

    def explain_prediction(self, model_id: str, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Simulate Local SHAP values for a single prediction.
        Returns:
            - prediction: The model output (e.g., Risk Score)
            - base_value: The average model output
            - shap_values: Contribution of each feature to the difference
        """
        # 1. Calculate a simulated risk score based on input
        # Default average risk
        base_value = 0.20 
        
        # Calculate contributions
        contributions = []
        current_score = base_value
        
        # failed_logins_count
        failed_logins = input_data.get("failed_logins_count", 0)
        shap_logins = 0.0
        if failed_logins > 3:
            shap_logins = 0.40 # Huge increase
        elif failed_logins > 0:
            shap_logins = 0.10
        else:
            shap_logins = -0.05 # slight decrease
        contributions.append({"feature": "failed_logins_count", "value": failed_logins, "shap": shap_logins})
        current_score += shap_logins
        
        # ip_reputation
        ip_rep = input_data.get("ip_reputation_score", 100)
        shap_ip = 0.0
        if ip_rep < 50:
            shap_ip = 0.25
        elif ip_rep > 80:
            shap_ip = -0.10
        contributions.append({"feature": "ip_reputation_score", "value": ip_rep, "shap": shap_ip})
        current_score += shap_ip
        
        # access_time
        hour = input_data.get("access_time_hour", 12)
        shap_time = 0.0
        if hour < 6 or hour > 22: # weird hours
            shap_time = 0.15
        else:
            shap_time = -0.05
        contributions.append({"feature": "access_time_hour", "value": hour, "shap": shap_time})
        current_score += shap_time
        
        # Add some noise for other features
        other_shap = random.uniform(-0.05, 0.05)
        contributions.append({"feature": "other_factors", "value": "N/A", "shap": other_shap})
        current_score += other_shap
        
        # Clamp score
        final_prediction = max(0.0, min(1.0, current_score))
        
        return {
            "model_id": model_id,
            "prediction": round(final_prediction, 4),
            "base_value": base_value,
            "features": contributions,
            "risk_level": "HIGH" if final_prediction > 0.7 else "MEDIUM" if final_prediction > 0.4 else "LOW"
        }

# Global instance
xai_service = XAIService()

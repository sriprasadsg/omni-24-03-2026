"""
Predictive Health Capability
Uses statistical trend analysis to predict potential agent or host issues.
"""
from .base import BaseCapability
import psutil
from typing import Dict, Any, List
from datetime import datetime, timedelta
from collections import deque


def _linear_forecast(series: list, steps: int) -> List[float]:
    """
    Least-squares linear regression extrapolation.
    Returns `steps` predicted values beyond the end of `series`.
    Falls back to the last value when there are fewer than 2 data points.
    """
    n = len(series)
    if n < 2:
        return [series[-1] if series else 0.0] * steps
    xs = list(range(n))
    mean_x = sum(xs) / n
    mean_y = sum(series) / n
    denom = sum((x - mean_x) ** 2 for x in xs)
    slope = sum((xs[i] - mean_x) * (series[i] - mean_y) for i in range(n)) / denom if denom else 0.0
    intercept = mean_y - slope * mean_x
    return [max(0.0, min(100.0, round(intercept + slope * (n + i), 1))) for i in range(steps)]

class PredictiveHealthCapability(BaseCapability):
    
    def __init__(self, config=None):
        super().__init__(config)
        self.metrics_history = {
            'cpu': deque(maxlen=100),
            'memory': deque(maxlen=100),
            'disk': deque(maxlen=100)
        }
    
    @property
    def capability_id(self) -> str:
        return "predictive_health"
    
    @property
    def capability_name(self) -> str:
        return "Predictive Health"
    
    def collect(self) -> Dict[str, Any]:
        """Predict potential health issues using historical trends"""
        # Collect current metrics
        cpu_percent = psutil.cpu_percent(interval=1)
        memory_percent = psutil.virtual_memory().percent
        disk_percent = psutil.disk_usage('/').percent if hasattr(psutil, 'disk_usage') else 0
        
        # Store in history
        self.metrics_history['cpu'].append(cpu_percent)
        self.metrics_history['memory'].append(memory_percent)
        self.metrics_history['disk'].append(disk_percent)
        
        predictions = []
        
        # Predict disk space exhaustion
        if len(self.metrics_history['disk']) > 10:
            disk_prediction = self._predict_resource_exhaustion(
                list(self.metrics_history['disk']), 
                threshold=95,
                resource_name="Disk Space"
            )
            if disk_prediction:
                predictions.append(disk_prediction)
        
        # Predict memory exhaustion
        if len(self.metrics_history['memory']) > 10:
            memory_prediction = self._predict_resource_exhaustion(
                list(self.metrics_history['memory']),
                threshold=90,
                resource_name="Memory"
            )
            if memory_prediction:
                predictions.append(memory_prediction)
        
        # Detect anomalies
        anomalies = self._detect_anomalies()
        
        # Generate short-term forecast using linear regression on collected history
        STEPS = 12  # next 2 hours at 10-min intervals
        now = datetime.now()
        current_health = self._calculate_health_score()

        cpu_hist = list(self.metrics_history['cpu']) or [cpu_percent]
        mem_hist = list(self.metrics_history['memory']) or [memory_percent]
        cpu_fc = _linear_forecast(cpu_hist, STEPS)
        mem_fc = _linear_forecast(mem_hist, STEPS)
        # Health score forecast: recompute from predicted cpu/mem (disk assumed stable)
        disk_val = list(self.metrics_history['disk'])[-1] if self.metrics_history['disk'] else disk_percent
        health_fc = [
            round(max(0, min(100, 100 - (cpu_fc[i] * 0.3 + mem_fc[i] * 0.4 + disk_val * 0.3))), 1)
            for i in range(STEPS)
        ]

        forecast = []
        for i in range(STEPS):
            future_time = now + timedelta(minutes=10 * i)
            forecast.append({
                "timestamp": future_time.strftime("%H:%M"),
                "cpu_prediction": cpu_fc[i],
                "memory_prediction": mem_fc[i],
                "health_score": health_fc[i],
            })

        warnings = [p["resource"] + " exhaustion predicted" for p in predictions]
        for a in anomalies:
            warnings.append(f"Anomaly detected: {a['type']} ({a['current']}%)")

        return {
            "current_score": current_health,
            "predictions": forecast,
            "warnings": warnings,
            "anomalies": anomalies,
            "health_score": current_health, # Keep for backward compatibility if any
            "metrics_samples": len(self.metrics_history['cpu']),
            "remediation": self._recommend_remediation(predictions, anomalies)
        }

    def _recommend_remediation(self, predictions: List[Dict], anomalies: List[Dict]) -> Dict[str, Any]:
        """Recommend remediation actions based on health state.

        Thresholds are read from config so they can be tuned per agent/workload:
          mem_restart_threshold  (default 95) — sustained % that triggers restart
          cpu_throttle_threshold (default 95) — sustained % that triggers throttle
          sustained_samples      (default 5)  — how many consecutive samples must exceed threshold
        """
        mem_threshold = float(self.config.get("mem_restart_threshold", 95))
        cpu_threshold = float(self.config.get("cpu_throttle_threshold", 95))
        sustained = int(self.config.get("sustained_samples", 5))

        # 1. Critical Memory Exhaustion → Restart
        if len(self.metrics_history["memory"]) > sustained:
            recent_mem = list(self.metrics_history["memory"])[-sustained:]
            if all(m > mem_threshold for m in recent_mem):
                return {
                    "action": "restart_agent",
                    "reason": f"Critical Memory Usage: sustained >{mem_threshold:.0f}% for {sustained} samples",
                    "timestamp": datetime.now().isoformat(),
                }

        # 2. Critical CPU Usage → Throttle
        if len(self.metrics_history["cpu"]) > sustained:
            recent_cpu = list(self.metrics_history["cpu"])[-sustained:]
            if all(c > cpu_threshold for c in recent_cpu):
                return {
                    "action": "throttle",
                    "reason": f"Critical CPU Usage: sustained >{cpu_threshold:.0f}% for {sustained} samples",
                    "timestamp": datetime.now().isoformat(),
                }

        return None
    
    def _predict_resource_exhaustion(self, history: List[float], threshold: float, resource_name: str) -> Dict[str, Any]:
        """Simple linear prediction for resource exhaustion"""
        if len(history) < 5:
            return None
        
        # Calculate growth rate
        recent = history[-5:]
        if recent[-1] > threshold * 0.8:  # 80% of threshold
            avg_growth = (recent[-1] - recent[0]) / len(recent)
            
            if avg_growth > 0.5:  # Growth rate > 0.5% per sample
                time_to_exhaustion = (threshold - recent[-1]) / avg_growth if avg_growth > 0 else float('inf')
                
                return {
                    "resource": resource_name,
                    "current_usage": round(recent[-1], 2),
                    "threshold": threshold,
                    "growth_rate": round(avg_growth, 2),
                    "predicted_exhaustion_samples": int(time_to_exhaustion),
                    "severity": "High" if time_to_exhaustion < 20 else "Medium"
                }
        
        return None
    
    def _detect_anomalies(self) -> List[Dict[str, Any]]:
        """Detect unusual spikes or patterns"""
        anomalies = []
        
        # CPU spike detection
        if len(self.metrics_history['cpu']) > 5:
            cpu_list = list(self.metrics_history['cpu'])
            avg_cpu = sum(cpu_list) / len(cpu_list)
            recent_cpu = cpu_list[-1]
            
            if recent_cpu > avg_cpu + 30:  # 30% above average
                anomalies.append({
                    "type": "CPU Spike",
                    "current": round(recent_cpu, 2),
                    "average": round(avg_cpu, 2),
                    "deviation": round(recent_cpu - avg_cpu, 2)
                })
        
        # Memory spike detection
        if len(self.metrics_history['memory']) > 5:
            mem_list = list(self.metrics_history['memory'])
            avg_mem = sum(mem_list) / len(mem_list)
            recent_mem = mem_list[-1]
            
            if recent_mem > avg_mem + 20:  # 20% above average
                anomalies.append({
                    "type": "Memory Spike",
                    "current": round(recent_mem, 2),
                    "average": round(avg_mem, 2),
                    "deviation": round(recent_mem - avg_mem, 2)
                })
        
        return anomalies
    
    def _calculate_health_score(self) -> float:
        """Calculate overall health score (0-100)"""
        if not self.metrics_history['cpu']:
            return 100.0
        
        cpu = list(self.metrics_history['cpu'])[-1] if self.metrics_history['cpu'] else 0
        memory = list(self.metrics_history['memory'])[-1] if self.metrics_history['memory'] else 0
        disk = list(self.metrics_history['disk'])[-1] if self.metrics_history['disk'] else 0
        
        # Simple scoring: 100 - weighted average of resource usage
        score = 100 - (cpu * 0.3 + memory * 0.4 + disk * 0.3)
        return max(0, min(100, round(score, 2)))

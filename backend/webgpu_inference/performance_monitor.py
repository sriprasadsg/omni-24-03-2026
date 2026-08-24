"""WebGPU Performance Monitor — tracks inference metrics and GPU utilization."""

import logging
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any

logger = logging.getLogger(__name__)


@dataclass
class InferenceMetrics:
    """Metrics for a single inference call."""
    model_id: str
    latency_ms: float
    input_size_bytes: int
    output_size_bytes: int
    timestamp: float = field(default_factory=time.time)
    success: bool = True
    error: str = ""


@dataclass
class GPUMetrics:
    """GPU device metrics snapshot."""
    timestamp: float = field(default_factory=time.time)
    memory_used_mb: float = 0.0
    memory_total_mb: float = 0.0
    compute_utilization: float = 0.0  # 0-1
    temperature_c: float = 0.0
    power_w: float = 0.0


class PerformanceMonitor:
    """Monitors WebGPU inference performance and GPU health."""

    def __init__(self, max_history: int = 1000):
        self.max_history = max_history
        self.inference_history: deque = deque(maxlen=max_history)
        self.gpu_history: deque = deque(maxlen=max_history)
        self.model_stats: Dict[str, Dict[str, float]] = defaultdict(lambda: {
            "count": 0,
            "total_latency": 0.0,
            "min_latency": float("inf"),
            "max_latency": 0.0,
            "total_input_bytes": 0,
            "total_output_bytes": 0,
            "errors": 0,
        })
        self.start_time = time.time()

    def record_inference(self, metrics: InferenceMetrics) -> None:
        """Record inference call metrics."""
        self.inference_history.append(metrics)

        stats = self.model_stats[metrics.model_id]
        stats["count"] += 1
        stats["total_latency"] += metrics.latency_ms
        stats["min_latency"] = min(stats["min_latency"], metrics.latency_ms)
        stats["max_latency"] = max(stats["max_latency"], metrics.latency_ms)
        stats["total_input_bytes"] += metrics.input_size_bytes
        stats["total_output_bytes"] += metrics.output_size_bytes
        if not metrics.success:
            stats["errors"] += 1

    def record_gpu_metrics(self, metrics: GPUMetrics) -> None:
        """Record GPU device metrics."""
        self.gpu_history.append(metrics)

    def get_model_stats(self, model_id: str = "") -> Dict[str, Any]:
        """Get aggregated stats for model(s)."""
        if model_id:
            stats = self.model_stats.get(model_id, {})
            if not stats:
                return {}
            count = stats["count"]
            return {
                "model_id": model_id,
                "total_calls": count,
                "avg_latency_ms": stats["total_latency"] / count if count else 0,
                "min_latency_ms": stats["min_latency"] if count else 0,
                "max_latency_ms": stats["max_latency"] if count else 0,
                "total_throughput_mb": (stats["total_input_bytes"] + stats["total_output_bytes"]) / 1e6,
                "error_rate": stats["errors"] / count if count else 0,
            }
        return {
            m: self.get_model_stats(m)
            for m in self.model_stats
        }

    def get_recent_inferences(self, model_id: str = "", limit: int = 100) -> List[Dict[str, Any]]:
        """Get recent raw inference call records, most recent first."""
        result = []
        for m in reversed(self.inference_history):
            if model_id and m.model_id != model_id:
                continue
            result.append({
                "model_id": m.model_id,
                "latency_ms": m.latency_ms,
                "input_size_bytes": m.input_size_bytes,
                "output_size_bytes": m.output_size_bytes,
                "timestamp": m.timestamp,
                "success": m.success,
                "error": m.error,
            })
            if len(result) >= limit:
                break
        return result

    def get_recent_latencies(self, model_id: str = "", limit: int = 100) -> List[float]:
        """Get recent latency samples for charting."""
        latencies = []
        for m in reversed(self.inference_history):
            if model_id and m.model_id != model_id:
                continue
            if m.success:
                latencies.append(m.latency_ms)
            if len(latencies) >= limit:
                break
        return list(reversed(latencies))

    def get_gpu_usage(self, limit: int = 60) -> List[Dict[str, float]]:
        """Get recent GPU utilization samples."""
        result = []
        for m in list(self.gpu_history)[-limit:]:
            result.append({
                "timestamp": m.timestamp,
                "memory_used_mb": m.memory_used_mb,
                "memory_total_mb": m.memory_total_mb,
                "compute_utilization": m.compute_utilization,
                "temperature_c": m.temperature_c,
                "power_w": m.power_w,
            })
        return result

    def get_summary(self) -> Dict[str, Any]:
        """Get overall performance summary."""
        total_calls = sum(s["count"] for s in self.model_stats.values())
        total_errors = sum(s["errors"] for s in self.model_stats.values())
        total_latency = sum(s["total_latency"] for s in self.model_stats.values())

        return {
            "uptime_seconds": time.time() - self.start_time,
            "total_inferences": total_calls,
            "total_errors": total_errors,
            "error_rate": total_errors / total_calls if total_calls else 0,
            "avg_latency_ms": total_latency / total_calls if total_calls else 0,
            "models_tracked": len(self.model_stats),
            "inference_history_size": len(self.inference_history),
        }

    def clear(self) -> None:
        """Clear all metrics."""
        self.inference_history.clear()
        self.gpu_history.clear()
        self.model_stats.clear()
        self.start_time = time.time()


# Singleton monitor
performance_monitor = PerformanceMonitor()
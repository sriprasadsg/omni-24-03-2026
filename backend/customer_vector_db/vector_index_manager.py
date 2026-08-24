"""Vector Index Manager — advanced HNSW indexing with auto-tuning.

Manages index parameters, monitors performance, and auto-tunes
HNSW settings based on query patterns and data distribution.
"""

import logging
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any

logger = logging.getLogger(__name__)


@dataclass
class IndexConfig:
    """HNSW index configuration."""
    space: str = "cosine"  # cosine | l2 | ip
    m: int = 16  # max connections per node
    ef_construction: int = 200
    ef_search: int = 50
    max_elements: int = 100000


@dataclass
class IndexStats:
    """Index performance statistics."""
    collection_name: str
    vector_count: int
    index_size_mb: float
    avg_query_latency_ms: float
    recall_at_k: Dict[int, float]
    last_optimized: float = field(default_factory=time.time)
    tuning_history: List[Dict[str, Any]] = field(default_factory=list)


class VectorIndexManager:
    """Advanced index management with auto-tuning."""

    # Recommended settings by data size
    SIZE_TUNING = {
        "small": {"m": 16, "ef_construction": 100, "ef_search": 50},      # < 10k
        "medium": {"m": 24, "ef_construction": 200, "ef_search": 100},    # 10k - 100k
        "large": {"m": 32, "ef_construction": 400, "ef_search": 200},     # 100k - 1M
        "xlarge": {"m": 48, "ef_construction": 800, "ef_search": 400},    # > 1M
    }

    def __init__(self):
        self.index_configs: Dict[str, IndexConfig] = {}
        self.index_stats: Dict[str, IndexStats] = {}

    def get_optimal_config(self, vector_count: int) -> IndexConfig:
        """Get optimal HNSW config for data size."""
        if vector_count < 10000:
            tier = "small"
        elif vector_count < 100000:
            tier = "medium"
        elif vector_count < 1000000:
            tier = "large"
        else:
            tier = "xlarge"

        params = self.SIZE_TUNING[tier]
        return IndexConfig(
            m=params["m"],
            ef_construction=params["ef_construction"],
            ef_search=params["ef_search"],
            max_elements=max(vector_count * 2, 10000),
        )

    def set_config(self, collection_name: str, config: IndexConfig) -> None:
        """Set index config for collection."""
        self.index_configs[collection_name] = config
        logger.info("Index config set for %s: m=%d, ef_construction=%d",
                    collection_name, config.m, config.ef_construction)

    def get_config(self, collection_name: str) -> Optional[IndexConfig]:
        """Get index config for collection."""
        return self.index_configs.get(collection_name)

    def auto_tune(self, collection_name: str, vector_count: int) -> IndexConfig:
        """Auto-tune index based on vector count."""
        config = self.get_optimal_config(vector_count)
        self.set_config(collection_name, config)
        return config

    def record_query_performance(
        self,
        collection_name: str,
        latency_ms: float,
        k: int,
        recall: float,
    ) -> None:
        """Record query performance for adaptive tuning."""
        stats = self.index_stats.get(collection_name)
        if not stats:
            stats = IndexStats(
                collection_name=collection_name,
                vector_count=0,
                index_size_mb=0.0,
                avg_query_latency_ms=latency_ms,
                recall_at_k={k: recall},
            )
            self.index_stats[collection_name] = stats
        else:
            # Exponential moving average
            alpha = 0.1
            stats.avg_query_latency_ms = (
                alpha * latency_ms + (1 - alpha) * stats.avg_query_latency_ms
            )
            stats.recall_at_k[k] = recall

    def suggest_tuning(self, collection_name: str) -> Dict[str, Any]:
        """Suggest index tuning based on performance."""
        stats = self.index_stats.get(collection_name)
        config = self.index_configs.get(collection_name)

        if not stats or not config:
            return {"suggestion": "insufficient_data"}

        suggestions = []

        # Check if recall is too low
        for k, recall in stats.recall_at_k.items():
            if recall < 0.9:
                suggestions.append({
                    "parameter": "ef_search",
                    "action": "increase",
                    "reason": f"recall@{k}={recall:.2f} < 0.9",
                    "suggested_value": min(config.ef_search * 2, 500),
                })

        # Check if latency is too high
        if stats.avg_query_latency_ms > 100:
            suggestions.append({
                "parameter": "ef_search",
                "action": "decrease",
                "reason": f"avg_latency={stats.avg_query_latency_ms:.1f}ms > 100ms",
                "suggested_value": max(config.ef_search // 2, 10),
            })

        return {
            "collection": collection_name,
            "current_config": {
                "m": config.m,
                "ef_construction": config.ef_construction,
                "ef_search": config.ef_search,
            },
            "stats": {
                "avg_latency_ms": stats.avg_query_latency_ms,
                "recall": stats.recall_at_k,
            },
            "suggestions": suggestions,
        }

    def get_stats(self, collection_name: str = "") -> Dict[str, Any]:
        """Get index statistics."""
        if collection_name:
            stats = self.index_stats.get(collection_name)
            config = self.index_configs.get(collection_name)
            if not stats:
                return {}
            recall_values = list(stats.recall_at_k.values())
            return {
                "collection_name": collection_name,
                "vector_count": stats.vector_count,
                "hnsw_config": {
                    "m": config.m if config else 0,
                    "ef_construction": config.ef_construction if config else 0,
                    "ef_search": config.ef_search if config else 0,
                    "max_elements": config.max_elements if config else 0,
                },
                "avg_query_latency": stats.avg_query_latency_ms,
                "approx_recall": sum(recall_values) / len(recall_values) if recall_values else 0.0,
                "last_tuned": stats.last_optimized,
            }
        return {
            name: self.get_stats(name)
            for name in self.index_stats
        }


# Singleton
vector_index_manager = VectorIndexManager()
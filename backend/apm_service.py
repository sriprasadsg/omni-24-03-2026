"""
Application Performance Monitoring (APM) Service

Provides comprehensive performance monitoring with OpenTelemetry integration,
metrics collection, distributed tracing, and performance analytics.
"""

from typing import Dict, Any, List, Optional
from datetime import datetime, timezone, timedelta
from motor.motor_asyncio import AsyncIOMotorDatabase
import time
from collections import defaultdict
import statistics


class APMService:
    """Application Performance Monitoring Service"""
    
    def __init__(self, db: AsyncIOMotorDatabase):
        self.db = db
        
        # In-memory metrics cache (for real-time aggregation)
        self.metrics_cache = {
            "requests": defaultdict(list),  # endpoint -> [durations]
            "errors": defaultdict(int),     # endpoint -> error_count
            "throughput": defaultdict(int),  # endpoint -> request_count
        }
        
        # Performance thresholds (ms)
        self.thresholds = {
            "p50": 100,   # 50th percentile
            "p95": 500,   # 95th percentile
            "p99": 1000,  # 99th percentile
        }
    
    async def record_request(
        self,
        endpoint: str,
        method: str,
        duration_ms: float,
        status_code: int,
        tenant_id: Optional[str] = None,
        user_id: Optional[str] = None,
        trace_id: Optional[str] = None
    ):
        """
        Record an API request for performance monitoring
        
        Args:
            endpoint: API endpoint path
            method: HTTP method
            duration_ms: Request duration in milliseconds
            status_code: HTTP status code
            tenant_id: Tenant ID (optional)
            user_id: User ID (optional)
            trace_id: Distributed trace ID (optional)
        """
        # Update in-memory cache
        self.metrics_cache["requests"][endpoint].append(duration_ms)
        self.metrics_cache["throughput"][endpoint] += 1
        
        if status_code >= 400:
            self.metrics_cache["errors"][endpoint] += 1
        
        # Store in database for historical analysis
        metric = {
            "type": "http_request",
            "endpoint": endpoint,
            "method": method,
            "duration_ms": duration_ms,
            "status_code": status_code,
            "tenant_id": tenant_id,
            "user_id": user_id,
            "trace_id": trace_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "is_error": status_code >= 400,
            "is_slow": duration_ms > self.thresholds["p95"]
        }
        
        await self.db.apm_metrics.insert_one(metric)
    
    async def record_database_query(
        self,
        query_type: str,
        collection: str,
        duration_ms: float,
        tenant_id: Optional[str] = None
    ):
        """Record database query performance"""
        metric = {
            "type": "database_query",
            "query_type": query_type,
            "collection": collection,
            "duration_ms": duration_ms,
            "tenant_id": tenant_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "is_slow": duration_ms > 100  # Slow query threshold
        }
        
        await self.db.apm_metrics.insert_one(metric)
    
    async def record_external_api_call(
        self,
        service: str,
        endpoint: str,
        duration_ms: float,
        success: bool,
        tenant_id: Optional[str] = None
    ):
        """Record external API call performance"""
        metric = {
            "type": "external_api",
            "service": service,
            "endpoint": endpoint,
            "duration_ms": duration_ms,
            "success": success,
            "tenant_id": tenant_id,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
        await self.db.apm_metrics.insert_one(metric)
    
    async def record_background_job(
        self,
        job_type: str,
        duration_ms: float,
        success: bool,
        tenant_id: Optional[str] = None
    ):
        """Record background job performance"""
        metric = {
            "type": "background_job",
            "job_type": job_type,
            "duration_ms": duration_ms,
            "success": success,
            "tenant_id": tenant_id,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
        await self.db.apm_metrics.insert_one(metric)
    
    async def get_endpoint_metrics(
        self,
        time_window_minutes: int = 60
    ) -> List[Dict[str, Any]]:
        """
        Get aggregated metrics for all endpoints
        
        Returns latency percentiles, error rates, throughput
        """
        threshold = datetime.now(timezone.utc) - timedelta(minutes=time_window_minutes)
        
        # Aggregate by endpoint
        pipeline = [
            {
                "$match": {
                    "type": "http_request",
                    "timestamp": {"$gte": threshold.isoformat()}
                }
            },
            {
                "$group": {
                    "_id": "$endpoint",
                    "durations": {"$push": "$duration_ms"},
                    "total_requests": {"$sum": 1},
                    "error_count": {
                        "$sum": {"$cond": ["$is_error", 1, 0]}
                    },
                    "slow_count": {
                        "$sum": {"$cond": ["$is_slow", 1, 0]}
                    }
                }
            }
        ]
        
        cursor = self.db.apm_metrics.aggregate(pipeline)
        
        metrics = []
        async for doc in cursor:
            durations = sorted(doc["durations"])
            total = doc["total_requests"]
            
            if durations:
                p50 = self._percentile(durations, 50)
                p95 = self._percentile(durations, 95)
                p99 = self._percentile(durations, 99)
                avg = statistics.mean(durations)
            else:
                p50 = p95 = p99 = avg = 0
            
            error_rate = (doc["error_count"] / total * 100) if total > 0 else 0
            
            metrics.append({
                "endpoint": doc["_id"],
                "total_requests": total,
                "error_count": doc["error_count"],
                "error_rate": round(error_rate, 2),
                "slow_count": doc["slow_count"],
                "latency": {
                    "avg": round(avg, 2),
                    "p50": round(p50, 2),
                    "p95": round(p95, 2),
                    "p99": round(p99, 2)
                },
                "throughput_per_min": round(total / time_window_minutes, 2),
                "health_status": self._calculate_health_status(error_rate, p95)
            })
        
        return sorted(metrics, key=lambda x: x["total_requests"], reverse=True)
    
    def _percentile(self, data: List[float], percentile: int) -> float:
        """Calculate percentile from sorted data"""
        if not data:
            return 0.0
        
        index = (len(data) - 1) * percentile / 100
        lower = int(index)
        upper = lower + 1
        
        if upper >= len(data):
            return data[lower]
        
        weight = index - lower
        return data[lower] * (1 - weight) + data[upper] * weight
    
    def _calculate_health_status(self, error_rate: float, p95_latency: float) -> str:
        """Calculate endpoint health status"""
        if error_rate > 5 or p95_latency > self.thresholds["p99"]:
            return "critical"
        elif error_rate > 1 or p95_latency > self.thresholds["p95"]:
            return "warning"
        else:
            return "healthy"
    
    async def get_slowest_endpoints(
        self,
        limit: int = 10,
        time_window_minutes: int = 60
    ) -> List[Dict[str, Any]]:
        """Get slowest endpoints by p95 latency"""
        metrics = await self.get_endpoint_metrics(time_window_minutes)
        return sorted(metrics, key=lambda x: x["latency"]["p95"], reverse=True)[:limit]
    
    async def get_error_prone_endpoints(
        self,
        limit: int = 10,
        time_window_minutes: int = 60
    ) -> List[Dict[str, Any]]:
        """Get endpoints with highest error rates"""
        metrics = await self.get_endpoint_metrics(time_window_minutes)
        return sorted(metrics, key=lambda x: x["error_rate"], reverse=True)[:limit]
    
    async def get_database_performance(
        self,
        time_window_minutes: int = 60
    ) -> Dict[str, Any]:
        """Get database query performance metrics"""
        threshold = datetime.now(timezone.utc) - timedelta(minutes=time_window_minutes)
        
        pipeline = [
            {
                "$match": {
                    "type": "database_query",
                    "timestamp": {"$gte": threshold.isoformat()}
                }
            },
            {
                "$group": {
                    "_id": "$collection",
                    "avg_duration": {"$avg": "$duration_ms"},
                    "max_duration": {"$max": "$duration_ms"},
                    "query_count": {"$sum": 1},
                    "slow_queries": {
                        "$sum": {"$cond": ["$is_slow", 1, 0]}
                    }
                }
            }
        ]
        
        cursor = self.db.apm_metrics.aggregate(pipeline)
        
        collections = []
        async for doc in cursor:
            collections.append({
                "collection": doc["_id"],
                "avg_duration_ms": round(doc["avg_duration"], 2),
                "max_duration_ms": round(doc["max_duration"], 2),
                "query_count": doc["query_count"],
                "slow_queries": doc["slow_queries"]
            })
        
        return {
            "collections": sorted(collections, key=lambda x: x["avg_duration_ms"], reverse=True),
            "total_queries": sum(c["query_count"] for c in collections),
            "total_slow_queries": sum(c["slow_queries"] for c in collections)
        }
    
    async def get_external_api_performance(
        self,
        time_window_minutes: int = 60
    ) -> List[Dict[str, Any]]:
        """Get external API call performance"""
        threshold = datetime.now(timezone.utc) - timedelta(minutes=time_window_minutes)
        
        pipeline = [
            {
                "$match": {
                    "type": "external_api",
                    "timestamp": {"$gte": threshold.isoformat()}
                }
            },
            {
                "$group": {
                    "_id": "$service",
                    "avg_duration": {"$avg": "$duration_ms"},
                    "max_duration": {"$max": "$duration_ms"},
                    "call_count": {"$sum": 1},
                    "success_count": {
                        "$sum": {"$cond": ["$success", 1, 0]}
                    }
                }
            }
        ]
        
        cursor = self.db.apm_metrics.aggregate(pipeline)
        
        services = []
        async for doc in cursor:
            success_rate = (doc["success_count"] / doc["call_count"] * 100) if doc["call_count"] > 0 else 0
            
            services.append({
                "service": doc["_id"],
                "avg_duration_ms": round(doc["avg_duration"], 2),
                "max_duration_ms": round(doc["max_duration"], 2),
                "call_count": doc["call_count"],
                "success_rate": round(success_rate, 2)
            })
        
        return sorted(services, key=lambda x: x["avg_duration_ms"], reverse=True)
    
    async def get_system_health(self) -> Dict[str, Any]:
        """Get overall system health metrics"""
        # Get recent metrics (last 5 minutes)
        metrics = await self.get_endpoint_metrics(time_window_minutes=5)
        
        if not metrics:
            return {
                "status": "unknown",
                "message": "No recent metrics available"
            }
        
        # Calculate overall health
        total_requests = sum(m["total_requests"] for m in metrics)
        total_errors = sum(m["error_count"] for m in metrics)
        overall_error_rate = (total_errors / total_requests * 100) if total_requests > 0 else 0
        
        avg_p95 = statistics.mean([m["latency"]["p95"] for m in metrics])
        
        # Determine status
        if overall_error_rate > 5 or avg_p95 > self.thresholds["p99"]:
            status = "critical"
        elif overall_error_rate > 1 or avg_p95 > self.thresholds["p95"]:
            status = "degraded"
        else:
            status = "healthy"
        
        return {
            "status": status,
            "total_requests": total_requests,
            "error_rate": round(overall_error_rate, 2),
            "avg_p95_latency": round(avg_p95, 2),
            "endpoints_monitored": len(metrics),
            "critical_endpoints": len([m for m in metrics if m["health_status"] == "critical"]),
            "warning_endpoints": len([m for m in metrics if m["health_status"] == "warning"])
        }
    
    async def get_performance_trend(
        self,
        endpoint: str,
        hours: int = 24
    ) -> List[Dict[str, Any]]:
        """Get performance trend for an endpoint over time"""
        threshold = datetime.now(timezone.utc) - timedelta(hours=hours)
        
        # Group by hour
        pipeline = [
            {
                "$match": {
                    "type": "http_request",
                    "endpoint": endpoint,
                    "timestamp": {"$gte": threshold.isoformat()}
                }
            },
            {
                "$group": {
                    "_id": {
                        "$dateToString": {
                            "format": "%Y-%m-%d %H:00",
                            "date": {"$toDate": "$timestamp"}
                        }
                    },
                    "avg_duration": {"$avg": "$duration_ms"},
                    "request_count": {"$sum": 1},
                    "error_count": {
                        "$sum": {"$cond": ["$is_error", 1, 0]}
                    }
                }
            },
            {"$sort": {"_id": 1}}
        ]
        
        cursor = self.db.apm_metrics.aggregate(pipeline)
        
        trend = []
        async for doc in cursor:
            trend.append({
                "timestamp": doc["_id"],
                "avg_duration_ms": round(doc["avg_duration"], 2),
                "request_count": doc["request_count"],
                "error_count": doc["error_count"]
            })
        
        return trend
    
    async def create_alert(
        self,
        alert_type: str,
        severity: str,
        message: str,
        details: Dict[str, Any]
    ):
        """Create a performance alert"""
        alert = {
            "type": alert_type,
            "severity": severity,
            "message": message,
            "details": details,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "acknowledged": False
        }
        
        await self.db.apm_alerts.insert_one(alert)
        
        return alert
    
    async def check_sla_violations(self) -> List[Dict[str, Any]]:
        """Check for SLA violations and create alerts"""
        metrics = await self.get_endpoint_metrics(time_window_minutes=5)
        violations = []
        
        for metric in metrics:
            # Check error rate SLA (< 1%)
            if metric["error_rate"] > 1:
                violation = await self.create_alert(
                    alert_type="sla_violation",
                    severity="high",
                    message=f"High error rate on {metric['endpoint']}",
                    details={
                        "endpoint": metric["endpoint"],
                        "error_rate": metric["error_rate"],
                        "threshold": 1.0
                    }
                )
                violations.append(violation)
            
            # Check latency SLA (p95 < 500ms)
            if metric["latency"]["p95"] > self.thresholds["p95"]:
                violation = await self.create_alert(
                    alert_type="sla_violation",
                    severity="medium",
                    message=f"High latency on {metric['endpoint']}",
                    details={
                        "endpoint": metric["endpoint"],
                        "p95_latency": metric["latency"]["p95"],
                        "threshold": self.thresholds["p95"]
                    }
                )
                violations.append(violation)
        
        return violations


# Singleton
_apm_service: Optional[APMService] = None

def get_apm_service(db: AsyncIOMotorDatabase) -> APMService:
    """Get or create APM service singleton"""
    global _apm_service
    if _apm_service is None:
        _apm_service = APMService(db)
    return _apm_service

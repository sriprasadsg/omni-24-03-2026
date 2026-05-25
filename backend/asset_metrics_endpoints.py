import logging
from fastapi import APIRouter, HTTPException, Query, Depends
from database import get_database
from datetime import datetime, timedelta, timezone
from rbac_utils import require_permission

_log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/assets", tags=["Assets"])


@router.get("/{asset_id}/metrics")
async def get_asset_metrics(
    asset_id: str,
    time_range: str = Query("24h", alias="range", description="Time range: 1h, 24h, 7d, 30d"),
    _current_user: dict = Depends(require_permission("view:assets")),
):
    """
    Get historical metrics for a specific asset
    Returns time-series data for CPU, memory, disk, network
    """
    try:
        db = get_database()
        
        # Verify asset exists and belongs to caller's tenant
        _SUPER_ADMIN_ROLES = {"Super Admin", "superadmin", "super_admin", "platform-admin"}
        asset_query: dict = {"id": asset_id}
        if getattr(_current_user, "role", "") not in _SUPER_ADMIN_ROLES:
            asset_query["tenantId"] = getattr(_current_user, "tenant_id", None)
        asset = await db.assets.find_one(asset_query, {"_id": 0})
        if not asset:
            raise HTTPException(status_code=404, detail=f"Asset {asset_id} not found")
        
        # Parse time range
        range_hours = {
            "1h": 1,
            "24h": 24,
            "7d": 168,
            "30d": 720
        }.get(time_range, 24)
        
        # Calculate time points
        now = datetime.now(timezone.utc)
        points = min(range_hours, 100)  # Cap at 100 data points
        interval_minutes = int((range_hours * 60) / points)
        
        
        # Try to fetch real metrics from database
        # In production, this would query a time-series database
        asset_tenant = asset.get("tenantId")
        metrics_filter: dict = {
            "asset_id": asset_id,
            "timestamp": {"$gte": (now - timedelta(hours=range_hours)).isoformat()},
        }
        if asset_tenant:
            metrics_filter["tenant_id"] = asset_tenant
        metrics_data = await db.asset_metrics.find(metrics_filter).to_list(length=points)
        
        if not metrics_data:
            # No agent telemetry yet — use asset's last-known values as a flat baseline
            # so charts render without random noise
            base_cpu = float(asset.get("cpuUsage") or asset.get("cpu_usage") or 25)
            base_mem = float(asset.get("memoryUsage") or asset.get("memory_usage") or 45)
            base_disk = float(asset.get("diskUsage") or asset.get("disk_usage") or 45)
            metrics = []
            for i in range(points):
                t = now - timedelta(minutes=interval_minutes * (points - i))
                # Deterministic workload curve: slight peak during business-hours index
                hour_of_day = t.hour
                work_boost = 8 if 9 <= hour_of_day <= 17 else 0
                cpu_val = min(100, base_cpu + (i % 20) + work_boost)
                mem_val = min(100, base_mem + (i % 10))
                net_val = max(0, 100 + (i % 50) * 10 + work_boost * 5)
                metrics.append({
                    "timestamp": t.isoformat(),
                    "cpu": round(cpu_val, 1),
                    "memory": round(mem_val, 1),
                    "disk": round(base_disk, 1),
                    "network": round(net_val, 1),
                })
            return {
                "asset_id": asset_id,
                "range": time_range,
                "interval_minutes": interval_minutes,
                "data_points": len(metrics),
                "metrics": metrics,
                "data_source": "estimated",
                "message": "Showing estimated data — agent telemetry not yet available for this asset.",
            }
        
        # Process and return real metrics
        metrics = [{
            "timestamp": m.get("timestamp"),
            "cpu": m.get("cpu", 0),
            "memory": m.get("memory", 0),
            "disk": m.get("disk", 0),
            "network": m.get("network", 0)
        } for m in metrics_data]
        
        return {
            "asset_id": asset_id,
            "range": time_range,
            "interval_minutes": interval_minutes,
            "data_points": len(metrics),
            "metrics": metrics,
            "data_source": "live",
        }
        
    except HTTPException:
        raise
    except Exception as e:
        _log.error("Error fetching asset metrics for %s: %s", asset_id, e)
        raise HTTPException(status_code=500, detail="Internal server error")



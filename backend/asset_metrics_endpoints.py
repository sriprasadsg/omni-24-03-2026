from fastapi import APIRouter, HTTPException, Query
from database import get_database
from datetime import datetime, timedelta, timezone
import random

router = APIRouter(prefix="/api/assets", tags=["Assets"])

@router.get("/{asset_id}/metrics")
async def get_asset_metrics(
    asset_id: str,
    time_range: str = Query("24h", alias="range", description="Time range: 1h, 24h, 7d, 30d")
):
    """
    Get historical metrics for a specific asset
    Returns time-series data for CPU, memory, disk, network
    """
    try:
        db = get_database()
        
        # Verify asset exists
        asset = await db.assets.find_one({"id": asset_id}, {"_id": 0})
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
        metrics_data = await db.asset_metrics.find({
            "asset_id": asset_id,
            "timestamp": {"$gte": (now - timedelta(hours=range_hours)).isoformat()}
        }).to_list(length=points)
        
        if not metrics_data:
            # Generate synthtetic data for demonstration
            # In a real scenario, this would just be empty, but we want to show charts
            metrics = []
            for i in range(points):
                # timestamp from past to present
                t = now - timedelta(minutes=interval_minutes * (points - i))
                
                # Create some realistic-looking variations
                base_cpu = 20 + (i % 20)  # simple pattern
                base_mem = 40 + (i % 10)
                
                metrics.append({
                    "timestamp": t.isoformat(),
                    "cpu": min(100, max(0, base_cpu + random.uniform(-5, 15))),
                    "memory": min(100, max(0, base_mem + random.uniform(-2, 5))),
                    "disk": random.uniform(45, 46), # stable disk
                    "network": max(0, random.uniform(50, 500) + (i % 50) * 10) # Kbps
                })
            
            return {
                "asset_id": asset_id,
                "range": time_range,
                "interval_minutes": interval_minutes,
                "data_points": len(metrics),
                "metrics": metrics,
                "message": "Showing synthetic data (Agent data not available)"
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
            "metrics": metrics
        }
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error fetching asset metrics: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/")
async def get_assets():
    """
    Get all assets
    """
    db = get_database()
    assets = await db.assets.find({}, {"_id": 0}).to_list(length=1000)
    return assets

@router.get("/{asset_id}")
async def get_asset(asset_id: str):
    """
    Get a specific asset by ID
    """
    db = get_database()
    asset = await db.assets.find_one({"id": asset_id}, {"_id": 0})
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    return asset

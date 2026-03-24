from fastapi import APIRouter, Depends, HTTPException, Body
from database import get_database
from datetime import datetime, timezone
from integration_service import get_integration_service
from ml_service import get_ml_service

router = APIRouter(tags=["Advanced Analytics & Integrations"])

# Phase 8: Integration Endpoints

@router.post("/api/integrations/siem/send")
async def send_to_siem(data: dict):
    """
    Send event to SIEM platform
    
    Body:
    {
        "event_type": "patch_deployed",
        "severity": "info",
        "details": {},
        "platform": "splunk|wazuh|qradar"
    }
    """
    try:
        db = get_database()
        integration_service = get_integration_service(db)
        
        result = await integration_service.send_to_siem(
            event_type=data.get("event_type"),
            severity=data.get("severity", "info"),
            details=data.get("details", {}),
            platform=data.get("platform", "splunk")
        )
        
        return result
    except Exception as e:
        print(f"Error sending to SIEM: {e}")
        return {"error": str(e)}, 500


@router.post("/api/integrations/cmdb/sync")
async def sync_to_cmdb(data: dict):
    """
    Sync assets to CMDB
    
    Body:
    {
        "platform": "servicenow|device42",
        "tenant_id": "optional"
    }
    """
    try:
        db = get_database()
        integration_service = get_integration_service(db)
        
        result = await integration_service.sync_assets_to_cmdb(
            platform=data.get("platform", "servicenow"),
            tenant_id=data.get("tenant_id")
        )
        
        return result
    except Exception as e:
        print(f"Error syncing to CMDB: {e}")
        return {"error": str(e)}, 500


@router.post("/api/integrations/ticketing/create")
async def create_ticket(data: dict):
    """
    Create ticket in ticketing system
    
    Body:
    {
        "title": "Ticket title",
        "description": "Description",
        "priority": "critical|high|medium|low",
        "platform": "jira|servicenow",
        "metadata": {}
    }
    """
    try:
        db = get_database()
        integration_service = get_integration_service(db)
        
        result = await integration_service.create_ticket(
            title=data.get("title"),
            description=data.get("description"),
            priority=data.get("priority", "medium"),
            platform=data.get("platform", "jira"),
            metadata=data.get("metadata")
        )
        
        return result
    except Exception as e:
        print(f"Error creating ticket: {e}")
        return {"error": str(e)}, 500


@router.post("/api/integrations/config")
async def configure_integration(data: dict):
    """
    Configure external integration
    
    Body:
    {
        "type": "siem|cmdb|ticketing|edr",
        "platform": "splunk|servicenow|jira|...",
        "enabled": true,
        "config": {
            "endpoint": "https://...",
            "token": "...",
            "instance_url": "...",
            "auth_token": "..."
        }
    }
    """
    try:
        db = get_database()
        
        integration_config = {
            "type": data.get("type"),
            "platform": data.get("platform"),
            "enabled": data.get("enabled", True),
            **data.get("config", {}),
            "updated_at": datetime.now(timezone.utc).isoformat()
        }
        
        await db.integration_configs.update_one(
            {"type": data.get("type"), "platform": data.get("platform")},
            {"$set": integration_config},
            upsert=True
        )
        
        return {
            "success": True,
            "message": f"{data.get('type')} integration for {data.get('platform')} configured"
        }
    except Exception as e:
        print(f"Error configuring integration: {e}")
        return {"error": str(e)}, 500


# Phase 9: ML/AI Endpoints

@router.post("/api/ml/predict-failure")
async def predict_patch_failure(data: dict):
    """
    Predict patch deployment failure probability
    
    Body:
    {
        "patch_id": "patch-001",
        "asset_id": "asset-001"
    }
    """
    try:
        db = get_database()
        ml_service = get_ml_service(db)
        
        prediction = await ml_service.predict_patch_failure(
            patch_id=data.get("patch_id"),
            asset_id=data.get("asset_id")
        )
        
        return prediction
    except Exception as e:
        print(f"Error predicting failure: {e}")
        return {"error": str(e)}, 500


@router.get("/api/ml/detect-anomalies")
async def detect_anomalies(tenant_id: str = None, lookback_days: int = 7):
    """
    Detect anomalies in patch deployment patterns
    
    Query params:
    - tenant_id: Optional tenant filter
    - lookback_days: Days to analyze (default: 7)
    """
    try:
        db = get_database()
        ml_service = get_ml_service(db)
        
        anomalies = await ml_service.detect_anomalies(
            tenant_id=tenant_id,
            lookback_days=lookback_days
        )
        
        return anomalies
    except Exception as e:
        print(f"Error detecting anomalies: {e}")
        return {"error": str(e)}, 500


@router.post("/api/ml/recommend-action")
async def recommend_autonomous_action(data: dict):
    """
    Recommend autonomous deployment action
    
    Body:
    {
        "patch_id": "patch-001",
        "failure_predictions": [
            {"asset_id": "...", "failure_probability": 0.2},
            ...
        ]
    }
    """
    try:
        db = get_database()
        ml_service = get_ml_service(db)
        
        recommendation = await ml_service.recommend_autonomous_action(
            patch_id=data.get("patch_id"),
            failure_predictions=data.get("failure_predictions", [])
        )
        
        return recommendation
    except Exception as e:
        print(f"Error generating recommendation: {e}")
        return {"error": str(e)}, 500


# Phase 7: Scalability Status Endpoint

@router.get("/api/system/health")
async def get_system_health():
    """
    Get system health metrics for load balancing/monitoring
    
    Returns metrics for:
    - Database connections
    - API response times
    - Active deployments
    - Resource usage
    """
    try:
        db = get_database()
        
        # Count active deployments
        active_deployments = await db.patch_deployment_jobs.count_documents(
            {"status": {"$in": ["scheduled", "in_progress"]}}
        )
        
        # Count total assets
        total_assets = await db.assets.count_documents({})
        
        # Count pending patches
        pending_patches = await db.patches.count_documents({"status": "Pending"})
        
        return {
            "status": "healthy",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "metrics": {
                "active_deployments": active_deployments,
                "total_assets": total_assets,
                "pending_patches": pending_patches,
                "database_status": "connected"
            },
            "version": "1.0.0"
        }
    except Exception as e:
        print(f"Error getting health: {e}")
        return {
            "status": "unhealthy",
            "error": str(e)
        }, 503

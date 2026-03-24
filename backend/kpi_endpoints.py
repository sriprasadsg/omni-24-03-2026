from fastapi import APIRouter, HTTPException, Depends
from typing import List, Dict, Any
from datetime import datetime, timedelta
import random
from database import get_database

router = APIRouter(prefix="/api/kpi", tags=["Business KPI"])

from authentication_service import get_current_user
from auth_types import TokenData
from tenant_context import get_tenant_id
from rbac_service import rbac_service

@router.get("/summary")
async def get_kpi_summary(current_user: TokenData = Depends(rbac_service.has_permission("view:dashboard"))):
    """
    Get absolute counts for agents and assets for the current tenant.
    """
    db = get_database()
    tenant_id = get_tenant_id()
    
    # Global aggregation for Super Admins
    query = {"tenantId": tenant_id}
    if tenant_id == "platform-admin" or tenant_id is None:
        query = {}
    
    # 1. Total Agents
    total_agents = await db.agents.count_documents(query)
    
    # 2. Online Agents
    online_agents = await db.agents.count_documents({**query, "status": "Online"})
    
    # 3. Total Assets
    total_assets = await db.assets.count_documents(query)
    
    # 4. Critical Alerts
    critical_alerts = await db.alerts.count_documents({**query, "severity": "Critical", "status": "Open"})

    return {
        "totalAgents": total_agents,
        "onlineAgents": online_agents,
        "totalAssets": total_assets,
        "criticalAlerts": critical_alerts,
        "timestamp": datetime.utcnow().isoformat()
    }

@router.get("/business-metrics")
async def get_business_metrics(current_user: TokenData = Depends(rbac_service.has_permission("view:reporting"))):
    """
    Get correlated security and business metrics.
    """
    db = get_database()
    tenant_id = get_tenant_id()
    
    # 1. Calculate Real Security Score (aggregated from agents for this tenant)
    query = {"tenantId": tenant_id}
    if tenant_id == "platform-admin" or tenant_id is None:
        query = {}
        
    agents = await db.agents.find(query, {"securityScore": 1}).to_list(length=None)
    avg_sec_score = 0
    if agents:
        scores = [a.get('securityScore', 0) for a in agents if a.get('securityScore')]
        if scores:
            avg_sec_score = sum(scores) / len(scores)
    
    # If no real data, use a baseline but dynamic score
    if avg_sec_score == 0:
        avg_sec_score = 85.0 # Baseline
        
    # 2. Simulate Business Metrics (Revenue, Uptime) correlated to Security
    # In production, fetch this from Salesforce/Stripe/Datadog APIs
    
    # Logic: Higher security score = Better uptime = Higher revenue protection
    uptime_impact = (avg_sec_score - 80) * 0.05 # +/- impact based on score
    uptime = min(99.99, 99.9 + uptime_impact)
    
    # Generate 6 months of trend data
    months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun"]
    data = []
    
    base_revenue = 1000000 # $1M
    base_risk = 100 - avg_sec_score
    
    for i, month in enumerate(months):
        # Add some randomness but keep trend
        monthly_risk = max(0, base_risk + random.uniform(-5, 5))
        monthly_sec_score = 100 - monthly_risk
        
        # Revenue impact: High risk = potential loss
        revenue_loss_risk = (monthly_risk / 100) * 50000 # Potential loss
        actual_revenue = base_revenue - revenue_loss_risk + random.uniform(-10000, 20000)
        
        data.append({
            "month": month,
            "securityScore": round(monthly_sec_score, 1),
            "revenue": round(actual_revenue, 2),
            "riskExposure": round(monthly_risk * 10000, 2), # $ value of risk
            "uptime": round(uptime + random.uniform(-0.05, 0.05), 3)
        })
        
    return {
        "summary": {
            "currentSecurityScore": round(avg_sec_score, 1),
            "projectedRevenueProtected": "$4.2M",
            "complianceRate": "98.5%",
            "mttrHours": 4.2
        },
        "trends": data
    }

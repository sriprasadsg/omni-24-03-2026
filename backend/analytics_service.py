"""
Real-time Analytics Service for Reporting
Generates historical trend data from actual database records
"""
import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, Any

logger = logging.getLogger(__name__)

async def generate_analytics(db, tenant_id: str) -> Dict[str, Any]:
    """
    Generate analytics data from real database records.

    Args:
        db: MongoDB database instance
        tenant_id: Required — callers must provide a non-empty tenant ID.
                   Passing an empty/None value raises ValueError to prevent
                   cross-tenant data leakage from unfiltered queries.

    Returns:
        Dictionary containing historical trends
    """
    if not tenant_id:
        raise ValueError("tenant_id is required for generate_analytics")
    
    # Calculate date range (last 6 months)
    end_date = datetime.now(timezone.utc)
    start_date = end_date - timedelta(days=180)
    
    # Generate month labels
    months = []
    current = start_date
    while current <= end_date:
        months.append(current.strftime("%b %Y"))
        # Move to next month
        if current.month == 12:
            current = current.replace(year=current.year + 1, month=1)
        else:
            current = current.replace(month=current.month + 1)
    
    # Initialize data structures
    alert_data = {month: {"Critical": 0, "High": 0, "Medium": 0} for month in months}
    compliance_data = {month: 0.0 for month in months}
    vulnerability_data = {month: {"Critical": 0, "High": 0, "Medium": 0, "Low": 0} for month in months}
    
    # Query filter
    query_filter = {}
    if tenant_id:
        query_filter["tenantId"] = tenant_id

    start_iso = start_date.isoformat()
    end_iso = end_date.isoformat()

    # === ALERTS DATA ===
    alerts_filter = {**query_filter, "timestamp": {"$gte": start_iso, "$lte": end_iso}}
    alerts = await db.security_events.find(alerts_filter, {"_id": 0}).to_list(length=2000)
    for alert in alerts:
        timestamp_str = alert.get("timestamp")
        if timestamp_str:
            try:
                timestamp = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
                if start_date <= timestamp <= end_date:
                    month_key = timestamp.strftime("%b %Y")
                    severity = alert.get("severity", "Medium")
                 
                    if month_key in alert_data and severity in alert_data[month_key]:
                        alert_data[month_key][severity] += 1
            except Exception:
                continue

    # === COMPLIANCE DATA ===
    # Calculate compliance score based on compliant vs non-compliant controls
    compliance_results = await db.compliance_results.find(query_filter, {"_id": 0}).to_list(length=2000)
    
    # Group compliance results by month using their timestamp
    month_compliance: Dict[str, list] = {month: [] for month in months}
    for r in compliance_results:
        ts_str = r.get("createdAt") or r.get("timestamp") or r.get("updatedAt", "")
        if ts_str:
            try:
                ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                if start_date <= ts <= end_date:
                    mk = ts.strftime("%b %Y")
                    if mk in month_compliance:
                        month_compliance[mk].append(r)
            except Exception:
                continue

    for month_key in compliance_data.keys():
        month_results = month_compliance[month_key]
        if month_results:
            total = len(month_results)
            passed = sum(1 for r in month_results if r.get("status") in ("Passed", "Pass"))
            compliance_data[month_key] = round(passed / total * 100, 1)
    
    # === VULNERABILITY DATA ===
    vuln_filter = {**query_filter, "discoveredAt": {"$gte": start_iso, "$lte": end_iso}}
    vulnerabilities = await db.vulnerabilities.find(vuln_filter, {"_id": 0}).to_list(length=2000)
    for vuln in vulnerabilities:
        discovered_at = vuln.get("discoveredAt")
        if discovered_at:
            try:
                timestamp = datetime.fromisoformat(discovered_at.replace('Z', '+00:00'))
                if start_date <= timestamp <= end_date:
                    month_key = timestamp.strftime("%b %Y")
                    severity = vuln.get("severity", "Medium")
                    
                    if month_key in vulnerability_data and severity in vulnerability_data[month_key]:
                        vulnerability_data[month_key][severity] += 1
            except Exception as e:
                logger.debug("Skipping vulnerability with unparseable date: %s", e)
                continue
    
    # Format data for frontend charts
    alerts_trend = [{"date": month, **values} for month, values in alert_data.items()]
    compliance_trend = [{"date": month, "score": score} for month, score in compliance_data.items()]
    vulnerabilities_trend = [{"date": month, **values} for month, values in vulnerability_data.items()]
    
    return {
        "alerts": alerts_trend,
        "compliance": compliance_trend,
        "vulnerabilities": vulnerabilities_trend
    }

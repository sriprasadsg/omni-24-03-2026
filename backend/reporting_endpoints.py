
# Reporting & Notification Endpoints
from reporting_service import get_reporting_service
from notification_service import get_notification_service

@app.get("/api/reports/sla-compliance")
async def get_sla_compliance_report(
    tenant_id: str = None,
    framework: str = "SOC2",
    start_date: str = None,
    end_date: str = None
):
    """
    Generate SLA compliance report
    
    Query params:
    - tenant_id: Optional tenant filter
    - framework: SOC2, PCI-DSS, HIPAA, ISO27001 (default: SOC2)
    - start_date: ISO format (default: 30 days ago)
    - end_date: ISO format (default: now)
    """
    try:
        db = get_database()
        reporting_service = get_reporting_service(db)
        
        start = datetime.fromisoformat(start_date) if start_date else None
        end= datetime.fromisoformat(end_date) if end_date else None
        
        report = await reporting_service.generate_sla_compliance_report(
            tenant_id=tenant_id,
            framework=framework,
            start_date=start,
            end_date=end
        )
        
        return report
    except Exception as e:
        print(f"Error generating SLA report: {e}")
        return {"error": str(e)}, 500


@app.get("/api/reports/vulnerability-exposure")
async def get_vulnerability_exposure_report(tenant_id: str = None):
    """
    Generate vulnerability exposure report
    
    Shows asset exposure, critical CVEs, and exploit probability
    """
    try:
        db = get_database()
        reporting_service = get_reporting_service(db)
        
        report = await reporting_service.generate_vulnerability_exposure_report(
            tenant_id=tenant_id
        )
        
        return report
    except Exception as e:
        print(f"Error generating vulnerability report: {e}")
        return {"error": str(e)}, 500


@app.get("/api/reports/change-management")
async def get_change_management_log(
    tenant_id: str = None,
    start_date: str = None,
    end_date: str = None,
    limit: int = 100
):
    """
    Generate ITIL-compliant change management log
    
    Tracks all deployment activities for audit/compliance
    """
    try:
        db = get_database()
        reporting_service = get_reporting_service(db)
        
        start = datetime.fromisoformat(start_date) if start_date else None
        end = datetime.fromisoformat(end_date) if end_date else None
        
        report = await reporting_service.generate_change_management_log(
            tenant_id=tenant_id,
            start_date=start,
            end_date=end,
            limit=limit
        )
        
        return report
    except Exception as e:
        print(f"Error generating change log: {e}")
        return {"error": str(e)}, 500


@app.get("/api/reports/executive-summary")
async def get_executive_summary(tenant_id: str = None):
    """
    Generate executive-level KPI summary
    
    High-level dashboard for C-suite:
    - Security posture
    - Compliance status
    - Patch velocity
    - Risk exposure
    """
    try:
        db = get_database()
        reporting_service = get_reporting_service(db)
        
        summary = await reporting_service.generate_executive_summary(
            tenant_id=tenant_id
        )
        
        return summary
    except Exception as e:
        print(f"Error generating executive summary: {e}")
        return {"error": str(e)}, 500


# Notification Endpoints

@app.post("/api/notifications/send")
async def send_notification(data: dict):
    """
    Send multi-channel notification
    
    Body:
    {
        "title": "Alert Title",
        "message": "Alert message",
        "severity": "critical|warning|info",
        "recipients": ["email@example.com", "+1234567890"],
        "channels": ["email", "sms", "slack", "webhook"],
        "metadata": {}
    }
    """
    try:
        db = get_database()
        notification_service = get_notification_service(db)
        
        result = await notification_service.send_alert(
            title=data.get("title"),
            message=data.get("message"),
            severity=data.get("severity", "info"),
            recipients=data.get("recipients", []),
            channels=data.get("channels", ["email"]),
            metadata=data.get("metadata")
        )
        
        return result
    except Exception as e:
        print(f"Error sending notification: {e}")
        return {"error": str(e)}, 500


@app.post("/api/notifications/config")
async def configure_notifications(data: dict):
    """
    Configure notification channels
    
    Body:
    {
        "type": "slack|email|sms",
        "enabled": true,
        "config": {
            "webhook_url": "https://hooks.slack.com/...",
            "smtp_host": "smtp.gmail.com",
            "phone_number": "+1234567890"
        }
    }
    """
    try:
        db = get_database()
        
        config = {
            "type": data.get("type"),
            "enabled": data.get("enabled", True),
            **data.get("config", {}),
            "updated_at": datetime.now(timezone.utc).isoformat()
        }
        
        await db.notification_config.update_one(
            {"type": data.get("type")},
            {"$set": config},
            upsert=True
        )
        
        return {
            "success": True,
            "message": f"{data.get('type')} notifications configured"
        }
    except Exception as e:
        print(f"Error configuring notifications: {e}")
        return {"error": str(e)}, 500


@app.get("/api/notifications/config")
async def get_notification_configs():
    """Get all notification channel configurations"""
    try:
        db = get_database()
        
        configs = await db.notification_config.find({}, {"_id": 0}).to_list(length=None)
        
        # Redact sensitive fields
        for config in configs:
            if "webhook_url" in config:
                config["webhook_url"] =config["webhook_url"][:30] + "..." if len(config.get("webhook_url", "")) > 30 else config.get("webhook_url")
            if "smtp_password" in config:
                config["smtp_password"] = "***"
        
        return {"configs": configs}
    except Exception as e:
        print(f"Error getting configs: {e}")
        return {"error": str(e)}, 500


@app.get("/api/notifications/history")
async def get_notification_history(limit: int = 50, severity: str = None):
    """Get notification history"""
    try:
        db = get_database()
        
        query = {}
        if severity:
            query["severity"] = severity
        
        notifications = await db.notifications.find(
            query,
            {"_id": 0}
        ).sort("sent_at", -1).limit(limit).to_list(length=None)
        
        return {
            "notifications": notifications,
            "count": len(notifications)
        }
    except Exception as e:
        print(f"Error getting notification history: {e}")
        return {"error": str(e)}, 500

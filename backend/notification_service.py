"""
Notification Service - Multi-Channel Alerts
Handles email, SMS, Slack, and webhook notifications
"""

from datetime import datetime, timezone
from typing import Dict, List, Optional, Any
import aiohttp


class NotificationService:
    """Multi-channel notification and alerting service"""
    
    def __init__(self, db):
        self.db = db
        self.email_enabled = False  # Configure SMTP
        self.sms_enabled = False    # Configure Twilio/etc
        self.slack_enabled = False  # Configure webhook
    
    async def send_alert(
        self,
        title: str,
        message: str,
        severity: str,
        recipients: List[str],
        channels: List[str] = None,
        metadata: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """
        Send multi-channel alert
        
        Channels: email, sms, slack, webhook
        Severity: critical, warning, info
        """
        if not channels:
            channels = ["email"]  # Default
        
        results = {
            "alert_id": f"alert-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}",
            "title": title,
            "severity": severity,
            "sent_at": datetime.now(timezone.utc).isoformat(),
            "channels": {}
        }
        
        # Send via each channel
        if "email" in channels:
            results["channels"]["email"] = await self._send_email(
                recipients, title, message, severity
            )
        
        if "sms" in channels:
            results["channels"]["sms"] = await self._send_sms(
                recipients, f"{title}: {message}"
            )
        
        if "slack" in channels:
            results["channels"]["slack"] = await self._send_slack(
                title, message, severity, metadata
            )
        
        if "webhook" in channels and metadata and "webhook_url" in metadata:
            results["channels"]["webhook"] = await self._send_webhook(
                metadata["webhook_url"], title, message, severity, metadata
            )
        
        # Log notification
        await self.db.notifications.insert_one({
            **results,
            "metadata": metadata
        })
        
        return results
    
    async def _send_email(
        self,
        recipients: List[str],
        subject: str,
        body: str,
        severity: str
    ) -> Dict[str, Any]:
        """
        Send email notification using SMTP logic (Synchronous wrapper)
        """
        import smtplib
        from email.mime.text import MIMEText
        from email.mime.multipart import MIMEMultipart
        import os
        
        # 1. Config (Try Env Vars, else Mock)
        smtp_host = os.getenv("SMTP_HOST", "localhost")
        smtp_port = int(os.getenv("SMTP_PORT", "1025")) # Default to MailHog/Mock port
        smtp_user = os.getenv("SMTP_USER", "")
        smtp_pass = os.getenv("SMTP_PASS", "")
        
        # If no host configured and not testing, log and return
        if smtp_host == "localhost" and not os.getenv("FORCE_SMTP"):
             # Fallback to Logger
             with open("notifications.log", "a") as f:
                 f.write(f"[EMAIL] To: {recipients} | Subject: {subject} | Body: {body[:50]}...\n")
             return {
                 "success": True,
                 "provider": "logger",
                 "message": "Logged to file (SMTP not configured)"
             }
        
        try:
            msg = MIMEMultipart()
            msg['From'] = smtp_user or "alert@omni-agent.ai"
            msg['To'] = ", ".join(recipients)
            msg['Subject'] = f"[{severity.upper()}] {subject}"
            
            msg.attach(MIMEText(body, 'plain'))
            
            # Synchronous SMTP (Block briefly) - acceptable for MVP
            with smtplib.SMTP(smtp_host, smtp_port) as server:
                if smtp_user and smtp_pass:
                    server.starttls()
                    server.login(smtp_user, smtp_pass)
                server.send_message(msg)
                
            return {
                "success": True,
                "provider": "smtp",
                "host": smtp_host
            }
        except Exception as e:
             with open("notifications.log", "a") as f:
                 f.write(f"[EMAIL_FAIL] To: {recipients} | Error: {e}\n")
             return {
                "success": False,
                "error": str(e)
            }
    
    async def _send_sms(
        self,
        phone_numbers: List[str],
        message: str
    ) -> Dict[str, Any]:
        """Send SMS via Twilio when configured; log to file as fallback."""
        import os
        import aiohttp

        account_sid = os.environ.get("TWILIO_ACCOUNT_SID", "")
        auth_token = os.environ.get("TWILIO_AUTH_TOKEN", "")
        from_number = os.environ.get("TWILIO_FROM_NUMBER", "")

        if account_sid and auth_token and from_number:
            results = []
            url = f"https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Messages.json"
            auth = aiohttp.BasicAuth(account_sid, auth_token)
            timeout = aiohttp.ClientTimeout(total=10)
            async with aiohttp.ClientSession(auth=auth, timeout=timeout) as session:
                for number in phone_numbers:
                    try:
                        resp = await session.post(
                            url,
                            data={"From": from_number, "To": number, "Body": message},
                        )
                        results.append({"number": number, "success": resp.status in (200, 201)})
                    except Exception as exc:
                        results.append({"number": number, "success": False, "error": str(exc)})
            sent = sum(1 for r in results if r["success"])
            return {"success": sent > 0, "provider": "twilio",
                    "sent": sent, "total": len(phone_numbers), "results": results}

        # Fallback: write to file and warn
        import logging
        logging.getLogger(__name__).warning(
            "SMS not sent — Twilio not configured (TWILIO_ACCOUNT_SID/AUTH_TOKEN/FROM_NUMBER missing). "
            "Writing to sms_outbox.log instead."
        )
        try:
            with open("sms_outbox.log", "a") as f:
                for number in phone_numbers:
                    f.write(f"[SMS] To: {number} | Msg: {message}\n")
        except OSError:
            pass
        return {"success": False, "provider": "file_fallback", "recipients": phone_numbers}
    
    async def _send_slack(
        self,
        title: str,
        message: str,
        severity: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Send Slack notification via webhook
        
        Requires: Slack webhook URL in configuration
        """
        # Get Slack webhook URL from config
        config = await self.db.notification_config.find_one({"type": "slack"}, {"_id": 0})
        
        if not config or not config.get("webhook_url"):
            return {
                "success": False,
                "error": "Slack webhook not configured"
            }
        
        # Determine color based on severity
        color_map = {
            "critical": "#FF0000",
            "warning": "#FFA500",
            "info": "#0000FF"
        }
        color = color_map.get(severity, "#808080")
        
        # Build Slack message
        slack_payload = {
            "text": title,
            "attachments": [{
                "color": color,
                "title": title,
                "text": message,
                "fields": [],
                "footer": "Patch Management System",
                "ts": int(datetime.now(timezone.utc).timestamp())
            }]
        }
        
        # Add metadata fields
        if metadata:
            for key, value in metadata.items():
                if key != "webhook_url":
                    slack_payload["attachments"][0]["fields"].append({
                        "title": key.replace("_", " ").title(),
                        "value": str(value),
                        "short": True
                    })
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    config["webhook_url"],
                    json=slack_payload,
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as response:
                    if response.status == 200:
                        return {
                            "success": True,
                            "provider": "slack",
                            "webhook_url": config["webhook_url"]
                        }
                    else:
                        return {
                            "success": False,
                            "error": f"Slack API returned {response.status}"
                        }
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }
    
    async def _send_webhook(
        self,
        url: str,
        title: str,
        message: str,
        severity: str,
        metadata: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Send generic webhook notification"""
        payload = {
            "title": title,
            "message": message,
            "severity": severity,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "metadata": metadata
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as response:
                    return {
                        "success": response.status in [200, 201, 202],
                        "status_code": response.status,
                        "webhook_url": url
                    }
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }
    
    async def send_sla_breach_alert(
        self,
        patch: Dict[str, Any],
        breach_hours: float,
        recipients: List[str]
    ) -> Dict[str, Any]:
        """Send alert for SLA breach"""
        title = f"🚨 SLA Breach: {patch.get('name')}"
        message = f"""
Patch SLA has been exceeded:

Patch: {patch.get('name')}
Severity: {patch.get('severity')}
SLA: {patch.get('sla_hours')} hours
Breach: {breach_hours:.1f} hours over deadline
Affected Assets: {len(patch.get('affectedAssets', []))}

Immediate action required.
"""
        
        return await self.send_alert(
            title=title,
            message=message,
            severity="critical",
            recipients=recipients,
            channels=["email", "slack"],
            metadata={
                "patch_id": patch.get("id"),
                "breach_hours": breach_hours,
                "asset_count": len(patch.get("affectedAssets", []))
            }
        )
    
    async def send_critical_patch_alert(
        self,
        patch: Dict[str, Any],
        recipients: List[str]
    ) -> Dict[str, Any]:
        """Send alert for new critical patch"""
        cvss = patch.get("cvss_score", "N/A")
        epss = patch.get("epss_score", 0)
        
        title = f"⚠️ Critical Patch Available: {patch.get('name')}"
        message = f"""
New critical security patch detected:

Patch: {patch.get('name')}
Severity: {patch.get('severity')}
CVSS Score: {cvss}
Exploit Probability: {epss * 100:.1f}%
Priority Score: {patch.get('priority_score', 'N/A')}
Affected Assets: {len(patch.get('affectedAssets', []))}

Review and deploy as soon as possible.
"""
        
        return await self.send_alert(
            title=title,
            message=message,
            severity="warning",
            recipients=recipients,
            channels=["email", "slack"],
            metadata={
                "patch_id": patch.get("id"),
                "cvss_score": cvss,
                "epss_score": epss
            }
        )
    
    async def send_deployment_complete_alert(
        self,
        deployment_id: str,
        success_count: int,
        failure_count: int,
        recipients: List[str]
    ) -> Dict[str, Any]:
        """Send alert when deployment completes"""
        total = success_count + failure_count
        success_rate = (success_count / total * 100) if total > 0 else 0
        
        title = f"✅ Deployment Complete: {deployment_id}"
        message = f"""
Patch deployment has completed:

Deployment ID: {deployment_id}
Total Assets: {total}  
Successful: {success_count}
Failed: {failure_count}
Success Rate: {success_rate:.1f}%

View details in the dashboard.
"""
        
        severity = "info" if success_rate >= 90 else "warning"
        
        return await self.send_alert(
            title=title,
            message=message,
            severity=severity,
            recipients=recipients,
            channels=["email", "slack"],
            metadata={
                "deployment_id": deployment_id,
                "success_count": success_count,
                "failure_count": failure_count,
                "success_rate": success_rate
            }
        )


def get_notification_service(db):
    """Get notification service instance"""
    return NotificationService(db)

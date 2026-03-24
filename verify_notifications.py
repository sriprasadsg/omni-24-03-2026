import asyncio
from unittest.mock import MagicMock, AsyncMock
from backend.notification_service import NotificationService
import os

async def verify():
    print("Verifying Notification Service...")
    
    # Mock DB
    mock_db = MagicMock()
    mock_db.notifications.insert_one = AsyncMock()
    mock_db.notification_config.find_one = AsyncMock(return_value=None) # Slack mock
    
    service = NotificationService(mock_db)
    
    # 1. Test Email (Mock Mode)
    # Ensure logs are clear or we just check append
    if os.path.exists("notifications.log"):
        os.remove("notifications.log")
        
    print("Sending Test Email...")
    res_email = await service.send_alert(
        title="Test Alert",
        message="This is a verify script test.",
        severity="critical",
        recipients=["admin@example.com"],
        channels=["email"]
    )
    print(f"Email Result: {res_email}")
    
    # Check Log
    if os.path.exists("notifications.log"):
         with open("notifications.log", "r") as f:
             content = f.read()
             if "To: ['admin@example.com']" in content and "Subject: [CRITICAL] Test Alert" in content:
                 print("✅ Email Logged Successfully!")
             else:
                 print(f"❌ Email Log Content Mismatch: {content}")
    else:
        print("❌ Email Log File Not Found!")

    # 2. Test SMS
    if os.path.exists("sms_outbox.log"):
        os.remove("sms_outbox.log")
        
    print("Sending Test SMS...")
    res_sms = await service.send_alert(
        title="Test SMS",
        message="This is a verify script test.",
        severity="warning",
        recipients=["+1234567890"],
        channels=["sms"]
    )
    print(f"SMS Result: {res_sms}")
    
    # Check Log
    if os.path.exists("sms_outbox.log"):
         with open("sms_outbox.log", "r") as f:
             content = f.read()
             if "To: +1234567890" in content:
                 print("✅ SMS Logged Successfully!")
             else:
                 print(f"❌ SMS Log Content Mismatch: {content}")
    else:
        print("❌ SMS Log File Not Found!")

if __name__ == "__main__":
    asyncio.run(verify())

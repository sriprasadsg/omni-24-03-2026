# ARCHIVED 2026-11-14 (Phase 86): moved out of backend/. Reads every organization's unsent notices with
# no tenant filter and sends them through the first SMTP config found. Nothing runs it. Do not run or import.
import asyncio
import os
from motor.motor_asyncio import AsyncIOMotorClient
from email_service import email_service

async def send_pending_notifications():
    mongo_uri = os.getenv("MONGO_URI", "mongodb://localhost:27017")
    db_name = os.getenv("DB_NAME", "omni_agent_ai_platform")
    client = AsyncIOMotorClient(mongo_uri)
    db = client[db_name]

    print("Checking pending notifications and approval alerts...")

    # 1. Fetch tenant smtp config
    smtp_configs = await db.smtp_config.find().to_list(length=10)
    default_smtp = smtp_configs[0] if smtp_configs else None

    # 2. Process notifications collection with un-dispatched status or pending emails
    pending_notifs = await db.notifications.find({"email_sent": {"$ne": True}}).to_list(length=50)
    print(f"Found {len(pending_notifs)} pending notifications in DB.")

    for notif in pending_notifs:
        recipient = notif.get("recipient") or notif.get("user_email")
        if not recipient and default_smtp:
            recipient = default_smtp.get("sender_email") or default_smtp.get("fromEmail")

        if recipient and default_smtp:
            try:
                result = await email_service.send_email(
                    smtp_config=default_smtp,
                    to_email=recipient,
                    subject=notif.get("title", "Platform Notification"),
                    body_text=notif.get("message", "")
                )
                if result.get("success"):
                    await db.notifications.update_one(
                        {"_id": notif["_id"]},
                        {"$set": {"email_sent": True}}
                    )
                    print(f"Sent notification email to {recipient}")
                else:
                    print(f"SMTP send failed for {recipient}: {result.get('message')}")
            except Exception as e:
                print(f"Failed to send notification email to {recipient}: {e}")

    # 3. Check notifications.log fallback
    if os.path.exists("notifications.log"):
        with open("notifications.log", "r") as f:
            logs = f.readlines()
        print(f"Found {len(logs)} lines in notifications.log.")
        if default_smtp:
            fallback_recipient = default_smtp.get("fromEmail") or default_smtp.get("sender_email", "admin@localhost")
            for line in logs:
                try:
                    await email_service.send_email(
                        smtp_config=default_smtp,
                        to_email=fallback_recipient,
                        subject="Flushed Notification Log Entry",
                        body_text=line
                    )
                except Exception:
                    pass
            # Clear log after flush attempt
            open("notifications.log", "w").close()
            print("Flushed notifications.log")

    print("Email dispatch script completed.")

if __name__ == "__main__":
    asyncio.run(send_pending_notifications())
import asyncio
import logging
from datetime import datetime, timedelta
from database import get_database
import uuid
# import httpx  # For real API requests

logger = logging.getLogger(__name__)

async def fetch_okta_logs(tenant_id, domain, api_token, last_fetch_time):
    """
    Simulates fetching Okta System Logs via their /api/v1/logs API
    """
    logger.info(f"Fetching Okta logs for tenant {tenant_id} from {domain}")
    
    # Simulated log generation
    simulated_logs = [
        {
            "id": str(uuid.uuid4()),
            "tenant_id": tenant_id,
            "timestamp": datetime.utcnow().isoformat(),
            "log_type": "okta_system",
            "eventType": "user.session.start",
            "displayMessage": "User login to Okta",
            "severity": "INFO",
            "actor": {
                "id": "00u12345",
                "type": "User",
                "alternateId": "bwayne@gotham.com",
                "displayName": "Bruce Wayne"
            },
            "client": {
                "userAgent": {"os": "Mac OS X", "browser": "Chrome"},
                "zone": "null",
                "device": "Computer",
                "ipAddress": "100.200.50.10"
            },
            "outcome": {
                "result": "SUCCESS",
                "reason": None
            },
            "raw_message": "user.session.start SUCCESS"
        }
    ]

    try:
        if simulated_logs:
            db = get_database()
            await db.security_events.insert_many(simulated_logs) # Fix: use security_events
            logger.info(f"Inserted {len(simulated_logs)} Okta logs for SIEM.")
    except Exception as e:
        logger.error(f"Error saving Okta logs to DB: {e}")

async def start_okta_polling():
    while True:
        try:
            db = get_database()
            # Look up configured Okta integrations
            configs = await db.siem_configs.find({"provider": "okta"}).to_list(length=100)
            for config in configs:
                await fetch_okta_logs(
                    tenant_id=config.get("tenant_id", "default"),
                    domain=config.get("domain", "example.okta.com"),
                    api_token="fake_token",
                    last_fetch_time=datetime.utcnow() - timedelta(minutes=1)
                )
        except Exception as e:
            logger.error(f"Error in Okta polling loop: {e}")
        
        await asyncio.sleep(60) # Poll every 1 minute

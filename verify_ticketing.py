import asyncio
import os
import sys

# Add backend to path
sys.path.append(os.path.join(os.getcwd(), 'backend'))

import ticketing_service

async def verify():
    print("--- Verification: Zoho Desk & Custom Webhook ---")
    
    dummy_alert = {
        "alert_id": "test-alert-999",
        "type": "ticketing_verification",
        "severity": "critical",
        "description": "Verification of new ticketing providers.",
        "hostname": "omni-verify-host"
    }
    
    # 1. Test Zoho Desk logic (should fail with 'Missing configuration' if not provided)
    print("\n[1] Testing Zoho Desk (Incomplete Config)...")
    zoho_config = {"provider": "zoho", "zoho_org_id": "", "zoho_token": "", "zoho_department_id": ""}
    res = await ticketing_service.create_zoho_desk_ticket(dummy_alert, zoho_config)
    print(f"Result: {res}")
    
    # 2. Test Custom Webhook logic (with mockbin/local)
    print("\n[2] Testing Custom Webhook (Mock)...")
    # We'll use a local non-existent URL just to see if it correctly attempts the POST and handles error
    custom_config = {
        "provider": "custom",
        "custom_webhook_url": "http://127.0.0.1:0", # Guaranteed to fail but test logic
        "custom_webhook_method": "POST",
        "custom_webhook_headers": {"X-Test": "Omni"},
        "custom_webhook_payload": {"id": "{{alert_id}}", "msg": "New alert on {{hostname}}"}
    }
    res = await ticketing_service.create_custom_webhook_ticket(dummy_alert, custom_config)
    print(f"Result (Expected failure but shows logic flow): {res}")

    print("\n--- Verification Complete ---")

if __name__ == '__main__':
    asyncio.run(verify())

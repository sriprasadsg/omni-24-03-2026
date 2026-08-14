import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any

from database import get_database, TenantIsolatedDatabase
from itam_finance_service import compute_warranty_status, get_warranty_alert_window, WARRANTY_STATUS_EXPIRING, WARRANTY_STATUS_EXPIRED
from itam_notification_service import ItamNotificationService

logger = logging.getLogger(__name__)

# An hourly cadence is ample for a window measured in days
_WARRANTY_SWEEP_INTERVAL_SECONDS = 3600

async def _tenant_admin_emails(db, tenant_id: str) -> List[str]:
    """Placeholder for fetching tenant admin emails"""
    # In a real system, this would query the users collection
    # For now, returning a dummy email
    return [f"admin@{tenant_id}.com"]

async def run_warranty_alert_pass(db) -> int:
    """
    Background sweep for assets with expiring or expired warranties.
    Triggers notifications via ItamNotificationService.
    """
    count = 0
    try:
        query = {
            "warranty_expiry_date": {"$exists": True, "$ne": None},
            "warrantyAlertSentAt": {"$exists": False}, # Only alert once per warranty
        }
        cursor = db.assets.find(query) # db.assets is a TenantIsolatedCollection if db is TenantIsolatedDatabase

        async for asset in cursor:
            # Check for warrantyAlertSentAt inside the loop as well, as the query might not catch it if updated concurrently
            if asset.get("warrantyAlertSentAt"):
                continue
            tenant_id = asset.get("tenantId")
            if not tenant_id:
                logger.warning(f"Asset {asset.get('id')} has no tenantId, skipping warranty check.")
                continue

            # If db is TenantIsolatedDatabase, we need the raw db for ItamNotificationService
            # Or ItamNotificationService can be instantiated with TenantIsolatedDatabase
            # For simplicity, pass the same db object
            notification_service = ItamNotificationService(db)

            window_days = await get_warranty_alert_window(db, tenant_id)
            now = datetime.now(timezone.utc)

            status_result = compute_warranty_status(
                purchase_date=asset.get("purchaseDate"), # compute_warranty_status expects purchase_date
                warranty_months=None, # Not used here, as we have warranty_expiry_date directly
                now=now,
                alert_window_days=window_days
            )
            # Re-calculate status using warranty_expiry_date directly
            warranty_expiry_dt_str = asset.get("warranty_expiry_date")
            if not warranty_expiry_dt_str:
                continue

            try:
                warranty_expiry_dt = datetime.fromisoformat(warranty_expiry_dt_str.replace("Z", "+00:00"))
                if warranty_expiry_dt.tzinfo is None:
                    warranty_expiry_dt = warranty_expiry_dt.replace(tzinfo=timezone.utc)
            except ValueError:
                logger.error(f"Invalid warranty_expiry_date for asset {asset.get('id')}: {warranty_expiry_dt_str}")
                continue

            days_to_expiry = (warranty_expiry_dt - now).days

            current_warranty_status = "active"
            if now >= warranty_expiry_dt:
                current_warranty_status = WARRANTY_STATUS_EXPIRED
            elif days_to_expiry <= window_days:
                current_warranty_status = WARRANTY_STATUS_EXPIRING

            if current_warranty_status not in (WARRANTY_STATUS_EXPIRING, WARRANTY_STATUS_EXPIRED):
                continue

            # Trigger notification
            recipients = await _tenant_admin_emails(db, tenant_id)
            if not recipients:
                logger.warning(f"No admin recipients found for tenant {tenant_id}, skipping warranty alert for asset {asset.get('id')}.")
                continue

            await notification_service.send_warranty_expiry_alert(
                tenant_id=tenant_id,
                asset_id=asset["id"],
                asset_tag=asset.get("assetTag", asset["id"]),
                warranty_status=current_warranty_status,
                warranty_expires_at=warranty_expiry_dt.isoformat(),
                recipients=recipients
            )

            # Mark asset as alerted
            await db.assets.update_one(
                {"id": asset["id"], "tenantId": tenant_id},
                {"$set": {"warrantyAlertSentAt": now.isoformat()}}
            )
            count += 1
    except Exception as e:
        logger.error(f"Error during warranty alert pass: {e}", exc_info=True)
    return count

async def start_warranty_alert_scheduler(db) -> None:
    """
    Starts the background scheduler for warranty alerts.
    """
    logger.info("Warranty alert scheduler started (interval=%ss)", _WARRANTY_SWEEP_INTERVAL_SECONDS)
    while True:
        await run_warranty_alert_pass(db)
        await asyncio.sleep(_WARRANTY_SWEEP_INTERVAL_SECONDS)

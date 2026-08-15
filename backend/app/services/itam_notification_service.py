from app.services.notification_service import NotificationService
from app.models.itam import AssetRequest

class ItamNotificationService:
    def __init__(self, notification_service: NotificationService):
        self.notification_service = notification_service

    def send_asset_request_submission_notification(self, asset_request: AssetRequest, recipient_user: dict):
        message = (
            f"Your asset request for '{asset_request.item_description}' (Quantity: {asset_request.quantity}) "
            f"has been submitted successfully and is awaiting approval."
        )
        self.notification_service.send_email(
            recipient_email=recipient_user.get("email", ""),
            subject="Asset Request Submitted",
            body=message
        )
        if recipient_user.get("slack_id"):
            self.notification_service.send_slack_message(
                slack_id=recipient_user.get("slack_id"),
                message=message
            )

    def send_asset_request_approval_notification(self, asset_request: AssetRequest, recipient_user: dict):
        message = (
            f"Your asset request for '{asset_request.item_description}' (Quantity: {asset_request.quantity}) "
            f"has been APPROVED on {asset_request.approval_date.strftime('%Y-%m-%d %H:%M:%S')}."
        )
        self.notification_service.send_email(
            recipient_email=recipient_user.get("email", ""),
            subject="Asset Request Approved",
            body=message
        )
        if recipient_user.get("slack_id"):
            self.notification_service.send_slack_message(
                slack_id=recipient_user.get("slack_id"),
                message=message
            )

    def send_asset_request_rejection_notification(self, asset_request: AssetRequest, recipient_user: dict):
        message = (
            f"Your asset request for '{asset_request.item_description}' (Quantity: {asset_request.quantity}) "
            f"has been REJECTED on {asset_request.approval_date.strftime('%Y-%m-%d %H:%M:%S')}."
        )
        self.notification_service.send_email(
            recipient_email=recipient_user.get("email", ""),
            subject="Asset Request Rejected",
            body=message
        )
        if recipient_user.get("slack_id"):
            self.notification_service.send_slack_message(
                slack_id=recipient_user.get("slack_id"),
                message=message
            )
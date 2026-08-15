from typing import Optional, List
from pydantic import BaseModel
from datetime import datetime
import enum

class NotificationType(str, enum.Enum):
    EMAIL = "email"
    SLACK = "slack"
    IN_APP = "in_app"

class NotificationStatus(str, enum.Enum):
    PENDING = "pending"
    SENT = "sent"
    FAILED = "failed"

class NotificationBase(BaseModel):
    recipient_id: int
    message: str
    notification_type: NotificationType
    status: NotificationStatus = NotificationStatus.PENDING
    created_at: datetime = datetime.utcnow()
    sent_at: Optional[datetime] = None
    read_at: Optional[datetime] = None

class NotificationCreate(NotificationBase):
    pass

class NotificationInDB(NotificationBase):
    id: int
    class Config:
        orm_mode = True

# Placeholder for notification service
def send_notification(recipient_id: int, message: str, notification_type: str):
    print(f"Sending notification to {recipient_id} ({notification_type}): {message}")

class NotificationService:
    def send_email(self, recipient_email: str, subject: str, body: str):
        print(f"Sending email to {recipient_email} with subject '{subject}': {body}")

    def send_slack_message(self, slack_id: str, message: str):
        print(f"Sending Slack message to {slack_id}: {message}")

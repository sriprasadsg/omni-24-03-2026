from typing import List, Optional
from sqlalchemy.orm import Session
from app.models.itam import AssetRequest, AssetRequestStatus
from app.schemas.itam_asset_request_schemas import AssetRequestCreate, AssetRequestUpdate
from app.services.notification_service import send_notification
from datetime import datetime

class ItamAssetRequestService:
    def __init__(self, db: Session):
        self.db = db

    def create_asset_request(self, request_data: AssetRequestCreate, requester_id: int, tenant_id: int) -> AssetRequest:
        db_request = AssetRequest(
            **request_data.dict(),
            requester_id=requester_id,
            tenant_id=tenant_id,
            status=AssetRequestStatus.PENDING
        )
        self.db.add(db_request)
        self.db.commit()
        self.db.refresh(db_request)

        send_notification(
            recipient_id=requester_id,
            message=f"Your asset request for '{db_request.item_description}' has been submitted.",
            notification_type="asset_request_submission"
        )
        return db_request

    def get_asset_request(self, request_id: int) -> Optional[AssetRequest]:
        return self.db.query(AssetRequest).filter(AssetRequest.id == request_id).first()

    def list_asset_requests(self, tenant_id: int, status: Optional[AssetRequestStatus] = None) -> List[AssetRequest]:
        query = self.db.query(AssetRequest).filter(AssetRequest.tenant_id == tenant_id)
        if status:
            query = query.filter(AssetRequest.status == status)
        return query.all()

    def approve_asset_request(self, request_id: int, approver_id: int) -> Optional[AssetRequest]:
        db_request = self.get_asset_request(request_id)
        if db_request and db_request.status == AssetRequestStatus.PENDING:
            db_request.status = AssetRequestStatus.APPROVED
            db_request.approval_date = datetime.utcnow()
            db_request.approver_id = approver_id
            self.db.commit()
            self.db.refresh(db_request)

            send_notification(
                recipient_id=db_request.requester_id,
                message=f"Your asset request for '{db_request.item_description}' has been approved.",
                notification_type="asset_request_approval"
            )
            return db_request
        return None

    def reject_asset_request(self, request_id: int, approver_id: int) -> Optional[AssetRequest]:
        db_request = self.get_asset_request(request_id)
        if db_request and db_request.status == AssetRequestStatus.PENDING:
            db_request.status = AssetRequestStatus.REJECTED
            db_request.approval_date = datetime.utcnow()
            db_request.approver_id = approver_id
            self.db.commit()
            self.db.refresh(db_request)

            send_notification(
                recipient_id=db_request.requester_id,
                message=f"Your asset request for '{db_request.item_description}' has been rejected.",
                notification_type="asset_request_rejection"
            )
            return db_request
        return None
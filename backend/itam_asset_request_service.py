import logging
import uuid
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any

from database import TenantIsolatedDatabase
from itam_models import AssetRequest, AssetRequestCreate, AssetRequestUpdate, AssetRequestStatus
from approval_service import ApprovalService
from itam_notification_service import ItamNotificationService

logger = logging.getLogger(__name__)

class ItamAssetRequestService:
    def __init__(self, db: TenantIsolatedDatabase):
        self.db = db
        self.approval_service = ApprovalService(db) # Reuse existing approval service
        self.notification_service = ItamNotificationService(db) # Reuse ITAM notification service

    async def create_asset_request(self, tenant_id: str, requester_id: str, request_data: AssetRequestCreate) -> AssetRequest:
        now = datetime.now(timezone.utc)
        generated_id = f"ar-{uuid.uuid4().hex[:8]}"
        doc = request_data.model_dump()
        doc.update({
            "_id": generated_id,
            "id": generated_id,
            "tenant_id": tenant_id,
            "requester_id": requester_id,
            "status": AssetRequestStatus.PENDING,
            "request_date": now,
            "createdAt": now,
            "updatedAt": now,
        })

        # "_id" is set explicitly (not left to Mongo's auto ObjectId) so that
        # AssetRequest.id (Pydantic alias="_id") serializes back the SAME
        # value get/approve/reject query by via {"id": ...} — otherwise the
        # client receives Mongo's raw ObjectId as "id" while the document's
        # separate "id" field holds this generated string, and every
        # subsequent lookup 404s/400s on the mismatch.
        result = await self.db.asset_requests.insert_one(doc)
        created_request = await self.db.asset_requests.find_one({"_id": result.inserted_id})
        asset_request = AssetRequest.model_validate(created_request)

        # Trigger approval workflow
        # Example: single-step approval by a role "ITAM Approver"
        # In a real system, this would be more dynamic, e.g., based on asset value/type
        workflow_steps = [{"role": "ITAM Approver", "approvers": ["itam.approver@example.com"]}] # Placeholder

        await self.approval_service.create_approval_request(
            tenant_id=tenant_id,
            requester=requester_id,
            action_type="Asset Request",
            description=f"Request for {request_data.quantity} x {request_data.item_description}",
            details={"asset_request_id": str(asset_request.id), **request_data.model_dump()},
            workflow_steps=workflow_steps
        )

        # Send notification for request submission
        await self.notification_service.send_asset_request_notification(
            tenant_id=tenant_id,
            request_id=str(asset_request.id),
            item_description=asset_request.item_description,
            status=AssetRequestStatus.PENDING,
            requester_id=requester_id,
            recipients=[requester_id] # Notify requester
        )

        return asset_request

    async def get_asset_request(self, tenant_id: str, request_id: str) -> Optional[AssetRequest]:
        doc = await self.db.asset_requests.find_one({"id": request_id, "tenant_id": tenant_id})
        if doc:
            return AssetRequest.model_validate(doc)
        return None

    async def list_asset_requests(self, tenant_id: str, status: Optional[AssetRequestStatus] = None, skip: int = 0, limit: int = 100) -> List[AssetRequest]:
        query: Dict[str, Any] = {"tenant_id": tenant_id}
        if status:
            query["status"] = status
        cursor = self.db.asset_requests.find(query).skip(skip).limit(limit)
        requests = await cursor.to_list(length=limit)
        return [AssetRequest.model_validate(req) for req in requests]

    async def update_asset_request(self, tenant_id: str, request_id: str, request_data: AssetRequestUpdate) -> Optional[AssetRequest]:
        now = datetime.now(timezone.utc)
        update_data = request_data.model_dump(exclude_unset=True)
        update_data["updatedAt"] = now

        result = await self.db.asset_requests.find_one_and_update(
            {"id": request_id, "tenant_id": tenant_id},
            {"$set": update_data},
            return_document=True
        )
        if result:
            return AssetRequest.model_validate(result)
        return None

    async def approve_asset_request(self, tenant_id: str, request_id: str, approver_id: str) -> Optional[AssetRequest]:
        asset_request = await self.get_asset_request(tenant_id, request_id)
        if not asset_request or asset_request.status != AssetRequestStatus.PENDING:
            return None # Or raise HTTPException

        # Update request status — build $set dict directly (Pydantic models are immutable)
        now = datetime.now(timezone.utc)

        # Update in DB
        result = await self.db.asset_requests.find_one_and_update(
            {"id": request_id, "tenant_id": tenant_id},
            {"$set": {
                "status": AssetRequestStatus.APPROVED,
                "approval_date": now,
                "approver_id": approver_id,
                "updatedAt": now,
            }},
            return_document=True
        )

        if result:
            approved_request = AssetRequest.model_validate(result)
            # Send notification for approval
            await self.notification_service.send_asset_request_notification(
                tenant_id=tenant_id,
                request_id=str(approved_request.id),
                item_description=approved_request.item_description,
                status=AssetRequestStatus.APPROVED,
                requester_id=approved_request.requester_id,
                recipients=[approved_request.requester_id, approver_id] # Notify requester and approver
            )
            return approved_request
        return None

    async def reject_asset_request(self, tenant_id: str, request_id: str, approver_id: str) -> Optional[AssetRequest]:
        asset_request = await self.get_asset_request(tenant_id, request_id)
        if not asset_request or asset_request.status != AssetRequestStatus.PENDING:
            return None # Or raise HTTPException

        # Update request status — build $set dict directly (Pydantic models are immutable)
        now = datetime.now(timezone.utc)

        # Update in DB
        result = await self.db.asset_requests.find_one_and_update(
            {"id": request_id, "tenant_id": tenant_id},
            {"$set": {
                "status": AssetRequestStatus.REJECTED,
                "approval_date": now,
                "approver_id": approver_id,
                "updatedAt": now,
            }},
            return_document=True
        )

        if result:
            rejected_request = AssetRequest.model_validate(result)
            # Send notification for rejection
            await self.notification_service.send_asset_request_notification(
                tenant_id=tenant_id,
                request_id=str(rejected_request.id),
                item_description=rejected_request.item_description,
                status=AssetRequestStatus.REJECTED,
                requester_id=rejected_request.requester_id,
                recipients=[rejected_request.requester_id, approver_id] # Notify requester and approver
            )
            return rejected_request
        return None
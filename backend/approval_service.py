from datetime import datetime, timezone
from typing import Dict, List, Optional, Any
import uuid
from email_service import email_service

class ApprovalService:
    def __init__(self, db):
        self.db = db

    async def create_approval_request(
        self,
        tenant_id: str,
        requester: str,
        action_type: str,
        description: str,
        details: Dict[str, Any],
        workflow_steps: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Create a new multi-step approval request.
        workflow_steps: List of {"role": "SecurityAdmin", "approvers": ["user@example.com"]}
        """
        request_id = f"req-{uuid.uuid4().hex[:8]}"
        
        # Initialize steps
        steps = []
        for i, step in enumerate(workflow_steps):
            steps.append({
                "step_number": i + 1,
                "role": step.get("role"),
                "approvers": step.get("approvers", []),
                "status": "pending" if i == 0 else "waiting",
                "decided_by": None,
                "decided_at": None,
                "decision": None,
                "comments": None
            })

        request = {
            "id": request_id,
            "tenantId": tenant_id,
            "requester": requester,
            "actionType": action_type,
            "description": description,
            "details": details,
            "status": "pending",
            "createdAt": datetime.now(timezone.utc).isoformat(),
            "updatedAt": datetime.now(timezone.utc).isoformat(),
            "currentStep": 1,
            "steps": steps
        }

        await self.db.approval_requests.insert_one(request)
        return request

    async def get_request(self, request_id: str) -> Optional[Dict[str, Any]]:
        return await self.db.approval_requests.find_one({"id": request_id}, {"_id": 0})

    async def get_pending_for_user(self, user_email: str, tenant_id: str) -> List[Dict[str, Any]]:
        """Fetch requests where the user is an approver for the current pending step."""
        cursor = self.db.approval_requests.find({
            "tenantId": tenant_id,
            "status": "pending",
            "steps": {
                "$elemMatch": {
                    "status": "pending",
                    "approvers": user_email
                }
            }
        }, {"_id": 0})
        return await cursor.to_list(length=100)

    async def submit_decision(
        self,
        request_id: str,
        user_email: str,
        decision: str, # "approve" or "reject"
        comments: Optional[str] = None
    ) -> Dict[str, Any]:
        request = await self.get_request(request_id)
        if not request:
            raise ValueError("Request not found")
        
        if request["status"] != "pending":
            raise ValueError(f"Request is already {request['status']}")

        current_step_num = request["currentStep"]
        step_idx = current_step_num - 1
        step = request["steps"][step_idx]

        if user_email not in step["approvers"]:
            raise ValueError("User is not an authorized approver for this step")

        # Update current step
        step["status"] = "approved" if decision == "approve" else "rejected"
        step["decided_by"] = user_email
        step["decided_at"] = datetime.now(timezone.utc).isoformat()
        step["decision"] = decision
        step["comments"] = comments

        # Determine overall status
        new_status = "pending"
        if decision == "reject":
            new_status = "rejected"
        elif current_step_num == len(request["steps"]):
            new_status = "approved"
        else:
            # Move to next step
            request["currentStep"] += 1
            request["steps"][current_step_num]["status"] = "pending"

        request["status"] = new_status
        request["updatedAt"] = datetime.now(timezone.utc).isoformat()

        await self.db.approval_requests.update_one(
            {"id": request_id},
            {"$set": {
                "status": request["status"],
                "currentStep": request["currentStep"],
                "steps": request["steps"],
                "updatedAt": request["updatedAt"]
            }}
        )

        # Trigger notification if request is fully resolved
        if new_status in ["approved", "rejected"]:
            try:
                smtp_config = await self.db.smtp_config.find_one({"tenant_id": request["tenantId"]})
                if smtp_config:
                    alert_data = {
                        "title": f"Approval Request {new_status.capitalize()}: {request.get('actionType')}",
                        "severity": "Info",
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "asset": f"Request ID: {request_id}",
                        "description": f"The request for '{request.get('description', 'Unknown')}' has been {new_status}.\nFinal Decision by: {user_email}\nComments: {comments or 'None'}",
                        "recommendations": "No further action is required for this request."
                    }
                    # Send to requester (could also send to approvers depending on workflow, sticking to requester here)
                    requester = request.get("requester")
                    if requester:
                         email_service.send_alert_notification(
                             smtp_config=smtp_config,
                             recipients=[requester],
                             alert=alert_data
                         )
            except Exception as e:
                print(f"[ApprovalService] Failed to send notification email: {e}")

        return request

def get_approval_service(db):
    return ApprovalService(db)

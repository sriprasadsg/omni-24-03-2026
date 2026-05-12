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

        # Notify first-step approvers
        await self._notify_approvers(request, steps[0])

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
        next_step = None
        if decision == "reject":
            new_status = "rejected"
        elif current_step_num == len(request["steps"]):
            new_status = "approved"
        else:
            # Move to next step
            request["currentStep"] += 1
            request["steps"][current_step_num]["status"] = "pending"
            next_step = request["steps"][current_step_num]

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

        # Notify next-step approvers when workflow advances
        if next_step is not None:
            await self._notify_approvers(request, next_step)

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

        # Always push to in-app notifications regardless of SMTP
        try:
            await self.db.notifications.insert_one({
                "alert_id": f"jit-{request_id}",
                "type": "jit_approval",
                "title": f"JIT Request {new_status.capitalize()}: {request.get('actionType', '')}",
                "message": f"Approval request '{request.get('description', request_id)}' was {new_status} by {user_email}.",
                "severity": "info",
                "read": False,
                "tenantId": request.get("tenantId", "global"),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
        except Exception:
            pass

        return request

    async def _notify_approvers(self, request: Dict[str, Any], step: Dict[str, Any]) -> None:
        """Send an email to all approvers for a given workflow step."""
        approvers = step.get("approvers", [])
        if not approvers:
            return
        try:
            smtp_config = await self.db.smtp_config.find_one({"tenant_id": request["tenantId"]})
            if not smtp_config:
                return
            subject = f"Action Required: Approval Request — {request.get('actionType', 'Unknown')}"
            body_text = (
                f"You have a pending approval request.\n\n"
                f"Request ID : {request['id']}\n"
                f"Action     : {request.get('actionType', 'N/A')}\n"
                f"Description: {request.get('description', 'N/A')}\n"
                f"Requested by: {request.get('requester', 'N/A')}\n"
                f"Step       : {step['step_number']} — {step.get('role', 'N/A')}\n\n"
                "Please log in to the platform to approve or reject this request."
            )
            for approver in approvers:
                email_service.send_email(
                    smtp_config=smtp_config,
                    to_email=approver,
                    subject=subject,
                    body_text=body_text,
                )
        except Exception as exc:
            print(f"[ApprovalService] Failed to notify approvers: {exc}")


def get_approval_service(db):
    return ApprovalService(db)

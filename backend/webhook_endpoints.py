from fastapi import APIRouter, Depends, HTTPException, Body, Request
from typing import List, Dict, Any, Optional
from database import get_database
from authentication_service import get_current_user
from auth_types import TokenData
from datetime import datetime, timezone
import uuid
import httpx
from intent_parser_service import intent_parser_service
from integration_service import get_integration_service

router = APIRouter(prefix="/api/webhooks", tags=["Webhooks"])

@router.post("/jira/inbound")
async def handle_jira_webhook(payload: Dict[str, Any]):
    """
    Handle inbound Jira webhook events.
    Parses 'issue_created' or 'issue_updated' and dispatches tasks.
    """
    db = get_database()
    integration_svc = get_integration_service(db)
    
    result = await intent_parser_service.parse_and_dispatch(payload, "jira")
    
    if result.get("success") and result.get("task_id"):
        # Post a comment back to Jira (optional/configurable)
        ticket_id = result.get("ticket_id")
        comment = f"Omni-Agent: Intent detected as '{result['intent']['action']}'. Automated task dispatched (ID: {result['task_id']})."
        await integration_svc.comment_on_ticket(ticket_id, comment, "jira")
    
    return result

@router.post("/zoho/inbound")
async def handle_zoho_webhook(payload: Dict[str, Any]):
    """
    Handle inbound Zoho Desk webhook events.
    """
    db = get_database()
    integration_svc = get_integration_service(db)
    
    result = await intent_parser_service.parse_and_dispatch(payload, "zohodesk")
    
    if result.get("success") and result.get("task_id"):
        ticket_id = result.get("ticket_id")
        comment = f"Omni-Agent: Automated task dispatched for '{result['intent']['action']}'."
        await integration_svc.comment_on_ticket(ticket_id, comment, "zohodesk")
        
    return result

@router.get("")
async def get_webhooks(current_user: TokenData = Depends(get_current_user)):
    """Get all configured webhooks"""
    db = get_database()
    # Filter by user's permission ideally, for now return all active/inactive
    # In a real app, strict tenant filtering is needed
    query = {}
    if current_user.tenant_id and current_user.tenant_id != "platform-admin":
         query["tenantId"] = current_user.tenant_id

    cursor = db.webhooks.find(query, {"_id": 0})
    return await cursor.to_list(length=100)

@router.post("")
async def create_webhook(
    webhook_data: Dict[str, Any],
    current_user: TokenData = Depends(get_current_user)
):
    """Create a new webhook"""
    db = get_database()
    
    webhook_id = f"wh-{uuid.uuid4().hex[:12]}"
    
    new_webhook = {
        "id": webhook_id,
        "name": webhook_data.get("name"),
        "url": webhook_data.get("url"),
        "events": webhook_data.get("events", []),
        "status": "Active",
        "secret": f"whsec_{uuid.uuid4().hex[:24]}", # Auto-generated secret
        "tenantId": current_user.tenant_id,
        "createdBy": current_user.username,
        "createdAt": datetime.now(timezone.utc).isoformat(),
        "failureCount": 0,
        "lastResult": None
    }
    
    await db.webhooks.insert_one(new_webhook)
    return new_webhook

@router.delete("/{webhook_id}")
async def delete_webhook(webhook_id: str, current_user: TokenData = Depends(get_current_user)):
    """Delete a webhook"""
    db = get_database()
    result = await db.webhooks.delete_one({"id": webhook_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Webhook not found")
    return {"success": True}

@router.put("/{webhook_id}")
async def update_webhook(
    webhook_id: str, 
    data: Dict[str, Any], 
    current_user: TokenData = Depends(get_current_user)
):
    """Update webhook status or details"""
    db = get_database()
    
    update_fields = {}
    if "status" in data:
        update_fields["status"] = data["status"]
    if "name" in data:
        update_fields["name"] = data["name"]
    if "url" in data:
        update_fields["url"] = data["url"]
    if "events" in data:
        update_fields["events"] = data["events"]
        
    if not update_fields:
        return {"success": False, "message": "No fields to update"}

    result = await db.webhooks.update_one(
        {"id": webhook_id},
        {"$set": update_fields}
    )
    
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Webhook not found")
        
    # Return updated document
    updated_webhook = await db.webhooks.find_one({"id": webhook_id}, {"_id": 0})
    return updated_webhook

@router.get("/{webhook_id}/deliveries")
async def get_webhook_deliveries(webhook_id: str):
    """Get delivery history for a webhook (mocked for now as we don't store full history yet)"""
    # In a real implementation, we would query a webhook_deliveries collection
    # For now, we return an empty list or mock data
    return []

@router.post("/{webhook_id}/test")
async def test_webhook(webhook_id: str, current_user: TokenData = Depends(get_current_user)):
    """Test a webhook by sending a ping event"""
    db = get_database()
    webhook = await db.webhooks.find_one({"id": webhook_id})
    if not webhook:
        raise HTTPException(status_code=404, detail="Webhook not found")
        
    payload = {
        "event": "ping",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "data": {
            "message": "This is a test event from Omni Agent Platform",
            "triggeredBy": current_user.username
        }
    }
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                webhook["url"], 
                json=payload, 
                headers={"Content-Type": "application/json", "User-Agent": "Omni-Platform-Test"},
                timeout=5.0
            )
            
        success = response.status_code >= 200 and response.status_code < 300
        
        return {
            "success": success,
            "status": response.status_code,
            "response": response.text[:200]
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }

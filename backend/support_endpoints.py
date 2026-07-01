"""
Support Chat Endpoints
Three-tier messaging:
  User           → Tenant Admin   (chat_type: user_to_admin)
  Tenant Admin   → Super Admin    (chat_type: admin_to_superadmin)
  Admin          → Specific User  (chat_type: admin_to_user)
  Super Admin    can read/reply to all conversations
"""
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from authentication_service import get_current_user
from auth_types import TokenData
from database import get_database
import logging


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/support", tags=["Support Chat"])

_SUPER_ROLES  = {"Super Admin", "super_admin", "admin", "platform-admin"}
_ADMIN_ROLES  = {"Tenant Admin", "tenant_admin"} | _SUPER_ROLES


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _is_super(role: str) -> bool:
    return role in _SUPER_ROLES


def _is_admin(role: str) -> bool:
    return role in _ADMIN_ROLES


def _caller(cu: TokenData):
    return {
        "username": cu.username or "",
        "role":     cu.role or "user",
        "tenant":   cu.tenant_id or "",
    }


def _access_filter(cu: TokenData) -> Dict[str, Any]:
    """MongoDB filter that scopes conversations to what the caller may see."""
    role = cu.role or ""
    if _is_super(role):
        return {}
    if _is_admin(role):
        return {"tenant_id": cu.tenant_id or ""}
    # Regular user — conversations they started OR were targeted in (admin_to_user)
    uname = cu.username or ""
    return {
        "tenant_id": cu.tenant_id or "",
        "$or": [{"initiator_id": uname}, {"target_user_id": uname}],
    }


# ── Pydantic models ───────────────────────────────────────────────────────────

class StartConvoRequest(BaseModel):
    subject: str = Field(..., max_length=300)
    message: str = Field(..., max_length=5000)
    chat_type: str = Field("user_to_admin")  # user_to_admin | admin_to_superadmin | admin_to_user
    target_user_id: Optional[str] = Field(None, max_length=320)   # required for admin_to_user
    target_user_name: Optional[str] = Field(None, max_length=120)  # display name hint
    # Escalation context — only for admin_to_superadmin
    original_convo_id: Optional[str] = Field(None, max_length=36)
    original_subject: Optional[str] = Field(None, max_length=300)
    original_user_name: Optional[str] = Field(None, max_length=120)
    original_user_email: Optional[str] = Field(None, max_length=320)


class SendMessageRequest(BaseModel):
    content: str = Field(..., max_length=5000)


class UpdateStatusRequest(BaseModel):
    status: str  # open | in_progress | resolved | closed


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_msg(username: str, role: str, content: str) -> Dict[str, Any]:
    return {
        "id":         str(uuid.uuid4()),
        "sender_id":  username,
        "sender_role": role,
        "content":    content,
        "created_at": _now(),
    }


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/conversations")
async def list_conversations(
    status: Optional[str] = None,
    chat_type: Optional[str] = None,
    current_user: TokenData = Depends(get_current_user),
) -> List[Dict[str, Any]]:
    db = get_database()
    query = _access_filter(current_user)
    if status:
        query["status"] = status
    if chat_type:
        query["chat_type"] = chat_type
    convos = await db.support_conversations.find(query, {"_id": 0}).sort("updated_at", -1).to_list(200)
    for c in convos:
        msgs = c.pop("messages", [])
        c["message_count"] = len(msgs)
        c["last_message"] = msgs[-1] if msgs else None
    return convos


@router.post("/conversations")
async def start_conversation(
    body: StartConvoRequest,
    current_user: TokenData = Depends(get_current_user),
) -> Dict[str, Any]:
    db = get_database()
    c = _caller(current_user)

    VALID_TYPES = ("user_to_admin", "admin_to_superadmin", "admin_to_user")
    if body.chat_type not in VALID_TYPES:
        raise HTTPException(status_code=400, detail="Invalid chat_type")
    if body.chat_type == "admin_to_superadmin" and not _is_admin(c["role"]):
        raise HTTPException(status_code=403, detail="Only admins can escalate to Super Admin")
    if body.chat_type == "user_to_admin" and _is_super(c["role"]):
        raise HTTPException(status_code=400, detail="Super Admins use admin_to_superadmin conversations")
    if body.chat_type == "admin_to_user":
        if not _is_admin(c["role"]):
            raise HTTPException(status_code=403, detail="Only admins can message users directly")
        if not body.target_user_id:
            raise HTTPException(status_code=400, detail="target_user_id is required for admin_to_user")
        # Verify the target user exists and belongs to the caller's tenant.
        # Super-admins may cross tenant boundaries; all others are scoped.
        target = await db._db.users.find_one(
            {"$or": [
                {"id":       body.target_user_id},
                {"email":    body.target_user_id},
                {"username": body.target_user_id},
            ]},
            {"tenantId": 1, "_id": 0},
        )
        if not target:
            raise HTTPException(status_code=404, detail="Target user not found")
        if not _is_super(c["role"]) and target.get("tenantId") != c["tenant"]:
            raise HTTPException(status_code=403, detail="Target user is not in your tenant")

    # Resolve initiator display name + email from the users collection
    user_doc = await db._db.users.find_one(
        {"$or": [{"email": c["username"]}, {"username": c["username"]}]},
        {"name": 1, "email": 1, "_id": 0},
    )
    initiator_name  = (user_doc or {}).get("name")  or c["username"]
    initiator_email = (user_doc or {}).get("email") or c["username"]

    first_msg = _make_msg(c["username"], c["role"], body.message)
    convo: Dict[str, Any] = {
        "id":               str(uuid.uuid4()),
        "tenant_id":        c["tenant"],
        "subject":          body.subject,
        "chat_type":        body.chat_type,
        "status":           "open",
        "initiator_id":     c["username"],
        "initiator_name":   initiator_name,
        "initiator_email":  initiator_email,
        "initiator_role":   c["role"],
        "messages":         [first_msg],
        "created_at":       _now(),
        "updated_at":       _now(),
    }
    if body.chat_type == "admin_to_user":
        convo["target_user_id"]   = body.target_user_id
        convo["target_user_name"] = body.target_user_name or body.target_user_id
    if body.chat_type == "admin_to_superadmin" and body.original_convo_id:
        convo["original_convo_id"]   = body.original_convo_id
        convo["original_subject"]    = body.original_subject or ""
        convo["original_user_name"]  = body.original_user_name or ""
        convo["original_user_email"] = body.original_user_email or ""
    await db.support_conversations.insert_one({**convo})
    convo.pop("_id", None)

    try:
        from websocket_manager import broadcast_support_event
        await broadcast_support_event(
            c["tenant"], body.chat_type, "new_conversation",
            {**convo, "target_user_id": convo.get("target_user_id")},
        )
    except Exception as e:
        logger.debug("Support WS broadcast failed (non-fatal): %s", e)

    return convo


@router.get("/conversations/{convo_id}")
async def get_conversation(
    convo_id: str,
    current_user: TokenData = Depends(get_current_user),
) -> Dict[str, Any]:
    db = get_database()
    query = {"id": convo_id, **_access_filter(current_user)}
    convo = await db.support_conversations.find_one(query, {"_id": 0})
    if not convo:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return convo


@router.post("/conversations/{convo_id}/messages")
async def send_message(
    convo_id: str,
    body: SendMessageRequest,
    current_user: TokenData = Depends(get_current_user),
) -> Dict[str, Any]:
    db = get_database()
    c = _caller(current_user)

    query = {"id": convo_id, **_access_filter(current_user)}
    convo = await db.support_conversations.find_one(query, {"_id": 0})
    if not convo:
        raise HTTPException(status_code=404, detail="Conversation not found")
    if convo.get("status") in ("resolved", "closed"):
        raise HTTPException(status_code=400, detail="Conversation is already closed")

    msg = _make_msg(c["username"], c["role"], body.content)
    await db.support_conversations.update_one(
        {"id": convo_id},
        {
            "$push": {"messages": msg},
            "$set": {"updated_at": _now(), "status": "in_progress"},
        },
    )

    try:
        from websocket_manager import broadcast_support_event
        await broadcast_support_event(
            convo.get("tenant_id", c["tenant"]),
            convo.get("chat_type", "user_to_admin"),
            "new_message",
            {
                "convo_id":       convo_id,
                "message":        msg,
                "initiator_id":   convo.get("initiator_id"),
                "target_user_id": convo.get("target_user_id"),
            },
        )
    except Exception as e:
        logger.debug("Support WS broadcast failed (non-fatal): %s", e)

    return msg


@router.patch("/conversations/{convo_id}/status")
async def update_status(
    convo_id: str,
    body: UpdateStatusRequest,
    current_user: TokenData = Depends(get_current_user),
) -> Dict[str, Any]:
    db = get_database()
    if body.status not in ("open", "in_progress", "resolved", "closed"):
        raise HTTPException(status_code=400, detail="Invalid status")
    if body.status in ("resolved", "closed") and not _is_admin(current_user.role or ""):
        raise HTTPException(status_code=403, detail="Only admins can resolve conversations")

    query = {"id": convo_id, **_access_filter(current_user)}
    patch: Dict[str, Any] = {"status": body.status, "updated_at": _now()}
    if body.status == "resolved":
        patch["resolved_at"] = _now()
    result = await db.support_conversations.update_one(query, {"$set": patch})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Conversation not found")
    convo = await db.support_conversations.find_one({"id": convo_id}, {"_id": 0})
    return convo


@router.post("/conversations/{convo_id}/read")
async def mark_conversation_read(
    convo_id: str,
    current_user: TokenData = Depends(get_current_user),
) -> Dict[str, Any]:
    """Record that the calling user has read this conversation and broadcast the receipt."""
    db = get_database()
    c = _caller(current_user)
    query = {"id": convo_id, **_access_filter(current_user)}
    convo = await db.support_conversations.find_one(query, {"_id": 0, "id": 1, "tenant_id": 1, "chat_type": 1, "initiator_id": 1, "target_user_id": 1})
    if not convo:
        raise HTTPException(status_code=404, detail="Conversation not found")
    now = _now()
    await db.support_conversations.update_one(
        {"id": convo_id},
        {"$set": {f"readers.{c['username']}": now}},
    )
    try:
        from websocket_manager import broadcast_support_event
        await broadcast_support_event(
            convo["tenant_id"], convo["chat_type"], "read_receipt",
            {
                "convo_id":       convo_id,
                "reader":         c["username"],
                "at":             now,
                "initiator_id":   convo.get("initiator_id"),
                "target_user_id": convo.get("target_user_id"),
            },
        )
    except Exception as e:
        logger.debug("Read receipt broadcast failed (non-fatal): %s", e)
    return {"ok": True}


@router.get("/presence")
async def get_presence(
    usernames: str = "",
    current_user: TokenData = Depends(get_current_user),
) -> Dict[str, bool]:
    """Return online/offline status for the requested comma-separated usernames."""
    from websocket_manager import user_sessions
    requested = [u.strip() for u in usernames.split(",") if u.strip()]
    return {u: (u in user_sessions) for u in requested}


@router.get("/unread-count")
async def unread_count(
    current_user: TokenData = Depends(get_current_user),
) -> Dict[str, int]:
    """Returns the number of open conversations for the inbox badge."""
    db = get_database()
    query = {**_access_filter(current_user), "status": {"$in": ["open", "in_progress"]}}
    count = await db.support_conversations.count_documents(query)
    return {"count": count}


@router.get("/tenant-users")
async def list_tenant_users(
    current_user: TokenData = Depends(get_current_user),
) -> List[Dict[str, Any]]:
    """
    Returns non-admin users in the caller's tenant for the admin-to-user picker.
    Only accessible by admins and super-admins.
    """
    if not _is_admin(current_user.role or ""):
        raise HTTPException(status_code=403, detail="Admin access required")
    db = get_database()
    tenant_id = current_user.tenant_id or ""
    query: Dict[str, Any] = {"role": {"$nin": list(_ADMIN_ROLES)}}
    if not _is_super(current_user.role or ""):
        query["tenantId"] = tenant_id
    users = await db._db.users.find(
        query,
        {"_id": 0, "id": 1, "email": 1, "username": 1, "name": 1, "role": 1, "status": 1},
    ).sort("name", 1).to_list(500)
    return [
        {
            "id":       u.get("id") or u.get("email") or u.get("username", ""),
            "email":    u.get("email", ""),
            "name":     u.get("name") or u.get("username") or u.get("email", ""),
            "role":     u.get("role", "user"),
            "status":   u.get("status", "Active"),
        }
        for u in users
    ]

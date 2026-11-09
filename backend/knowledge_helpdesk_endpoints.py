"""Knowledge Base routes of the service desk (Phase 85, plan 85-15).

Included under /api/knowledge by ``knowledge_endpoints``, so the Knowledge Base catalogue guard
(manage:settings) of that mount covers every route here. Rules that hold for all of them:

* only the caller's own tenant is read or written, always through the raw handle with an explicit
  tenantId; the shared platform documents (tenantId "global") answer 404 and are never marked Help desk
  (D-16, D-17, T-85-57);
* the Platform tenant is not eligible for the desk (nothing there can be marked Help desk);
* Help desk content is capped at HELPDESK_CONTENT_MAX characters (T-85-59).

The Help desk mark, the article edit route and the flags the list carries; the idempotent copy of the four
starter articles (D-28): a unique (tenantId, starterKey) index plus an upsert with $setOnInsert per starter, so
a double press or two admins at once leave one copy of each.

The knowledge-gap list (D-26, D-27): the questions the desk could not answer, grouped by text similarity. It shows
requesters' questions to authors, so every gap route needs BOTH view:dashboard (ticket access) and manage:ai_risks
(Knowledge Base editing) on top of the router guard. A group is found again by grouping the same rows.
"""
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from pymongo.errors import DuplicateKeyError

from auth_types import TokenData
from autonomous_ops import PLATFORM_TENANT_ID
from autonomous_ops.scope import raw
from database import get_database
from rbac_service import rbac_service
from service_desk import HELPDESK_CONTENT_MAX, TITLE_CAP, gaps, messages, starters
from service_desk import settings as desk_settings

logger = logging.getLogger(__name__)

router = APIRouter()

TAGS_MAX = 20
TAG_CAP = 40
GROUP_NOT_FOUND = "Group not found."
NOTHING_TO_CHANGE = "Change at least one field."
TAGS_LIMIT = "Use up to 20 tags of 40 characters or fewer."


def _refuse(status: int, code: str, **values: Any) -> HTTPException:
    detail = messages.API_DETAIL[code]
    for key, value in values.items():
        detail = detail.replace("{" + key + "}", str(value))
    return HTTPException(status_code=status, detail=detail)


def tenant_of(user: TokenData) -> str:
    """The caller's tenant; a missing tenant or the shared "global" marker is refused."""
    tenant = getattr(user, "tenant_id", None)
    if not isinstance(tenant, str) or not tenant or tenant == "global":
        raise HTTPException(status_code=403, detail="Tenant context required")
    return tenant


def desk_eligible(tenant_id: str) -> bool:
    """False for the Platform tenant: the service desk is not available there."""
    return tenant_id != PLATFORM_TENANT_ID


def refuse_help_desk(tenant_id: str, content: str, *, too_long_status: int) -> None:
    """Raise when ``tenant_id`` may not hold a Help desk article, or ``content`` is over the cap."""
    if not desk_eligible(tenant_id):
        raise _refuse(403, "platform_tenant")
    if len(content) > HELPDESK_CONTENT_MAX:
        raise _refuse(too_long_status, "article_too_long", max=HELPDESK_CONTENT_MAX)


class DocPatch(BaseModel):
    """A change to the caller's own article. Every key may be left out; no other key is accepted."""
    model_config = ConfigDict(extra="forbid")
    title: Optional[str] = None
    content: Optional[str] = None
    tags: Optional[List[str]] = None
    helpdesk: Optional[bool] = None


def _validated(changes: Dict[str, Any]) -> Dict[str, Any]:
    """The changes cleaned and checked in plain words (422 on the first problem)."""
    clean: Dict[str, Any] = {}
    if "title" in changes:
        title = changes["title"].strip()
        if not title:
            raise _refuse(422, "article_title")
        if len(title) > TITLE_CAP:
            raise _refuse(422, "help_too_long", max=TITLE_CAP)
        clean["title"] = title
    if "content" in changes:
        content = changes["content"].strip()
        if not content:
            raise _refuse(422, "article_content")
        if len(content) > HELPDESK_CONTENT_MAX:
            raise _refuse(422, "article_too_long", max=HELPDESK_CONTENT_MAX)
        clean["content"] = content
    if "tags" in changes:
        tags = [t.strip() for t in changes["tags"] if t.strip()]
        if len(tags) > TAGS_MAX or any(len(t) > TAG_CAP for t in tags):
            raise HTTPException(status_code=422, detail=TAGS_LIMIT)
        clean["tags"] = tags
    if "helpdesk" in changes:
        clean["helpdesk"] = changes["helpdesk"]
    return clean


@router.patch("/docs/{doc_id}")
async def patch_doc(
    doc_id: str,
    body: DocPatch,
    current_user: TokenData = Depends(rbac_service.has_permission("manage:ai_risks")),
) -> Dict[str, Any]:
    """Change the title, text, tags or Help desk mark of one of the caller's own articles (D-17)."""
    tenant = tenant_of(current_user)
    given = body.model_dump(exclude_none=True)
    if not given:
        raise HTTPException(status_code=422, detail=NOTHING_TO_CHANGE)
    changes = _validated(given)
    if changes.get("helpdesk") is True and not desk_eligible(tenant):
        raise _refuse(403, "platform_tenant")
    docs = raw(get_database()).knowledge_docs
    scope = {"id": doc_id, "tenantId": tenant}         # never "global": a shared document matches nothing here
    stored = await docs.find_one(scope, {"_id": 0, "content": 1, "helpdesk": 1})
    if stored is None:
        raise _refuse(404, "article_not_found")
    marked = changes.get("helpdesk", bool(stored.get("helpdesk")))
    text = changes.get("content", stored.get("content") if isinstance(stored.get("content"), str) else "")
    if marked and len(text) > HELPDESK_CONTENT_MAX:
        raise _refuse(422, "article_too_long", max=HELPDESK_CONTENT_MAX)
    changes["updatedAt"] = datetime.now(timezone.utc).isoformat()
    result = await docs.update_one(scope, {"$set": changes})
    if result.matched_count == 0:
        raise _refuse(404, "article_not_found")
    return await docs.find_one(scope, {"_id": 0})


async def starter_missing(db, tenant_id: str) -> int:
    """How many of the four starter articles the tenant has no copy of (a copy it edited or unmarked counts as had)."""
    have = set(await raw(db).knowledge_docs.distinct("starterKey", {"tenantId": tenant_id}))
    return sum(1 for starter in starters.STARTERS if starter["key"] not in have)


def _eligible_tenant(user: TokenData) -> str:
    """The caller's tenant, refused (403) for the Platform tenant: no desk articles there."""
    tenant = tenant_of(user)
    if not desk_eligible(tenant):
        raise _refuse(403, "platform_tenant")
    return tenant


@router.get("/helpdesk/starters")
async def starter_status(
    current_user: TokenData = Depends(rbac_service.has_permission("manage:ai_risks")),
) -> Dict[str, int]:
    """How many of the four starter articles the caller's tenant does not have yet."""
    tenant = _eligible_tenant(current_user)
    return {"total": len(starters.STARTERS), "missing": await starter_missing(get_database(), tenant)}


@router.post("/helpdesk/starters")
async def add_starters(
    current_user: TokenData = Depends(rbac_service.has_permission("manage:ai_risks")),
) -> Dict[str, Any]:
    """Copy the starters the tenant lacks as editable Help desk articles (D-28). Nothing is seeded automatically.

    Idempotent: each starter is one upsert keyed on (tenantId, starterKey) that only inserts, so a second press
    adds nothing, an edited copy is never overwritten, and two presses at once add each starter exactly once
    (the loser of a race sees the unique index and counts the starter as existing)."""
    tenant = _eligible_tenant(current_user)
    docs = raw(get_database()).knowledge_docs
    now = datetime.now(timezone.utc).isoformat()
    added: List[str] = []
    existing = 0
    for doc in starters.copy_docs(tenant, {"username": getattr(current_user, "username", None)}, now):
        try:
            result = await docs.update_one({"tenantId": tenant, "starterKey": doc["starterKey"]},
                                           {"$setOnInsert": doc}, upsert=True)
        except DuplicateKeyError:
            existing += 1
            continue
        if result.upserted_id is not None:
            added.append(doc["starterKey"])
        else:
            existing += 1
    return {"added": len(added), "existing": existing, "addedKeys": added}


async def _require_ticket_access(
    current_user: TokenData = Depends(rbac_service.has_permission("view:dashboard")),
) -> TokenData:
    """D-27: a Knowledge Base editor without ticket access must not read what requesters asked."""
    return current_user


@router.get("/helpdesk/gaps")
async def list_gaps(
    dismissed: bool = False,
    current_user: TokenData = Depends(rbac_service.has_permission("manage:ai_risks")),
    _tickets: TokenData = Depends(_require_ticket_access),
) -> Dict[str, Any]:
    """The grouped questions no article covered (``dismissed=true`` adds the dismissed groups)."""
    tenant = _eligible_tenant(current_user)
    db = get_database()
    view = await gaps.list_view(db, tenant, include_dismissed=dismissed)
    view["deskOff"] = (await desk_settings.load(db, tenant)).mode == "off"
    return view


async def _move_group(group_identifier: str, user: TokenData, *, to_status: str, from_status: str) -> Dict[str, Any]:
    tenant = _eligible_tenant(user)
    db = get_database()
    found = await gaps.find_group(db, tenant, group_identifier)
    if found is None:
        raise HTTPException(status_code=404, detail=GROUP_NOT_FOUND)
    status, members = found
    if status != from_status:                       # a second press: already where it should be
        return {"status": to_status, "changed": 0}
    changed = await gaps.set_status(db, tenant, [row["id"] for row in members], to_status, expect=from_status)
    return {"status": to_status, "changed": changed}


@router.post("/helpdesk/gaps/{group_id}/dismiss")
async def dismiss_group(
    group_id: str,
    current_user: TokenData = Depends(rbac_service.has_permission("manage:ai_risks")),
    _tickets: TokenData = Depends(_require_ticket_access),
) -> Dict[str, Any]:
    """Hide a group: every member is dismissed."""
    return await _move_group(group_id, current_user, to_status="dismissed", from_status="open")


@router.post("/helpdesk/gaps/{group_id}/restore")
async def restore_group(
    group_id: str,
    current_user: TokenData = Depends(rbac_service.has_permission("manage:ai_risks")),
    _tickets: TokenData = Depends(_require_ticket_access),
) -> Dict[str, Any]:
    """Bring a dismissed group back: every member is open again."""
    return await _move_group(group_id, current_user, to_status="open", from_status="dismissed")


class ArticleIn(BaseModel):
    """A new article for the caller's tenant, optionally written to answer a gap group."""
    model_config = ConfigDict(extra="forbid")
    title: str
    content: str
    tags: List[str] = []
    helpdesk: bool = True
    gapGroupId: Optional[str] = None


@router.post("/helpdesk/articles")
async def write_article(
    body: ArticleIn,
    current_user: TokenData = Depends(rbac_service.has_permission("manage:ai_risks")),
    _tickets: TokenData = Depends(_require_ticket_access),
) -> Dict[str, Any]:
    """Save a new article; with ``gapGroupId`` the group's members are marked written (and leave the list)."""
    tenant = _eligible_tenant(current_user)
    clean = _validated({"title": body.title, "content": body.content, "tags": body.tags})
    db = get_database()
    claimed: List[str] = []
    claimed_from = ""
    if body.gapGroupId:
        found = await gaps.find_group(db, tenant, body.gapGroupId)
        if found is None:
            raise HTTPException(status_code=404, detail=GROUP_NOT_FOUND)
        claimed_from, members = found
        ids = [row["id"] for row in members]
        # Claiming the rows first keeps a double press from saving two articles for one group.
        if await gaps.set_status(db, tenant, ids, "written", expect=claimed_from) == 0:
            raise HTTPException(status_code=404, detail=GROUP_NOT_FOUND)
        claimed = ids
    now = datetime.now(timezone.utc).isoformat()
    doc = {"id": "kb-" + uuid.uuid4().hex[:12], "tenantId": tenant, **clean, "source": "manual",
           "helpdesk": body.helpdesk, "createdBy": getattr(current_user, "username", None) or "system",
           "createdAt": now, "updatedAt": now}
    try:
        await raw(db).knowledge_docs.insert_one(dict(doc))
    except Exception:
        if claimed:
            await gaps.set_status(db, tenant, claimed, claimed_from, expect="written")
        raise
    return {"success": True, "id": doc["id"], "doc_id": doc["id"], "title": doc["title"], "helpdesk": doc["helpdesk"],
            "gapsWritten": len(claimed)}


def shape_docs(docs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """The per-document fields the screen reads: helpdesk (absent reads False, and never True on a shared
    document), starterKey and updatedAt (the creation time until the first edit)."""
    for doc in docs:
        doc["helpdesk"] = doc.get("helpdesk") is True and doc.get("tenantId") != "global"
        doc.setdefault("starterKey", None)
        doc["updatedAt"] = doc.get("updatedAt") or doc.get("createdAt")
    return docs


async def list_flags(db, user: TokenData) -> Dict[str, Any]:
    """What the Knowledge Base screen reads about the caller and the desk."""
    tenant = tenant_of(user)
    held = await rbac_service.get_user_permissions(user)

    def has(permission: str) -> bool:
        return "*" in held or permission in held

    if not desk_eligible(tenant):
        return {"canManageArticles": False, "canSeeGaps": False, "helpdeskCount": 0, "starterMissing": 0,
                "deskOff": True}
    manage = has("manage:ai_risks")
    return {
        "canManageArticles": manage,
        "canSeeGaps": manage and has("view:dashboard"),
        "helpdeskCount": await raw(db).knowledge_docs.count_documents({"tenantId": tenant, "helpdesk": True}),
        "starterMissing": await starter_missing(db, tenant),
        "deskOff": (await desk_settings.load(db, tenant)).mode == "off",
    }

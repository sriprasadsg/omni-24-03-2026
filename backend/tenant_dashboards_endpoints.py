"""Dashboards a tenant designs for itself ("Dashboard Studio").

A tenant admin (``manage:dashboards``) builds named dashboards from the widget catalogue
(``dashboard_widgets``) and publishes each to the whole tenant or to chosen roles. Everyone with
``view:dashboard`` sees the published dashboards shared with them, minus the widgets of screens
their role cannot read or their tenant has not bought, and may hide widgets for themselves.

Each document keeps the draft being edited apart from the published copy, so saving never changes
what users see until Publish. ``version`` makes two admins editing the same dashboard fail with 409
instead of overwriting each other. Every query names the caller's tenant itself: the database
wrapper scopes tenant callers, but leaves platform callers (``platform-admin``) unscoped, and their
dashboards must not mix with any tenant's.
"""
import logging
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator

import dashboard_widgets
from auth_types import TokenData
from database import get_database
from rbac_defaults import normalize_role
from rbac_service import rbac_service
from rbac_utils import is_super_admin, require_permission
from tenant_context import get_tenant_id

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/dashboards", tags=["Dashboard Studio"])

DESIGN = "manage:dashboards"
VIEW = "view:dashboard"
_INSTANCE_ID = re.compile(r"^[A-Za-z0-9_-]{1,40}$")
_COLUMNS = dashboard_widgets.GRID["columns"]


class Placement(BaseModel):
    i: str = Field(..., max_length=40)
    widget: str = Field(..., max_length=64)
    x: int = Field(..., ge=0, lt=_COLUMNS)
    y: int = Field(..., ge=0, le=dashboard_widgets.GRID["maxRows"])
    w: int = Field(..., ge=1, le=_COLUMNS)
    h: int = Field(..., ge=1, le=24)
    title: Optional[str] = Field(None, max_length=80)

    @field_validator("i")
    @classmethod
    def _instance_id(cls, v: str) -> str:
        if not _INSTANCE_ID.match(v):
            raise ValueError("widget instance ids use letters, digits, '-' and '_' only")
        return v


class Sharing(BaseModel):
    everyone: bool = False
    roles: List[str] = Field(default_factory=list, max_length=30)

    @field_validator("roles")
    @classmethod
    def _roles(cls, v: List[str]) -> List[str]:
        out: List[str] = []
        for role in v:
            role = str(role).strip()[:80]
            if role and role not in out:
                out.append(role)
        return out


class DashboardDraft(BaseModel):
    name: str = Field(..., min_length=1, max_length=80)
    description: str = Field("", max_length=280)
    widgets: List[Placement] = Field(default_factory=list, max_length=dashboard_widgets.GRID["maxWidgets"])
    sharing: Sharing = Field(default_factory=Sharing)

    @field_validator("name")
    @classmethod
    def _name(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("a dashboard needs a name")
        return v


class DraftUpdate(BaseModel):
    draft: DashboardDraft
    version: int = Field(..., ge=1)


class VersionOnly(BaseModel):
    version: int = Field(..., ge=1)


class HiddenWidgets(BaseModel):
    hidden: List[str] = Field(default_factory=list, max_length=dashboard_widgets.GRID["maxWidgets"])


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _scope() -> str:
    """The tenant whose dashboards this request works on; refused without a tenant context."""
    tenant_id = get_tenant_id()
    if not tenant_id:
        raise HTTPException(status_code=403, detail="No tenant context")
    return tenant_id


async def _perms(user: TokenData) -> List[str]:
    return await rbac_service.get_user_permissions(user)


def _is_designer(user: TokenData, perms: List[str]) -> bool:
    return "*" in perms or DESIGN in perms or is_super_admin(user.role)


def _check_layout(draft: DashboardDraft, perms: List[str], role: Optional[str]) -> None:
    """Every widget known, readable by the designer, sized within its limits, on the grid and
    not overlapping another; instance ids unique. Raises 400 naming the first problem."""
    seen = set()
    cells = set()
    for p in draft.widgets:
        spec = dashboard_widgets.widget(p.widget)
        if spec is None:
            raise HTTPException(status_code=400, detail=f"Unknown widget: {p.widget}")
        if not dashboard_widgets.can_read_view(spec["view"], perms, role):
            raise HTTPException(status_code=400, detail=(
                f"'{spec['title']}' is not available to your organization or role; remove it to save"))
        if p.i in seen:
            raise HTTPException(status_code=400, detail=f"Duplicate widget instance id: {p.i}")
        seen.add(p.i)
        size = spec["size"]
        if not (size["minW"] <= p.w and size["minH"] <= p.h <= size["maxH"]):
            raise HTTPException(status_code=400, detail=f"'{spec['title']}' size {p.w}x{p.h} is outside its limits")
        if p.x + p.w > _COLUMNS:
            raise HTTPException(status_code=400, detail=f"'{spec['title']}' runs past the right edge of the grid")
        for cx in range(p.x, p.x + p.w):
            for cy in range(p.y, p.y + p.h):
                if (cx, cy) in cells:
                    raise HTTPException(status_code=400, detail=f"'{spec['title']}' overlaps another widget")
                cells.add((cx, cy))


def _shared_with(layout: Optional[Dict[str, Any]], role: Optional[str]) -> bool:
    if not layout:
        return False
    sharing = layout.get("sharing") or {}
    if sharing.get("everyone"):
        return True
    mine = normalize_role(role)
    return any(normalize_role(r) == mine for r in sharing.get("roles") or [])


def _summary(doc: Dict[str, Any], layout: Dict[str, Any], designer: bool) -> Dict[str, Any]:
    out = {
        "id": doc["id"],
        "name": layout.get("name"),
        "description": layout.get("description", ""),
        "widgetCount": len(layout.get("widgets") or []),
        "status": doc.get("status", "draft"),
        "publishedAt": doc.get("publishedAt"),
        "updatedAt": doc.get("updatedAt"),
    }
    if designer:
        out.update({"version": doc.get("version", 1), "sharing": layout.get("sharing"),
                    "hasUnpublishedChanges": bool(doc.get("hasUnpublishedChanges"))})
    return out


async def _load(db, dashboard_id: str) -> Dict[str, Any]:
    doc = await db.tenant_dashboards.find_one({"id": dashboard_id, "tenantId": _scope()}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Dashboard not found")
    return doc


async def _audit(user: TokenData, action: str, doc: Dict[str, Any], details: str) -> None:
    try:
        from audit_service import get_audit_service
        await get_audit_service().log_action_async(
            user.username, action, "dashboard", doc["id"], details,
            tenant_id=user.tenant_id or "platform-admin")
    except Exception as exc:  # the change is made; a ledger hiccup must not undo it
        logger.warning("Dashboard audit entry failed for %s: %s", doc.get("id"), exc)


@router.get("/widgets")
async def list_widgets(user: TokenData = Depends(require_permission(VIEW))):
    """The catalogue for this user: every widget, marked available when its screen is readable."""
    perms = await _perms(user)
    readable = set(dashboard_widgets.readable_widget_ids(perms, user.role))
    return {
        "grid": dashboard_widgets.GRID,
        "widgets": [dict(w, available=w["id"] in readable) for w in dashboard_widgets.CATALOGUE["widgets"]],
    }


@router.get("")
async def list_dashboards(user: TokenData = Depends(require_permission(VIEW))):
    """Designers get every dashboard of the tenant (drafts included); others the published ones
    shared with their role."""
    db = get_database()
    perms = await _perms(user)
    designer = _is_designer(user, perms)
    docs = await db.tenant_dashboards.find({"tenantId": _scope()}, {"_id": 0}).to_list(length=200)
    out = []
    for doc in docs:
        if designer:
            out.append(_summary(doc, doc.get("draft") or {}, True))
        elif doc.get("status") == "published" and _shared_with(doc.get("published"), user.role):
            out.append(_summary(doc, doc["published"], False))
    out.sort(key=lambda d: (d.get("name") or "").lower())
    return {"dashboards": out, "canDesign": designer}


@router.get("/{dashboard_id}")
async def get_dashboard(dashboard_id: str, mode: Literal["published", "draft"] = "published",
                        user: TokenData = Depends(require_permission(VIEW))):
    """One dashboard to show (``mode=published``) or to edit (``mode=draft``, designers only).

    Widgets of screens the caller cannot read are left out and counted in ``withheld``."""
    db = get_database()
    perms = await _perms(user)
    designer = _is_designer(user, perms)
    doc = await _load(db, dashboard_id)
    if mode == "draft":
        if not designer:
            raise HTTPException(status_code=403, detail=f"Missing required permission: {DESIGN}")
        layout = doc.get("draft") or {}
    else:
        layout = doc.get("published") if doc.get("status") == "published" else None
        if not layout or not (designer or _shared_with(layout, user.role)):
            raise HTTPException(status_code=404, detail="Dashboard not found")
    widgets = layout.get("widgets") or []
    readable = set(dashboard_widgets.readable_widget_ids(perms, user.role))
    shown = [w for w in widgets if w.get("widget") in readable]
    prefs = await db.dashboard_user_prefs.find_one(
        {"dashboardId": dashboard_id, "user": user.username, "tenantId": _scope()}, {"_id": 0, "hidden": 1}) or {}
    body = _summary(doc, layout, designer)
    body.update({"widgets": shown, "withheld": len(widgets) - len(shown),
                 "hidden": [i for i in prefs.get("hidden") or [] if any(w["i"] == i for w in shown)],
                 "mode": mode})
    if mode == "draft":
        body["unavailable"] = [w for w in widgets if w.get("widget") not in readable]
    return body


@router.post("")
async def create_dashboard(body: DashboardDraft, user: TokenData = Depends(require_permission(DESIGN))):
    db = get_database()
    _check_layout(body, await _perms(user), user.role)
    now = _now()
    doc = {
        "id": f"dash-{uuid.uuid4().hex[:12]}",
        "tenantId": _scope(),
        "draft": body.model_dump(),
        "published": None,
        "status": "draft",
        "version": 1,
        "hasUnpublishedChanges": False,
        "createdBy": user.username, "createdAt": now,
        "updatedBy": user.username, "updatedAt": now,
    }
    await db.tenant_dashboards.insert_one(dict(doc))
    await _audit(user, "dashboard.created", doc, f"Created dashboard '{body.name}'")
    return _summary(doc, doc["draft"], True)


@router.put("/{dashboard_id}")
async def save_draft(dashboard_id: str, body: DraftUpdate, user: TokenData = Depends(require_permission(DESIGN))):
    """Save the draft. Users keep seeing the published copy until Publish."""
    db = get_database()
    _check_layout(body.draft, await _perms(user), user.role)
    doc = await _load(db, dashboard_id)
    if doc.get("version", 1) != body.version:
        raise HTTPException(status_code=409, detail="Someone else saved this dashboard; reload to see their changes")
    update = {
        "draft": body.draft.model_dump(),
        "version": body.version + 1,
        "hasUnpublishedChanges": doc.get("status") == "published",
        "updatedBy": user.username, "updatedAt": _now(),
    }
    res = await db.tenant_dashboards.update_one({"id": dashboard_id, "tenantId": _scope(), "version": body.version},
                                                {"$set": update})
    if getattr(res, "matched_count", 1) == 0:
        raise HTTPException(status_code=409, detail="Someone else saved this dashboard; reload to see their changes")
    doc.update(update)
    return _summary(doc, doc["draft"], True)


@router.post("/{dashboard_id}/publish")
async def publish_dashboard(dashboard_id: str, body: VersionOnly,
                            user: TokenData = Depends(require_permission(DESIGN))):
    """Make the saved draft what users see."""
    db = get_database()
    doc = await _load(db, dashboard_id)
    if doc.get("version", 1) != body.version:
        raise HTTPException(status_code=409, detail="Someone else saved this dashboard; reload before publishing")
    draft = doc.get("draft") or {}
    sharing = draft.get("sharing") or {}
    if not sharing.get("everyone") and not sharing.get("roles"):
        raise HTTPException(status_code=400, detail="Choose who sees this dashboard before publishing")
    now = _now()
    update = {"published": draft, "status": "published", "hasUnpublishedChanges": False,
              "version": body.version + 1, "publishedBy": user.username, "publishedAt": now,
              "updatedBy": user.username, "updatedAt": now}
    res = await db.tenant_dashboards.update_one({"id": dashboard_id, "tenantId": _scope(), "version": body.version},
                                                {"$set": update})
    if getattr(res, "matched_count", 1) == 0:
        raise HTTPException(status_code=409, detail="Someone else saved this dashboard; reload before publishing")
    doc.update(update)
    await _audit(user, "dashboard.published", doc, f"Published dashboard '{draft.get('name')}'")
    return _summary(doc, draft, True)


@router.post("/{dashboard_id}/unpublish")
async def unpublish_dashboard(dashboard_id: str, user: TokenData = Depends(require_permission(DESIGN))):
    """Take a dashboard away from users; the draft stays."""
    db = get_database()
    doc = await _load(db, dashboard_id)
    update = {"published": None, "status": "draft", "hasUnpublishedChanges": False,
              "version": doc.get("version", 1) + 1, "updatedBy": user.username, "updatedAt": _now()}
    await db.tenant_dashboards.update_one({"id": dashboard_id, "tenantId": _scope()}, {"$set": update})
    doc.update(update)
    await _audit(user, "dashboard.unpublished", doc, f"Unpublished dashboard '{(doc.get('draft') or {}).get('name')}'")
    return _summary(doc, doc.get("draft") or {}, True)


@router.delete("/{dashboard_id}")
async def delete_dashboard(dashboard_id: str, user: TokenData = Depends(require_permission(DESIGN))):
    db = get_database()
    doc = await _load(db, dashboard_id)
    await db.tenant_dashboards.delete_one({"id": dashboard_id, "tenantId": _scope()})
    await db.dashboard_user_prefs.delete_many({"dashboardId": dashboard_id, "tenantId": _scope()})
    await _audit(user, "dashboard.deleted", doc, f"Deleted dashboard '{(doc.get('draft') or {}).get('name')}'")
    return {"deleted": dashboard_id}


@router.put("/{dashboard_id}/hidden")
async def set_hidden_widgets(dashboard_id: str, body: HiddenWidgets,
                             user: TokenData = Depends(require_permission(VIEW))):
    """The widgets this user hides on a dashboard they can see; the admin's layout is unchanged."""
    db = get_database()
    perms = await _perms(user)
    doc = await _load(db, dashboard_id)
    layout = doc.get("published") if doc.get("status") == "published" else None
    if not layout or not (_is_designer(user, perms) or _shared_with(layout, user.role)):
        raise HTTPException(status_code=404, detail="Dashboard not found")
    known = {w["i"] for w in layout.get("widgets") or []}
    hidden = [i for i in dict.fromkeys(body.hidden) if i in known]
    scope = _scope()
    await db.dashboard_user_prefs.update_one(
        {"dashboardId": dashboard_id, "user": user.username, "tenantId": scope},
        {"$set": {"dashboardId": dashboard_id, "user": user.username, "tenantId": scope, "hidden": hidden,
                  "updatedAt": _now()}},
        upsert=True)
    return {"hidden": hidden}

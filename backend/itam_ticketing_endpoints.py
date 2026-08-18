"""ITAM Ticketing Endpoints (Phase 73 Plan 04) — the manual half of D-10: an
operator can create a Jira issue or ServiceNow incident on demand for any
asset or asset request via `POST /api/itam/tickets`.

Reuses `ticketing_bridge.create_ticket_for_itam_event` (D-09/D-10/D-11)
unchanged; this module is a thin HTTP wrapper around it — entity
resolution, dedup-aware 409, and auth gating only, no ticketing logic of
its own. Gated by `_require_itam_admin` (dual session/API-key auth + scope
narrowing, `itam_asset_endpoints.py`) — the same guard as the rest of the
ITAM surface (D-01/D-02), so the manual action inherits the identical
permission and API-key scope narrowing.

Must be registered in `router_registry.py` — a route module that is never
registered 404s every route it declares, a defect this project has
shipped before (see the module registration block below and its test
coverage in `test_itam_ticketing_bridge.py -k manual_create`).
"""
import logging
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from auth_types import TokenData
from database import get_database
from itam_asset_endpoints import _require_itam_admin
from ticketing_bridge import (
    ITAM_ENTITY_COLLECTIONS,
    ITAM_TICKET_EVENT_MANUAL,
    create_ticket_for_itam_event,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/itam/tickets", tags=["ITAM Ticketing"])


class ItamTicketCreateRequest(BaseModel):
    """`provider` is a strict two-value enum, never free text (73-UI-SPEC.md
    Component Notes for Executor; RESEARCH.md's V5 input-validation
    guidance) — an out-of-vocabulary value is refused by request
    validation before the handler body runs."""

    entityKind: Literal["asset", "asset_request"]
    entityId: str = Field(min_length=1)
    provider: Literal["jira", "servicenow"]


class ItamTicketResponse(BaseModel):
    ticket_provider: str
    ticket_ref: str
    ticket_url: Optional[str] = None


@router.post("", response_model=ItamTicketResponse)
async def create_itam_ticket(
    body: ItamTicketCreateRequest,
    current_user: TokenData = Depends(_require_itam_admin),
):
    """Manual "Create Ticket" action (D-10) for any ITAM asset or asset
    request.

    404 when the entity does not exist in the caller's tenant (the lookup
    filter always includes that entity kind's own tenant field, drawn from
    ITAM_ENTITY_COLLECTIONS, so a cross-tenant id looks identical to an
    unknown one — T-73-13). 409 when the entity already carries a ticket
    reference — never a second ticket for the same entity (T-73-15). 502
    when the bridge itself fails to create the ticket, mirroring
    compliance_remediation_endpoints.py's identical failure contract,
    which the console's error toast copy already assumes. The response is
    restricted to exactly the three ticket keys — the resolved ticketing
    configuration is never echoed (T-73-12).
    """
    tenant_id = current_user.tenant_id
    db = get_database()

    info = ITAM_ENTITY_COLLECTIONS[body.entityKind]
    collection = getattr(db, info.collection)
    entity = await collection.find_one(
        {info.id_field: body.entityId, info.tenant_field: tenant_id}
    )
    if not entity:
        raise HTTPException(status_code=404, detail="Entity not found")

    if entity.get("ticket_ref"):
        raise HTTPException(
            status_code=409,
            detail=f"Entity already has a ticket: {entity['ticket_ref']}",
        )

    result = await create_ticket_for_itam_event(
        db,
        body.entityKind,
        entity,
        tenant_id,
        event_type=ITAM_TICKET_EVENT_MANUAL,
        provider_override=body.provider,
    )
    if not result:
        raise HTTPException(status_code=502, detail="Ticket creation failed")

    return result

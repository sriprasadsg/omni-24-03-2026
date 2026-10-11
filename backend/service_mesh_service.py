from fastapi import APIRouter, Depends
from pydantic import BaseModel
from typing import List, Optional
import logging
from database import get_database
from authentication_service import get_current_user
from auth_types import TokenData

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/mesh", tags=["Service Mesh"])

_SUPER_ROLES = {"Super Admin", "super_admin", "platform-admin"}


# --- Models ---
class SidecarStatus(BaseModel):
    injected: bool
    version: str
    status: str  # Running, Failed, Pending


class MeshService(BaseModel):
    id: str
    name: str
    namespace: str
    sidecar: SidecarStatus
    health: str  # Healthy, Degraded, Unhealthy


class MeshMetric(BaseModel):
    timestamp: str
    serviceId: str
    requestCount: int
    errorCount: int
    latencyP50: float
    latencyP95: float
    latencyP99: float


class MeshGraphNode(BaseModel):
    id: str
    name: str
    type: str  # service, database, gateway


class MeshGraphEdge(BaseModel):
    source: str
    target: str
    weight: int  # Represents Ops/sec


class MeshGraph(BaseModel):
    nodes: List[MeshGraphNode]
    edges: List[MeshGraphEdge]


# No mesh data means an empty result: this page must never show invented
# services, traffic or topology (they were indistinguishable from real data).


def _tenant_id(user: TokenData) -> Optional[str]:
    role = getattr(user, "role", "")
    if role in _SUPER_ROLES:
        return None  # super-admins see all tenants
    return getattr(user, "tenant_id", None)


def _tenant_query(user: TokenData) -> dict:
    tid = _tenant_id(user)
    return {"tenantId": tid} if tid else {}


# --- Endpoints ---

@router.get("/services", response_model=List[MeshService])
async def get_services(current_user: TokenData = Depends(get_current_user)):
    """Return mesh services scoped to the caller's tenant (empty when none are reported)."""
    query = _tenant_query(current_user)
    try:
        db = get_database()
        docs = await db.mesh_services.find(query, {"_id": 0}).to_list(length=200)
        if docs:
            return [MeshService(**d) for d in docs]
    except Exception as exc:
        logger.warning("mesh_services DB query failed: %s", exc)

    return []


@router.get("/metrics", response_model=List[MeshMetric])
async def get_metrics(duration: str = "5m", current_user: TokenData = Depends(get_current_user)):
    """Return latest mesh metrics scoped to the caller's tenant (empty when none are reported)."""
    query = _tenant_query(current_user)
    try:
        db = get_database()
        docs = await db.mesh_metrics.find(query, {"_id": 0}).sort("timestamp", -1).limit(50).to_list(length=50)
        return [MeshMetric(**d) for d in docs]
    except Exception as exc:
        logger.warning("mesh_metrics DB query failed: %s", exc)
    return []


@router.get("/graph", response_model=MeshGraph)
async def get_topology_graph(current_user: TokenData = Depends(get_current_user)):
    """Return service dependency graph scoped to the caller's tenant."""
    query = _tenant_query(current_user)
    try:
        db = get_database()
        node_docs = await db.mesh_graph_nodes.find(query, {"_id": 0}).to_list(length=200)
        edge_docs = await db.mesh_graph_edges.find(query, {"_id": 0}).to_list(length=500)
        return MeshGraph(
            nodes=[MeshGraphNode(**n) for n in node_docs],
            edges=[MeshGraphEdge(**e) for e in edge_docs],
        )
    except Exception as exc:
        logger.warning("mesh_graph DB query failed: %s", exc)
    return MeshGraph(nodes=[], edges=[])

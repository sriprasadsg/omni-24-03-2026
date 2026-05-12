from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Dict, Optional
import datetime
import logging
from database import get_database

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/mesh", tags=["Service Mesh"])

# --- Models ---
class SidecarStatus(BaseModel):
    injected: bool
    version: str
    status: str # Running, Failed, Pending

class MeshService(BaseModel):
    id: str
    name: str
    namespace: str
    sidecar: SidecarStatus
    health: str # Healthy, Degraded, Unhealthy

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
    type: str # service, database, gateway

class MeshGraphEdge(BaseModel):
    source: str
    target: str
    weight: int # Represents Ops/sec

class MeshGraph(BaseModel):
    nodes: List[MeshGraphNode]
    edges: List[MeshGraphEdge]

# --- Mock Data ---
SERVICES = [
    MeshService(id="svc-1", name="frontend", namespace="default", sidecar=SidecarStatus(injected=True, version="1.18.0", status="Running"), health="Healthy"),
    MeshService(id="svc-2", name="auth-service", namespace="default", sidecar=SidecarStatus(injected=True, version="1.18.0", status="Running"), health="Healthy"),
    MeshService(id="svc-3", name="payment-service", namespace="default", sidecar=SidecarStatus(injected=True, version="1.18.0", status="Running"), health="Degraded"),
    MeshService(id="svc-4", name="inventory-service", namespace="default", sidecar=SidecarStatus(injected=True, version="1.18.0", status="Running"), health="Healthy"),
    MeshService(id="svc-5", name="notification-service", namespace="default", sidecar=SidecarStatus(injected=False, version="N/A", status="N/A"), health="Healthy")
]

# --- Endpoints ---
@router.get("/services", response_model=List[MeshService])
async def get_services():
    """Return mesh services from DB; fall back to built-in defaults when empty."""
    try:
        db = get_database()
        docs = await db.mesh_services.find({}, {"_id": 0}).to_list(length=200)
        if docs:
            return [MeshService(**d) for d in docs]
    except Exception as exc:
        logger.warning("mesh_services DB query failed: %s", exc)
    return SERVICES


@router.get("/metrics", response_model=List[MeshMetric])
async def get_metrics(duration: str = "5m"):
    """Return latest mesh metrics from DB; derive from service health when none stored."""
    now = datetime.datetime.now(datetime.timezone.utc)
    try:
        db = get_database()
        docs = await db.mesh_metrics.find({}, {"_id": 0}).sort("timestamp", -1).limit(50).to_list(length=50)
        if docs:
            return [MeshMetric(**d) for d in docs]
    except Exception as exc:
        logger.warning("mesh_metrics DB query failed: %s", exc)

    # Deterministic fallback derived from service health (no random)
    metrics = []
    for svc in SERVICES:
        if not svc.sidecar.injected:
            continue
        healthy = svc.health == "Healthy"
        metrics.append(MeshMetric(
            timestamp=now.isoformat(),
            serviceId=svc.id,
            requestCount=500 if healthy else 200,
            errorCount=5 if healthy else 30,
            latencyP50=25.0 if healthy else 150.0,
            latencyP95=75.0 if healthy else 400.0,
            latencyP99=150.0 if healthy else 800.0,
        ))
    return metrics


@router.get("/graph", response_model=MeshGraph)
async def get_topology_graph():
    """Return service dependency graph from DB; use built-in topology when empty."""
    try:
        db = get_database()
        node_docs = await db.mesh_graph_nodes.find({}, {"_id": 0}).to_list(length=200)
        edge_docs = await db.mesh_graph_edges.find({}, {"_id": 0}).to_list(length=500)
        if node_docs:
            return MeshGraph(
                nodes=[MeshGraphNode(**n) for n in node_docs],
                edges=[MeshGraphEdge(**e) for e in edge_docs],
            )
    except Exception as exc:
        logger.warning("mesh_graph DB query failed: %s", exc)

    nodes = [
        MeshGraphNode(id="gateway", name="Ingress Gateway", type="gateway"),
        *[MeshGraphNode(id=s.id, name=s.name, type="service") for s in SERVICES],
        MeshGraphNode(id="db-1", name="Primary DB", type="database"),
    ]
    edges = [
        MeshGraphEdge(source="gateway", target="svc-1", weight=100),
        MeshGraphEdge(source="svc-1", target="svc-2", weight=80),
        MeshGraphEdge(source="svc-1", target="svc-3", weight=40),
        MeshGraphEdge(source="svc-1", target="svc-4", weight=60),
        MeshGraphEdge(source="svc-3", target="svc-5", weight=20),
        MeshGraphEdge(source="svc-2", target="db-1", weight=80),
        MeshGraphEdge(source="svc-4", target="db-1", weight=60),
    ]
    return MeshGraph(nodes=nodes, edges=edges)

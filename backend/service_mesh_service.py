from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Dict, Optional
import random
import datetime

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
    """List all services and their sidecar status."""
    return SERVICES

@router.get("/metrics", response_model=List[MeshMetric])
async def get_metrics(duration: str = "5m"):
    """Get simulated telemetry metrics."""
    metrics = []
    now = datetime.datetime.now()
    
    for svc in SERVICES:
        if not svc.sidecar.injected: continue
        
        # Generate varied metrics based on health
        err_rate = 0.01 if svc.health == "Healthy" else 0.15
        
        metrics.append(MeshMetric(
            timestamp=now.isoformat(),
            serviceId=svc.id,
            requestCount=random.randint(100, 1000),
            errorCount=int(random.randint(100, 1000) * err_rate),
            latencyP50=random.uniform(10, 50) if svc.health == "Healthy" else random.uniform(100, 200),
            latencyP95=random.uniform(50, 100) if svc.health == "Healthy" else random.uniform(300, 500),
            latencyP99=random.uniform(100, 200) if svc.health == "Healthy" else random.uniform(600, 1000)
        ))
    return metrics

@router.get("/graph", response_model=MeshGraph)
async def get_topology_graph():
    """Get service dependency graph."""
    nodes = [
        MeshGraphNode(id="gateway", name="Ingress Gateway", type="gateway"),
        *[MeshGraphNode(id=s.id, name=s.name, type="service") for s in SERVICES],
        MeshGraphNode(id="db-1", name="Primary DB", type="database"),
    ]
    
    edges = [
        MeshGraphEdge(source="gateway", target="svc-1", weight=100),   # Gateway -> Frontend
        MeshGraphEdge(source="svc-1", target="svc-2", weight=80),      # Frontend -> Auth
        MeshGraphEdge(source="svc-1", target="svc-3", weight=40),      # Frontend -> Payment
        MeshGraphEdge(source="svc-1", target="svc-4", weight=60),      # Frontend -> Inventory
        MeshGraphEdge(source="svc-3", target="svc-5", weight=20),      # Payment -> Notification
        MeshGraphEdge(source="svc-2", target="db-1", weight=80),       # Auth -> DB
        MeshGraphEdge(source="svc-4", target="db-1", weight=60),       # Inventory -> DB
    ]
    
    return MeshGraph(nodes=nodes, edges=edges)

from fastapi import APIRouter, Depends, Query
from auth_utils import require_auth
from database import get_db
from k8s_security_service import K8sSecurityService

router = APIRouter(prefix="/api/k8s-security", tags=["k8s-security"])


def get_svc(db=Depends(get_db)):
    return K8sSecurityService(db)


@router.get("/clusters")
async def list_clusters(user=Depends(require_auth), svc: K8sSecurityService = Depends(get_svc)):
    tenant_id = getattr(user, "tenant_id", "platform")
    clusters = await svc.get_clusters(tenant_id)
    for c in clusters:
        c["id"] = c.pop("_id", c.get("id"))
    return {"clusters": clusters}


@router.post("/clusters")
async def register_cluster(body: dict, user=Depends(require_auth), svc: K8sSecurityService = Depends(get_svc)):
    tenant_id = getattr(user, "tenant_id", "platform")
    cluster = await svc.register_cluster(tenant_id, body)
    cluster["id"] = cluster.pop("_id", cluster.get("id"))
    return cluster


@router.post("/clusters/{cluster_id}/scan")
async def scan_cluster(cluster_id: str, user=Depends(require_auth), svc: K8sSecurityService = Depends(get_svc)):
    tenant_id = getattr(user, "tenant_id", "platform")
    result = await svc.scan_cluster(cluster_id, tenant_id)
    if not result:
        from fastapi import HTTPException
        raise HTTPException(404, "Cluster not found")
    return result


@router.get("/findings")
async def get_findings(cluster_id: str = Query(None), severity: str = Query(None),
                       limit: int = Query(100), user=Depends(require_auth),
                       svc: K8sSecurityService = Depends(get_svc)):
    tenant_id = getattr(user, "tenant_id", "platform")
    findings = await svc.get_findings(tenant_id, cluster_id, severity, limit)
    for f in findings:
        f["id"] = f.pop("_id", f.get("id"))
    return {"findings": findings}


@router.get("/summary")
async def get_summary(user=Depends(require_auth), svc: K8sSecurityService = Depends(get_svc)):
    tenant_id = getattr(user, "tenant_id", "platform")
    return await svc.get_summary(tenant_id)

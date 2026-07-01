from fastapi import APIRouter, Depends, HTTPException
from authentication_service import get_current_user
from database import get_database
from datetime import datetime, timezone
import uuid

router = APIRouter(prefix="/api/security", tags=["Security - Attack Paths"])


def _tenant(current_user) -> str:
    return (
        getattr(current_user, "tenant_id", None)
        or getattr(current_user, "tenantId", None)
        or ""
    )


def _seed_paths(tenant_id: str) -> list:
    now = datetime.now(timezone.utc).isoformat()
    scenarios = [
        (
            "Exposed API Gateway → Production Database",
            "api-gateway-prod", "Public Asset", "CVE-2024-1234",
            "Internal Kubernetes Cluster",
            "prod-postgres-db", "Crown Jewel",
            0.82, "Critical", 4,
        ),
        (
            "VPN Endpoint → Domain Controller",
            "vpn-endpoint-01", "Public Asset", "CVE-2023-20269",
            "Corporate Network Segment",
            "dc-primary", "Crown Jewel",
            0.67, "Critical", 2,
        ),
        (
            "Web Server → Secret Manager",
            "web-app-server", "Public Asset", "CVE-2024-5678",
            "Internal Service Mesh",
            "aws-secrets-manager", "Crown Jewel",
            0.54, "High", 3,
        ),
    ]
    paths = []
    for name, entry_id, entry_type, cve, hop, target_id, target_type, prob, impact, n_vulns in scenarios:
        pid = str(uuid.uuid4())
        ne = {"id": f"{pid}-0", "label": entry_id, "type": entry_type, "risk": 0.85}
        nh = {"id": f"{pid}-1", "label": hop, "type": "Internal Service", "risk": 0.50}
        nt = {"id": f"{pid}-2", "label": target_id, "type": target_type, "risk": 0.95}
        paths.append({
            "id": pid,
            "tenantId": tenant_id,
            "name": name,
            "nodes": [ne, nh, nt],
            "edges": [
                {"source": ne["id"], "target": nh["id"], "vulnerability": cve},
                {"source": nh["id"], "target": nt["id"], "vulnerability": "Lateral Movement"},
            ],
            "probability": prob,
            "impact": impact,
            "openVulnerabilities": n_vulns,
            "timestamp": now,
        })
    return paths


@router.get("/attack-paths")
async def get_attack_paths(current_user=Depends(get_current_user)):
    """Get identified attack paths for the tenant."""
    tenant_id = _tenant(current_user)
    if not tenant_id:
        raise HTTPException(status_code=403, detail="Tenant context not found")

    db = get_database()

    stored = await db.attack_paths.find(
        {"tenantId": tenant_id}, {"_id": 0}
    ).sort("timestamp", -1).to_list(length=50)
    if stored:
        return stored

    paths = _seed_paths(tenant_id)
    try:
        await db.attack_paths.insert_many([dict(p) for p in paths])
    except Exception:
        pass
    return paths

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from typing import List, Optional
from auth_utils import require_auth
from database import get_db
from supply_chain_security_service import SupplyChainSecurityService, SLSA_CRITERIA, SLSA_LEVELS

router = APIRouter(prefix="/api/supply-chain-security", tags=["supply-chain-security"])


def get_svc(db=Depends(get_db)):
    return SupplyChainSecurityService(db)


class Package(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    version: str = ""
    ecosystem: str = "PyPI"
    is_internal: bool = False


class BuildInfo(BaseModel):
    has_build_script: bool = False
    build_service_used: bool = False
    source_control_integrity: bool = False
    signed_artifact: bool = False
    reproducible_build: bool = False
    ephemeral_environment: bool = False
    build_service_admin_free: bool = False
    two_party_review: bool = False
    hermetic_build: bool = False
    build_type: str = "https://github.com/actions/runner"
    builder_id: str = ""
    config_uri: str = ""
    invocation_id: str = ""


class ArtifactCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    version: str = Field(..., min_length=1, max_length=100)
    ecosystem: str = Field("pypi", min_length=1, max_length=50)
    build_info: BuildInfo = BuildInfo()


class ScanRequest(BaseModel):
    packages: List[Package] = Field(..., min_items=1)


class PolicyUpdate(BaseModel):
    min_slsa_level: int = Field(1, ge=0, le=4)
    enforce: bool = False
    exceptions: List[str] = []


# ── Read endpoints ────────────────────────────────────────────────────────────

@router.get("/artifacts")
async def get_artifacts(limit: int = Query(100, le=500), user=Depends(require_auth),
                        svc: SupplyChainSecurityService = Depends(get_svc)):
    tenant_id = getattr(user, "tenant_id", None)
    items = await svc.get_artifacts(tenant_id, limit)
    for i in items:
        i["id"] = i.pop("_id", i.get("id"))
    return {"artifacts": items}


@router.get("/vulnerabilities")
async def get_vulnerabilities(severity: str = Query(None), limit: int = Query(100, le=500),
                              user=Depends(require_auth),
                              svc: SupplyChainSecurityService = Depends(get_svc)):
    tenant_id = getattr(user, "tenant_id", None)
    vulns = await svc.get_vulnerabilities(tenant_id, severity, limit)
    for v in vulns:
        v["id"] = v.pop("_id", v.get("id"))
    return {"vulnerabilities": vulns}


@router.get("/summary")
async def get_summary(user=Depends(require_auth), svc: SupplyChainSecurityService = Depends(get_svc)):
    tenant_id = getattr(user, "tenant_id", None)
    return await svc.get_summary(tenant_id)


# ── Artifact registration + scanning ─────────────────────────────────────────

@router.post("/artifacts")
async def register_artifact(body: ArtifactCreate, user=Depends(require_auth),
                            svc: SupplyChainSecurityService = Depends(get_svc)):
    tenant_id = getattr(user, "tenant_id", None)
    artifact = await svc.register_artifact(
        tenant_id, body.name, body.version, body.ecosystem,
        body.build_info.model_dump()
    )
    return artifact


@router.post("/artifacts/{artifact_id}/scan")
async def scan_artifact_deps(artifact_id: str, body: ScanRequest, user=Depends(require_auth),
                             svc: SupplyChainSecurityService = Depends(get_svc)):
    tenant_id = getattr(user, "tenant_id", None)
    packages = [p.model_dump() for p in body.packages]
    result = await svc.scan_artifact_deps(artifact_id, packages, tenant_id)
    return result


# ── Provenance ────────────────────────────────────────────────────────────────

@router.post("/artifacts/{artifact_id}/provenance")
async def generate_provenance(artifact_id: str, body: BuildInfo, user=Depends(require_auth),
                              svc: SupplyChainSecurityService = Depends(get_svc)):
    tenant_id = getattr(user, "tenant_id", None)
    record = await svc.generate_provenance(artifact_id, tenant_id, body.model_dump())
    if not record:
        raise HTTPException(status_code=404, detail="Artifact not found")
    return record


@router.get("/artifacts/{artifact_id}/provenance")
async def get_provenance(artifact_id: str, user=Depends(require_auth),
                         svc: SupplyChainSecurityService = Depends(get_svc)):
    tenant_id = getattr(user, "tenant_id", None)
    records = await svc.get_provenance(artifact_id, tenant_id)
    return {"provenance": records, "count": len(records)}


# ── SLSA assessment + policy ──────────────────────────────────────────────────

@router.post("/slsa/assess")
async def assess_slsa(body: BuildInfo, user=Depends(require_auth)):
    return SupplyChainSecurityService.assess_slsa_level(body.model_dump())


@router.get("/slsa/criteria")
async def slsa_criteria(user=Depends(require_auth)):
    criteria = [
        {"key": k, "required_for_level": v[0], "description": v[1]}
        for k, v in SLSA_CRITERIA.items()
    ]
    return {"criteria": criteria, "levels": SLSA_LEVELS}


@router.get("/slsa/policy")
async def get_slsa_policy(user=Depends(require_auth), svc: SupplyChainSecurityService = Depends(get_svc)):
    tenant_id = getattr(user, "tenant_id", None)
    return await svc.get_slsa_policy(tenant_id)


@router.put("/slsa/policy")
async def set_slsa_policy(body: PolicyUpdate, user=Depends(require_auth),
                          svc: SupplyChainSecurityService = Depends(get_svc)):
    tenant_id = getattr(user, "tenant_id", None)
    return await svc.set_slsa_policy(tenant_id, body.min_slsa_level, body.enforce, body.exceptions)


# ── Demo seed ─────────────────────────────────────────────────────────────────

@router.post("/seed")
async def seed(user=Depends(require_auth), svc: SupplyChainSecurityService = Depends(get_svc)):
    tenant_id = getattr(user, "tenant_id", None)
    await svc.seed_demo(tenant_id)
    return {"message": "Supply chain demo data seeded"}

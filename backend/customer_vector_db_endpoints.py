"""Customer Vector DB REST API endpoints."""

from __future__ import annotations

import uuid
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any, Set

from auth_types import TokenData
from rbac_service import rbac_service
from rbac_utils import is_super_admin
from customer_vector_db.customer_vector_db import customer_vector_db, SearchResult, VectorCollection
from customer_vector_db.vector_index_manager import vector_index_manager, IndexConfig
from customer_vector_db.vector_access_controller import vector_access_controller, Role, DataClassification, Operation
from customer_vector_db.vector_pipeline import vector_pipeline, DataSource, SourceType, PipelineStatus, PipelineRun

router = APIRouter(prefix="/api/vector", tags=["Customer Vector DB"])


def _require_own_tenant(current_user: TokenData, tenant_id: str) -> None:
    """Non-super-admin callers may only operate on their own tenant's vector data.

    The `view:vector_db` permission (checked at the route dependency) only proves
    the caller is a tenant/super admin somewhere — it says nothing about *which*
    tenant. This closes the cross-tenant gap without it.
    """
    if is_super_admin(current_user.role):
        return
    if current_user.tenant_id != tenant_id:
        raise HTTPException(status_code=403, detail="Not authorized for this tenant's vector data")


# Request/Response Models
class CreateCollectionRequest(BaseModel):
    tenant_id: str
    collection_name: str
    dimensions: int = 1536
    metadata: Optional[Dict[str, Any]] = None


class AddVectorsRequest(BaseModel):
    tenant_id: str
    collection_name: str
    embeddings: List[List[float]]
    documents: List[str]
    metadatas: List[Dict[str, Any]]
    ids: Optional[List[str]] = None


class QueryVectorsRequest(BaseModel):
    tenant_id: str
    collection_name: str
    query_embedding: List[float]
    n_results: int = 10
    where: Optional[Dict[str, Any]] = None
    include: List[str] = ["documents", "metadatas", "distances"]


class SetIndexConfigRequest(BaseModel):
    collection_name: str
    m: int
    ef_construction: int
    ef_search: int
    max_elements: int


class SetAccessPolicyRequest(BaseModel):
    collection_name: str
    tenant_id: str
    role_permissions: Optional[Dict[Role, Set[Operation]]] = None
    classification: DataClassification = DataClassification.INTERNAL
    pii_fields: Optional[List[str]] = None
    quarantine_enabled: bool = False


class AddDataSourceRequest(BaseModel):
    name: str
    source_type: SourceType
    config: Dict[str, Any]
    tenant_id: str
    collection_name: str
    enabled: bool = True
    sync_interval_seconds: int = 3600


# Customer Vector DB Endpoints
@router.post("/collections/create")
async def create_vector_collection(
    request: CreateCollectionRequest,
    current_user: TokenData = Depends(rbac_service.has_permission("view:vector_db")),
):
    """Create a tenant-isolated vector collection."""
    _require_own_tenant(current_user, request.tenant_id)

    try:
        full_name = customer_vector_db.create_collection(
            request.tenant_id,
            request.collection_name,
            request.dimensions,
            request.metadata,
        )
        return {"full_name": full_name, "status": "created"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/collections/add_vectors")
async def add_vectors_to_collection(
    request: AddVectorsRequest,
    current_user: TokenData = Depends(rbac_service.has_permission("view:vector_db")),
):
    """Add vectors to a tenant collection."""
    _require_own_tenant(current_user, request.tenant_id)

    try:
        result = customer_vector_db.add_vectors(
            request.tenant_id,
            request.collection_name,
            request.embeddings,
            request.documents,
            request.metadatas,
            request.ids,
        )
        return {"status": "added", "count": result["count"], "ids": result["ids"]}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/collections/query")
async def query_vector_collection(
    request: QueryVectorsRequest,
    current_user: TokenData = Depends(rbac_service.has_permission("view:vector_db")),
):
    """Query a tenant vector collection."""
    _require_own_tenant(current_user, request.tenant_id)

    try:
        results = customer_vector_db.query(
            request.tenant_id,
            request.collection_name,
            request.query_embedding,
            request.n_results,
            request.where,
            request.include,
        )
        return results
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/collections/{tenant_id}")
async def list_vector_collections(
    tenant_id: str,
    current_user: TokenData = Depends(rbac_service.has_permission("view:vector_db")),
):
    """List collections for a tenant."""
    _require_own_tenant(current_user, tenant_id)

    return customer_vector_db.list_collections(tenant_id)


@router.delete("/collections/{tenant_id}/{collection_name}")
async def delete_vector_collection(
    tenant_id: str,
    collection_name: str,
    current_user: TokenData = Depends(rbac_service.has_permission("view:vector_db")),
):
    """Delete a tenant vector collection."""
    _require_own_tenant(current_user, tenant_id)

    success = customer_vector_db.delete_collection(tenant_id, collection_name)
    if not success:
        raise HTTPException(status_code=404, detail="Collection not found")
    return {"status": "deleted"}


# Index Manager Endpoints
@router.post("/index/{collection_name}/config")
async def set_index_config(
    collection_name: str,
    request: SetIndexConfigRequest,
    current_user: TokenData = Depends(rbac_service.has_permission("view:vector_db")),
):
    """Set HNSW index configuration for a collection."""
    config = IndexConfig(**request.dict())
    vector_index_manager.set_config(collection_name, config)
    return {"status": "configured"}


@router.post("/index/{collection_name}/auto_tune")
async def auto_tune_index(
    collection_name: str,
    vector_count: int,
    current_user: TokenData = Depends(rbac_service.has_permission("view:vector_db")),
):
    """Auto-tune index parameters based on vector count."""
    config = vector_index_manager.auto_tune(collection_name, vector_count)
    return {"status": "tuned", "new_config": config}


@router.get("/index/{collection_name}/stats")
async def get_index_stats(
    collection_name: str,
    current_user: TokenData = Depends(rbac_service.has_permission("view:vector_db")),
):
    """Get index performance statistics."""
    stats = vector_index_manager.get_stats(collection_name)
    if not stats:
        raise HTTPException(status_code=404, detail="Index stats not found")
    return stats


# Access Controller Endpoints
@router.post("/access/policy")
async def set_access_policy(
    request: SetAccessPolicyRequest,
    current_user: TokenData = Depends(rbac_service.has_permission("view:vector_db")),
):
    """Set access policy for a vector collection."""
    _require_own_tenant(current_user, request.tenant_id)

    vector_access_controller.set_policy(
        request.tenant_id,
        request.collection_name,
        request.role_permissions,
        request.classification,
        request.pii_fields,
        request.quarantine_enabled,
    )
    return {"status": "policy_set"}


@router.get("/access/policy")
async def get_access_policy(
    tenant_id: str,
    collection_name: str,
    current_user: TokenData = Depends(rbac_service.has_permission("view:vector_db")),
):
    """Get access policy for a vector collection."""
    _require_own_tenant(current_user, tenant_id)
    policy = vector_access_controller.get_policy(tenant_id, collection_name)
    if not policy:
        raise HTTPException(status_code=404, detail="Policy not found")
    return {
        "collection_name": policy.collection_name,
        "tenant_id": policy.tenant_id,
        "role_permissions": {role.value: [op.value for op in ops] for role, ops in policy.role_permissions.items()},
        "classification": policy.classification.value,
        "pii_fields": list(policy.pii_fields),
        "quarantine_enabled": policy.quarantine_enabled,
    }


@router.get("/access/log")
async def get_access_log(
    tenant_id: str = "",
    user_id: str = "",
    limit: int = 100,
    current_user: TokenData = Depends(rbac_service.has_permission("view:vector_db")),
):
    """Retrieve vector access audit log."""
    # Non-super-admins are pinned to their own tenant regardless of what's
    # passed — an empty tenant_id would otherwise return every tenant's log.
    if not is_super_admin(current_user.role):
        tenant_id = current_user.tenant_id or ""

    return vector_access_controller.get_audit_log(tenant_id, user_id, limit)


# Vector Pipeline Endpoints
@router.post("/pipeline/sources")
async def add_data_source(
    request: AddDataSourceRequest,
    current_user: TokenData = Depends(rbac_service.has_permission("view:vector_db")),
):
    """Add a data source for the vector ingestion pipeline."""
    _require_own_tenant(current_user, request.tenant_id)

    source_id = str(uuid.uuid4())
    source = DataSource(
        source_id=source_id,
        name=request.name,
        source_type=request.source_type,
        config=request.config,
        tenant_id=request.tenant_id,
        collection_name=request.collection_name,
        enabled=request.enabled,
        sync_interval_seconds=request.sync_interval_seconds,
    )
    vector_pipeline.add_source(source)
    return {"source_id": source_id, "status": "added"}


@router.post("/pipeline/{source_id}/run")
async def run_pipeline_for_source(
    source_id: str,
    current_user: TokenData = Depends(rbac_service.has_permission("view:vector_db")),
):
    """Manually trigger pipeline run for a specific source."""
    source = vector_pipeline.get_source(source_id)
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")
    _require_own_tenant(current_user, source.tenant_id)

    run = await vector_pipeline.process_source(source_id)
    return run


@router.get("/pipeline/runs")
async def list_pipeline_runs(
    source_id: str = "",
    limit: int = 20,
    current_user: TokenData = Depends(rbac_service.has_permission("view:vector_db")),
):
    """List pipeline runs."""
    if source_id:
        source = vector_pipeline.get_source(source_id)
        if source:
            _require_own_tenant(current_user, source.tenant_id)
    elif not is_super_admin(current_user.role):
        # No source_id given and list_runs() has no tenant filter of its own —
        # a non-super-admin can't be shown "all runs" without leaking other
        # tenants', so require narrowing to a specific (ownership-checked) source.
        raise HTTPException(status_code=400, detail="source_id is required")

    return vector_pipeline.list_runs(source_id, limit)


@router.get("/pipeline/sources")
async def list_pipeline_sources(
    tenant_id: str = "",
    current_user: TokenData = Depends(rbac_service.has_permission("view:vector_db")),
):
    """List configured data sources for pipelines."""
    if not is_super_admin(current_user.role):
        tenant_id = current_user.tenant_id or ""
    return vector_pipeline.list_sources(tenant_id)


@router.post("/pipeline/scheduler/start")
async def start_pipeline_scheduler(
    current_user: TokenData = Depends(rbac_service.has_permission("view:vector_db")),
):
    """Start background scheduler for pipelines."""
    await vector_pipeline.start_scheduler()
    return {"status": "scheduler_started"}


@router.post("/pipeline/scheduler/stop")
async def stop_pipeline_scheduler(
    current_user: TokenData = Depends(rbac_service.has_permission("view:vector_db")),
):
    """Stop background scheduler for pipelines."""
    await vector_pipeline.stop_scheduler()
    return {"status": "scheduler_stopped"}
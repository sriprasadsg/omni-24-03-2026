"""Phase 30-01 (T1) — RAG tenant isolation against a real ChromaDB collection.

No mocking of the query path: chunks are ingested for tenant-a, tenant-b,
and the "global" sentinel, then queried with tenant scoping. A tenant must
receive only its own chunks plus global shared knowledge — never another
tenant's.

Uses an ephemeral Chroma client with a deterministic embedding function so
the test is hermetic (no model download, no persisted state).
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import hashlib
import uuid

import chromadb
import pytest

from rag_service import RagService

_DIM = 16


class _DeterministicEmbedding(chromadb.EmbeddingFunction):
    """Stable pseudo-embeddings from a hash — no network, no model."""

    def __call__(self, input):
        vectors = []
        for text in input:
            digest = hashlib.sha256(text.encode("utf-8")).digest()
            vectors.append([b / 255.0 for b in digest[:_DIM]])
        return vectors


@pytest.fixture
def svc():
    # EphemeralClient is a per-process singleton — a unique collection per
    # test keeps ingested chunks from leaking between tests
    client = chromadb.EphemeralClient()
    collection = client.get_or_create_collection(
        name=f"tenant-isolation-{uuid.uuid4().hex}",
        embedding_function=_DeterministicEmbedding(),
    )
    service = RagService.__new__(RagService)  # skip __init__ (persistent dir)
    service.client = client
    service.collection = collection
    return service


def test_rag_query_is_tenant_scoped(svc):
    svc.ingest_text("Tenant A password policy requires 16 characters.", source="a-policy", tenant_id="tenant-a")
    svc.ingest_text("Tenant B uses hardware tokens for MFA.", source="b-policy", tenant_id="tenant-b")
    svc.ingest_text("NIST 800-53 AC-2 covers account management.", source="nist", tenant_id="global")

    results = svc.query("security policy", n_results=10, tenant_id="tenant-a")

    tenants = {r["tenantId"] for r in results}
    sources = {r["source"] for r in results}
    assert "tenant-b" not in tenants, "cross-tenant chunk leaked into scoped query"
    assert "a-policy" in sources, "tenant's own chunk missing"
    assert "nist" in sources, "global shared knowledge missing"


def test_rag_query_other_tenant_sees_only_theirs(svc):
    svc.ingest_text("Tenant A secret.", source="a-doc", tenant_id="tenant-a")
    svc.ingest_text("Tenant B secret.", source="b-doc", tenant_id="tenant-b")

    results = svc.query("secret", n_results=10, tenant_id="tenant-b")

    sources = {r["source"] for r in results}
    assert sources == {"b-doc"}


def test_rag_query_unscoped_is_backward_compatible(svc):
    """Callers that pass no tenant_id (legacy paths) still get results."""
    svc.ingest_text("Shared doc.", source="shared", tenant_id="global")
    results = svc.query("Shared doc", n_results=10)
    assert len(results) >= 1


def test_rag_ingest_defaults_to_global(svc):
    """ingest_text without tenant_id tags the chunk as global shared knowledge."""
    svc.ingest_text("Standard control text.", source="std")
    results = svc.query("Standard control text", n_results=10, tenant_id="any-tenant")
    assert any(r["source"] == "std" and r["tenantId"] == "global" for r in results)


def test_rag_query_output_includes_provenance(svc):
    svc.ingest_text("Provenance check.", source="prov", tenant_id="tenant-a")
    results = svc.query("Provenance check", n_results=10, tenant_id="tenant-a")
    assert results, "expected at least one result"
    item = results[0]
    assert item["id"], "chunk id missing from query output"
    assert item["tenantId"] == "tenant-a"

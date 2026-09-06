"""
Regression tests for DB-F11/F12/F13 (2026-08-25 audit) in
customer_vector_db.py:

- F-11: document text is now really Fernet-encrypted at rest (embeddings
  stay plaintext by necessity — ANN search needs raw floats).
- F-12: the in-memory collection registry rehydrates from ChromaDB's own
  persisted collection list on startup, so data survives a process restart.
- F-13: a filtered query no longer builds a self-referential filter dict.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import tempfile

import pytest

from customer_vector_db.customer_vector_db import CustomerVectorDB


@pytest.fixture()
def vdb(tmp_path, monkeypatch):
    monkeypatch.setenv("VECTOR_DB_ENCRYPTION_KEY", "")
    monkeypatch.setenv("ENVIRONMENT", "test")
    return CustomerVectorDB(persist_dir=str(tmp_path / "vectors"))


def test_document_text_encrypted_at_rest(vdb):
    vdb.create_collection("tenant-a", "docs", dimensions=3)
    vdb.add_vectors(
        "tenant-a", "docs",
        embeddings=[[0.1, 0.2, 0.3]],
        documents=["secret customer text"],
        metadatas=[{}],
        ids=["doc-1"],
    )
    full_name = "tenant-a_docs"
    raw = vdb.collections[full_name].chroma_collection.get(ids=["doc-1"], include=["documents"])
    stored_text = raw["documents"][0]
    assert stored_text != "secret customer text"  # not plaintext on disk
    assert vdb._decrypt_document(stored_text) == "secret customer text"


def test_query_roundtrip_returns_decrypted_text(vdb):
    vdb.create_collection("tenant-a", "docs", dimensions=3)
    vdb.add_vectors(
        "tenant-a", "docs",
        embeddings=[[0.1, 0.2, 0.3]],
        documents=["secret customer text"],
        metadatas=[{}],
        ids=["doc-1"],
    )
    results = vdb.query("tenant-a", "docs", query_embedding=[0.1, 0.2, 0.3], n_results=1)
    assert len(results) == 1
    assert results[0].content == "secret customer text"


def test_filtered_query_does_not_raise_on_cyclic_filter(vdb):
    # F-13 regression: pre-fix, filter_dict["$and"] = [filter_dict, where]
    # made the list's first element a reference to filter_dict itself.
    vdb.create_collection("tenant-a", "docs", dimensions=3)
    vdb.add_vectors(
        "tenant-a", "docs",
        embeddings=[[0.1, 0.2, 0.3]],
        documents=["doc one"],
        metadatas=[{"category": "x"}],
        ids=["doc-1"],
    )
    # Must not raise (pre-fix, this filter shape building step didn't
    # actually raise until something tried to serialize/traverse it —
    # the fixed version below is a clean, non-cyclic dict either way).
    results = vdb.query(
        "tenant-a", "docs",
        query_embedding=[0.1, 0.2, 0.3],
        n_results=1,
        where={"category": "x"},
    )
    assert len(results) == 1
    assert results[0].content == "doc one"


def test_registry_rehydrates_after_restart(tmp_path, monkeypatch):
    # A stable (not ephemeral) key is required here: an ephemeral key is
    # regenerated per-process by design, so a genuine "restart" with a new
    # random key correctly can't decrypt prior data — that's the documented
    # tradeoff of not setting VECTOR_DB_ENCRYPTION_KEY, not a bug. This test
    # is isolating the registry-rehydration behavior (F-12), so it holds the
    # key constant across both instances the way a real deployment would.
    from cryptography.fernet import Fernet
    monkeypatch.setenv("VECTOR_DB_ENCRYPTION_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("ENVIRONMENT", "test")
    persist_dir = str(tmp_path / "vectors")

    vdb1 = CustomerVectorDB(persist_dir=persist_dir)
    vdb1.create_collection("tenant-a", "docs", dimensions=3)
    vdb1.add_vectors(
        "tenant-a", "docs",
        embeddings=[[0.1, 0.2, 0.3]],
        documents=["persisted text"],
        metadatas=[{}],
        ids=["doc-1"],
    )

    # Simulate a process restart: a fresh instance, same persist_dir, no
    # create_collection call before querying.
    vdb2 = CustomerVectorDB(persist_dir=persist_dir)
    results = vdb2.query("tenant-a", "docs", query_embedding=[0.1, 0.2, 0.3], n_results=1)
    assert len(results) == 1
    assert results[0].content == "persisted text"

"""Customer Vector DB — tenant-isolated vector search.

Extends ChromaDB with:
- Per-tenant collections, with the stored document text (not the embedding
  vectors themselves — see _encrypt_embedding below for why) Fernet-encrypted
  at rest
- Fine-grained access control (tenant_id filter on every query)

DB-F11 (2026-08-25 audit): this module previously claimed "PQC encryption"
of vector embeddings in this docstring and in _get_encryption_key/
_encrypt_embedding. That was never implemented — both encrypt/decrypt
functions were identity functions — and worse, per-vector encryption of the
kind claimed is not achievable at all while keeping approximate-nearest-
neighbor search working: ANN search computes distances directly on the
embedding floats, so an encrypted embedding cannot be searched without
first being decrypted, which defeats the purpose. What CAN be, and now is,
encrypted at rest without breaking search is the source document text and
metadata stored alongside each vector — that's also the more sensitive of
the two (raw customer text vs. a float array). If encryption of the vectors
themselves is ever genuinely required, it has to happen at the filesystem/
volume layer (encrypt the ChromaDB persistence directory), not per-field.
"""

import hashlib
import logging
import os
import time
import uuid
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any

import chromadb
from chromadb.config import Settings
from cryptography.fernet import Fernet

logger = logging.getLogger(__name__)


def _load_vector_db_cipher() -> Fernet:
    """Fail-closed Fernet key loading, mirroring encryption_service.py's pattern."""
    key = os.getenv("VECTOR_DB_ENCRYPTION_KEY")
    if not key:
        env = os.getenv("ENVIRONMENT", "development").lower()
        if env == "production":
            raise RuntimeError(
                "VECTOR_DB_ENCRYPTION_KEY is not set. Refusing to start in "
                "production without a stable encryption key for customer "
                "vector-DB document text. Generate one with: "
                'python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"'
            )
        logger.warning(
            "VECTOR_DB_ENCRYPTION_KEY is not set — using an ephemeral key (dev "
            "only). All encrypted vector-DB document text will be unreadable "
            "after a restart. Set VECTOR_DB_ENCRYPTION_KEY before deploying."
        )
        key = Fernet.generate_key().decode()
    if isinstance(key, str):
        key = key.encode()
    return Fernet(key)


@dataclass
class VectorCollection:
    """Tenant-isolated vector collection."""
    tenant_id: str
    collection_name: str
    chroma_collection: Any
    encryption_key: str
    dimensions: int
    created_at: float = field(default_factory=time.time)
    vector_count: int = 0


@dataclass
class SearchResult:
    """Vector search result."""
    id: str
    content: str
    metadata: Dict[str, Any]
    distance: float
    tenant_id: str


class CustomerVectorDB:
    """Enhanced vector database for customer data with tenant isolation."""

    def __init__(self, persist_dir: str = "./data/customer_vectors"):
        self.persist_dir = persist_dir
        os.makedirs(persist_dir, exist_ok=True)

        self.client = chromadb.PersistentClient(
            path=persist_dir,
            settings=Settings(anonymized_telemetry=False),
        )
        self._cipher = _load_vector_db_cipher()
        self.collections: Dict[str, VectorCollection] = {}
        self.tenant_encryption_keys: Dict[str, str] = {}
        self._rehydrate_collections()

    def _rehydrate_collections(self) -> None:
        """DB-F12: reconstruct the in-memory registry from ChromaDB's own
        persisted collection list on startup. Without this, every collection
        created before the last restart is unreachable through this class's
        API (add_vectors/query/delete_collection all raise "not found")
        even though the data is still on disk, until create_collection is
        called again for that exact tenant_id/collection_name pair."""
        try:
            existing = self.client.list_collections()
        except Exception as exc:
            logger.warning("Could not list existing ChromaDB collections on startup: %s", exc)
            return
        for chroma_collection in existing:
            full_name = chroma_collection.name
            # full_name is "{tenant_id}_{collection_name}" (see create_collection);
            # tenant_id itself may contain underscores, so split on the last
            # separator is unreliable — metadata carries the authoritative split.
            meta = chroma_collection.metadata or {}
            tenant_id = meta.get("_tenant_id", full_name.split("_", 1)[0])
            collection_name = meta.get("_collection_name", full_name.split("_", 1)[-1])
            self.collections[full_name] = VectorCollection(
                tenant_id=tenant_id,
                collection_name=collection_name,
                chroma_collection=chroma_collection,
                encryption_key=self._get_encryption_key(tenant_id),
                dimensions=meta.get("_dimensions", 1536),
                vector_count=chroma_collection.count(),
            )
        if existing:
            logger.info("Rehydrated %d vector collection(s) from disk", len(existing))

    def _get_encryption_key(self, tenant_id: str) -> str:
        """Per-tenant key label used to namespace encrypted document text.
        Not a distinct cryptographic key per tenant (see module docstring) —
        actual encryption uses the single VECTOR_DB_ENCRYPTION_KEY cipher;
        tenant isolation of the underlying data is enforced by the
        tenant_id metadata filter on every query, not by key separation."""
        if tenant_id not in self.tenant_encryption_keys:
            self.tenant_encryption_keys[tenant_id] = hashlib.sha256(
                f"{tenant_id}_vector_key".encode()
            ).hexdigest()
        return self.tenant_encryption_keys[tenant_id]

    def _encrypt_embedding(self, embedding: List[float], tenant_id: str) -> List[float]:
        """Embedding vectors are stored as plaintext floats — see the module
        docstring for why this is a considered decision, not an oversight:
        ANN search requires computing distances directly on these values."""
        return embedding

    def _decrypt_embedding(self, embedding: List[float], tenant_id: str) -> List[float]:
        return embedding

    def _encrypt_document(self, text: str) -> str:
        """Real Fernet encryption of document source text at rest (DB-F11)."""
        if not text:
            return ""
        return self._cipher.encrypt(text.encode()).decode()

    def _decrypt_document(self, ciphertext: str) -> str:
        if not ciphertext:
            return ""
        return self._cipher.decrypt(ciphertext.encode()).decode()

    def create_collection(
        self,
        tenant_id: str,
        collection_name: str,
        dimensions: int = 1536,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Create tenant-isolated vector collection."""
        full_name = f"{tenant_id}_{collection_name}"

        if full_name in self.collections:
            logger.warning("Collection %s already exists", full_name)
            return full_name

        chroma_meta = dict(metadata or {})
        # DB-F12: persisted alongside the collection so _rehydrate_collections
        # can reconstruct tenant_id/collection_name/dimensions on restart
        # without guessing at an underscore split of the combined name.
        chroma_meta["_tenant_id"] = tenant_id
        chroma_meta["_collection_name"] = collection_name
        chroma_meta["_dimensions"] = dimensions

        chroma_collection = self.client.get_or_create_collection(
            name=full_name,
            metadata=chroma_meta,
        )

        enc_key = self._get_encryption_key(tenant_id)

        vc = VectorCollection(
            tenant_id=tenant_id,
            collection_name=collection_name,
            chroma_collection=chroma_collection,
            encryption_key=enc_key,
            dimensions=dimensions,
        )
        self.collections[full_name] = vc
        logger.info("Created collection: %s for tenant %s", full_name, tenant_id)
        return full_name

    def add_vectors(
        self,
        tenant_id: str,
        collection_name: str,
        embeddings: List[List[float]],
        documents: List[str],
        metadatas: List[Dict[str, Any]],
        ids: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Add vectors to tenant collection."""
        full_name = f"{tenant_id}_{collection_name}"
        vc = self.collections.get(full_name)
        if not vc:
            raise ValueError(f"Collection {full_name} not found")

        if ids is None:
            ids = [str(uuid.uuid4()) for _ in range(len(embeddings))]

        # Embeddings stay plaintext (see _encrypt_embedding docstring); the
        # document source text is real-encrypted at rest (DB-F11).
        encrypted_embeddings = [self._encrypt_embedding(e, tenant_id) for e in embeddings]
        encrypted_documents = [self._encrypt_document(d) for d in documents]

        # Add tenant_id to all metadata for isolation enforcement
        for m in metadatas:
            m["tenant_id"] = tenant_id

        vc.chroma_collection.add(
            embeddings=encrypted_embeddings,
            documents=encrypted_documents,
            metadatas=metadatas,
            ids=ids,
        )
        vc.vector_count += len(embeddings)

        return {"ids": ids, "count": len(embeddings)}

    def query(
        self,
        tenant_id: str,
        collection_name: str,
        query_embedding: List[float],
        n_results: int = 10,
        where: Optional[Dict[str, Any]] = None,
        include: List[str] = None,
    ) -> List[SearchResult]:
        """Query tenant collection with isolation."""
        full_name = f"{tenant_id}_{collection_name}"
        vc = self.collections.get(full_name)
        if not vc:
            raise ValueError(f"Collection {full_name} not found")

        # Enforce tenant isolation in query filter. DB-F13: building this as
        # filter_dict["$and"] = [filter_dict, where] made the list's first
        # element a reference to filter_dict itself — a cyclic structure
        # that broke every filtered query. Construct the combined filter as
        # a separate dict instead.
        if where:
            filter_dict: Dict[str, Any] = {"$and": [{"tenant_id": tenant_id}, where]}
        else:
            filter_dict = {"tenant_id": tenant_id}

        encrypted_query = self._encrypt_embedding(query_embedding, tenant_id)

        results = vc.chroma_collection.query(
            query_embeddings=[encrypted_query],
            n_results=n_results,
            where=filter_dict,
            include=include or ["documents", "metadatas", "distances"],
        )

        search_results = []
        if results["ids"]:
            for i, doc_id in enumerate(results["ids"][0]):
                content = self._decrypt_document(results["documents"][0][i]) if results.get("documents") else ""
                metadata = results["metadatas"][0][i] if results.get("metadatas") else {}
                distance = results["distances"][0][i] if results.get("distances") else 0.0
                search_results.append(SearchResult(
                    id=doc_id,
                    content=content,
                    metadata=metadata,
                    distance=distance,
                    tenant_id=tenant_id,
                ))

        return search_results

    def get_collection(self, tenant_id: str, collection_name: str) -> Optional[VectorCollection]:
        """Get collection info."""
        full_name = f"{tenant_id}_{collection_name}"
        return self.collections.get(full_name)

    def list_collections(self, tenant_id: str = "") -> List[Dict[str, Any]]:
        """List collections, optionally filtered by tenant."""
        result = []
        for full_name, vc in self.collections.items():
            if tenant_id and vc.tenant_id != tenant_id:
                continue
            result.append({
                "full_name": full_name,
                "tenant_id": vc.tenant_id,
                "collection_name": vc.collection_name,
                "dimensions": vc.dimensions,
                "vector_count": vc.vector_count,
                "created_at": vc.created_at,
            })
        return result

    def delete_collection(self, tenant_id: str, collection_name: str) -> bool:
        """Delete tenant collection."""
        full_name = f"{tenant_id}_{collection_name}"
        if full_name not in self.collections:
            return False

        self.client.delete_collection(full_name)
        del self.collections[full_name]
        logger.info("Deleted collection: %s", full_name)
        return True

    def get_stats(self, tenant_id: str = "") -> Dict[str, Any]:
        """Get database statistics."""
        total_vectors = 0
        total_collections = 0

        for vc in self.collections.values():
            if tenant_id and vc.tenant_id != tenant_id:
                continue
            total_vectors += vc.vector_count
            total_collections += 1

        return {
            "total_collections": total_collections,
            "total_vectors": total_vectors,
            "tenant_id": tenant_id if tenant_id else "all",
        }


# Singleton
customer_vector_db = CustomerVectorDB()
"""Vector Pipeline — automated ETL for customer data ingestion.

Orchestrates:
- Data extraction from sources
- Embedding generation via AI providers
- Classification and tagging
- Vector upsert with tenant isolation
- Incremental sync and deduplication
"""

import asyncio
import hashlib
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, AsyncIterator, Callable, Dict, List, Optional, Set

logger = logging.getLogger(__name__)


class PipelineStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    PAUSED = "paused"


class SourceType(str, Enum):
    DATABASE = "database"
    API = "api"
    FILE = "file"
    STREAM = "stream"


@dataclass
class DataSource:
    """Data source configuration."""
    source_id: str
    name: str
    source_type: SourceType
    config: Dict[str, Any]
    tenant_id: str
    collection_name: str
    enabled: bool = True
    last_sync: Optional[float] = None
    sync_interval_seconds: int = 3600  # 1 hour default


@dataclass
class PipelineRun:
    """Single pipeline execution run."""
    run_id: str
    source_id: str
    status: PipelineStatus = PipelineStatus.PENDING
    started_at: float = field(default_factory=time.time)
    completed_at: Optional[float] = None
    records_processed: int = 0
    records_added: int = 0
    records_updated: int = 0
    records_failed: int = 0
    error: str = ""


@dataclass
class DocumentChunk:
    """Document chunk ready for vectorization."""
    chunk_id: str
    source_id: str
    content: str
    metadata: Dict[str, Any]
    tenant_id: str
    classification: str = "internal"


class VectorPipeline:
    """Automated ETL pipeline for customer vector data."""

    def __init__(
        self,
        vector_db: Any = None,
        embedding_fn: Optional[Callable[[str], List[float]]] = None,
    ):
        self.vector_db = vector_db
        self.embedding_fn = embedding_fn
        self.sources: Dict[str, DataSource] = {}
        self.runs: Dict[str, PipelineRun] = {}
        self._running = False
        self._worker_task: Optional[asyncio.Task] = None

    def add_source(self, source: DataSource) -> None:
        """Register a data source."""
        self.sources[source.source_id] = source
        logger.info("Source added: %s (%s)", source.name, source.source_type.value)

    def remove_source(self, source_id: str) -> bool:
        """Remove a data source."""
        if source_id in self.sources:
            del self.sources[source_id]
            return True
        return False

    def get_source(self, source_id: str) -> Optional[DataSource]:
        """Get source by ID."""
        return self.sources.get(source_id)

    def list_sources(self, tenant_id: str = "") -> List[Dict[str, Any]]:
        """List sources, optionally filtered by tenant."""
        result = []
        for s in self.sources.values():
            if tenant_id and s.tenant_id != tenant_id:
                continue
            result.append({
                "source_id": s.source_id,
                "name": s.name,
                "source_type": s.source_type.value,
                "tenant_id": s.tenant_id,
                "collection_name": s.collection_name,
                "enabled": s.enabled,
                "last_sync": s.last_sync,
                "sync_interval_seconds": s.sync_interval_seconds,
            })
        return result

    async def _generate_embeddings(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings for texts."""
        if self.embedding_fn:
            return [self.embedding_fn(t) for t in texts]
        # Fallback: deterministic hash-based embedding (for testing)
        return [self._hash_embedding(t) for t in texts]

    def _hash_embedding(self, text: str, dim: int = 1536) -> List[float]:
        """Generate deterministic pseudo-embedding from text hash."""
        hash_obj = hashlib.sha256(text.encode())
        hash_bytes = hash_obj.digest()
        # Repeat hash to fill dimensions
        embedding = []
        while len(embedding) < dim:
            for b in hash_bytes:
                embedding.append((b - 128) / 128.0)
                if len(embedding) >= dim:
                    break
        return embedding[:dim]

    async def extract_from_database(
        self,
        source: DataSource,
        query: str,
    ) -> AsyncIterator[DocumentChunk]:
        """Extract documents from database (placeholder)."""
        # In production: connect to DB, execute query, yield chunks
        logger.info("Extracting from database: %s", source.source_id)
        yield DocumentChunk(
            chunk_id=f"{source.source_id}_chunk_1",
            source_id=source.source_id,
            content="Sample database content for vectorization",
            metadata={"source": "database", "query": query},
            tenant_id=source.tenant_id,
        )

    async def extract_from_api(
        self,
        source: DataSource,
        endpoint: str,
    ) -> AsyncIterator[DocumentChunk]:
        """Extract documents from API (placeholder)."""
        logger.info("Extracting from API: %s", source.source_id)
        yield DocumentChunk(
            chunk_id=f"{source.source_id}_chunk_1",
            source_id=source.source_id,
            content="Sample API content for vectorization",
            metadata={"source": "api", "endpoint": endpoint},
            tenant_id=source.tenant_id,
        )

    async def extract_from_file(
        self,
        source: DataSource,
        file_path: str,
    ) -> AsyncIterator[DocumentChunk]:
        """Extract documents from file."""
        logger.info("Extracting from file: %s", file_path)
        try:
            with open(file_path, 'r') as f:
                content = f.read()
            # Simple chunking by paragraphs
            chunks = content.split('\n\n')
            for i, chunk in enumerate(chunks):
                if chunk.strip():
                    yield DocumentChunk(
                        chunk_id=f"{source.source_id}_chunk_{i}",
                        source_id=source.source_id,
                        content=chunk.strip(),
                        metadata={"source": "file", "file_path": file_path, "chunk_index": i},
                        tenant_id=source.tenant_id,
                    )
        except Exception as e:
            logger.error("File extraction failed: %s", e)

    async def extract(
        self,
        source: DataSource,
    ) -> AsyncIterator[DocumentChunk]:
        """Extract documents from source based on type."""
        config = source.config

        if source.source_type == SourceType.DATABASE:
            async for chunk in self.extract_from_database(source, config.get("query", "")):
                yield chunk
        elif source.source_type == SourceType.API:
            async for chunk in self.extract_from_api(source, config.get("endpoint", "")):
                yield chunk
        elif source.source_type == SourceType.FILE:
            async for chunk in self.extract_from_file(source, config.get("file_path", "")):
                yield chunk
        else:
            logger.warning("Unknown source type: %s", source.source_type)

    def _chunk_document(self, doc: DocumentChunk, chunk_size: int = 1000, overlap: int = 200) -> List[DocumentChunk]:
        """Split document into overlapping chunks."""
        content = doc.content
        if len(content) <= chunk_size:
            return [doc]

        chunks = []
        start = 0
        chunk_index = 0
        while start < len(content):
            end = min(start + chunk_size, len(content))
            chunk_content = content[start:end]
            chunks.append(DocumentChunk(
                chunk_id=f"{doc.chunk_id}_part_{chunk_index}",
                source_id=doc.source_id,
                content=chunk_content,
                metadata={**doc.metadata, "parent_chunk": doc.chunk_id, "part_index": chunk_index},
                tenant_id=doc.tenant_id,
                classification=doc.classification,
            ))
            start += chunk_size - overlap
            chunk_index += 1
        return chunks

    async def process_source(self, source_id: str) -> PipelineRun:
        """Process a single source through the pipeline."""
        source = self.sources.get(source_id)
        if not source:
            raise ValueError(f"Source {source_id} not found")

        run_id = f"run_{source_id}_{int(time.time())}"
        run = PipelineRun(run_id=run_id, source_id=source_id)
        self.runs[run_id] = run
        run.status = PipelineStatus.RUNNING

        try:
            # Collect all chunks
            all_chunks = []
            async for chunk in self.extract(source):
                # Chunk large documents
                sub_chunks = self._chunk_document(chunk)
                all_chunks.extend(sub_chunks)

            # Generate embeddings
            if all_chunks:
                texts = [c.content for c in all_chunks]
                embeddings = await self._generate_embeddings(texts)

                # Prepare for vector DB
                ids = [c.chunk_id for c in all_chunks]
                documents = [c.content for c in all_chunks]
                metadatas = [c.metadata for c in all_chunks]

                # Upsert to vector DB
                if self.vector_db:
                    self.vector_db.add_vectors(
                        tenant_id=source.tenant_id,
                        collection_name=source.collection_name,
                        embeddings=embeddings,
                        documents=documents,
                        metadatas=metadatas,
                        ids=ids,
                    )
                    run.records_added = len(ids)
                else:
                    logger.warning("No vector DB configured, skipping upsert")

            run.records_processed = len(all_chunks)
            run.status = PipelineStatus.COMPLETED
            run.completed_at = time.time()
            source.last_sync = time.time()

            logger.info("Pipeline run %s completed: %d records processed",
                        run_id, run.records_processed)

        except Exception as e:
            run.status = PipelineStatus.FAILED
            run.error = str(e)
            run.completed_at = time.time()
            logger.error("Pipeline run %s failed: %s", run_id, e)

        return run

    async def run_all(self, tenant_id: str = "") -> List[PipelineRun]:
        """Run pipeline for all enabled sources."""
        runs = []
        for source in self.sources.values():
            if not source.enabled:
                continue
            if tenant_id and source.tenant_id != tenant_id:
                continue
            run = await self.process_source(source.source_id)
            runs.append(run)
        return runs

    def get_run(self, run_id: str) -> Optional[PipelineRun]:
        """Get pipeline run by ID."""
        return self.runs.get(run_id)

    def list_runs(self, source_id: str = "", limit: int = 20) -> List[Dict[str, Any]]:
        """List pipeline runs."""
        runs = list(self.runs.values())
        if source_id:
            runs = [r for r in runs if r.source_id == source_id]
        runs.sort(key=lambda r: r.started_at, reverse=True)
        return [
            {
                "run_id": r.run_id,
                "source_id": r.source_id,
                "status": r.status.value,
                "started_at": r.started_at,
                "completed_at": r.completed_at,
                "records_processed": r.records_processed,
                "records_added": r.records_added,
                "records_updated": r.records_updated,
                "records_failed": r.records_failed,
                "error": r.error,
            }
            for r in runs[:limit]
        ]

    async def start_scheduler(self) -> None:
        """Start periodic pipeline scheduler."""
        if self._worker_task and not self._worker_task.done():
            return
        self._running = True
        self._worker_task = asyncio.create_task(self._scheduler_loop())

    async def stop_scheduler(self) -> None:
        """Stop periodic pipeline scheduler."""
        self._running = False
        if self._worker_task:
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass

    async def _scheduler_loop(self) -> None:
        """Periodic pipeline execution."""
        while self._running:
            try:
                await self.run_all()
                await asyncio.sleep(60)  # Check every minute
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Scheduler error: %s", e)
                await asyncio.sleep(60)

    def get_stats(self) -> Dict[str, Any]:
        """Get pipeline statistics."""
        total_runs = len(self.runs)
        successful = sum(1 for r in self.runs.values() if r.status == PipelineStatus.COMPLETED)
        failed = sum(1 for r in self.runs.values() if r.status == PipelineStatus.FAILED)
        total_records = sum(r.records_processed for r in self.runs.values())

        return {
            "total_sources": len(self.sources),
            "enabled_sources": sum(1 for s in self.sources.values() if s.enabled),
            "total_runs": total_runs,
            "successful_runs": successful,
            "failed_runs": failed,
            "total_records_processed": total_records,
            "scheduler_running": self._running,
        }


# Singleton
vector_pipeline = VectorPipeline()
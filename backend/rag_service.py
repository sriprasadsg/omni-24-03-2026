import chromadb
import os
import uuid
import logging
from datetime import datetime

# Setup logging
logger = logging.getLogger("uvicorn.error")

# Persistent path for the vector DB
# d:/Downloads/enterprise-omni-agent-ai-platform/data/chroma_db
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_DIR = os.path.join(BASE_DIR, "data", "chroma_db")
os.makedirs(DB_DIR, exist_ok=True)

class RagService:
    def __init__(self):
        self.client = None
        self.collection = None
        try:
            logger.info(f"Initializing ChromaDB at: {DB_DIR}")
            self.client = chromadb.PersistentClient(path=DB_DIR)
            self.collection = self.client.get_or_create_collection(name="omni-agent-knowledge")
            logger.info("✅ RAG Service initialized successfully.")
        except Exception as e:
            logger.error(f"❌ Failed to initialize ChromaDB: {e}")

    def ingest_text(self, content: str, source: str = "manual_entry", tenant_id: str = "global") -> dict:
        """
        Add a text snippet to the knowledge base.

        tenant_id tags the chunk for isolation at query time; "global" marks
        shared knowledge (e.g. security standards) visible to every tenant.
        """
        if not self.collection:
            return {"success": False, "error": "Database not initialized"}

        try:
            doc_id = str(uuid.uuid4())
            timestamp = datetime.now().isoformat()

            # Chroma handles embedding automatically by default
            self.collection.add(
                documents=[content],
                metadatas=[{"source": source, "ingested_at": timestamp, "tenantId": tenant_id}],
                ids=[doc_id]
            )
            
            return {
                "success": True, 
                "id": doc_id, 
                "message": "Content indexed successfully"
            }
        except Exception as e:
            logger.error(f"Ingestion error: {e}")
            return {"success": False, "error": str(e)}

    def query(self, query_text: str, n_results: int = 3, tenant_id: str = None) -> list:
        """
        Retrieve relevant context for a query.

        When tenant_id is given, results are restricted to that tenant's
        chunks plus "global" shared knowledge (T1 isolation guard — chunks
        ingested without a tenantId tag are excluded from scoped queries).
        """
        if not self.collection:
            return []

        try:
            query_kwargs = {
                "query_texts": [query_text],
                "n_results": n_results,
            }
            if tenant_id:
                query_kwargs["where"] = {
                    "$or": [{"tenantId": tenant_id}, {"tenantId": "global"}]
                }
            results = self.collection.query(**query_kwargs)

            output = []
            # Results are lists of lists (one list per query)
            if results and results['documents']:
                for i, doc in enumerate(results['documents'][0]):
                    meta = results['metadatas'][0][i] if results['metadatas'] else {}
                    # Distances might not be returned depending on version, check safely
                    distance = results['distances'][0][i] if 'distances' in results and results['distances'] else None
                    doc_id = results['ids'][0][i] if results.get('ids') else ""

                    output.append({
                        "id": doc_id,
                        "content": doc,
                        "source": meta.get("source", "unknown"),
                        "tenantId": meta.get("tenantId", ""),
                        "relevance": distance
                    })

            return output

        except Exception as e:
            logger.error(f"Query error: {e}")
            return []

# Singleton instance
rag_service = RagService()

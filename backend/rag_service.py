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

    def ingest_text(self, content: str, source: str = "manual_entry") -> dict:
        """
        Add a text snippet to the knowledge base.
        """
        if not self.collection:
            return {"success": False, "error": "Database not initialized"}
        
        try:
            doc_id = str(uuid.uuid4())
            timestamp = datetime.now().isoformat()
            
            # Chroma handles embedding automatically by default
            self.collection.add(
                documents=[content],
                metadatas=[{"source": source, "ingested_at": timestamp}],
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

    def query(self, query_text: str, n_results: int = 3) -> list:
        """
        Retrieve relevant context for a query.
        """
        if not self.collection:
            return []
        
        try:
            results = self.collection.query(
                query_texts=[query_text],
                n_results=n_results
            )
            
            output = []
            # Results are lists of lists (one list per query)
            if results and results['documents']:
                for i, doc in enumerate(results['documents'][0]):
                    meta = results['metadatas'][0][i] if results['metadatas'] else {}
                    # Distances might not be returned depending on version, check safely
                    distance = results['distances'][0][i] if 'distances' in results and results['distances'] else None
                    
                    output.append({
                        "content": doc,
                        "source": meta.get("source", "unknown"),
                        "relevance": distance
                    })
            
            return output
            
        except Exception as e:
            logger.error(f"Query error: {e}")
            return []

# Singleton instance
rag_service = RagService()

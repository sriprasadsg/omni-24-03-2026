
from database import get_database
from typing import List, Optional, Dict, Any
from datetime import datetime, timezone
import logging

logger = logging.getLogger(__name__)

async def create_prompt(prompt_data: Dict[str, Any]) -> Dict[str, Any]:
    """Create a new prompt template"""
    db = get_database()
    
    # Check if exists
    existing = await db.prompts.find_one({"name": prompt_data["name"]})
    if existing:
        raise ValueError(f"Prompt with name '{prompt_data['name']}' already exists")

    new_prompt = {
        "name": prompt_data["name"],
        "description": prompt_data.get("description", ""),
        "template": prompt_data["template"],
        "input_variables": prompt_data.get("input_variables", []),
        "version": prompt_data.get("version", "1.0.0"),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "tags": prompt_data.get("tags", [])
    }
    
    result = await db.prompts.insert_one(new_prompt)
    new_prompt["_id"] = str(result.inserted_id)
    return new_prompt

async def list_prompts() -> List[Dict[str, Any]]:
    """List all prompts"""
    db = get_database()
    cursor = db.prompts.find({})
    prompts = []
    async for doc in cursor:
        doc["_id"] = str(doc["_id"])
        prompts.append(doc)
    return prompts

async def get_prompt(name: str) -> Optional[Dict[str, Any]]:
    """Get a prompt by name"""
    db = get_database()
    doc = await db.prompts.find_one({"name": name})
    if doc:
        doc["_id"] = str(doc["_id"])
    return doc

async def update_prompt(name: str, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Update a prompt"""
    db = get_database()
    
    updates["updated_at"] = datetime.now(timezone.utc).isoformat()
    
    result = await db.prompts.find_one_and_update(
        {"name": name},
        {"$set": updates},
        return_document=True
    )
    
    if result:
        result["_id"] = str(result["_id"])
    
    return result

async def delete_prompt(name: str) -> bool:
    """Delete a prompt"""
    db = get_database()
    result = await db.prompts.delete_one({"name": name})
    return result.deleted_count > 0

# --- Knowledge Base / RAG ---

_CHUNK_SIZE = 400          # characters per chunk
_CHUNK_OVERLAP = 80        # overlap to preserve context across boundaries
_MAX_RESULTS = 5


def _chunk_text(text: str) -> List[str]:
    """Split text into overlapping sentence-aware chunks."""
    import re
    # Split on sentence boundaries first
    sentences = re.split(r'(?<=[.!?])\s+', text.strip())
    chunks: List[str] = []
    current = ""
    for sentence in sentences:
        if len(current) + len(sentence) + 1 <= _CHUNK_SIZE:
            current = (current + " " + sentence).strip()
        else:
            if current:
                chunks.append(current)
            # Start new chunk with overlap from previous chunk tail
            overlap = current[-_CHUNK_OVERLAP:] if len(current) > _CHUNK_OVERLAP else current
            current = (overlap + " " + sentence).strip() if overlap else sentence
    if current:
        chunks.append(current)
    return chunks or [text[:_CHUNK_SIZE]]


async def _ensure_text_index(db) -> None:
    """Create MongoDB text index on knowledge_docs if not present."""
    try:
        await db.knowledge_docs._collection.create_index(
            [("content", "text"), ("source", "text")],
            name="knowledge_text_idx",
            default_language="english",
        )
    except Exception:
        pass  # Index already exists or collection not yet created — both fine


async def ingest_knowledge(content: str, source: str) -> str:
    """
    Ingest text into the knowledge base.
    Splits content into overlapping sentence-level chunks and persists each
    chunk as a separate document so MongoDB text search can rank by relevance.
    Returns the number of chunks stored.
    """
    db = get_database()
    await _ensure_text_index(db)

    chunks = _chunk_text(content)
    now = datetime.now(timezone.utc).isoformat()
    docs = [
        {
            "content": chunk,
            "source": source,
            "chunk_index": idx,
            "total_chunks": len(chunks),
            "created_at": now,
            "status": "indexed",
        }
        for idx, chunk in enumerate(chunks)
    ]
    if docs:
        await db.knowledge_docs._collection.insert_many(docs)
    logger.info("Ingested %d chunks from source '%s'", len(docs), source)
    return f"{len(docs)} chunks indexed"


async def query_knowledge(query: str) -> List[Dict[str, Any]]:
    """
    Query the knowledge base using MongoDB full-text search.
    Results are ranked by MongoDB's text score (relevance).
    Falls back to regex search if text index is not available.
    """
    db = get_database()
    await _ensure_text_index(db)

    try:
        # Full-text search with relevance score
        cursor = db.knowledge_docs._collection.find(
            {"$text": {"$search": query}},
            {"score": {"$meta": "textScore"}, "content": 1, "source": 1, "_id": 0},
        ).sort([("score", {"$meta": "textScore"})]).limit(_MAX_RESULTS)
        docs = await cursor.to_list(length=_MAX_RESULTS)
        return [
            {
                "content": d.get("content", "")[:600],
                "source": d.get("source", "knowledge_base"),
                "relevance": round(min(d.get("score", 1.0) / 5.0, 1.0), 3),
            }
            for d in docs
        ]
    except Exception:
        # Fallback: regex search when text index not yet built
        docs = await db.knowledge_docs.find(
            {"content": {"$regex": query, "$options": "i"}},
            {"_id": 0, "content": 1, "source": 1},
        ).limit(_MAX_RESULTS).to_list(length=_MAX_RESULTS)
        return [
            {"content": d.get("content", "")[:600], "source": d.get("source", "knowledge_base"), "relevance": 0.5}
            for d in docs
        ]

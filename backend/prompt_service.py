
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

# --- Knowledge Base / RAG Stubs ---

async def ingest_knowledge(content: str, source: str) -> str:
    """Ingest text into knowledge base (Stub for now)"""
    # In a real implementation, this would chunk text, embed it, and save to Vector DB
    db = get_database()
    
    doc = {
        "content": content,
        "source": source,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": "processed" # Mocking success
    }
    
    result = await db.knowledge_docs.insert_one(doc)
    return str(result.inserted_id)

async def query_knowledge(query: str) -> List[Dict[str, Any]]:
    """Query knowledge base (Stub for now)"""
    # Mock search
    return [
        {
            "content": f"Mock result for query: {query}",
            "source": "manual_ui",
            "relevance": 0.95
        }
    ]

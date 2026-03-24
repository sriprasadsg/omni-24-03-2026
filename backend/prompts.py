from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from datetime import datetime
from database import get_database
import logging

class PromptTemplate(BaseModel):
    name: str
    version: str = "1.0.0"
    template: str
    input_variables: List[str]
    description: Optional[str] = None
    tags: List[str] = []
    created_at: str = datetime.utcnow().isoformat()
    updated_at: str = datetime.utcnow().isoformat()

class PromptRegistry:
    def __init__(self):
        self.logger = logging.getLogger("PromptRegistry")

    async def save_prompt(self, prompt: PromptTemplate) -> bool:
        """Save or update a prompt template in the database."""
        db = get_database()
        try:
            # Check if version exists
            existing = await db.prompts.find_one({"name": prompt.name, "version": prompt.version})
            if existing:
                # Update
                await db.prompts.update_one(
                    {"_id": existing["_id"]},
                    {"$set": prompt.dict(exclude={"created_at"})}
                )
            else:
                # Insert
                await db.prompts.insert_one(prompt.dict())
            return True
        except Exception as e:
            self.logger.error(f"Failed to save prompt: {e}")
            return False

    async def get_prompt(self, name: str, version: Optional[str] = None) -> Optional[PromptTemplate]:
        """Retrieve a prompt by name and optional version (defaults to latest)."""
        db = get_database()
        try:
            query = {"name": name}
            if version:
                query["version"] = version
                doc = await db.prompts.find_one(query)
            else:
                # Find latest by sorting (assuming simplified semantic versioning or just created_at)
                # For string versions, sorting might be tricky, but created_at is reliable
                cursor = db.prompts.find(query).sort("created_at", -1).limit(1)
                docs = await cursor.to_list(length=1)
                doc = docs[0] if docs else None
            
            if doc:
                return PromptTemplate(**doc)
            return None
        except Exception as e:
            self.logger.error(f"Failed to get prompt: {e}")
            return None

    async def list_prompts(self) -> List[Dict[str, Any]]:
        """List all prompts."""
        db = get_database()
        try:
            cursor = db.prompts.find({})
            prompts = await cursor.to_list(length=100)
            # Group by name? For now just return raw list
            return [PromptTemplate(**p).dict() for p in prompts]
        except Exception as e:
            self.logger.error(f"Failed to list prompts: {e}")
            return []

prompt_registry = PromptRegistry()

from typing import List, Dict, Any, Optional
from datetime import datetime
from database import get_database
from bson.objectid import ObjectId
import logging

class PlaybookService:
    def __init__(self):
        self.logger = logging.getLogger("PlaybookService")
        self.collection_name = "playbooks"

    async def create_playbook(self, 
                            name: str, 
                            description: str, 
                            trigger: str, 
                            steps: List[Dict[str, Any]],
                            tenant_id: str = "unknown") -> Optional[str]:
        """
        Create a new remediation playbook.
        Steps should be a list of dicts: {"action": "restart_service", "params": {...}}
        """
        try:
            db = get_database()
            playbook = {
                "name": name,
                "description": description,
                "trigger": trigger,
                "steps": steps,
                "tenantId": tenant_id,
                "created_at": datetime.utcnow().isoformat(),
                "updated_at": datetime.utcnow().isoformat()
            }
            result = await db[self.collection_name].insert_one(playbook)
            self.logger.info(f"Created playbook: {name} [{result.inserted_id}]")
            return str(result.inserted_id)
        except Exception as e:
            self.logger.error(f"Failed to create playbook: {e}")
            return None

    async def get_playbooks(self, tenant_id: str = "unknown") -> List[Dict[str, Any]]:
        """List all playbooks."""
        try:
            db = get_database()
            cursor = db[self.collection_name].find({"tenantId": tenant_id})
            playbooks = await cursor.to_list(length=100)
            for p in playbooks:
                p["id"] = str(p["_id"])
                del p["_id"]
            return playbooks
        except Exception as e:
            self.logger.error(f"Failed to fetch playbooks: {e}")
            return []

    async def get_playbook(self, playbook_id: str) -> Optional[Dict[str, Any]]:
        """Get a specific playbook."""
        try:
            db = get_database()
            playbook = await db[self.collection_name].find_one({"_id": ObjectId(playbook_id)})
            if playbook:
                playbook["id"] = str(playbook["_id"])
                del playbook["_id"]
            return playbook
        except Exception as e:
            self.logger.error(f"Failed to fetch playbook {playbook_id}: {e}")
            return None

    async def delete_playbook(self, playbook_id: str) -> bool:
        """Delete a playbook."""
        try:
            db = get_database()
            result = await db[self.collection_name].delete_one({"_id": ObjectId(playbook_id)})
            return result.deleted_count > 0
        except Exception as e:
            self.logger.error(f"Failed to delete playbook {playbook_id}: {e}")
            return False

playbook_service = PlaybookService()

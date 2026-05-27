from typing import List, Dict, Any, Optional
from datetime import datetime, timezone
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
                "created_at": datetime.now(timezone.utc).isoformat(),
                "updated_at": datetime.now(timezone.utc).isoformat()
            }
            result = await db[self.collection_name].insert_one(playbook)
            self.logger.info(f"Created playbook: {name} [{result.inserted_id}]")
            return str(result.inserted_id)
        except Exception as e:
            self.logger.error(f"Failed to create playbook: {e}")
            return None

    async def get_playbooks(self) -> List[Dict[str, Any]]:
        """List all playbooks."""
        try:
            db = get_database()
            cursor = db[self.collection_name].find({})
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

    async def toggle_playbook(self, playbook_id: str) -> Optional[Dict[str, Any]]:
        """Toggle a playbook's enabled state. Returns updated doc or None if not found."""
        try:
            db = get_database()
            query: dict = {"id": playbook_id}
            try:
                query = {"$or": [{"_id": ObjectId(playbook_id)}, {"id": playbook_id}]}
            except Exception:
                pass
            playbook = await db[self.collection_name].find_one(query)
            if not playbook:
                return None
            new_state = not playbook.get("enabled", True)
            await db[self.collection_name].update_one(
                {"_id": playbook["_id"]},
                {"$set": {"enabled": new_state, "updated_at": datetime.now(timezone.utc).isoformat()}},
            )
            playbook["enabled"] = new_state
            playbook["id"] = str(playbook.pop("_id"))
            return playbook
        except Exception as e:
            self.logger.error(f"Failed to toggle playbook {playbook_id}: {e}")
            return None

    async def execute_playbook(self, playbook_id: str, context: Dict[str, Any]) -> Dict[str, Any]:
        """Queue a playbook for execution via the enhanced playbook engine."""
        try:
            from database import get_database as _gdb
            from enhanced_playbook_engine import get_playbook_engine
            db = _gdb()
            engine = get_playbook_engine(db._db)
            result = await engine.execute_playbook(
                playbook_id=playbook_id,
                trigger_data=context,
                tenant_id=context.get("tenant_id"),
                executed_by=context.get("executed_by", "manual"),
            )
            return result
        except Exception as e:
            self.logger.error(
                "Playbook execution failed [id=%s tenant=%s trigger=%s]: %s",
                playbook_id,
                context.get("tenant_id"),
                context.get("trigger_type", "manual"),
                e,
                exc_info=True,
            )
            return {"status": "error", "playbook_id": playbook_id, "error": str(e)}


playbook_service = PlaybookService()


from ai_service import ai_service
import json
import os
from database import get_database
from datetime import datetime
import uuid

class AIPlaybookService:
    def __init__(self):
        self.model = None
        self.is_configured = False

        pass # Initialization handled by ai_service

    async def generate_playbook(self, prompt: str, tenant_id: str = "default"):
        """Generate a playbook from a natural language prompt"""
        if not self.is_configured:
            await self.initialize()
            
        if not self.is_configured:
            # Fallback to mock/template if not configured
            return self._generate_mock_playbook(prompt, tenant_id)

        system_prompt = """
        You are an expert SOAR (Security Orchestration, Automation and Response) Engineer.
        Create a detailed security playbook based on the user's request.
        
        The output must be a valid JSON object with the following structure:
        {
            "name": "Short descriptive title",
            "description": "Detailed description of what this playbook does",
            "trigger": "Event that triggers this playbook (e.g., 'Phishing Alert', 'High CPU')",
            "steps": [
                {
                    "id": "step-1",
                    "name": "Step Name",
                    "action": "Action Type (e.g., 'Script', 'Approval', 'Notification', 'Query')",
                    "description": "What this step does",
                    "automated": true/false
                }
            ],
            "estimatedDuration": "e.g., '5 minutes'",
            "tags": ["tag1", "tag2"]
        }
        
        Ensure the steps are logical and follow standard incident response procedures (NIST/SANS).
        """
        
        try:
            response_text = await ai_service.generate_text(f"{system_prompt}\n\nUSER REQUEST: {prompt}", source="playbook_gen")
            if response_text.startswith("BLOCKED:"):
                return {"error": response_text}
                
            cleaned_text = response_text.replace("```json", "").replace("```", "").strip()
            playbook_data = json.loads(cleaned_text)
            
            # Add metadata
            playbook_data["id"] = f"pb-{uuid.uuid4()}"
            playbook_data["tenantId"] = tenant_id
            playbook_data["created_at"] = datetime.utcnow().isoformat()
            playbook_data["updated_at"] = datetime.utcnow().isoformat()
            playbook_data["is_active"] = True
            
            # Save to DB
            db = get_database()
            await db.playbooks.insert_one(playbook_data)
            
            # Convert ObjectId to string if needed (though we used custom ID)
            if "_id" in playbook_data:
                del playbook_data["_id"]
                
            return playbook_data
            
        except Exception as e:
            print(f"Error generating playbook: {e}")
            return self._generate_mock_playbook(prompt, tenant_id, error=str(e))

    def _generate_mock_playbook(self, prompt: str, tenant_id: str, error: str = None):
        """Fallback generator"""
        return {
            "id": f"pb-{uuid.uuid4()}",
            "tenantId": tenant_id,
            "name": f"Playbook for: {prompt[:30]}...",
            "description": f"Generated playbook for '{prompt}'. (AI Service Unavailable)",
            "trigger": "Manual",
            "steps": [
                {
                    "id": "step-1",
                    "name": "Initial Triage",
                    "action": "Notification",
                    "description": "Notify SOC team of new incident",
                    "automated": True
                },
                {
                    "id": "step-2",
                    "name": "Investigate",
                    "action": "Query",
                    "description": "Query logs for related activity",
                    "automated": False
                }
            ],
            "estimatedDuration": "10 minutes",
            "tags": ["generated", "fallback"],
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
            "is_active": True,
            "note": "This is a placeholder. Configure AI Settings to enable real generation."
        }

ai_playbook_service = AIPlaybookService()

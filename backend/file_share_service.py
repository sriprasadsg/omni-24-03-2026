from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any
from pydantic import BaseModel
import uuid
import secrets

class SharedFile(BaseModel):
    id: str
    file_name: str
    file_url: str
    created_by: str
    created_at: str
    expires_at: Optional[str]
    access_token: str
    password_protected: bool
    password: Optional[str] # In real app, store hash
    access_count: int
    max_accesses: Optional[int]
    is_active: bool

class FileShareService:
    def __init__(self):
        self.shares: List[SharedFile] = [
             SharedFile(
                id="share-1",
                file_name="SOC2_Report.pdf",
                file_url="/secure/docs/SOC2_Report.pdf",
                created_by="admin@omni-agent.com",
                created_at=datetime.now().isoformat(),
                expires_at=(datetime.now() + timedelta(days=7)).isoformat(),
                access_token=secrets.token_urlsafe(16),
                password_protected=True,
                password="secret_password", 
                access_count=2,
                max_accesses=10,
                is_active=True
            )
        ]

    def get_my_shares(self, user_email: str) -> List[SharedFile]:
        # For simplicity in demo, return all or filter by creator
        return self.shares

    def create_share(self, share_data: Dict[str, Any]) -> SharedFile:
        token = secrets.token_urlsafe(16)
        new_share = SharedFile(
            id=str(uuid.uuid4()),
            access_token=token,
            created_at=datetime.now().isoformat(),
            access_count=0,
            is_active=True,
            **share_data
        )
        self.shares.append(new_share)
        return new_share

    def revoke_share(self, share_id: str) -> bool:
        for share in self.shares:
            if share.id == share_id:
                share.is_active = False
                return True
        return False
    
    def access_share(self, token: str, password: Optional[str] = None) -> Dict[str, Any]:
        for share in self.shares:
            if share.access_token == token:
                if not share.is_active:
                    return {"error": "Link revoked"}
                if share.expires_at and datetime.now().isoformat() > share.expires_at:
                    return {"error": "Link expired"}
                if share.max_accesses and share.access_count >= share.max_accesses:
                    return {"error": "Max accesses reached"}
                if share.password_protected and share.password != password:
                    return {"error": "Invalid password", "password_required": True}
                
                share.access_count += 1
                return {"file_url": share.file_url, "file_name": share.file_name}
        return {"error": "Not found"}

file_share_service = FileShareService()

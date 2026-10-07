from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any
from pydantic import BaseModel
import uuid
import secrets
import bcrypt

class SharedFile(BaseModel):
    id: str
    file_name: str
    file_url: str
    created_by: str
    tenant_id: Optional[str] = None
    created_at: str
    expires_at: Optional[str]
    access_token: str
    password_protected: bool
    password_hash: Optional[str] = None  # bcrypt hash, never plaintext
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
                password_protected=False,
                password_hash=None,
                access_count=2,
                max_accesses=10,
                is_active=True
            )
        ]

    def get_my_shares(self, user_email: str, tenant_id: Optional[str]) -> List[SharedFile]:
        """Shares the caller created in their own tenant (tokens are bearer credentials)."""
        return [s for s in self.shares if s.created_by == user_email and s.tenant_id == tenant_id]

    def create_share(self, share_data: Dict[str, Any]) -> SharedFile:
        token = secrets.token_urlsafe(16)
        # Hash the password before storing if one was provided
        raw_password = share_data.pop("password", None)
        password_hash = None
        password_protected = share_data.get("password_protected", False)
        if password_protected and raw_password:
            password_hash = bcrypt.hashpw(
                raw_password.encode("utf-8"), bcrypt.gensalt()
            ).decode("utf-8")

        new_share = SharedFile(
            id=str(uuid.uuid4()),
            access_token=token,
            created_at=datetime.now().isoformat(),
            access_count=0,
            is_active=True,
            password_hash=password_hash,
            **share_data
        )
        self.shares.append(new_share)
        return new_share

    def revoke_share(self, share_id: str, user_email: str, tenant_id: Optional[str]) -> bool:
        for share in self.shares:
            if share.id == share_id and share.created_by == user_email and share.tenant_id == tenant_id:
                share.is_active = False
                return True
        return False

    def access_share(self, token: str, password: Optional[str] = None) -> Dict[str, Any]:
        import hmac
        for share in self.shares:
            if hmac.compare_digest(share.access_token, token):
                if not share.is_active:
                    return {"error": "Link revoked"}
                if share.expires_at and datetime.now().isoformat() > share.expires_at:
                    return {"error": "Link expired"}
                if share.max_accesses and share.access_count >= share.max_accesses:
                    return {"error": "Max accesses reached"}
                if share.password_protected:
                    if not password or not share.password_hash:
                        return {"error": "Invalid password", "password_required": True}
                    if not bcrypt.checkpw(password.encode("utf-8"), share.password_hash.encode("utf-8")):
                        return {"error": "Invalid password", "password_required": True}

                share.access_count += 1
                return {"file_url": share.file_url, "file_name": share.file_name}
        return {"error": "Not found"}

file_share_service = FileShareService()

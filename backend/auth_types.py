from dataclasses import dataclass
from typing import Optional, Dict, Any
from pydantic import BaseModel

@dataclass
class TokenData:
    username: Optional[str] = None
    role: Optional[str] = "user"
    tenant_id: Optional[str] = None
    mfa_verified: bool = False

class Token(BaseModel):
    access_token: str
    token_type: str
    success: bool = True
    user: Optional[Dict[str, Any]] = None

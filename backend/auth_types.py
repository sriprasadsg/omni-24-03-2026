from dataclasses import dataclass
from typing import Optional, Dict, Any, List
from pydantic import BaseModel

@dataclass
class TokenData:
    username: Optional[str] = None
    role: Optional[str] = "user"
    tenant_id: Optional[str] = None
    mfa_verified: bool = False
    # ITAM-USR-05 (Phase 64-05): scope-aware API tokens. Appended AFTER the
    # existing fields so every positional TokenData(...) call site elsewhere
    # in the codebase keeps working unchanged.
    # scopes: None means "not scope-restricted" (session/JWT auth — the
    # request carries the user's full role permissions). A list narrows the
    # request to exactly those scopes (api_key auth) — None and [] are
    # semantically distinct; do NOT give this a mutable default.
    scopes: Optional[List[str]] = None
    # auth_source distinguishes how this TokenData was constructed: "session"
    # (JWT/cookie login, the default — every existing caller inherits this
    # unchanged) or "api_key" (set by api_key_auth.APIKeyService.authenticate).
    auth_source: str = "session"

class Token(BaseModel):
    access_token: str
    token_type: str
    success: bool = True
    user: Optional[Dict[str, Any]] = None

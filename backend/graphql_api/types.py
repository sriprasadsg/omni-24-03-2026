import strawberry
from typing import Optional, List
from datetime import datetime

@strawberry.type
class ComplianceControl:
    id: str
    framework: str
    control_id: str
    title: str
    description: Optional[str] = None
    status: str
    risk_score: Optional[int] = None
    # ReBAC fields for relationships
    owner_id: Optional[str] = None
    viewer_user_ids: Optional[List[str]] = None

@strawberry.type
class Evidence:
    id: str
    title: str
    description: Optional[str] = None
    file_type: str
    url: Optional[str] = None
    uploaded_at: str
    status: str

@strawberry.type
class Risk:
    id: str
    title: str
    description: str
    category: str
    status: str
    likelihood: int
    impact: int
    risk_score: int

@strawberry.type
class User:
    id: str
    username: str
    email: str
    role: str
    tenant_id: str
    # ISO-8601 strings — the platform stores timestamps as isoformat() strings
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

@strawberry.type
class Tenant:
    id: str
    name: str
    subscription_tier: str
    enabled_features: List[str]

from pydantic import BaseModel
from datetime import datetime
from typing import Optional
from app.models.itam import AssetRequestStatus

class AssetRequestBase(BaseModel):
    item_description: str
    quantity: int
    reason: str

class AssetRequestCreate(AssetRequestBase):
    pass

class AssetRequestUpdate(BaseModel):
    status: Optional[AssetRequestStatus] = None

class AssetRequestInDB(AssetRequestBase):
    id: int
    tenant_id: int
    requester_id: int
    status: AssetRequestStatus
    request_date: datetime
    approval_date: Optional[datetime]
    approver_id: Optional[int]

    class Config:
        from_attributes = True
        use_enum_values = True

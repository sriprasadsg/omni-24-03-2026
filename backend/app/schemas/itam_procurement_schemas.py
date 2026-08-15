from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime

class PurchaseOrderItem(BaseModel):
    name: str
    quantity: int
    unit_price: float

class PurchaseOrderBase(BaseModel):
    order_number: str
    supplier_name: str
    order_date: datetime
    total_cost: float
    items: List[PurchaseOrderItem]
    notes: Optional[str] = None

class PurchaseOrderCreate(PurchaseOrderBase):
    pass

class PurchaseOrderUpdate(PurchaseOrderBase):
    pass

class PurchaseOrderInDB(PurchaseOrderBase):
    id: str = Field(..., alias="_id")
    tenant_id: str

class PurchaseOrder(PurchaseOrderInDB):
    pass

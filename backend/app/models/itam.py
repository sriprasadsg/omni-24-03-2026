from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Enum, Boolean
from sqlalchemy.orm import relationship
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime
import enum

Base = declarative_base()

class AssetRequestStatus(enum.Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"

class AssetRequest(Base):
    __tablename__ = "itam_asset_requests"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer)
    requester_id = Column(Integer)
    item_description = Column(String, index=True)
    quantity = Column(Integer)
    reason = Column(String)
    status = Column(Enum(AssetRequestStatus), default=AssetRequestStatus.PENDING)
    request_date = Column(DateTime, default=datetime.utcnow)
    approval_date = Column(DateTime, nullable=True)
    approver_id = Column(Integer, nullable=True)
    purchase_order_id = Column(Integer, ForeignKey('purchase_orders.id'), nullable=True)
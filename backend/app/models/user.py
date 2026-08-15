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
    tenant_id = Column(Integer, ForeignKey("tenants.id"))
    requester_id = Column(Integer, ForeignKey("users.id"))
    item_description = Column(String, index=True)
    quantity = Column(Integer)
    reason = Column(String)
    status = Column(Enum(AssetRequestStatus), default=AssetRequestStatus.PENDING)
    request_date = Column(DateTime, default=datetime.utcnow)
    approval_date = Column(DateTime, nullable=True)
    approver_id = Column(Integer, ForeignKey("users.id"), nullable=True)

    tenant = relationship("Tenant", back_populates="asset_requests")
    requester = relationship("User", foreign_keys=[requester_id], back_populates="asset_requests_made")
    approver = relationship("User", foreign_keys=[approver_id], back_populates="asset_requests_approved")

class Tenant(Base):
    __tablename__ = "tenants"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True)
    asset_requests = relationship("AssetRequest", back_populates="tenant")
    users = relationship("User", back_populates="tenant")

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True)
    is_approver = Column(Boolean, default=False)
    slack_id = Column(String, nullable=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"))

    tenant = relationship("Tenant", back_populates="users")
    asset_requests_made = relationship("AssetRequest", foreign_keys=[AssetRequest.requester_id], back_populates="requester")
    asset_requests_approved = relationship("AssetRequest", foreign_keys=[AssetRequest.approver_id], back_populates="approver")

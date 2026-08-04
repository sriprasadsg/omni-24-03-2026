"""
Pydantic models for ITAM (IT Asset Management) entities.

This module defines the data contracts for catalog entities and manual assets,
intended to be shared across ITAM-related backend services and endpoints.
"""
import uuid
from enum import Enum
from typing import Dict, Any, List, Literal, Optional

from pydantic import BaseModel, EmailStr, Field, ConfigDict

# Asset Tag and Lifecycle Status Decisions (from Phase 56, Task 1 Option A)
# These decisions are foundational and impact later phases (57-61).

# Tag format: IT-{seq:04d}
# This allows for short, readable tags for up to 9999 assets per tenant.
# It aligns with PITFALLS.md guidelines and is sufficient for physical labels.
ASSET_TAG_PREFIX = "IT"

# Lifecycle Status vocabulary
# These values are stored verbatim lowercase.
# Corresponds to ROADMAP.md Phase 56 success criterion 4 and ITAM-LIFE-01.
LIFECYCLE_STATUSES = (
    "deployable",
    "deployed",
    "archived",
    "retired",
    "disposed",
    "broken",
)

class LifecycleStatus(str, Enum):
    """
    Defines the possible lifecycle states for an ITAM asset.
    """
    DEPLOYABLE = "deployable"
    DEPLOYED = "deployed"
    ARCHIVED = "archived"
    RETIRED = "retired"
    DISPOSED = "disposed"
    BROKEN = "broken"

# Default lifecycle status for newly created manual assets.
# This value also serves as the read-time default for pre-existing agent-discovered
# assets that do not have a lifecycleStatus key.
DEFAULT_LIFECYCLE_STATUS = LifecycleStatus.DEPLOYABLE

# Asset source discriminators
# Used to differentiate agent-discovered assets from manually catalogued assets.
ASSET_SOURCE_AGENT = "agent"
ASSET_SOURCE_MANUAL = "manual"

# Generic Catalog Entities
class CatalogEntityCreate(BaseModel):
    """
    Base model for creating generic ITAM catalog entities.
    """
    name: str = Field(min_length=1, max_length=200)
    notes: Optional[str] = None

    model_config = ConfigDict(extra="forbid")

class CatalogEntityUpdate(BaseModel):
    """
    Base model for updating generic ITAM catalog entities.
    All fields are optional for partial updates.
    """
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    notes: Optional[str] = None

    model_config = ConfigDict(extra="forbid")

# Manual Asset Creation
class ManualAssetCreate(BaseModel):
    """
    Model for creating a manual ITAM asset.
    """
    name: str
    assetTag: Optional[str] = None
    manufacturerId: Optional[str] = None
    modelId: Optional[str] = None
    categoryId: Optional[str] = None
    supplierId: Optional[str] = None
    locationId: Optional[str] = None
    serialNumber: Optional[str] = None
    type: Optional[str] = None  # e.g., 'laptop', 'monitor'
    notes: Optional[str] = None
    lifecycleStatus: LifecycleStatus = DEFAULT_LIFECYCLE_STATUS
    customFields: Dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(extra="forbid")


# Suppliers — a distinct catalog entity per ITAM-CAT-03, not a bare name: carries its own
# contact shape on top of the generic CatalogEntityCreate/Update base.
class SupplierCreate(CatalogEntityCreate):
    """Request contract for creating a Supplier catalog entity."""
    contactName: Optional[str] = None
    contactEmail: Optional[EmailStr] = None
    contactPhone: Optional[str] = None
    website: Optional[str] = None
    address: Optional[str] = None

    model_config = ConfigDict(extra="forbid")


class SupplierUpdate(CatalogEntityUpdate):
    """Request contract for partially updating a Supplier catalog entity."""
    contactName: Optional[str] = None
    contactEmail: Optional[EmailStr] = None
    contactPhone: Optional[str] = None
    website: Optional[str] = None
    address: Optional[str] = None

    model_config = ConfigDict(extra="forbid")


# Asset Model fieldset definitions (ITAM-CAT-04, definition half). A fieldset lives only on a
# Model — 56-04 consumes these definitions when validating customFields values on an asset.
class CustomFieldDef(BaseModel):
    """A single typed custom-field definition within a fieldset."""
    key: str
    label: str
    type: Literal["text", "number", "date", "boolean", "select"]
    required: bool = False
    options: Optional[List[str]] = None

    model_config = ConfigDict(extra="forbid")


class FieldsetDef(BaseModel):
    """A named group of custom-field definitions attached to an asset Model."""
    name: str
    fields: List[CustomFieldDef]

    model_config = ConfigDict(extra="forbid")


class AssetModelCreate(CatalogEntityCreate):
    """Request contract for creating an asset Model — references a Manufacturer and a
    Category by id (validated at write time in itam_catalog_endpoints.py) and carries the
    model-level fieldset definitions."""
    modelNumber: Optional[str] = None
    manufacturerId: Optional[str] = None
    categoryId: Optional[str] = None
    fieldsets: List[FieldsetDef] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")


class AssetModelUpdate(CatalogEntityUpdate):
    """Request contract for partially updating an asset Model."""
    modelNumber: Optional[str] = None
    manufacturerId: Optional[str] = None
    categoryId: Optional[str] = None
    fieldsets: Optional[List[FieldsetDef]] = None

    model_config = ConfigDict(extra="forbid")


# Lifecycle Check-Out (Phase 57-01, ITAM-LIFE-02). targetType/targetId are a polymorphic
# pair (PD-01): a user or a location, never two separate optional id fields.
class CheckoutRequest(BaseModel):
    """Request contract for POST /api/assets/{asset_id}/checkout."""
    targetType: Literal["user", "location"]
    targetId: str
    note: Optional[str] = None
    expectedReturnDate: Optional[str] = None

    model_config = ConfigDict(extra="forbid")


# Lifecycle Check-In (Phase 57-02, ITAM-LIFE-03). Check-in takes no target — the
# target of a check-in is always stock.
class CheckinRequest(BaseModel):
    """Request contract for POST /api/assets/{asset_id}/checkin."""
    note: Optional[str] = None

    model_config = ConfigDict(extra="forbid")


# Physical Audit Mark (Phase 57-03, ITAM-LIFE-05). An omitted auditedAt means
# "audited now" — the server clock is used as the asserted date.
class AuditMarkRequest(BaseModel):
    """Request contract for POST /api/assets/{asset_id}/audit."""
    auditedAt: Optional[str] = None
    note: Optional[str] = None

    model_config = ConfigDict(extra="forbid")

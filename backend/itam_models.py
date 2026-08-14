"""
Pydantic models for ITAM (IT Asset Management) entities.

This module defines the data contracts for catalog entities and manual assets,
intended to be shared across ITAM-related backend services and endpoints.
"""
import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, Any, List, Literal, Optional
from bson import ObjectId  # Added for ObjectId reference in field_validator

from pydantic import Field, ConfigDict, field_validator
from dependencies import PyObjectId
import bson

from pydantic import BaseModel, EmailStr, Field, ConfigDict, field_validator

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


def _validate_iso8601_date(v: Optional[str]) -> Optional[str]:
    """WR-02 boundary check: rejects a caller-supplied date string that
    datetime.fromisoformat can't parse (after the same 'Z' -> '+00:00'
    normalization itam_lifecycle_endpoints.py's _overdue_row applies), so a
    malformed value never reaches the overdue report's date-math or its raw
    lexicographic-string $lt query comparison.

    Relocated here (Phase 59, Plan 59-01) from just above CheckoutRequest so
    that ManualAssetCreate and AssetPurchaseUpdate — both defined above where
    CheckoutRequest used to be the first binder — can also bind it via
    field_validator. Python evaluates a class body at definition time, so the
    function must be defined before any class that binds it. Exactly one
    definition of this function exists in this file."""
    if v is None:
        return v
    try:
        datetime.fromisoformat(v.replace("Z", "+00:00"))
    except ValueError:
        raise ValueError(f"must be an ISO-8601 date/datetime string, got {v!r}")
    return v


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
    # ITAM-FIN-01/02 (Phase 59): purchase/warranty fields. All optional —
    # agent-discovered assets have no admin-controlled creation step, and
    # financial data is routinely entered long after physical receipt.
    purchaseCostCents: Optional[int] = Field(None, ge=0)
    purchaseDate: Optional[str] = None
    poNumber: Optional[str] = Field(None, max_length=100)
    warrantyMonths: Optional[int] = Field(None, ge=0, le=600)
    # New fields for warranty expiry date, salvage value, and useful life years
    warranty_expiry_date: Optional[str] = None
    salvage_value: Optional[float] = Field(None, ge=0)
    useful_life_years: Optional[int] = Field(None, gt=0)

    model_config = ConfigDict(extra="forbid")

    _validate_purchase_date_ma = field_validator("purchaseDate")(_validate_iso8601_date)
    _validate_warranty_expiry_date_ma = field_validator("warranty_expiry_date")(_validate_iso8601_date)


class AssetPurchaseUpdate(BaseModel):
    """Request contract for PATCH /api/assets/{asset_id}/purchase.

    This is the primary way an agent-discovered asset — which has no
    ITAM-admin-controlled creation step — gets its financial record
    populated; it also corrects a manual asset's record after creation.

    Changing purchaseDate or warrantyMonths through this contract resets
    the asset's warrantyAlertSentAt marker, so a renewed or corrected
    warranty becomes alertable again (Plan 59-04's sweep idempotency
    contract)."""
    purchaseCostCents: Optional[int] = Field(None, ge=0)
    purchaseDate: Optional[str] = None
    poNumber: Optional[str] = Field(None, max_length=100)
    purchase_order_id: Optional[str] = Field(None, max_length=100) # Link to PurchaseOrder
    supplierId: Optional[str] = None
    warrantyMonths: Optional[int] = Field(None, ge=0, le=600)

    model_config = ConfigDict(extra="forbid")

    _validate_purchase_date_ma = field_validator("purchaseDate")(_validate_iso8601_date)
    _validate_warranty_expiry_date_ma = field_validator("warranty_expiry_date")(_validate_iso8601_date)


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
    # ITAM-FIN-03: Model-level depreciation policy fields
    usefulLifeYears: Optional[int] = Field(None, gt=0)
    salvageValueCents: Optional[int] = Field(None, ge=0)

    model_config = ConfigDict(extra="forbid")


class AssetModelUpdate(CatalogEntityUpdate):
    """Request contract for updating an asset Model."""
    modelNumber: Optional[str] = None
    manufacturerId: Optional[str] = None
    categoryId: Optional[str] = None
    fieldsets: Optional[List[FieldsetDef]] = None
    usefulLifeYears: Optional[int] = Field(None, gt=0)
    salvageValueCents: Optional[int] = Field(None, ge=0)

    model_config = ConfigDict(extra="forbid")


class AssetModel(AssetModelCreate):
    """Asset Model entity. Extends ModelCreate."""
    id: str = Field(default_factory=lambda: f"model-{uuid.uuid4().hex[:8]}", alias="_id")
    tenantId: str
    createdAt: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updatedAt: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    @field_validator("id", mode="before")
    def convert_objectid_to_str(cls, v):
        if isinstance(v, ObjectId):
            return str(v)
        return v


# Category — a distinct catalog entity per ITAM-CAT-02: a simple name, no
# special fields beyond the generic CatalogEntityCreate/Update base.
class CategoryCreate(CatalogEntityCreate):
    pass


class CategoryUpdate(CatalogEntityUpdate):
    pass


# Manual Assets - overrides base Asset with ITAM-specific fields
class Asset(BaseModel):
    """Represents an ITAM asset."""
    id: str = Field(default_factory=lambda: f"asset-{uuid.uuid4().hex[:8]}", alias="_id")
    tenantId: str
    name: str = Field(min_length=1, max_length=200)
    assetTag: str
    serialNumber: Optional[str] = None
    type: Optional[str] = None  # e.g., 'laptop', 'monitor', 'server'
    manufacturerId: Optional[str] = None
    modelId: Optional[str] = None
    categoryId: Optional[str] = None
    supplierId: Optional[str] = None
    locationId: Optional[str] = None
    notes: Optional[str] = None
    customFields: Dict[str, Any] = Field(default_factory=dict)
    lifecycleStatus: LifecycleStatus = DEFAULT_LIFECYCLE_STATUS
    parentAssetId: Optional[str] = None # For component attachments
    components: List[str] = Field(default_factory=list) # List of component IDs attached

    # Financial details
    purchaseCostCents: Optional[int] = Field(None, ge=0)
    purchaseDate: Optional[str] = None
    poNumber: Optional[str] = Field(None, max_length=100)
    purchase_order_id: Optional[str] = Field(None, max_length=100) # Links to PurchaseOrder.id
    warrantyMonths: Optional[int] = Field(None, ge=0, le=600)
    warrantyAlertSentAt: Optional[str] = None # ITAM-FIN-02: idempotency marker for warranty sweeps
    warranty_expiry_date: Optional[str] = None
    salvage_value: Optional[float] = Field(None, ge=0)
    useful_life_years: Optional[int] = Field(None, gt=0)

    createdAt: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updatedAt: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    @field_validator("id", mode="before")
    def convert_objectid_to_str(cls, v):
        if isinstance(v, ObjectId):
            return str(v)
        return v

    @field_validator("purchaseDate", mode="before")
    def _validate_purchase_date_field(cls, v):
        return _validate_iso8601_date(v)

    @field_validator("warrantyAlertSentAt", mode="before")
    def _validate_warranty_alert_sent_at_field(cls, v):
        return _validate_iso8601_date(v)

    @field_validator("warranty_expiry_date", mode="before")
    def _validate_warranty_expiry_date_field(cls, v):
        return _validate_iso8601_date(v)


# ITAM-LIC-01: License models (Phase 60).
class LicenseCreate(CatalogEntityCreate):
    """Request contract for creating a new software license."""
    seatCount: int = Field(ge=0)
    expiryDate: Optional[str] = None
    isReassignable: bool = True
    manufacturerId: Optional[str] = None
    productKey: Optional[str] = None # Encrypted in real deployments

    model_config = ConfigDict(extra="forbid")

    _validate_expiry_date = field_validator("expiryDate")(_validate_iso8601_date)


class LicenseUpdate(CatalogEntityUpdate):
    """Request contract for updating an existing software license."""
    seatCount: Optional[int] = Field(None, ge=0)
    expiryDate: Optional[str] = None
    isReassignable: Optional[bool] = None
    manufacturerId: Optional[str] = None
    productKey: Optional[str] = None

    model_config = ConfigDict(extra="forbid")

    _validate_expiry_date = field_validator("expiryDate")(_validate_iso8601_date)


class License(LicenseCreate):
    """Represents a software license entity."""
    id: str = Field(default_factory=lambda: f"lic-{uuid.uuid4().hex[:8]}", alias="_id")
    tenantId: str
    createdAt: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updatedAt: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    @field_validator("id", mode="before")
    def convert_objectid_to_str(cls, v):
        if isinstance(v, ObjectId):
            return str(v)
        return v


class LicenseSeatAssignmentRequest(BaseModel):
    """Request contract for assigning a license seat."""
    targetType: Literal["user", "asset"]
    targetId: str
    note: Optional[str] = None

    model_config = ConfigDict(extra="forbid")


class LicenseSeatAssignment(BaseModel):
    """Represents an assigned license seat."""
    id: str = Field(default_factory=lambda: f"la-{uuid.uuid4().hex[:8]}", alias="_id")
    tenantId: str
    licenseId: str
    targetType: Literal["user", "asset"]
    targetId: str
    assignedAt: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    assignedBy: str # Username or system
    note: Optional[str] = None

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    @field_validator("id", mode="before")
    def convert_objectid_to_str(cls, v):
        if isinstance(v, ObjectId):
            return str(v)
        return v


# ITAM-LIC-02: Consumable models (Phase 60).
class ConsumableCreate(CatalogEntityCreate):
    """Request contract for creating a new consumable."""
    initialQuantity: int = Field(ge=0)
    unitType: str = Field(min_length=1, max_length=50) # e.g., "unit", "pack", "meter"

    model_config = ConfigDict(extra="forbid")


class ConsumableUpdate(CatalogEntityUpdate):
    """Request contract for updating an existing consumable."""
    initialQuantity: Optional[int] = Field(None, ge=0) # Can't update directly, managed by checkout/checkin
    unitType: Optional[str] = Field(None, min_length=1, max_length=50)

    model_config = ConfigDict(extra="forbid")


class ConsumableCheckoutRequest(BaseModel):
    """Request contract for checking out a consumable."""
    quantity: int = Field(ge=1)
    assignedTo: str
    assignedToType: Literal["user", "asset", "location"]
    notes: Optional[str] = None

    model_config = ConfigDict(extra="forbid")


class ConsumableCheckoutRecord(BaseModel):
    """Represents a single checkout record for a consumable."""
    checkoutDate: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    quantity: int
    assignedTo: str
    assignedToType: Literal["user", "asset", "location", "system"]
    notes: Optional[str] = None

    model_config = ConfigDict(extra="forbid")


class Consumable(ConsumableCreate):
    """Represents a consumable entity."""
    id: str = Field(default_factory=lambda: f"con-{uuid.uuid4().hex[:8]}", alias="_id")
    tenantId: str
    availableQuantity: int # Derived from initialQuantity and checkout/checkin
    checkoutRecords: List[ConsumableCheckoutRecord] = Field(default_factory=list)
    createdAt: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updatedAt: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    @field_validator("id", mode="before")
    def convert_objectid_to_str(cls, v):
        if isinstance(v, ObjectId):
            return str(v)
        return v


# ITAM-LIC-03: Component models (Phase 60).
class ComponentCreate(CatalogEntityCreate):
    """Request contract for creating a new component."""
    type: Optional[str] = None
    serialNumber: Optional[str] = None
    manufacturerId: Optional[str] = None
    modelId: Optional[str] = None
    assetIds: List[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")


class ComponentUpdate(CatalogEntityUpdate):
    """Request contract for updating an existing component."""
    serialNumber: Optional[str] = None
    manufacturerId: Optional[str] = None
    modelId: Optional[str] = None

    model_config = ConfigDict(extra="forbid")


class Component(ComponentCreate):
    """Represents an ITAM component."""
    id: str = Field(default_factory=lambda: f"comp-{uuid.uuid4().hex[:8]}", alias="_id")
    tenantId: str
    createdAt: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updatedAt: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    parentAssetId: Optional[str] = None # ID of the asset this component is attached to

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    @field_validator("id", mode="before")
    def convert_objectid_to_str(cls, v):
        if isinstance(v, ObjectId):
            return str(v)
        return v


class CheckoutRequest(BaseModel):
    """Request contract for POST /api/assets/{asset_id}/checkout."""
    targetType: Literal["user", "location"]
    targetId: str
    note: Optional[str] = None
    expectedReturnDate: Optional[str] = None

    model_config = ConfigDict(extra="forbid")

    _validate_expected_return_date = field_validator("expectedReturnDate")(_validate_iso8601_date)


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

    _validate_audited_at = field_validator("auditedAt")(_validate_iso8601_date)


# Procurement - Purchase Order Models (Phase 71)
class PurchaseOrderItem(BaseModel):
    name: str
    quantity: int = Field(ge=1)
    unit_price: float = Field(ge=0.0)

class PurchaseOrderBase(BaseModel):
    order_number: str = Field(min_length=1, max_length=100)
    supplier_name: str = Field(min_length=1, max_length=200)
    order_date: datetime
    total_cost: float = Field(ge=0.0)
    items: List[PurchaseOrderItem] = Field(min_items=1)
    notes: Optional[str] = None

class PurchaseOrderCreate(PurchaseOrderBase):
    pass

class PurchaseOrderUpdate(BaseModel):
    order_number: Optional[str] = Field(None, min_length=1, max_length=100)
    supplier_name: Optional[str] = Field(None, min_length=1, max_length=200)
    order_date: Optional[datetime] = None
    total_cost: Optional[float] = Field(None, ge=0.0)
    items: Optional[List[PurchaseOrderItem]] = Field(None, min_items=1)
    notes: Optional[str] = None

class PurchaseOrder(PurchaseOrderBase):
    id: str = Field(default_factory=lambda: f"po-{uuid.uuid4().hex[:8]}", alias="_id")
    tenantId: str
    createdAt: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updatedAt: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    @field_validator("id", mode="before")
    def convert_objectid_to_str_po(cls, v):
        if isinstance(v, ObjectId):
            return str(v)
        return v



# Label Sheet (Phase 58-04, ITAM-CAT-05). Bounds how much PDF-generation work
# one request can trigger — enforced as an explicit 400 refusal in the
# endpoint handler, not as a Pydantic length constraint, so an over-length
# request gets a body explaining what was wrong rather than a bare 422.
MAX_LABEL_SHEET_ASSETS = 500


class LabelSheetRequest(BaseModel):
    """Request contract for POST /api/assets/labels/sheet. Deliberately left
    without Pydantic length constraints on assetIds — the emptiness check
    and the MAX_LABEL_SHEET_ASSETS cap are both enforced in the handler so
    both violations produce a 400 with an explanatory body instead of a 422."""
    assetIds: List[str]

    model_config = ConfigDict(extra="forbid")
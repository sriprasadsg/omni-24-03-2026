import pytest
from datetime import datetime, timezone
from unittest.mock import MagicMock, AsyncMock

from database import TenantIsolatedDatabase
from itam_models import PurchaseOrder, PurchaseOrderCreate, PurchaseOrderUpdate, PurchaseOrderItem
from itam_procurement_service import ItamProcurementService

MOCK_TENANT_ID = "test-tenant-123"
MOCK_PO_ID = "po-12345"
MOCK_ORDER_NUMBER = "PO-UNIT-001"
MOCK_SUPPLIER_NAME = "Test Supplier Inc."
MOCK_ORDER_DATE = datetime(2023, 1, 1, 10, 0, 0, tzinfo=timezone.utc)
MOCK_TOTAL_COST = 1500.50
MOCK_ITEMS = [
    PurchaseOrderItem(name="Laptop", quantity=1, unit_price=1000.00),
    PurchaseOrderItem(name="Monitor", quantity=2, unit_price=250.25)
]
MOCK_NOTES = "Test notes for purchase order."

@pytest.fixture
def mock_db() -> TenantIsolatedDatabase:
    db_instance = AsyncMock(spec=TenantIsolatedDatabase)
    mock_collection = MagicMock()
    mock_collection.insert_one = AsyncMock()
    mock_collection.find_one = AsyncMock()
    mock_collection.find_one_and_update = AsyncMock()
    mock_collection.delete_one = AsyncMock()
    db_instance.purchase_orders = mock_collection
    return db_instance

@pytest.fixture
def procurement_service(mock_db: TenantIsolatedDatabase) -> ItamProcurementService:
    return ItamProcurementService(mock_db)

@pytest.mark.asyncio
async def test_create_purchase_order(procurement_service: ItamProcurementService, mock_db: TenantIsolatedDatabase):
    po_create_data = PurchaseOrderCreate(
        order_number=MOCK_ORDER_NUMBER,
        supplier_name=MOCK_SUPPLIER_NAME,
        order_date=MOCK_ORDER_DATE,
        total_cost=MOCK_TOTAL_COST,
        items=MOCK_ITEMS,
        notes=MOCK_NOTES
    )

    mock_inserted_id = "mock_mongo_id_123"
    mock_db.purchase_orders.insert_one.return_value = AsyncMock(inserted_id=mock_inserted_id)

    mock_po_doc = po_create_data.model_dump()
    mock_po_doc.update({
        "_id": MOCK_PO_ID,
        "id": MOCK_PO_ID,
        "tenantId": MOCK_TENANT_ID,
        "createdAt": datetime.now(timezone.utc),
        "updatedAt": datetime.now(timezone.utc)
    })
    mock_db.purchase_orders.find_one.return_value = mock_po_doc

    created_po = await procurement_service.create_purchase_order(MOCK_TENANT_ID, po_create_data)

    mock_db.purchase_orders.insert_one.assert_called_once()
    inserted_doc = mock_db.purchase_orders.insert_one.call_args[0][0]
    assert inserted_doc["id"]  # explicit id must be set before insert, not left to Mongo's _id
    mock_db.purchase_orders.find_one.assert_called_once_with({"_id": mock_inserted_id})

    assert isinstance(created_po, PurchaseOrder)
    assert created_po.order_number == MOCK_ORDER_NUMBER
    assert created_po.tenantId == MOCK_TENANT_ID
    assert len(created_po.items) == 2

@pytest.mark.asyncio
async def test_get_purchase_order(procurement_service: ItamProcurementService, mock_db: TenantIsolatedDatabase):
    mock_po_doc = {
        "_id": MOCK_PO_ID,
        "id": MOCK_PO_ID,
        "tenantId": MOCK_TENANT_ID,
        "order_number": MOCK_ORDER_NUMBER,
        "supplier_name": MOCK_SUPPLIER_NAME,
        "order_date": MOCK_ORDER_DATE,
        "total_cost": MOCK_TOTAL_COST,
        "items": [item.model_dump() for item in MOCK_ITEMS],
        "notes": MOCK_NOTES,
        "createdAt": datetime.now(timezone.utc),
        "updatedAt": datetime.now(timezone.utc)
    }
    mock_db.purchase_orders.find_one.return_value = mock_po_doc

    found_po = await procurement_service.get_purchase_order(MOCK_TENANT_ID, MOCK_PO_ID)

    mock_db.purchase_orders.find_one.assert_called_once_with({"id": MOCK_PO_ID, "tenantId": MOCK_TENANT_ID})
    assert isinstance(found_po, PurchaseOrder)
    assert found_po.id == MOCK_PO_ID
    assert found_po.order_number == MOCK_ORDER_NUMBER

@pytest.mark.asyncio
async def test_get_purchase_order_not_found(procurement_service: ItamProcurementService, mock_db: TenantIsolatedDatabase):
    mock_db.purchase_orders.find_one.return_value = None
    found_po = await procurement_service.get_purchase_order(MOCK_TENANT_ID, "non-existent-id")
    assert found_po is None

@pytest.mark.asyncio
async def test_list_purchase_orders(procurement_service: ItamProcurementService, mock_db: TenantIsolatedDatabase):
    mock_po_doc_1 = {
        "_id": "po-a1", "id": "po-a1", "tenantId": MOCK_TENANT_ID, "order_number": "PO-LIST-001",
        "supplier_name": "Sup A", "order_date": MOCK_ORDER_DATE, "total_cost": 100,
        "items": [{"name": "Item1", "quantity": 1, "unit_price": 100}],
        "createdAt": datetime.now(timezone.utc), "updatedAt": datetime.now(timezone.utc)
    }
    mock_po_doc_2 = {
        "_id": "po-b2", "id": "po-b2", "tenantId": MOCK_TENANT_ID, "order_number": "PO-LIST-002",
        "supplier_name": "Sup B", "order_date": MOCK_ORDER_DATE, "total_cost": 200,
        "items": [{"name": "Item2", "quantity": 1, "unit_price": 200}],
        "createdAt": datetime.now(timezone.utc), "updatedAt": datetime.now(timezone.utc)
    }

    mock_cursor = MagicMock()
    mock_cursor.to_list = AsyncMock(return_value=[mock_po_doc_1, mock_po_doc_2])
    mock_cursor.skip.return_value = mock_cursor
    mock_cursor.limit.return_value = mock_cursor

    mock_db.purchase_orders.find.return_value = mock_cursor

    pos = await procurement_service.list_purchase_orders(MOCK_TENANT_ID, skip=0, limit=10)

    mock_db.purchase_orders.find.assert_called_once_with({"tenantId": MOCK_TENANT_ID})
    mock_cursor.skip.assert_called_once_with(0)
    mock_cursor.limit.assert_called_once_with(10)
    assert len(pos) == 2
    assert all(isinstance(po, PurchaseOrder) for po in pos)
    assert pos[0].order_number == "PO-LIST-001"

@pytest.mark.asyncio
async def test_update_purchase_order(procurement_service: ItamProcurementService, mock_db: TenantIsolatedDatabase):
    update_data = PurchaseOrderUpdate(notes="Updated notes", total_cost=2000.00)

    updated_po_doc = {
        "_id": MOCK_PO_ID, "id": MOCK_PO_ID, "tenantId": MOCK_TENANT_ID, "order_number": MOCK_ORDER_NUMBER,
        "supplier_name": MOCK_SUPPLIER_NAME, "order_date": MOCK_ORDER_DATE, "total_cost": 2000.00,
        "items": [item.model_dump() for item in MOCK_ITEMS], "notes": "Updated notes",
        "createdAt": datetime.now(timezone.utc), "updatedAt": datetime.now(timezone.utc)
    }

    mock_db.purchase_orders.find_one_and_update.return_value = updated_po_doc

    updated_po = await procurement_service.update_purchase_order(MOCK_TENANT_ID, MOCK_PO_ID, update_data)

    mock_db.purchase_orders.find_one_and_update.assert_called_once()
    assert isinstance(updated_po, PurchaseOrder)
    assert updated_po.id == MOCK_PO_ID
    assert updated_po.notes == "Updated notes"
    assert updated_po.total_cost == 2000.00

@pytest.mark.asyncio
async def test_update_purchase_order_not_found(procurement_service: ItamProcurementService, mock_db: TenantIsolatedDatabase):
    update_data = PurchaseOrderUpdate(notes="Updated notes")
    mock_db.purchase_orders.find_one_and_update.return_value = None
    updated_po = await procurement_service.update_purchase_order(MOCK_TENANT_ID, "non-existent-id", update_data)
    assert updated_po is None

@pytest.mark.asyncio
async def test_delete_purchase_order(procurement_service: ItamProcurementService, mock_db: TenantIsolatedDatabase):
    mock_result = AsyncMock(deleted_count=1)
    mock_db.purchase_orders.delete_one.return_value = mock_result

    deleted = await procurement_service.delete_purchase_order(MOCK_TENANT_ID, MOCK_PO_ID)

    mock_db.purchase_orders.delete_one.assert_called_once_with({"id": MOCK_PO_ID, "tenantId": MOCK_TENANT_ID})
    assert deleted

@pytest.mark.asyncio
async def test_delete_purchase_order_not_found(procurement_service: ItamProcurementService, mock_db: TenantIsolatedDatabase):
    mock_result = AsyncMock(deleted_count=0)
    mock_db.purchase_orders.delete_one.return_value = mock_result
    deleted = await procurement_service.delete_purchase_order(MOCK_TENANT_ID, "non-existent-id")
    assert not deleted
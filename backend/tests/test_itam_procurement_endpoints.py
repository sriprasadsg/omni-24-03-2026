import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient
from app import _fastapi_app
from auth_types import TokenData
from authentication_service import get_current_user
from itam_models import PurchaseOrder
from itam_procurement_service import ItamProcurementService

@pytest.fixture(scope="module")
def test_client():
    with TestClient(_fastapi_app) as client:
        yield client

MOCK_TENANT_ID = "test-tenant-123"
MOCK_USERNAME = "testuser"
MOCK_PO_ID = "po-endpoint-123"
MOCK_ORDER_NUMBER = "PO-EP-001"
MOCK_SUPPLIER_NAME = "Endpoint Supplier Co."
MOCK_ORDER_DATE = datetime(2023, 1, 15, 10, 0, 0, tzinfo=timezone.utc)
MOCK_TOTAL_COST = 2500.75
MOCK_ITEMS = [
    {"name": "Server", "quantity": 1, "unit_price": 2000.00},
    {"name": "RAM", "quantity": 4, "unit_price": 125.18}
]
MOCK_NOTES = "Endpoint test notes."

MOCK_PO_DOC = {
    "id": MOCK_PO_ID,
    "tenantId": MOCK_TENANT_ID,
    "order_number": MOCK_ORDER_NUMBER,
    "supplier_name": MOCK_SUPPLIER_NAME,
    "order_date": MOCK_ORDER_DATE.isoformat(),
    "total_cost": MOCK_TOTAL_COST,
    "items": MOCK_ITEMS,
    "notes": MOCK_NOTES,
    "createdAt": datetime.now(timezone.utc).isoformat(),
    "updatedAt": datetime.now(timezone.utc).isoformat()
}

@pytest.fixture(autouse=True)
def patch_dependencies():
    """Use FastAPI dependency_overrides for get_current_user, patch verify_permission."""
    mock_user = TokenData(username=MOCK_USERNAME, tenant_id=MOCK_TENANT_ID, role="admin")
    _fastapi_app.dependency_overrides[get_current_user] = lambda: mock_user

    mock_service = AsyncMock(spec=ItamProcurementService)

    with patch("itam_procurement_endpoints.verify_permission", new_callable=AsyncMock, return_value=True), \
         patch("itam_procurement_endpoints.get_database", return_value=AsyncMock()), \
         patch("itam_procurement_endpoints.ItamProcurementService", return_value=mock_service):
        yield mock_service

    # Cleanup
    if get_current_user in _fastapi_app.dependency_overrides:
        del _fastapi_app.dependency_overrides[get_current_user]

def test_create_purchase_order_endpoint(patch_dependencies):
    patch_dependencies.create_purchase_order.return_value = PurchaseOrder.model_validate(MOCK_PO_DOC)

    with TestClient(_fastapi_app) as client:
        po_create_payload = {
            "order_number": MOCK_ORDER_NUMBER,
            "supplier_name": MOCK_SUPPLIER_NAME,
            "order_date": MOCK_ORDER_DATE.isoformat(),
            "total_cost": MOCK_TOTAL_COST,
            "items": MOCK_ITEMS,
            "notes": MOCK_NOTES
        }
        response = client.post("/api/v1/itam/purchase-orders", json=po_create_payload)
        assert response.status_code == 201
        assert response.json()["order_number"] == MOCK_ORDER_NUMBER

def test_get_purchase_order_endpoint(patch_dependencies):
    patch_dependencies.get_purchase_order.return_value = PurchaseOrder.model_validate(MOCK_PO_DOC)

    with TestClient(_fastapi_app) as client:
        response = client.get(f"/api/v1/itam/purchase-orders/{MOCK_PO_ID}")
        assert response.status_code == 200
        data = response.json()
        assert data.get("id") == MOCK_PO_ID or data.get("_id") == MOCK_PO_ID

def test_get_purchase_order_endpoint_not_found(patch_dependencies):
    patch_dependencies.get_purchase_order.return_value = None

    with TestClient(_fastapi_app) as client:
        response = client.get("/api/v1/itam/purchase-orders/non-existent-po")
        assert response.status_code == 404

def test_list_purchase_orders_endpoint(patch_dependencies):
    mock_po_list = [
        PurchaseOrder.model_validate(MOCK_PO_DOC),
        PurchaseOrder.model_validate({**MOCK_PO_DOC, "id": "po-2", "order_number": "PO-EP-002"})
    ]
    patch_dependencies.list_purchase_orders.return_value = mock_po_list

    with TestClient(_fastapi_app) as client:
        response = client.get("/api/v1/itam/purchase-orders?skip=0&limit=10")
        assert response.status_code == 200
        assert len(response.json()) == 2

def test_update_purchase_order_endpoint(patch_dependencies):
    updated_po_doc = {**MOCK_PO_DOC, "notes": "Updated notes from endpoint."}
    patch_dependencies.update_purchase_order.return_value = PurchaseOrder.model_validate(updated_po_doc)

    with TestClient(_fastapi_app) as client:
        response = client.put(f"/api/v1/itam/purchase-orders/{MOCK_PO_ID}", json={"notes": "Updated notes from endpoint."})
        assert response.status_code == 200
        assert response.json()["notes"] == "Updated notes from endpoint."

def test_update_purchase_order_endpoint_not_found(patch_dependencies):
    patch_dependencies.update_purchase_order.return_value = None

    with TestClient(_fastapi_app) as client:
        response = client.put("/api/v1/itam/purchase-orders/non-existent-po", json={"notes": "test"})
        assert response.status_code == 404

def test_delete_purchase_order_endpoint(patch_dependencies):
    patch_dependencies.delete_purchase_order.return_value = True

    with TestClient(_fastapi_app) as client:
        response = client.delete(f"/api/v1/itam/purchase-orders/{MOCK_PO_ID}")
        assert response.status_code == 204

def test_delete_purchase_order_endpoint_not_found(patch_dependencies):
    patch_dependencies.delete_purchase_order.return_value = False

    with TestClient(_fastapi_app) as client:
        response = client.delete("/api/v1/itam/purchase-orders/non-existent-po")
        assert response.status_code == 404

def test_permission_denied_endpoint():
    # No patch_dependencies fixture - manual setup with deny permission
    mock_user = TokenData(username=MOCK_USERNAME, tenant_id=MOCK_TENANT_ID, role="admin")
    _fastapi_app.dependency_overrides[get_current_user] = lambda: mock_user

    mock_service = AsyncMock(spec=ItamProcurementService)

    with patch("itam_procurement_endpoints.verify_permission", new_callable=AsyncMock, return_value=False), \
         patch("itam_procurement_endpoints.get_database", return_value=AsyncMock()), \
         patch("itam_procurement_endpoints.ItamProcurementService", return_value=mock_service):

        with TestClient(_fastapi_app) as client:
            response = client.post("/api/v1/itam/purchase-orders", json={
                "order_number": "PO-DENY", "supplier_name": "Sup", "order_date": MOCK_ORDER_DATE.isoformat(),
                "total_cost": 100, "items": [{"name": "Test", "quantity": 1, "unit_price": 100}]
            })
            assert response.status_code == 403

    if get_current_user in _fastapi_app.dependency_overrides:
        del _fastapi_app.dependency_overrides[get_current_user]
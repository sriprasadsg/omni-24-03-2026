// frontend/types/itam.ts
import { datetime } from "types/datetime"; // Assuming datetime type is defined elsewhere

export interface PurchaseOrderItem {
    name: string;
    quantity: number;
    unit_price: number;
}

export interface PurchaseOrder {
    id: string;
    tenantId: string;
    order_number: string;
    supplier_name: string;
    order_date: datetime;
    total_cost: number;
    items: PurchaseOrderItem[];
    notes?: string;
    createdAt: datetime;
    updatedAt: datetime;
}

export interface PurchaseOrderCreate {
    order_number: string;
    supplier_name: string;
    order_date: datetime;
    total_cost: number;
    items: PurchaseOrderItem[];
    notes?: string;
}

export interface PurchaseOrderUpdate {
    order_number?: string;
    supplier_name?: string;
    order_date?: datetime;
    total_cost?: number;
    items?: PurchaseOrderItem[];
    notes?: string;
}

export interface Asset {
    id: string;
    tenantId: string;
    name: string;
    assetTag: string;
    serialNumber?: string;
    type?: string;
    manufacturerId?: string;
    modelId?: string;
    categoryId?: string;
    supplierId?: string;
    locationId?: string;
    notes?: string;
    customFields: Record<string, any>;
    lifecycleStatus: string;
    parentAssetId?: string;
    components: string[];
    purchaseCostCents?: number;
    purchaseDate?: datetime;
    poNumber?: string;
    purchase_order_id?: string;
    warrantyMonths?: number;
    warrantyAlertSentAt?: datetime;
    warranty_expiry_date?: datetime;
    salvage_value?: number;
    useful_life_years?: number;
    createdAt: datetime;
    updatedAt: datetime;
}

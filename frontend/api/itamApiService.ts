// frontend/api/itamApiService.ts
import axios from "axios";
import { PurchaseOrder, PurchaseOrderCreate, PurchaseOrderUpdate } from "../types/itam";

const API_BASE_URL = "/api/v1/itam/purchase-orders";

export const itamApiService = {
    async createPurchaseOrder(poData: PurchaseOrderCreate): Promise<PurchaseOrder> {
        const response = await axios.post<PurchaseOrder>(API_BASE_URL, poData);
        return response.data;
    },

    async getPurchaseOrder(id: string): Promise<PurchaseOrder> {
        const response = await axios.get<PurchaseOrder>(`${API_BASE_URL}/${id}`);
        return response.data;
    },

    async listPurchaseOrders(): Promise<PurchaseOrder[]> {
        const response = await axios.get<PurchaseOrder[]>(API_BASE_URL);
        return response.data;
    },

    async updatePurchaseOrder(id: string, poData: PurchaseOrderUpdate): Promise<PurchaseOrder> {
        const response = await axios.put<PurchaseOrder>(`${API_BASE_URL}/${id}`, poData);
        return response.data;
    },

    async deletePurchaseOrder(id: string): Promise<void> {
        await axios.delete(`${API_BASE_URL}/${id}`);
    }
};
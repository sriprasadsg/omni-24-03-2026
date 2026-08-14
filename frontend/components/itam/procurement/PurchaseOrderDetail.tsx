// frontend/components/itam/procurement/PurchaseOrderDetail.tsx
import React, { useEffect, useState } from 'react';
import { useParams, Link, useNavigate } from 'react-router-dom';
import { PurchaseOrder } from '../../../types/itam';
import { itamApiService } from '../../../api/itamApiService';

const PurchaseOrderDetail: React.FC = () => {
    const { id } = useParams<{ id: string }>();
    const navigate = useNavigate();
    const [purchaseOrder, setPurchaseOrder] = useState<PurchaseOrder | null>(null);
    const [loading, setLoading] = useState<boolean>(true);
    const [error, setError] = useState<string | null>(null);

    useEffect(() => {
        const fetchPurchaseOrder = async () => {
            if (!id) {
                setError("Purchase Order ID is missing.");
                setLoading(false);
                return;
            }
            try {
                setLoading(true);
                const data = await itamApiService.getPurchaseOrder(id);
                setPurchaseOrder(data);
            } catch (err) {
                console.error(`Failed to fetch purchase order ${id}:`, err);
                setError("Failed to load purchase order.");
            } finally {
                setLoading(false);
            }
        };

        fetchPurchaseOrder();
    }, [id]);

    const handleDelete = async () => {
        if (!id || !window.confirm("Are you sure you want to delete this purchase order?")) {
            return;
        }
        try {
            await itamApiService.deletePurchaseOrder(id);
            navigate("/itam/purchase-orders");
        } catch (err) {
            console.error(`Failed to delete purchase order ${id}:`, err);
            setError("Failed to delete purchase order.");
        }
    };

    if (loading) return <div>Loading purchase order details...</div>;
    if (error) return <div className="text-red-500">{error}</div>;
    if (!purchaseOrder) return <div className="text-gray-500">Purchase Order not found.</div>;

    return (
        <div className="container mx-auto p-4">
            <h1 className="text-2xl font-bold mb-4">Purchase Order: {purchaseOrder.order_number}</h1>
            <div className="bg-white shadow overflow-hidden sm:rounded-lg mb-4">
                <div className="px-4 py-5 sm:px-6">
                    <h3 className="text-lg leading-6 font-medium text-gray-900">Purchase Order Details</h3>
                </div>
                <div className="border-t border-gray-200">
                    <dl>
                        <div className="bg-gray-50 px-4 py-5 sm:grid sm:grid-cols-3 sm:gap-4 sm:px-6">
                            <dt className="text-sm font-medium text-gray-500">Order Number</dt>
                            <dd className="mt-1 text-sm text-gray-900 sm:mt-0 sm:col-span-2">{purchaseOrder.order_number}</dd>
                        </div>
                        <div className="bg-white px-4 py-5 sm:grid sm:grid-cols-3 sm:gap-4 sm:px-6">
                            <dt className="text-sm font-medium text-gray-500">Supplier Name</dt>
                            <dd className="mt-1 text-sm text-gray-900 sm:mt-0 sm:col-span-2">{purchaseOrder.supplier_name}</dd>
                        </div>
                        <div className="bg-gray-50 px-4 py-5 sm:grid sm:grid-cols-3 sm:gap-4 sm:px-6">
                            <dt className="text-sm font-medium text-gray-500">Order Date</dt>
                            <dd className="mt-1 text-sm text-gray-900 sm:mt-0 sm:col-span-2">{new Date(purchaseOrder.order_date).toLocaleDateString()}</dd>
                        </div>
                        <div className="bg-white px-4 py-5 sm:grid sm:grid-cols-3 sm:gap-4 sm:px-6">
                            <dt className="text-sm font-medium text-gray-500">Total Cost</dt>
                            <dd className="mt-1 text-sm text-gray-900 sm:mt-0 sm:col-span-2">${purchaseOrder.total_cost.toFixed(2)}</dd>
                        </div>
                        <div className="bg-gray-50 px-4 py-5 sm:grid sm:grid-cols-3 sm:gap-4 sm:px-6">
                            <dt className="text-sm font-medium text-gray-500">Notes</dt>
                            <dd className="mt-1 text-sm text-gray-900 sm:mt-0 sm:col-span-2">{purchaseOrder.notes || 'N/A'}</dd>
                        </div>
                        <div className="bg-white px-4 py-5 sm:grid sm:grid-cols-3 sm:gap-4 sm:px-6">
                            <dt className="text-sm font-medium text-gray-500">Items</dt>
                            <dd className="mt-1 text-sm text-gray-900 sm:mt-0 sm:col-span-2">
                                <ul className="border border-gray-200 rounded-md divide-y divide-gray-200">
                                    {purchaseOrder.items.map((item, index) => (
                                        <li key={index} className="pl-3 pr-4 py-3 flex items-center justify-between text-sm">
                                            <div className="w-0 flex-1 flex items-center">
                                                <span className="ml-2 flex-1 w-0 truncate">{item.name}</span>
                                            </div>
                                            <div className="ml-4 flex-shrink-0">
                                                {item.quantity} x ${item.unit_price.toFixed(2)}
                                            </div>
                                        </li>
                                    ))}
                                </ul>
                            </dd>
                        </div>
                    </dl>
                </div>
            </div>
            <div className="flex space-x-4">
                <Link to={`/itam/purchase-orders/${purchaseOrder.id}/edit`} className="bg-yellow-500 hover:bg-yellow-700 text-white font-bold py-2 px-4 rounded">
                    Edit
                </Link>
                <button onClick={handleDelete} className="bg-red-500 hover:bg-red-700 text-white font-bold py-2 px-4 rounded">
                    Delete
                </button>
                <Link to="/itam/purchase-orders" className="bg-gray-500 hover:bg-gray-700 text-white font-bold py-2 px-4 rounded">
                    Back to List
                </Link>
            </div>
        </div>
    );
};

export default PurchaseOrderDetail;
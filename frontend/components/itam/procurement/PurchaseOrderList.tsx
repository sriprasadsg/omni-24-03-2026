// frontend/components/itam/procurement/PurchaseOrderList.tsx
import React, { useEffect, useState } from 'react';
import { PurchaseOrder } from '../../../types/itam';
import { itamApiService } from '../../../api/itamApiService';
import { Link } from 'react-router-dom';

const PurchaseOrderList: React.FC = () => {
    const [purchaseOrders, setPurchaseOrders] = useState<PurchaseOrder[]>([]);
    const [loading, setLoading] = useState<boolean>(true);
    const [error, setError] = useState<string | null>(null);

    useEffect(() => {
        const fetchPurchaseOrders = async () => {
            try {
                setLoading(true);
                const data = await itamApiService.listPurchaseOrders();
                setPurchaseOrders(data);
            } catch (err) {
                console.error("Failed to fetch purchase orders:", err);
                setError("Failed to load purchase orders.");
            } finally {
                setLoading(false);
            }
        };

        fetchPurchaseOrders();
    }, []);

    if (loading) return <div>Loading purchase orders...</div>;
    if (error) return <div className="text-red-500">{error}</div>;

    return (
        <div className="container mx-auto p-4">
            <h1 className="text-2xl font-bold mb-4">Purchase Orders</h1>
            <Link to="/itam/purchase-orders/new" className="bg-blue-500 hover:bg-blue-700 text-white font-bold py-2 px-4 rounded mb-4 inline-block">
                Create New Purchase Order
            </Link>
            {purchaseOrders.length === 0 ? (
                <p>No purchase orders found.</p>
            ) : (
                <table className="min-w-full bg-white border border-gray-200">
                    <thead>
                        <tr>
                            <th className="py-2 px-4 border-b">Order Number</th>
                            <th className="py-2 px-4 border-b">Supplier</th>
                            <th className="py-2 px-4 border-b">Order Date</th>
                            <th className="py-2 px-4 border-b">Total Cost</th>
                            <th className="py-2 px-4 border-b">Actions</th>
                        </tr>
                    </thead>
                    <tbody>
                        {purchaseOrders.map((po) => (
                            <tr key={po.id}>
                                <td className="py-2 px-4 border-b">{po.order_number}</td>
                                <td className="py-2 px-4 border-b">{po.supplier_name}</td>
                                <td className="py-2 px-4 border-b">{new Date(po.order_date).toLocaleDateString()}</td>
                                <td className="py-2 px-4 border-b">${po.total_cost.toFixed(2)}</td>
                                <td className="py-2 px-4 border-b">
                                    <Link to={`/itam/purchase-orders/${po.id}`} className="text-blue-600 hover:underline mr-2">View</Link>
                                    <Link to={`/itam/purchase-orders/${po.id}/edit`} className="text-yellow-600 hover:underline">Edit</Link>
                                </td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            )}
        </div>
    );
};

export default PurchaseOrderList;
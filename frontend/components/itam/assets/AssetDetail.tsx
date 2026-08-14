// frontend/components/itam/assets/AssetDetail.tsx
import React, { useEffect, useState } from 'react';
import { useParams, Link } from 'react-router-dom';
import { Asset, PurchaseOrder } from '../../../types/itam';
// Assumes assetApiService exists, otherwise use generic API
// import { assetApiService } from '../../../api/assetApiService';
import { itamApiService } from '../../../api/itamApiService';

// Minimal interface for the asset API if a dedicated one doesn't exist
const fetchAsset = async (assetId: string): Promise<Asset> => {
    const response = await fetch(`/api/assets/${assetId}`);
    if (!response.ok) {
        throw new Error("Failed to fetch asset");
    }
    return response.json();
};

const AssetDetail: React.FC = () => {
    const { id } = useParams<{ id: string }>();
    const [asset, setAsset] = useState<Asset | null>(null);
    const [linkedPurchaseOrder, setLinkedPurchaseOrder] = useState<PurchaseOrder | null>(null);
    const [loading, setLoading] = useState<boolean>(true);
    const [error, setError] = useState<string | null>(null);

    useEffect(() => {
        const fetchData = async () => {
            if (!id) {
                setError("Asset ID is missing.");
                setLoading(false);
                return;
            }
            try {
                setLoading(true);
                const assetData = await fetchAsset(id);
                setAsset(assetData);

                // Fetch linked Purchase Order if purchase_order_id is present
                if (assetData.purchase_order_id) {
                    try {
                        const poData = await itamApiService.getPurchaseOrder(assetData.purchase_order_id);
                        setLinkedPurchaseOrder(poData);
                    } catch (poErr) {
                        console.warn(`Failed to fetch linked purchase order ${assetData.purchase_order_id}:`, poErr);
                        // Don't fail the whole page just because linked PO fetch failed
                    }
                }
            } catch (err) {
                console.error(`Failed to fetch asset ${id}:`, err);
                setError("Failed to load asset.");
            } finally {
                setLoading(false);
            }
        };

        fetchData();
    }, [id]);

    if (loading) return <div>Loading asset details</div>;
    if (error) return <div className="text-red-500">{error</div>;
    if (!asset) return <div className="text-gray-500">Asset not found</div>;

    return (
        <div className="container mx-auto p-4">
            <h1 className="text-2xl font-bold mb-4">Asset: {asset.name} ({asset.assetTag})</h1>
            <div className="bg-white shadow overflow-hidden sm:rounded-lg mb-4">
                <div className="px-4 py-5 sm:px-6">
                    <h3 className="text-lg leading-6 font-medium text-gray-900">Asset Details</h3>
               </div>
                <div className="border-t border-gray-200">
                    <dl>
                        <div className="bg-gray-50 px-4 py-5 sm:grid sm:grid-cols-3 sm:gap-4 sm:px-6">
                            <dt className="text-sm font-medium text-gray-500">Asset Tag</dt>
                            <dd className="mt-1 text-sm text-gray-900 sm:mt-0 sm:col-span-2">{asset.assetTag</dd>
                       </div>
                        <div className="bg-white px-4 py-5 sm:grid sm:grid-cols-3 sm:gap-4 sm:px-6">
                            <dt className="text-sm font-medium text-gray-500">Type</dt>
                            <dd className="mt-1 text-sm text-gray-900 sm:mt-0 sm:col-span-2">{asset.type || 'N/A'</dd>
                       </div>
                        <div className="bg-gray-50 px-4 py-5 sm:grid sm:grid-cols-3 sm:gap-4 sm:px-6">
                            <dt className="text-sm font-medium text-gray-500">Lifecycle Status</dt>
                            <dd className="mt-1 text-sm text-gray-900 sm:mt-0 sm:col-span-2">{asset.lifecycleStatus</dd>
                       </div>
                        <div className="bg-white px-4 py-5 sm:grid sm:grid-cols-3 sm:gap-4 sm:px-6">
                            <dt className="text-sm font-medium text-gray-500">Linked Purchase Order</dt>
                            <dd className="mt-1 text-sm text-gray-900 sm:mt-0 sm:col-span-2">
                                {linkedPurchaseOrder ? (
                                    <Link to={`/itam/purchase-orders/${linkedPurchaseOrder.id}`} className="text-blue-600 hover:underline">
                                        {linkedPurchaseOrder.order_number} ({linkedPurchaseOrder.supplier_name})
                                   </Link>
                                ) : asset.purchase_order_id ? (
                                    <span className="text-gray-400">Purchase Order ID: {asset.purchase_order_id} (details unavailable</span>
                                ) : (
                                    <span className="text-gray-400">Not linked</span>
                                )}
                           </dd>
                       </div>
                   </dl>
               </div>
           </div>
       </div>
    );
};

export default AssetDetail;
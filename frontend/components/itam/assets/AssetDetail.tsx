// frontend/components/itam/assets/AssetDetail.tsx
import React, { useEffect, useState } from 'react';
import { useParams, Link } from 'react-router-dom';
import { Asset, PurchaseOrder } from '../../../types/itam';
import { itamApiService } from '../../../api/itamApiService';
import AssetEditForm from './AssetEditForm'; // New component for editing

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
    const [editMode, setEditMode] = useState<boolean>(false);

    // Calculate depreciation and warranty status dynamically on frontend
    const calculateDepreciation = (asset: Asset) => {
        if (!asset.purchaseCostCents || !asset.salvage_value || !asset.useful_life_years || !asset.purchaseDate) {
            return { bookValue: null, annualDepreciation: null, message: "Missing depreciation data" };
        }

        const purchasePrice = asset.purchaseCostCents / 100; // Convert cents to dollars
        const salvageValue = asset.salvage_value;
        const usefulLifeYears = asset.useful_life_years;

        if (usefulLifeYears <= 0) {
            return { bookValue: purchasePrice, annualDepreciation: 0, message: "Useful life is zero or less" };
        }

        const purchaseDate = new Date(asset.purchaseDate);
        const now = new Date();
        const yearsElapsed = now.getFullYear() - purchaseDate.getFullYear();

        const annualDepreciation = (purchasePrice - salvageValue) / usefulLifeYears;
        let bookValue = purchasePrice - (annualDepreciation * yearsElapsed);
        bookValue = Math.max(bookValue, salvageValue);

        return { bookValue, annualDepreciation };
    };

    const getWarrantyStatus = (asset: Asset) => {
        if (!asset.warranty_expiry_date) {
            return { status: "N/A", expiresOn: "N/A", daysToExpiry: null };
        }

        const expiryDate = new Date(asset.warranty_expiry_date);
        const now = new Date();
        const diffTime = expiryDate.getTime() - now.getTime();
        const diffDays = Math.ceil(diffTime / (1000 * 60 * 60 * 24));

        let status = "Active";
        if (diffDays <= 0) {
            status = "Expired";
        } else if (diffDays <= 30) { // Assuming 30 days is "expiring soon"
            status = "Expiring Soon";
        }

        return { status, expiresOn: expiryDate.toLocaleDateString(), daysToExpiry: diffDays };
    };

    const depreciationData = asset ? calculateDepreciation(asset) : null;
    const warrantyInfo = asset ? getWarrantyStatus(asset) : null;

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
    }, [id, editMode]); // Refetch if editMode changes to update data after save

    const handleSave = async (updatedAsset: Asset) => {
        try {
            // This is a simplified approach. In a real app, you'd likely call a specific update endpoint.
            // For this task, we assume the AssetEditForm handles the patch call via itamApiService.
            setAsset(updatedAsset);
            setEditMode(false);
        } catch (err) {
            console.error("Failed to save asset:", err);
            setError("Failed to save asset details.");
        }
    };

    const handleCancel = () => {
        setEditMode(false);
    };

    if (loading) return <div>Loading asset details</div>;
    if (error) return <div className="text-red-500">{error}</div>;
    if (!asset) return <div className="text-gray-500">Asset not found</div>;

    if (editMode) {
        return <AssetEditForm asset={asset} onSave={handleSave} onCancel={handleCancel} />;
    }

    return (
        <div className="container mx-auto p-4">
            <h1 className="text-2xl font-bold mb-4">Asset: {asset.name} ({asset.assetTag})</h1>
            <button
                onClick={() => setEditMode(true)}
                className="bg-blue-500 hover:bg-blue-700 text-white font-bold py-2 px-4 rounded mb-4"
            >
                Edit Asset
            </button>
            <div className="bg-white shadow overflow-hidden sm:rounded-lg mb-4">
                <div className="px-4 py-5 sm:px-6">
                    <h3 className="text-lg leading-6 font-medium text-gray-900">Asset Details</h3>
               </div>
                <div className="border-t border-gray-200">
                    <dl>
                        <div className="bg-gray-50 px-4 py-5 sm:grid sm:grid-cols-3 sm:gap-4 sm:px-6">
                            <dt className="text-sm font-medium text-gray-500">Asset Tag</dt>
                            <dd className="mt-1 text-sm text-gray-900 sm:mt-0 sm:col-span-2">{asset.assetTag}</dd>
                        </div>
                        <div className="bg-white px-4 py-5 sm:grid sm:grid-cols-3 sm:gap-4 sm:px-6">
                            <dt className="text-sm font-medium text-gray-500">Warranty Status</dt>
                            <dd className="mt-1 text-sm text-gray-900 sm:mt-0 sm:col-span-2">
                                {warrantyInfo?.status} {warrantyInfo?.expiresOn !== "N/A" && `(Expires: ${warrantyInfo?.expiresOn})`}
                                {warrantyInfo?.daysToExpiry !== null && warrantyInfo.daysToExpiry <= 30 && warrantyInfo.daysToExpiry > 0 && (
                                    <span className="ml-2 px-2 py-0.5 text-xs font-semibold text-orange-800 bg-orange-100 rounded-full">
                                        {warrantyInfo.daysToExpiry} days left
                                    </span>
                                )}
                                {warrantyInfo?.daysToExpiry !== null && warrantyInfo.daysToExpiry <= 0 && (
                                    <span className="ml-2 px-2 py-0.5 text-xs font-semibold text-red-800 bg-red-100 rounded-full">
                                        Expired
                                    </span>
                                )}
                            </dd>
                        </div>
                        <div className="bg-gray-50 px-4 py-5 sm:grid sm:grid-cols-3 sm:gap-4 sm:px-6">
                            <dt className="text-sm font-medium text-gray-500">Current Book Value</dt>
                            <dd className="mt-1 text-sm text-gray-900 sm:mt-0 sm:col-span-2">
                                {depreciationData?.bookValue ? `$${depreciationData.bookValue.toFixed(2)}` : depreciationData?.message || 'N/A'}
                            </dd>
                        </div>
                        <div className="bg-white px-4 py-5 sm:grid sm:grid-cols-3 sm:gap-4 sm:px-6">
                            <dt className="text-sm font-medium text-gray-500">Annual Depreciation</dt>
                            <dd className="mt-1 text-sm text-gray-900 sm:mt-0 sm:col-span-2">
                                {depreciationData?.annualDepreciation ? `$${depreciationData.annualDepreciation.toFixed(2)}` : 'N/A'}
                            </dd>
                        </div>
                        <div className="bg-white px-4 py-5 sm:grid sm:grid-cols-3 sm:gap-4 sm:px-6">
                            <dt className="text-sm font-medium text-gray-500">Type</dt>
                            <dd className="mt-1 text-sm text-gray-900 sm:mt-0 sm:col-span-2">{asset.type || 'N/A'}</dd>
                        </div>
                        <div className="bg-gray-50 px-4 py-5 sm:grid sm:grid-cols-3 sm:gap-4 sm:px-6">
                            <dt className="text-sm font-medium text-gray-500">Lifecycle Status</dt>
                            <dd className="mt-1 text-sm text-gray-900 sm:mt-0 sm:col-span-2">{asset.lifecycleStatus || 'N/A'}</dd>
                        </div>
                        <div className="bg-white px-4 py-5 sm:grid sm:grid-cols-3 sm:gap-4 sm:px-6">
                            <dt className="text-sm font-medium text-gray-500">Linked Purchase Order</dt>
                            <dd className="mt-1 text-sm text-gray-900 sm:mt-0 sm:col-span-2">
                                {linkedPurchaseOrder ? (
                                    <Link to={`/itam/purchase-orders/${linkedPurchaseOrder.id}`} className="text-blue-600 hover:underline">
                                        {linkedPurchaseOrder.order_number} ({linkedPurchaseOrder.supplier_name})
                                    </Link>
                                ) : asset.purchase_order_id ? (
                                    <span className="text-gray-400">Purchase Order ID: {asset.purchase_order_id} (details unavailable)</span>
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
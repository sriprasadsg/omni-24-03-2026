import React, { useState, useEffect } from 'react';
import { Asset } from '../../../types/itam';
import { itamApiService } from '../../../api/itamApiService';

interface AssetEditFormProps {
    asset: Asset;
    onSave: (updatedAsset: Asset) => void;
    onCancel: () => void;
}

const AssetEditForm: React.FC<AssetEditFormProps> = ({ asset, onSave, onCancel }) => {
    const [formData, setFormData] = useState<Partial<Asset>>({});
    const [loading, setLoading] = useState<boolean>(false);
    const [error, setError] = useState<string | null>(null);

    useEffect(() => {
        setFormData({
            warranty_expiry_date: asset.warranty_expiry_date ? new Date(asset.warranty_expiry_date).toISOString().split('T')[0] : '',
            salvage_value: asset.salvage_value,
            useful_life_years: asset.useful_life_years,
            purchaseCostCents: asset.purchaseCostCents,
            purchaseDate: asset.purchaseDate ? new Date(asset.purchaseDate).toISOString().split('T')[0] : '',
        });
    }, [asset]);

    const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
        const { name, value, type } = e.target;
        setFormData(prev => ({
            ...prev,
            [name]: type === 'number' ? parseFloat(value) : value
        }));
    };

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        setLoading(true);
        setError(null);

        const dataToUpdate: Partial<Asset> = {
            ...formData,
            purchaseCostCents: formData.purchaseCostCents ? Math.round(formData.purchaseCostCents) : undefined, // Ensure cents are integers
            warranty_expiry_date: formData.warranty_expiry_date ? new Date(formData.warranty_expiry_date).toISOString() : undefined,
            purchaseDate: formData.purchaseDate ? new Date(formData.purchaseDate).toISOString() : undefined,
        };

        try {
            const updatedAsset = await itamApiService.updateAssetPurchaseInfo(asset.id, dataToUpdate);
            onSave(updatedAsset);
        } catch (err) {
            console.error("Error updating asset:", err);
            setError("Failed to update asset. Please try again.");
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className="container mx-auto p-4 bg-white shadow-lg rounded-lg">
            <h2 className="text-2xl font-bold mb-4">Edit Asset: {asset.name}</h2>
            {error && <div className="text-red-500 mb-4">{error}</div>}
            <form onSubmit={handleSubmit} className="space-y-4">
                <div>
                    <label htmlFor="purchaseCostCents" className="block text-sm font-medium text-gray-700">Purchase Price ($)</label>
                    <input
                        type="number"
                        id="purchaseCostCents"
                        name="purchaseCostCents"
                        value={(formData.purchaseCostCents || 0) / 100}
                        onChange={(e) => setFormData(prev => ({ ...prev, purchaseCostCents: parseFloat(e.target.value) * 100 }))}
                        className="mt-1 block w-full border border-gray-300 rounded-md shadow-sm p-2"
                        step="0.01"
                    />
                </div>
                <div>
                    <label htmlFor="purchaseDate" className="block text-sm font-medium text-gray-700">Purchase Date</label>
                    <input
                        type="date"
                        id="purchaseDate"
                        name="purchaseDate"
                        value={formData.purchaseDate || ''}
                        onChange={handleChange}
                        className="mt-1 block w-full border border-gray-300 rounded-md shadow-sm p-2"
                    />
                </div>
                <div>
                    <label htmlFor="warranty_expiry_date" className="block text-sm font-medium text-gray-700">Warranty Expiry Date</label>
                    <input
                        type="date"
                        id="warranty_expiry_date"
                        name="warranty_expiry_date"
                        value={formData.warranty_expiry_date || ''}
                        onChange={handleChange}
                        className="mt-1 block w-full border border-gray-300 rounded-md shadow-sm p-2"
                    />
                </div>
                <div>
                    <label htmlFor="salvage_value" className="block text-sm font-medium text-gray-700">Salvage Value ($)</label>
                    <input
                        type="number"
                        id="salvage_value"
                        name="salvage_value"
                        value={formData.salvage_value || ''}
                        onChange={handleChange}
                        className="mt-1 block w-full border border-gray-300 rounded-md shadow-sm p-2"
                        step="0.01"
                    />
                </div>
                <div>
                    <label htmlFor="useful_life_years" className="block text-sm font-medium text-gray-700">Useful Life (Years)</label>
                    <input
                        type="number"
                        id="useful_life_years"
                        name="useful_life_years"
                        value={formData.useful_life_years || ''}
                        onChange={handleChange}
                        className="mt-1 block w-full border border-gray-300 rounded-md shadow-sm p-2"
                        min="1"
                    />
                </div>
                <div className="flex justify-end space-x-2">
                    <button
                        type="button"
                        onClick={onCancel}
                        className="px-4 py-2 border border-gray-300 rounded-md shadow-sm text-sm font-medium text-gray-700 hover:bg-gray-50"
                        disabled={loading}
                    >
                        Cancel
                    </button>
                    <button
                        type="submit"
                        className="px-4 py-2 bg-blue-600 border border-transparent rounded-md shadow-sm text-sm font-medium text-white hover:bg-blue-700"
                        disabled={loading}
                    >
                        {loading ? 'Saving...' : 'Save Changes'}
                    </button>
                </div>
            </form>
        </div>
    );
};

export default AssetEditForm;
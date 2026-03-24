import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { UploadIcon, SaveIcon } from './icons';

interface BrandingConfig {
    logoUrl?: string;
    primaryColor?: string;
    companyName?: string;
}

interface TenantBrandingSettingsProps {
    tenantId: string;
    tenantName: string;
    onClose: () => void;
}

const API_BASE_URL = 'http://localhost:5000';

export const TenantBrandingSettings: React.FC<TenantBrandingSettingsProps> = ({ tenantId, tenantName, onClose }) => {
    const [config, setConfig] = useState<BrandingConfig>({});
    const [loading, setLoading] = useState(false);
    const [saved, setSaved] = useState(false);

    useEffect(() => {
        const fetchBranding = async () => {
            try {
                const res = await axios.get(`${API_BASE_URL}/api/tenants/${tenantId}/branding`);
                setConfig(res.data);
            } catch (error) {
                console.error("Failed to load branding", error);
            }
        };
        fetchBranding();
    }, [tenantId]);

    const handleSave = async () => {
        setLoading(true);
        try {
            await axios.post(`${API_BASE_URL}/api/tenants/${tenantId}/branding`, config);
            setSaved(true);
            setTimeout(() => setSaved(false), 3000);
        } catch (error) {
            console.error("Failed to save branding", error);
            alert("Failed to save configuration");
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm p-4">
            <div className="bg-white dark:bg-gray-800 rounded-2xl w-full max-w-lg shadow-2xl overflow-hidden">
                <div className="p-6 border-b border-gray-200 dark:border-gray-700 flex justify-between items-center">
                    <h2 className="text-xl font-bold text-gray-900 dark:text-white">White-Labeling: {tenantName}</h2>
                    <button onClick={onClose} className="text-gray-500 hover:text-gray-700">×</button>
                </div>

                <div className="p-6 space-y-6">
                    <div>
                        <label className="block text-sm font-medium text-gray-700 dark:text-gray-300">Company Name</label>
                        <input
                            type="text"
                            value={config.companyName || ''}
                            onChange={(e) => setConfig({ ...config, companyName: e.target.value })}
                            className="mt-1 block w-full px-3 py-2 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-md shadow-sm text-sm"
                            placeholder="e.g. Acme Corp"
                        />
                    </div>

                    <div>
                        <label className="block text-sm font-medium text-gray-700 dark:text-gray-300">Logo URL</label>
                        <div className="flex space-x-2">
                            <input
                                type="text"
                                value={config.logoUrl || ''}
                                onChange={(e) => setConfig({ ...config, logoUrl: e.target.value })}
                                className="mt-1 block w-full px-3 py-2 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-md shadow-sm text-sm"
                                placeholder="https://example.com/logo.png"
                            />
                            {config.logoUrl && (
                                <img src={config.logoUrl} alt="Logo Preview" className="h-10 w-10 object-contain rounded border border-gray-200 bg-gray-50" />
                            )}
                        </div>
                    </div>

                    <div>
                        <label className="block text-sm font-medium text-gray-700 dark:text-gray-300">Primary Brand Color</label>
                        <div className="flex items-center space-x-3 mt-1">
                            <input
                                type="color"
                                value={config.primaryColor || '#3b82f6'}
                                onChange={(e) => setConfig({ ...config, primaryColor: e.target.value })}
                                className="h-10 w-20 rounded border border-gray-300 cursor-pointer"
                            />
                            <span className="text-sm text-gray-500">{config.primaryColor || '#3b82f6'}</span>
                        </div>
                    </div>
                </div>

                <div className="p-6 bg-gray-50 dark:bg-gray-900/50 flex justify-end space-x-3">
                    <button onClick={onClose} className="px-4 py-2 text-gray-700 dark:text-gray-300 hover:bg-gray-100 rounded-md">Cancel</button>
                    <button
                        onClick={handleSave}
                        disabled={loading}
                        className={`flex items-center px-4 py-2 text-white rounded-md transition-colors ${saved ? 'bg-green-600' : 'bg-blue-600 hover:bg-blue-700'}`}
                    >
                        {saved ? 'Saved!' : (
                            <>
                                <SaveIcon size={16} className="mr-2" /> Save Branding
                            </>
                        )}
                    </button>
                </div>
            </div>
        </div>
    );
};

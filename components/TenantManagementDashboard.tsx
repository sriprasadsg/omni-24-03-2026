import React from 'react';
import { Tenant } from '../types';
import { SettingsIcon, ZapIcon, TrashIcon, UserIcon } from './icons';
import { TenantBrandingSettings } from './TenantBrandingSettings';
import { useUser } from '../contexts/UserContext';

interface TenantManagementDashboardProps {
    tenants: Tenant[];
    onManageTenant: (tenant: Tenant) => void;
    onViewTenant: (tenantId: string) => void;
    handleDelete: (tenantId: string, tenantName: string) => void;
    handleUpdateTenant: (tenantId: string, data: Partial<Tenant>) => Promise<void>;
    onAddNewTenant: () => void;
}

export const TenantManagementDashboard: React.FC<TenantManagementDashboardProps> = ({
    tenants,
    onManageTenant,
    onViewTenant,
    handleDelete,
    handleUpdateTenant,
    onAddNewTenant
}) => {
    const { hasPermission } = useUser();
    const [brandingTenant, setBrandingTenant] = React.useState<{ id: string, name: string } | null>(null);

    return (
        <div className="container mx-auto p-6">
            <div className="flex justify-between items-center mb-6">
                <h1 className="text-2xl font-bold text-gray-800 dark:text-white">Tenant Management</h1>
                <button
                    onClick={onAddNewTenant}
                    className="flex items-center px-4 py-2 text-sm font-medium text-white bg-primary-600 rounded-lg hover:bg-primary-700 transition-colors shadow-sm"
                >
                    <SettingsIcon size={16} className="mr-2 rotate-45" /> {/* Using SettingsIcon temporarily or Import PlusCircleIcon */}
                    Add New Tenant
                </button>
            </div>

            <div className="bg-white dark:bg-gray-800 rounded-lg shadow-md overflow-hidden">
                <table className="min-w-full divide-y divide-gray-200 dark:divide-gray-700">
                    <thead className="bg-gray-50 dark:bg-gray-700">
                        <tr>
                            <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-300 uppercase tracking-wider">Tenant Name</th>
                            <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-300 uppercase tracking-wider"># Agents</th>
                            <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-300 uppercase tracking-wider">Plan</th>
                            <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-300 uppercase tracking-wider">Actions</th>
                        </tr>
                    </thead>
                    <tbody className="bg-white dark:bg-gray-800 divide-y divide-gray-200 dark:divide-gray-700">
                        {tenants.map(tenant => (
                            <tr key={tenant.id}>
                                <td className="px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-900 dark:text-white">
                                    {tenant.name}
                                </td>
                                <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500 dark:text-gray-400">
                                    <span className="inline-flex items-center justify-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200">
                                        {tenant.agentCount || 0}
                                    </span>
                                </td>
                                <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500 dark:text-gray-400">
                                    {tenant.subscriptionTier}
                                </td>
                                <td className="px-6 py-4 whitespace-nowrap text-sm font-medium">
                                    <div className="flex items-center space-x-3">
                                        <button onClick={() => onViewTenant(tenant.id)} className="px-2.5 py-1 text-xs font-medium text-white bg-primary-600 rounded-md hover:bg-primary-700">View</button>
                                        <button onClick={() => onManageTenant(tenant)} className="flex items-center text-xs font-medium text-gray-500 hover:text-gray-700 dark:hover:text-gray-300"><SettingsIcon size={12} className="mr-1" />Config</button>
                                        <button onClick={() => setBrandingTenant(tenant)} className="flex items-center text-xs font-medium text-purple-600 hover:text-purple-800"><ZapIcon size={12} className="mr-1" />Brand</button>
                                        <button onClick={() => handleDelete(tenant.id, tenant.name)} className="flex items-center text-xs font-medium text-red-500 hover:text-red-700"><TrashIcon size={12} className="mr-1" />Delete</button>
                                    </div>
                                </td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            </div>

            {brandingTenant && (
                <TenantBrandingSettings
                    tenantId={brandingTenant.id}
                    tenantName={brandingTenant.name}
                    onClose={() => setBrandingTenant(null)}
                />
            )}
        </div>
    );
};

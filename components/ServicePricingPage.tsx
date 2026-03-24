import React, { useState, useEffect } from 'react';
import { DollarSignIcon, PlusIcon, TrashIcon, SettingsIcon } from './icons';
import { fetchServicePricing, createServicePricing, updateSingleServicePricing, deleteServicePricing } from '../services/apiService';

// Simple Edit Icon component (inline SVG)
const EditIcon: React.FC<{ size?: number }> = ({ size = 16 }) => (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
        <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7" />
        <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z" />
    </svg>
);

interface ServicePricing {
    id: string;
    name: string;
    category: string;
    unit: string;
    price: number;
    description: string;
    createdAt?: string;
    updatedAt?: string;
}

const CATEGORY_OPTIONS = ['Infrastructure', 'Software', 'Support', 'Network', 'Storage', 'Other'];
const UNIT_OPTIONS = [
    'per_agent_per_month',
    'per_core_per_hour',
    'per_gb_per_month',
    'per_gb_per_hour',
    'per_unit_per_month',
    'per_user_per_month',
    'per_transaction',
    'per_request'
];

export const ServicePricingPage: React.FC = () => {
    const [services, setServices] = useState<ServicePricing[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState('');

    // Modal state
    const [isModalOpen, setIsModalOpen] = useState(false);
    const [modalMode, setModalMode] = useState<'create' | 'edit'>('create');
    const [editingService, setEditingService] = useState<ServicePricing | null>(null);

    // Form state
    const [formData, setFormData] = useState({
        id: '',
        name: '',
        category: 'Infrastructure',
        unit: 'per_agent_per_month',
        price: 0,
        description: ''
    });

    useEffect(() => {
        loadServices();
    }, []);

    const loadServices = async () => {
        try {
            setLoading(true);
            setError('');
            const data = await fetchServicePricing();
            setServices(data);
        } catch (e) {
            setError('Failed to load services');
            console.error(e);
        } finally {
            setLoading(false);
        }
    };

    const handleOpenCreateModal = () => {
        setModalMode('create');
        setFormData({
            id: '',
            name: '',
            category: 'Infrastructure',
            unit: 'per_agent_per_month',
            price: 0,
            description: ''
        });
        setEditingService(null);
        setIsModalOpen(true);
    };

    const handleOpenEditModal = (service: ServicePricing) => {
        setModalMode('edit');
        setFormData({
            id: service.id,
            name: service.name,
            category: service.category,
            unit: service.unit,
            price: service.price,
            description: service.description
        });
        setEditingService(service);
        setIsModalOpen(true);
    };

    const handleCloseModal = () => {
        setIsModalOpen(false);
        setEditingService(null);
        setError('');
    };

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        setError('');

        try {
            if (modalMode === 'create') {
                await createServicePricing(formData);
            } else {
                await updateSingleServicePricing(formData.id, {
                    name: formData.name,
                    category: formData.category,
                    unit: formData.unit,
                    price: formData.price,
                    description: formData.description
                });
            }
            await loadServices();
            handleCloseModal();
        } catch (e: any) {
            setError(e.message || 'Failed to save service');
        }
    };

    const handleDelete = async (service: ServicePricing) => {
        if (!window.confirm(`Are you sure you want to delete "${service.name}"? This cannot be undone.`)) {
            return;
        }

        try {
            await deleteServicePricing(service.id);
            await loadServices();
        } catch (e: any) {
            alert(`Failed to delete service: ${e.message}`);
        }
    };

    return (
        <div className="container mx-auto space-y-6">
            <div className="flex flex-col sm:flex-row justify-between sm:items-center gap-4">
                <div>
                    <h2 className="text-2xl font-semibold text-gray-800 dark:text-white flex items-center gap-2">
                        <SettingsIcon size={28} className="text-primary-500" />
                        Service Pricing Configuration
                    </h2>
                    <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
                        Manage billable services and their pricing models. These settings apply to all tenants.
                    </p>
                </div>
                <button
                    onClick={handleOpenCreateModal}
                    className="px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 flex items-center gap-2 text-sm font-medium"
                >
                    <PlusIcon size={18} />
                    Add New Service
                </button>
            </div>

            {error && !isModalOpen && (
                <div className="bg-red-50 dark:bg-red-900/30 border border-red-200 dark:border-red-800 rounded-lg p-4">
                    <p className="text-red-800 dark:text-red-200 text-sm">{error}</p>
                </div>
            )}

            <div className="bg-white dark:bg-gray-800 rounded-lg shadow-md overflow-hidden">
                {loading ? (
                    <div className="p-8 text-center text-gray-500 dark:text-gray-400">
                        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary-600 mx-auto mb-2"></div>
                        Loading services...
                    </div>
                ) : services.length === 0 ? (
                    <div className="p-8 text-center text-gray-500 dark:text-gray-400">
                        <DollarSignIcon size={48} className="mx-auto mb-4 opacity-50" />
                        <p className="font-medium">No Services Configured</p>
                        <p className="text-sm mt-1">Click "Add New Service" to create your first billable service.</p>
                    </div>
                ) : (
                    <div className="overflow-x-auto">
                        <table className="w-full text-left text-sm">
                            <thead className="bg-gray-50 dark:bg-gray-900/50 text-gray-500 dark:text-gray-400 uppercase font-medium border-b border-gray-200 dark:border-gray-700">
                                <tr>
                                    <th className="px-6 py-4">Service Name</th>
                                    <th className="px-6 py-4">Category</th>
                                    <th className="px-6 py-4">Billing Unit</th>
                                    <th className="px-6 py-4 text-right">Unit Price</th>
                                    <th className="px-6 py-4">Description</th>
                                    <th className="px-6 py-4 text-right">Actions</th>
                                </tr>
                            </thead>
                            <tbody className="divide-y divide-gray-100 dark:divide-gray-700">
                                {services.map((service) => (
                                    <tr key={service.id} className="hover:bg-gray-50 dark:hover:bg-gray-750">
                                        <td className="px-6 py-4 font-medium text-gray-900 dark:text-white">
                                            {service.name}
                                        </td>
                                        <td className="px-6 py-4 text-gray-600 dark:text-gray-400">
                                            <span className="px-2 py-1 bg-gray-100 dark:bg-gray-700 rounded text-xs">
                                                {service.category}
                                            </span>
                                        </td>
                                        <td className="px-6 py-4 text-gray-600 dark:text-gray-400 font-mono text-xs">
                                            {service.unit}
                                        </td>
                                        <td className="px-6 py-4 text-right font-mono font-semibold text-gray-900 dark:text-white">
                                            ${service.price.toFixed(2)}
                                        </td>
                                        <td className="px-6 py-4 text-gray-600 dark:text-gray-400 max-w-xs truncate">
                                            {service.description}
                                        </td>
                                        <td className="px-6 py-4">
                                            <div className="flex justify-end gap-2">
                                                <button
                                                    onClick={() => handleOpenEditModal(service)}
                                                    className="p-2 text-gray-600 hover:text-primary-600 dark:text-gray-400 dark:hover:text-primary-400"
                                                    title="Edit Service"
                                                >
                                                    <EditIcon size={16} />
                                                </button>
                                                <button
                                                    onClick={() => handleDelete(service)}
                                                    className="p-2 text-gray-600 hover:text-red-600 dark:text-gray-400 dark:hover:text-red-400"
                                                    title="Delete Service"
                                                >
                                                    <TrashIcon size={16} />
                                                </button>
                                            </div>
                                        </td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                )}
            </div>

            {/* Modal for Create/Edit */}
            {isModalOpen && (
                <div className="fixed inset-0 bg-black bg-opacity-50 z-50 flex justify-center items-center" onClick={handleCloseModal}>
                    <div className="bg-white dark:bg-gray-800 rounded-lg shadow-xl w-full max-w-2xl p-6 m-4" onClick={e => e.stopPropagation()}>
                        <h3 className="text-xl font-bold text-gray-900 dark:text-white mb-4">
                            {modalMode === 'create' ? 'Add New Service' : 'Edit Service'}
                        </h3>

                        {error && (
                            <div className="mb-4 bg-red-50 dark:bg-red-900/30 border border-red-200 dark:border-red-800 rounded-lg p-3">
                                <p className="text-red-800 dark:text-red-200 text-sm">{error}</p>
                            </div>
                        )}

                        <form onSubmit={handleSubmit} className="space-y-4">
                            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                                <div>
                                    <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                                        Service ID *
                                    </label>
                                    <input
                                        type="text"
                                        value={formData.id}
                                        onChange={e => setFormData({ ...formData, id: e.target.value })}
                                        disabled={modalMode === 'edit'}
                                        className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-700 disabled:opacity-50 disabled:cursor-not-allowed"
                                        placeholder="e.g., premium_support"
                                        required
                                    />
                                    <p className="text-xs text-gray-500 mt-1">Unique identifier (cannot be changed after creation)</p>
                                </div>

                                <div>
                                    <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                                        Service Name *
                                    </label>
                                    <input
                                        type="text"
                                        value={formData.name}
                                        onChange={e => setFormData({ ...formData, name: e.target.value })}
                                        className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-700"
                                        placeholder="e.g., Premium Support"
                                        required
                                    />
                                </div>

                                <div>
                                    <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                                        Category *
                                    </label>
                                    <select
                                        value={formData.category}
                                        onChange={e => setFormData({ ...formData, category: e.target.value })}
                                        className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-700"
                                        required
                                    >
                                        {CATEGORY_OPTIONS.map(cat => (
                                            <option key={cat} value={cat}>{cat}</option>
                                        ))}
                                    </select>
                                </div>

                                <div>
                                    <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                                        Billing Unit *
                                    </label>
                                    <select
                                        value={formData.unit}
                                        onChange={e => setFormData({ ...formData, unit: e.target.value })}
                                        className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-700"
                                        required
                                    >
                                        {UNIT_OPTIONS.map(unit => (
                                            <option key={unit} value={unit}>{unit.replace(/_/g, ' ')}</option>
                                        ))}
                                    </select>
                                </div>

                                <div className="md:col-span-2">
                                    <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                                        Unit Price ($) *
                                    </label>
                                    <input
                                        type="number"
                                        step="0.01"
                                        min="0"
                                        value={formData.price}
                                        onChange={e => setFormData({ ...formData, price: parseFloat(e.target.value) })}
                                        className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-700"
                                        placeholder="0.00"
                                        required
                                    />
                                </div>

                                <div className="md:col-span-2">
                                    <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                                        Description
                                    </label>
                                    <textarea
                                        value={formData.description}
                                        onChange={e => setFormData({ ...formData, description: e.target.value })}
                                        className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-700"
                                        rows={3}
                                        placeholder="Brief description of the service"
                                    />
                                </div>
                            </div>

                            <div className="flex justify-end gap-3 pt-4 border-t border-gray-200 dark:border-gray-700">
                                <button
                                    type="button"
                                    onClick={handleCloseModal}
                                    className="px-4 py-2 text-gray-700 dark:text-gray-300 bg-gray-100 dark:bg-gray-700 rounded-lg hover:bg-gray-200 dark:hover:bg-gray-600"
                                >
                                    Cancel
                                </button>
                                <button
                                    type="submit"
                                    className="px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700"
                                >
                                    {modalMode === 'create' ? 'Create Service' : 'Save Changes'}
                                </button>
                            </div>
                        </form>
                    </div>
                </div>
            )}
        </div>
    );
};

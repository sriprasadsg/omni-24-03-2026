
import React, { useState, useEffect } from 'react';
import { DollarSignIcon, SaveIcon, RefreshCwIcon, CheckIcon, PlusIcon, TrashIcon } from './icons';
import { useUser } from '../contexts/UserContext';

interface ServicePrice {
    id: string;
    name: string;
    unit: string;
    price: number;
    category: string;
    description: string;
}

export const ServicePricing: React.FC = () => {
    const { currentUser } = useUser();
    const [prices, setPrices] = useState<ServicePrice[]>([]);
    const [isLoading, setIsLoading] = useState(true);
    const [isSaving, setIsSaving] = useState(false);
    const [saveMessage, setSaveMessage] = useState('');

    // New Service State
    const [isAdding, setIsAdding] = useState(false);
    const [newService, setNewService] = useState<Partial<ServicePrice>>({
        category: 'Services',
        unit: 'per_month_flat'
    });

    useEffect(() => {
        fetchPrices();
    }, []);

    const fetchPrices = async () => {
        setIsLoading(true);
        try {
            // FIX: Use correct finops endpoint
            const res = await fetch('/api/finops/pricing');
            if (res.ok) {
                const data = await res.json();
                setPrices(data);
            } else {
                console.error('Failed to fetch pricing:', res.statusText);
            }
        } catch (error) {
            console.error('Failed to fetch pricing', error);
        } finally {
            setIsLoading(false);
        }
    };

    const handlePriceChange = (id: string, newPrice: number) => {
        setPrices(prev => prev.map(p => p.id === id ? { ...p, price: newPrice } : p));
    };

    const handleSave = async () => {
        setIsSaving(true);
        try {
            // FIX: Use finops bulk update endpoint (POST)
            const res = await fetch('/api/finops/pricing', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                // Create auth header if needed, assuming cookie/token handling is global or implied
                // For now, using standard fetch assuming credential inclusion if configured globally
                // but checking ServicePricing original code, no special headers were added.
                // Adding Authorization header just in case if context provides it, but original didn't use it.
                // Assuming proxy or cookie auth.
                body: JSON.stringify(prices)
            });

            if (!res.ok) throw new Error('Update failed');

            setSaveMessage('Pricing updated successfully!');
            setTimeout(() => setSaveMessage(''), 3000);

            // Trigger recalculation
            await fetch('/api/finops/recalculate/all', { method: 'POST' }).catch(() => { });
            // Note: Endpoint /finops/refresh-all might be legacy, trying generic or skipping if not critical.

        } catch (error) {
            console.error('Failed to save pricing', error);
            setSaveMessage('Failed to save.');
        } finally {
            setIsSaving(false);
        }
    };

    const handleAddService = async () => {
        if (!newService.id || !newService.name || newService.price === undefined) {
            alert('Please fill all required fields');
            return;
        }

        try {
            const res = await fetch('/api/finops/pricing/service', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(newService)
            });

            if (res.ok) {
                await fetchPrices(); // Refresh list
                setIsAdding(false);
                setNewService({ category: 'Services', unit: 'per_month_flat' });
                setSaveMessage('Service added successfully!');
                setTimeout(() => setSaveMessage(''), 3000);
            } else {
                const err = await res.json();
                alert('Error adding service: ' + err.detail);
            }
        } catch (error) {
            console.error('Failed to add service', error);
        }
    };

    const handleDelete = async (id: string) => {
        if (!window.confirm('Delete this service configuration?')) return;
        try {
            const res = await fetch(`/api/finops/pricing/service/${id}`, {
                method: 'DELETE'
            });
            if (res.ok) {
                setPrices(prev => prev.filter(p => p.id !== id));
            }
        } catch (e) { console.error(e); }
    };

    if (currentUser?.role !== 'Super Admin') {
        return <div className="p-4">Access Denied. Super Admin only.</div>;
    }

    return (
        <div className="container mx-auto p-4 max-w-5xl">
            <div className="flex justify-between items-center mb-6">
                <div>
                    <h2 className="text-2xl font-semibold text-gray-800 dark:text-white flex items-center">
                        <DollarSignIcon className="mr-3 text-primary-500" />
                        Service Catalog & Pricing
                    </h2>
                    <p className="text-gray-500 dark:text-gray-400">Manage billable services and their unit costs.</p>
                </div>
                <div className="flex space-x-3">
                    <button
                        onClick={() => setIsAdding(!isAdding)}
                        className="flex items-center px-4 py-2 border border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-200 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-700"
                    >
                        <PlusIcon className="mr-2" size={16} />
                        Add Service
                    </button>
                    <button
                        onClick={handleSave}
                        disabled={isSaving}
                        className="flex items-center px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 disabled:opacity-50"
                    >
                        {isSaving ? <RefreshCwIcon className="animate-spin mr-2" /> : <SaveIcon className="mr-2" />}
                        Save All Changes
                    </button>
                </div>
            </div>

            {saveMessage && (
                <div className={`mb-4 p-3 rounded-lg flex items-center ${saveMessage.includes('Failed') ? 'bg-red-100 text-red-700' : 'bg-green-100 text-green-700'}`}>
                    {!saveMessage.includes('Failed') && <CheckIcon className="mr-2" size={18} />}
                    {saveMessage}
                </div>
            )}

            {isAdding && (
                <div className="mb-6 p-4 bg-gray-50 dark:bg-gray-700/50 rounded-lg border border-gray-200 dark:border-gray-600">
                    <h3 className="text-sm font-semibold mb-3 text-gray-800 dark:text-white">New Service Definition</h3>
                    <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-4">
                        <input
                            placeholder="Current ID (e.g. service_xyz)"
                            value={newService.id || ''}
                            onChange={e => setNewService({ ...newService, id: e.target.value })}
                            className="px-3 py-2 border rounded dark:bg-gray-800 dark:border-gray-600 dark:text-white"
                        />
                        <input
                            placeholder="Display Name"
                            value={newService.name || ''}
                            onChange={e => setNewService({ ...newService, name: e.target.value })}
                            className="px-3 py-2 border rounded dark:bg-gray-800 dark:border-gray-600 dark:text-white"
                        />
                        <input
                            type="number"
                            placeholder="Price"
                            value={newService.price || ''}
                            onChange={e => setNewService({ ...newService, price: parseFloat(e.target.value) })}
                            className="px-3 py-2 border rounded dark:bg-gray-800 dark:border-gray-600 dark:text-white"
                        />
                        <select
                            value={newService.category}
                            onChange={e => setNewService({ ...newService, category: e.target.value })}
                            className="px-3 py-2 border rounded dark:bg-gray-800 dark:border-gray-600 dark:text-white"
                        >
                            <option value="Services">Services</option>
                            <option value="Infrastructure">Infrastructure</option>
                            <option value="Compliance">Compliance</option>
                            <option value="Security">Security</option>
                            <option value="Software">Software</option>
                        </select>
                        <select
                            value={newService.unit}
                            onChange={e => setNewService({ ...newService, unit: e.target.value })}
                            className="px-3 py-2 border rounded dark:bg-gray-800 dark:border-gray-600 dark:text-white"
                        >
                            <option value="per_month_flat">Flat Rate (Per Month)</option>
                            <option value="per_agent_per_month">Per Agent / Month</option>
                            <option value="per_gb_per_month">Per GB / Month</option>
                            <option value="per_core_per_hour">Per vCPU / Hour</option>
                        </select>
                        <input
                            placeholder="Description"
                            value={newService.description || ''}
                            onChange={e => setNewService({ ...newService, description: e.target.value })}
                            className="px-3 py-2 border rounded dark:bg-gray-800 dark:border-gray-600 dark:text-white"
                        />
                    </div>
                    <div className="flex justify-end space-x-2">
                        <button onClick={() => setIsAdding(false)} className="px-3 py-1 text-sm text-gray-500 hover:text-gray-700">Cancel</button>
                        <button onClick={handleAddService} className="px-3 py-1 text-sm bg-blue-600 text-white rounded hover:bg-blue-700">Create Service</button>
                    </div>
                </div>
            )}

            {isLoading ? (
                <div className="animate-pulse space-y-4">
                    {[1, 2, 3].map(i => <div key={i} className="h-16 bg-gray-200 dark:bg-gray-700 rounded-md"></div>)}
                </div>
            ) : (
                <div className="bg-white dark:bg-gray-800 shadow-md rounded-lg overflow-hidden">
                    <table className="min-w-full divide-y divide-gray-200 dark:divide-gray-700">
                        <thead className="bg-gray-50 dark:bg-gray-900">
                            <tr>
                                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">Service Name</th>
                                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">Category</th>
                                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">Billing Unit</th>
                                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">Unit Price ($)</th>
                                <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">Actions</th>
                            </tr>
                        </thead>
                        <tbody className="bg-white dark:bg-gray-800 divide-y divide-gray-200 dark:divide-gray-700">
                            {prices.map((service) => (
                                <tr key={service.id}>
                                    <td className="px-6 py-4 whitespace-nowrap">
                                        <div className="text-sm font-medium text-gray-900 dark:text-white">{service.name}</div>
                                        <div className="text-xs text-gray-500 dark:text-gray-400">{service.id}</div>
                                        {/* Display ID helps referencing in permissions */}
                                    </td>
                                    <td className="px-6 py-4 whitespace-nowrap">
                                        <span className="px-2 inline-flex text-xs leading-5 font-semibold rounded-full bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200">
                                            {service.category}
                                        </span>
                                    </td>
                                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500 dark:text-gray-400">
                                        {service.unit.replace(/_/g, ' ')}
                                    </td>
                                    <td className="px-6 py-4 whitespace-nowrap">
                                        <div className="relative rounded-md shadow-sm w-32">
                                            <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                                                <span className="text-gray-500 sm:text-sm">$</span>
                                            </div>
                                            <input
                                                type="number"
                                                step="0.01"
                                                value={service.price}
                                                onChange={(e) => handlePriceChange(service.id, parseFloat(e.target.value))}
                                                className="focus:ring-primary-500 focus:border-primary-500 block w-full pl-7 pr-3 sm:text-sm border-gray-300 rounded-md dark:bg-gray-700 dark:border-gray-600 dark:text-white"
                                            />
                                        </div>
                                    </td>
                                    <td className="px-6 py-4 whitespace-nowrap text-right">
                                        <button onClick={() => handleDelete(service.id)} className="text-red-500 hover:text-red-700">
                                            <TrashIcon size={16} />
                                        </button>
                                    </td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
            )}
        </div>
    );
};

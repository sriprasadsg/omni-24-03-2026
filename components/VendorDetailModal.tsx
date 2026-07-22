import React, { useState, useEffect } from 'react';
import { Plus, Trash2, Loader2, ShieldCheck, AlertCircle } from 'lucide-react';
import * as api from '../services/apiService';
import { showToast } from '../utils/toast';
import { Modal } from './Modal';

interface Subprocessor {
    id: string;
    name: string;
    location: string;
    description: string;
}

interface DPA {
    id: string;
    business_associate: string;
    vendor_id: string;
    status: 'draft' | 'active' | 'terminated' | 'expired';
}

interface VendorDetailModalProps {
    vendor: {
        id: string;
        name: string;
    } | null;
    isOpen: boolean;
    onClose: () => void;
}

export function VendorDetailModal({ vendor, isOpen, onClose }: VendorDetailModalProps) {
    const [subprocessors, setSubprocessors] = useState<Subprocessor[]>([]);
    const [dpaStatus, setDpaStatus] = useState<'none' | 'draft' | 'active' | 'terminated' | 'expired'>('none');
    const [loading, setLoading] = useState(false);
    const [adding, setAdding] = useState(false);
    const [newSubprocessor, setNewSubprocessor] = useState({ name: '', location: '', description: '' });
    // const { showToast } = useToast(); // Remove this line


    useEffect(() => {
        if (isOpen && vendor) {
            fetchData();
        }
    }, [isOpen, vendor?.id]);

    const fetchData = async () => {
        setLoading(true);
        try {
            const [spData, dpaData] = await Promise.all([
                api.fetchVendorSubprocessors(vendor!.id),
                api.fetchDPAs()
            ]);
            setSubprocessors(spData);
            const vendorDpa = dpaData.find(d => d.vendor_id === vendor!.id);
            setDpaStatus(vendorDpa?.status || 'none');
        } catch (error) {
            console.error('Error fetching vendor details:', error);
            showToast('Failed to load vendor details', 'error');
        } finally {
            setLoading(false);
        }
    };

    const handleAddSubprocessor = async (e: React.FormEvent) => {
        e.preventDefault();
        if (!newSubprocessor.name.trim()) return;
        setAdding(true);
        try {
            const result = await api.addVendorSubprocessor(vendor!.id, newSubprocessor);
            setSubprocessors([...subprocessors, result]);
            setNewSubprocessor({ name: '', location: '', description: '' });
            showToast('Subprocessor added', 'success');
        } catch (error) {
            console.error('Error adding subprocessor:', error);
            showToast('Failed to add subprocessor', 'error');
        } finally {
            setAdding(false);
        }
    };

    const handleRemoveSubprocessor = async (subId: string) => {
        try {
            await api.removeVendorSubprocessor(vendor!.id, subId);
            setSubprocessors(subprocessors.filter(s => s.id !== subId));
            showToast('Subprocessor removed', 'success');
        } catch (error) {
            console.error('Error removing subprocessor:', error);
            showToast('Failed to remove subprocessor', 'error');
        }
    };

    const getStatusBadge = (status: string) => {
        const styles: Record<string, string> = {
            active: 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400',
            draft: 'bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-400',
            terminated: 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400',
            expired: 'bg-gray-100 text-gray-700 dark:bg-gray-700 dark:text-gray-400',
            none: 'bg-gray-100 text-gray-500 dark:bg-gray-700 dark:text-gray-500',
        };
        const icons: Record<string, React.ReactNode> = {
            active: <ShieldCheck className="w-3 h-3" />,
            draft: <AlertCircle className="w-3 h-3" />,
        };
        return (
            <span className={`px-2 py-1 rounded text-xs font-medium ${styles[status] || styles.none} flex items-center gap-1`}>
                {icons[status] || null}
                {status.charAt(0).toUpperCase() + status.slice(1)}
            </span>
        );
    };

    if (!vendor) return null;

    return (
        <Modal isOpen={isOpen} onClose={onClose} title={`${vendor.name} — Details`} size="2xl">
                <div className="space-y-6">
                    {/* DPA Status */}
                    <div>
                        <h3 className="text-sm font-medium text-gray-900 dark:text-gray-100 mb-3">Data Processing Agreement (DPA)</h3>
                        <div className="flex items-center gap-3">
                            {getStatusBadge(dpaStatus)}
                        </div>
                    </div>

                    {/* Subprocessors */}
                    <div>
                        <div className="flex justify-between items-center mb-4">
                            <h3 className="text-sm font-medium text-gray-900 dark:text-gray-100">Subprocessors</h3>
                            <button
                                onClick={() => setAdding(true)}
                                className="px-3 py-1.5 text-sm bg-teal-600 hover:bg-teal-700 text-white rounded-lg flex items-center gap-1 transition-colors"
                            >
                                <Plus className="w-4 h-4" />
                                Add Subprocessor
                            </button>
                        </div>

                        {loading ? (
                            <div className="flex justify-center py-8">
                                <Loader2 className="w-6 h-6 animate-spin text-teal-600" />
                            </div>
                        ) : subprocessors.length === 0 ? (
                            <div className="text-center py-8 text-gray-500 dark:text-gray-400">
                                No subprocessors added yet
                            </div>
                        ) : (
                            <div className="space-y-2">
                                {subprocessors.map(sp => (
                                    <div key={sp.id} className="flex items-center justify-between p-4 bg-gray-50 dark:bg-[#0b0c0e] rounded-lg border border-gray-200 dark:border-gray-800">
                                        <div>
                                            <div className="font-medium text-gray-900 dark:text-gray-100">{sp.name}</div>
                                            {sp.location && <div className="text-sm text-gray-500">{sp.location}</div>}
                                            {sp.description && <div className="text-xs text-gray-400 mt-1">{sp.description}</div>}
                                        </div>
                                        <button
                                            onClick={() => handleRemoveSubprocessor(sp.id)}
                                            className="text-red-500 hover:text-red-700 p-1"
                                            aria-label="Remove subprocessor"
                                        >
                                            <Trash2 className="w-5 h-5" />
                                        </button>
                                    </div>
                                ))}
                            </div>
                        )}

                        {/* Add Subprocessor Form */}
                        {adding && (
                            <form onSubmit={handleAddSubprocessor} className="mt-4 p-4 bg-gray-50 dark:bg-[#0b0c0e] rounded-lg border border-gray-200 dark:border-gray-800 space-y-3">
                                <div>
                                    <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Name *</label>
                                    <input
                                        type="text"
                                        value={newSubprocessor.name}
                                        onChange={(e) => setNewSubprocessor({...newSubprocessor, name: e.target.value})}
                                        className="w-full px-3 py-2 bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-teal-500"
                                        required
                                        autoFocus
                                    />
                                </div>
                                <div>
                                    <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Location</label>
                                    <input
                                        type="text"
                                        value={newSubprocessor.location}
                                        onChange={(e) => setNewSubprocessor({...newSubprocessor, location: e.target.value})}
                                        className="w-full px-3 py-2 bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-teal-500"
                                    />
                                </div>
                                <div>
                                    <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Description</label>
                                    <textarea
                                        value={newSubprocessor.description}
                                        onChange={(e) => setNewSubprocessor({...newSubprocessor, description: e.target.value})}
                                        className="w-full px-3 py-2 bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-teal-500"
                                        rows={2}
                                    />
                                </div>
                                <div className="flex justify-end gap-2 pt-2">
                                    <button type="button" onClick={() => setAdding(false)} className="px-4 py-2 text-sm text-gray-700 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-700 rounded-lg">
                                        Cancel
                                    </button>
                                    <button type="submit" disabled={adding || !newSubprocessor.name.trim()} className="px-4 py-2 text-sm bg-teal-600 hover:bg-teal-700 text-white rounded-lg disabled:opacity-50 disabled:cursor-not-allowed">
                                        {adding ? 'Adding...' : 'Add Subprocessor'}
                                    </button>
                                </div>
                            </form>
                        )}
                    </div>
                </div>
        </Modal>
    );
}
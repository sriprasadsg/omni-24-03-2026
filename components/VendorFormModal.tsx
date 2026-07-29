import React, { useState } from 'react';
import { Modal } from './Modal';

interface VendorFormModalProps {
    isOpen: boolean;
    onClose: () => void;
    onSubmit: (data: any) => Promise<void>;
}

export const VendorFormModal: React.FC<VendorFormModalProps> = ({ isOpen, onClose, onSubmit }) => {
    const [formData, setFormData] = useState({
        name: '',
        website: '',
        criticality: 'Medium',
        category: 'SaaS',
        contact_name: '',
        contact_email: '',
        contract_start: new Date().toISOString().split('T')[0],
        contract_end: '',
        status: 'Active'
    });
    const [submitting, setSubmitting] = useState(false);

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        setSubmitting(true);
        try {
            await onSubmit(formData);
            onClose();
        } catch (error) {
            console.error("Failed to create vendor", error);
        } finally {
            setSubmitting(false);
        }
    };

    const inputCls = "w-full rounded-lg border-gray-300 dark:border-gray-600 dark:bg-gray-700 dark:text-white";
    const labelCls = "block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1";

    const footer = (
        <>
            <button type="button" onClick={onClose} className="px-4 py-2 text-gray-700 dark:text-gray-200 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-lg">
                Cancel
            </button>
            <button type="submit" form="vendor-form" disabled={submitting} className="px-4 py-2 bg-teal-600 hover:bg-teal-700 text-white rounded-lg disabled:opacity-50">
                {submitting ? 'Adding...' : 'Add Vendor'}
            </button>
        </>
    );

    return (
        <Modal isOpen={isOpen} onClose={onClose} title="Add Vendor" size="lg" footer={footer}>
            <form id="vendor-form" onSubmit={handleSubmit} className="space-y-4">
                <div>
                    <label className={labelCls}>Vendor Name</label>
                    <input type="text" required value={formData.name} onChange={e => setFormData({ ...formData, name: e.target.value })} className={inputCls} />
                </div>
                <div className="grid grid-cols-2 gap-4">
                    <div>
                        <label className={labelCls}>Website</label>
                        <input type="url" required value={formData.website} onChange={e => setFormData({ ...formData, website: e.target.value })} className={inputCls} />
                    </div>
                    <div>
                        <label className={labelCls}>Category</label>
                        <input type="text" value={formData.category} onChange={e => setFormData({ ...formData, category: e.target.value })} className={inputCls} placeholder="e.g. Cloud Provider" />
                    </div>
                </div>
                <div>
                    <label className={labelCls}>Criticality</label>
                    <select value={formData.criticality} onChange={e => setFormData({ ...formData, criticality: e.target.value })} className={inputCls}>
                        <option value="Low">Low</option>
                        <option value="Medium">Medium</option>
                        <option value="High">High</option>
                        <option value="Critical">Critical</option>
                    </select>
                </div>
                <div className="grid grid-cols-2 gap-4">
                    <div>
                        <label className={labelCls}>Contact Name</label>
                        <input type="text" value={formData.contact_name} onChange={e => setFormData({ ...formData, contact_name: e.target.value })} className={inputCls} />
                    </div>
                    <div>
                        <label className={labelCls}>Contact Email</label>
                        <input type="email" value={formData.contact_email} onChange={e => setFormData({ ...formData, contact_email: e.target.value })} className={inputCls} />
                    </div>
                </div>
            </form>
        </Modal>
    );
};

import React, { useState } from 'react';
import { Modal } from './Modal';

interface AddIntegrationModalProps {
    isOpen: boolean;
    onClose: () => void;
    onSave: (integration: { name: string; category: string; description: string; logo?: string; apiKey?: string; apiUrl?: string }) => void;
}

const CATEGORIES = ['Collaboration', 'Ticketing', 'SIEM', 'Observability', 'Security', 'Community & Partners', 'Custom'];

export const AddIntegrationModal: React.FC<AddIntegrationModalProps> = ({ isOpen, onClose, onSave }) => {
    const [name, setName] = useState('');
    const [category, setCategory] = useState('Custom');
    const [description, setDescription] = useState('');
    const [logo, setLogo] = useState('');
    const [apiUrl, setApiUrl] = useState('');
    const [apiKey, setApiKey] = useState('');

    const handleSubmit = (e: React.FormEvent) => {
        e.preventDefault();
        onSave({ name, category, description, logo, apiUrl, apiKey });
        onClose();
        // Reset form
        setName('');
        setCategory('Custom');
        setDescription('');
        setLogo('');
        setApiUrl('');
        setApiKey('');
    };

    const inputCls = "mt-1 block w-full px-3 py-2 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-md shadow-sm text-sm focus:ring-primary-500 focus:border-primary-500";
    const labelCls = "block text-sm font-medium text-gray-700 dark:text-gray-300";

    const footer = (
        <>
            <button type="button" onClick={onClose} className="px-4 py-2 text-sm font-medium text-gray-700 bg-white dark:bg-gray-700 dark:text-gray-200 border border-gray-300 dark:border-gray-600 rounded-md hover:bg-gray-50 dark:hover:bg-gray-600">Cancel</button>
            <button type="submit" form="add-integration-form" className="px-4 py-2 text-sm font-medium text-white bg-primary-600 rounded-lg hover:bg-primary-700">Add Integration</button>
        </>
    );

    return (
        <Modal isOpen={isOpen} onClose={onClose} title="Add Custom Integration" size="md" footer={footer}>
            <form id="add-integration-form" onSubmit={handleSubmit} className="space-y-4">
                <div>
                    <label htmlFor="int-name" className={labelCls}>Name</label>
                    <input type="text" id="int-name" value={name} onChange={e => setName(e.target.value)} required className={inputCls} placeholder="e.g. My Internal Tool" />
                </div>
                <div>
                    <label htmlFor="int-category" className={labelCls}>Category</label>
                    <select id="int-category" value={category} onChange={e => setCategory(e.target.value)} className={inputCls}>
                        {CATEGORIES.map(cat => (
                            <option key={cat} value={cat}>{cat}</option>
                        ))}
                    </select>
                </div>
                <div>
                    <label htmlFor="int-desc" className={labelCls}>Description</label>
                    <textarea id="int-desc" value={description} onChange={e => setDescription(e.target.value)} rows={3} className={inputCls} placeholder="Brief description of this integration..." />
                </div>
                <div>
                    <label htmlFor="int-api-url" className={labelCls}>
                        API URL / Endpoint <span className="text-xs font-normal text-gray-400">(Optional)</span>
                    </label>
                    <input type="text" id="int-api-url" value={apiUrl} onChange={e => setApiUrl(e.target.value)} className={inputCls} placeholder="https://api.example.com" />
                </div>
                <div>
                    <label htmlFor="int-api-key" className={labelCls}>
                        API Key / Token <span className="text-xs font-normal text-gray-400">(Optional)</span>
                    </label>
                    <input type="password" id="int-api-key" value={apiKey} onChange={e => setApiKey(e.target.value)} className={inputCls} placeholder="Enter API key or token" />
                </div>
            </form>
        </Modal>
    );
};

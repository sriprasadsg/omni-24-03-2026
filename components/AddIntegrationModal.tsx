import React, { useState } from 'react';
import { XIcon } from './icons';

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

    if (!isOpen) return null;

    return (
        <div className="fixed inset-0 bg-black bg-opacity-50 z-50 flex justify-center items-center" onClick={onClose}>
            <div className="bg-white dark:bg-gray-800 rounded-lg shadow-xl w-full max-w-md p-6 m-4" onClick={e => e.stopPropagation()}>
                <div className="flex justify-between items-center mb-4">
                    <h2 className="text-xl font-bold text-gray-900 dark:text-white">Add Custom Integration</h2>
                    <button onClick={onClose} className="p-1 rounded-full text-gray-400 hover:bg-gray-200 dark:hover:bg-gray-700 focus:outline-none">
                        <XIcon size={20} />
                    </button>
                </div>
                <form onSubmit={handleSubmit} className="space-y-4">
                    <div>
                        <label htmlFor="int-name" className="block text-sm font-medium text-gray-700 dark:text-gray-300">Name</label>
                        <input
                            type="text"
                            id="int-name"
                            value={name}
                            onChange={e => setName(e.target.value)}
                            required
                            className="mt-1 block w-full px-3 py-2 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-md shadow-sm text-sm focus:ring-primary-500 focus:border-primary-500"
                            placeholder="e.g. My Internal Tool"
                        />
                    </div>
                    <div>
                        <label htmlFor="int-category" className="block text-sm font-medium text-gray-700 dark:text-gray-300">Category</label>
                        <select
                            id="int-category"
                            value={category}
                            onChange={e => setCategory(e.target.value)}
                            className="mt-1 block w-full px-3 py-2 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-md shadow-sm text-sm focus:ring-primary-500 focus:border-primary-500"
                        >
                            {CATEGORIES.map(cat => (
                                <option key={cat} value={cat}>{cat}</option>
                            ))}
                        </select>
                    </div>
                    <div>
                        <label htmlFor="int-desc" className="block text-sm font-medium text-gray-700 dark:text-gray-300">Description</label>
                        <textarea
                            id="int-desc"
                            value={description}
                            onChange={e => setDescription(e.target.value)}
                            rows={3}
                            className="mt-1 block w-full px-3 py-2 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-md shadow-sm text-sm focus:ring-primary-500 focus:border-primary-500"
                            placeholder="Brief description of this integration..."
                        />
                    </div>
                    <div>
                        <label htmlFor="int-api-url" className="block text-sm font-medium text-gray-700 dark:text-gray-300">
                            API URL / Endpoint <span className="text-xs font-normal text-gray-400">(Optional)</span>
                        </label>
                        <input
                            type="text"
                            id="int-api-url"
                            value={apiUrl}
                            onChange={e => setApiUrl(e.target.value)}
                            className="mt-1 block w-full px-3 py-2 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-md shadow-sm text-sm focus:ring-primary-500 focus:border-primary-500"
                            placeholder="https://api.example.com"
                        />
                    </div>
                    <div>
                        <label htmlFor="int-api-key" className="block text-sm font-medium text-gray-700 dark:text-gray-300">
                            API Key / Token <span className="text-xs font-normal text-gray-400">(Optional)</span>
                        </label>
                        <input
                            type="password"
                            id="int-api-key"
                            value={apiKey}
                            onChange={e => setApiKey(e.target.value)}
                            className="mt-1 block w-full px-3 py-2 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-md shadow-sm text-sm focus:ring-primary-500 focus:border-primary-500"
                            placeholder="Enter API key or token"
                        />
                    </div>
                    <div className="mt-6 flex justify-end space-x-3 pt-4 border-t border-gray-200 dark:border-gray-700">
                        <button type="button" onClick={onClose} className="px-4 py-2 text-sm font-medium text-gray-700 bg-white dark:bg-gray-700 dark:text-gray-200 border border-gray-300 dark:border-gray-600 rounded-md hover:bg-gray-50 dark:hover:bg-gray-600">Cancel</button>
                        <button type="submit" className="px-4 py-2 text-sm font-medium text-white bg-primary-600 rounded-lg hover:bg-primary-700">Add Integration</button>
                    </div>
                </form>
            </div>
        </div>
    );
};

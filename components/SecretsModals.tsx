import React from 'react';
import { Secret } from './SecretsTableTab';

interface SecretFormData {
    name: string;
    value: string;
    secret_type: string;
    description: string;
    rotation_enabled: boolean;
}

interface CreateSecretModalProps {
    formData: SecretFormData;
    onChange: (data: SecretFormData) => void;
    onSubmit: (e: React.FormEvent) => void;
    onClose: () => void;
}

export function CreateSecretModal({ formData, onChange, onSubmit, onClose }: CreateSecretModalProps) {
    return (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
            <div className="bg-white dark:bg-gray-800 rounded-xl p-8 max-w-md w-full mx-4 shadow-2xl">
                <h2 className="text-2xl font-bold text-gray-900 dark:text-gray-100 mb-6">Create New Secret</h2>
                <form onSubmit={onSubmit} className="space-y-4">
                    <div>
                        <label className="block text-sm font-semibold text-gray-700 dark:text-gray-300 mb-2">Name</label>
                        <input type="text" value={formData.name}
                            onChange={(e) => onChange({ ...formData, name: e.target.value })}
                            className="w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100"
                            required />
                    </div>
                    <div>
                        <label className="block text-sm font-semibold text-gray-700 dark:text-gray-300 mb-2">Value</label>
                        <input type="password" value={formData.value}
                            onChange={(e) => onChange({ ...formData, value: e.target.value })}
                            className="w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100"
                            required />
                    </div>
                    <div>
                        <label className="block text-sm font-semibold text-gray-700 dark:text-gray-300 mb-2">Type</label>
                        <select value={formData.secret_type}
                            onChange={(e) => onChange({ ...formData, secret_type: e.target.value })}
                            className="w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100">
                            <option value="api_key">API Key</option>
                            <option value="database_password">Database Password</option>
                            <option value="encryption_key">Encryption Key</option>
                            <option value="certificate">Certificate</option>
                            <option value="ssh_key">SSH Key</option>
                            <option value="oauth_token">OAuth Token</option>
                            <option value="webhook_secret">Webhook Secret</option>
                        </select>
                    </div>
                    <div>
                        <label className="block text-sm font-semibold text-gray-700 dark:text-gray-300 mb-2">Description (optional)</label>
                        <input type="text" value={formData.description}
                            onChange={(e) => onChange({ ...formData, description: e.target.value })}
                            className="w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100" />
                    </div>
                    <div className="flex items-center gap-2">
                        <input type="checkbox" checked={formData.rotation_enabled}
                            onChange={(e) => onChange({ ...formData, rotation_enabled: e.target.checked })}
                            className="w-4 h-4" />
                        <label className="text-sm text-gray-700 dark:text-gray-300">Enable automatic rotation</label>
                    </div>
                    <div className="flex gap-3 pt-4">
                        <button type="button" onClick={onClose}
                            className="flex-1 px-4 py-2 border border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-300 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors">
                            Cancel
                        </button>
                        <button type="submit"
                            className="flex-1 px-4 py-2 bg-purple-600 hover:bg-purple-700 text-white rounded-lg font-semibold transition-colors">
                            Create
                        </button>
                    </div>
                </form>
            </div>
        </div>
    );
}

interface ViewSecretModalProps {
    secret: Secret;
    secretValue: string;
    onClose: () => void;
}

export function ViewSecretModal({ secret, secretValue, onClose }: ViewSecretModalProps) {
    return (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
            <div className="bg-white dark:bg-gray-800 rounded-xl p-8 max-w-md w-full mx-4 shadow-2xl">
                <h2 className="text-2xl font-bold text-gray-900 dark:text-gray-100 mb-6">Secret Value</h2>
                <div className="space-y-4">
                    <div>
                        <label className="block text-sm font-semibold text-gray-700 dark:text-gray-300 mb-2">Name</label>
                        <p className="text-gray-900 dark:text-gray-100">{secret.name}</p>
                    </div>
                    <div>
                        <label className="block text-sm font-semibold text-gray-700 dark:text-gray-300 mb-2">Value</label>
                        <div className="p-4 bg-gray-100 dark:bg-gray-700 rounded-lg font-mono text-sm break-all">
                            {secretValue}
                        </div>
                    </div>
                    <div className="bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-700 rounded-lg p-4">
                        <p className="text-sm text-amber-700 dark:text-amber-300">
                            ⚠️ This access has been logged for audit purposes.
                        </p>
                    </div>
                    <button onClick={onClose}
                        className="w-full px-4 py-2 bg-purple-600 hover:bg-purple-700 text-white rounded-lg font-semibold transition-colors">
                        Close
                    </button>
                </div>
            </div>
        </div>
    );
}

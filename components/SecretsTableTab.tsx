import React from 'react';
import { EyeIcon, RefreshCwIcon, TrashIcon } from './icons';

export interface Secret {
    id: string;
    name: string;
    secret_type: string;
    tenant_id: string;
    description?: string;
    status: string;
    version: number;
    rotation_enabled: boolean;
    rotation_days?: number;
    next_rotation?: string;
    created_at: string;
    last_accessed?: string;
    access_count: number;
}

function getStatusColor(status: string) {
    switch (status) {
        case 'active': return 'bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-300';
        case 'rotating': return 'bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300';
        case 'deprecated': return 'bg-amber-100 dark:bg-amber-900/30 text-amber-700 dark:text-amber-300';
        case 'revoked': return 'bg-red-100 dark:bg-red-900/30 text-red-700 dark:text-red-300';
        default: return 'bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300';
    }
}

function getTypeIcon(type: string) {
    switch (type) {
        case 'api_key': return '🔑';
        case 'database_password': return '🗄️';
        case 'encryption_key': return '🔐';
        case 'certificate': return '📜';
        case 'ssh_key': return '🖥️';
        case 'oauth_token': return '🎫';
        case 'webhook_secret': return '🪝';
        default: return '🔒';
    }
}

interface Props {
    secrets: Secret[];
    isRotationDue: (secret: Secret) => boolean;
    onView: (secret: Secret) => void;
    onRotate: (name: string) => void;
    onRevoke: (name: string) => void;
}

export function SecretsTableTab({ secrets, isRotationDue, onView, onRotate, onRevoke }: Props) {
    return (
        <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 shadow-lg overflow-hidden">
            <table className="w-full">
                <thead className="bg-gray-50 dark:bg-gray-700/50">
                    <tr>
                        <th className="text-left py-3 px-4 text-sm font-semibold text-gray-700 dark:text-gray-300">Name</th>
                        <th className="text-left py-3 px-4 text-sm font-semibold text-gray-700 dark:text-gray-300">Type</th>
                        <th className="text-left py-3 px-4 text-sm font-semibold text-gray-700 dark:text-gray-300">Status</th>
                        <th className="text-left py-3 px-4 text-sm font-semibold text-gray-700 dark:text-gray-300">Version</th>
                        <th className="text-left py-3 px-4 text-sm font-semibold text-gray-700 dark:text-gray-300">Next Rotation</th>
                        <th className="text-right py-3 px-4 text-sm font-semibold text-gray-700 dark:text-gray-300">Actions</th>
                    </tr>
                </thead>
                <tbody>
                    {secrets.map((secret) => (
                        <tr key={secret.id} className="border-t border-gray-100 dark:border-gray-700 hover:bg-gray-50 dark:hover:bg-gray-700/50">
                            <td className="py-3 px-4">
                                <div className="flex items-center gap-2">
                                    <span className="text-xl">{getTypeIcon(secret.secret_type)}</span>
                                    <div>
                                        <p className="text-sm font-semibold text-gray-900 dark:text-gray-100">{secret.name}</p>
                                        {secret.description && (
                                            <p className="text-xs text-gray-600 dark:text-gray-400">{secret.description}</p>
                                        )}
                                    </div>
                                </div>
                            </td>
                            <td className="py-3 px-4 text-sm text-gray-700 dark:text-gray-300">{secret.secret_type.replace('_', ' ')}</td>
                            <td className="py-3 px-4">
                                <span className={`px-2 py-1 rounded-full text-xs font-bold ${getStatusColor(secret.status)}`}>
                                    {secret.status.toUpperCase()}
                                </span>
                            </td>
                            <td className="py-3 px-4 text-sm text-gray-700 dark:text-gray-300">v{secret.version}</td>
                            <td className="py-3 px-4">
                                {secret.next_rotation ? (
                                    <span className={`text-sm ${isRotationDue(secret) ? 'text-red-600 font-bold' : 'text-gray-700 dark:text-gray-300'}`}>
                                        {new Date(secret.next_rotation).toLocaleDateString()}
                                        {isRotationDue(secret) && ' ⚠️'}
                                    </span>
                                ) : (
                                    <span className="text-sm text-gray-500">Manual</span>
                                )}
                            </td>
                            <td className="py-3 px-4 text-right">
                                <div className="flex gap-2 justify-end">
                                    <button onClick={() => onView(secret)}
                                        className="p-2 text-blue-600 hover:bg-blue-50 dark:hover:bg-blue-900/20 rounded transition-colors"
                                        title="View secret">
                                        <EyeIcon size={18} />
                                    </button>
                                    {secret.status === 'active' && secret.rotation_enabled && (
                                        <button onClick={() => onRotate(secret.name)}
                                            className="p-2 text-green-600 hover:bg-green-50 dark:hover:bg-green-900/20 rounded transition-colors"
                                            title="Rotate secret">
                                            <RefreshCwIcon size={18} />
                                        </button>
                                    )}
                                    {secret.status === 'active' && (
                                        <button onClick={() => onRevoke(secret.name)}
                                            className="p-2 text-red-600 hover:bg-red-50 dark:hover:bg-red-900/20 rounded transition-colors"
                                            title="Revoke secret">
                                            <TrashIcon size={18} />
                                        </button>
                                    )}
                                </div>
                            </td>
                        </tr>
                    ))}
                </tbody>
            </table>
        </div>
    );
}

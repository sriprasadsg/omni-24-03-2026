import React, { useState, useEffect } from 'react';
import { Webhook, WebhookEvent, WebhookDelivery } from '../types';
import { PlusCircleIcon, TrashIcon, RefreshCwIcon, CheckIcon, XCircleIcon, ClockIcon, CheckCircleIcon } from './icons';

export const WebhookManagement: React.FC = () => {
    const [webhooks, setWebhooks] = useState<Webhook[]>([]);
    const [selectedWebhook, setSelectedWebhook] = useState<Webhook | null>(null);
    const [deliveries, setDeliveries] = useState<WebhookDelivery[]>([]);
    const [showCreateModal, setShowCreateModal] = useState(false);
    const [loading, setLoading] = useState(true);

    const availableEvents: WebhookEvent[] = [
        'agent.online',
        'agent.offline',
        'agent.error',
        'vulnerability.detected',
        'security.alert',
        'compliance.violation',
        'patch.deployed',
        'asset.discovered'
    ];

    useEffect(() => {
        fetchWebhooks();
    }, []);

    const fetchWebhooks = async () => {
        try {
            const response = await fetch('/api/webhooks');
            const data = await response.json();
            if (Array.isArray(data)) {
                setWebhooks(data);
            } else {
                console.warn('Webhooks API did not return an array:', data);
                setWebhooks([]);
            }
            setLoading(false);
        } catch (error) {
            console.error('Error fetching webhooks:', error);
            setLoading(false);
        }
    };

    const fetchDeliveries = async (webhookId: string) => {
        try {
            const response = await fetch(`/api/webhooks/${webhookId}/deliveries`);
            const data = await response.json();
            if (Array.isArray(data)) {
                setDeliveries(data);
            } else {
                setDeliveries([]);
            }
        } catch (error) {
            console.error('Error fetching deliveries:', error);
        }
    };

    const handleCreateWebhook = async (formData: any) => {
        try {
            const response = await fetch('/api/webhooks', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(formData)
            });
            const newWebhook = await response.json();
            setWebhooks([...webhooks, newWebhook]);
            setShowCreateModal(false);
        } catch (error) {
            console.error('Error creating webhook:', error);
        }
    };

    const handleDeleteWebhook = async (webhookId: string) => {
        if (!confirm('Are you sure you want to delete this webhook?')) return;

        try {
            await fetch(`/api/webhooks/${webhookId}`, {
                method: 'DELETE'
            });
            setWebhooks(webhooks.filter(w => w.id !== webhookId));
            if (selectedWebhook?.id === webhookId) {
                setSelectedWebhook(null);
                setDeliveries([]);
            }
        } catch (error) {
            console.error('Error deleting webhook:', error);
        }
    };

    const handleTestWebhook = async (webhookId: string) => {
        try {
            const response = await fetch(`/api/webhooks/${webhookId}/test`, {
                method: 'POST'
            });
            const delivery = await response.json();
            alert(delivery.success ? 'Test successful!' : `Test failed: ${delivery.error}`);
            if (selectedWebhook?.id === webhookId) {
                fetchDeliveries(webhookId);
            }
        } catch (error) {
            console.error('Error testing webhook:', error);
            alert('Test failed');
        }
    };

    const toggleWebhookStatus = async (webhook: Webhook) => {
        const newStatus = webhook.status === 'Active' ? 'Disabled' : 'Active';
        try {
            const response = await fetch(`/api/webhooks/${webhook.id}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ status: newStatus })
            });
            const updated = await response.json();
            setWebhooks(webhooks.map(w => w.id === webhook.id ? updated : w));
        } catch (error) {
            console.error('Error updating webhook:', error);
        }
    };

    if (loading) {
        return <div className="p-4">Loading webhooks...</div>;
    }

    return (
        <div className="p-6 space-y-6">
            {/* Header */}
            <div className="flex justify-between items-center">
                <div>
                    <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Webhook Management</h1>
                    <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">Configure webhooks to receive real-time event notifications</p>
                </div>
                <button
                    onClick={() => setShowCreateModal(true)}
                    className="flex items-center px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700"
                >
                    <PlusCircleIcon size={18} className="mr-2" />
                    Create Webhook
                </button>
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                {/* Webhooks List */}
                <div className="bg-white dark:bg-gray-800 rounded-lg shadow-md">
                    <div className="p-4 border-b border-gray-200 dark:border-gray-700">
                        <h2 className="text-lg font-semibold text-gray-900 dark:text-white">Webhooks ({webhooks.length})</h2>
                    </div>
                    <div className="divide-y divide-gray-200 dark:divide-gray-700">
                        {webhooks.length === 0 ? (
                            <div className="p-8 text-center text-gray-500">
                                No webhooks configured. Create one to get started.
                            </div>
                        ) : (
                            webhooks.map(webhook => (
                                <div
                                    key={webhook.id}
                                    className={`p-4 cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-700/50 ${selectedWebhook?.id === webhook.id ? 'bg-blue-50 dark:bg-blue-900/20' : ''}`}
                                    onClick={() => {
                                        setSelectedWebhook(webhook);
                                        fetchDeliveries(webhook.id);
                                    }}
                                >
                                    <div className="flex justify-between items-start">
                                        <div className="flex-1">
                                            <h3 className="font-semibold text-gray-900 dark:text-white">{webhook.name}</h3>
                                            <p className="text-sm text-gray-600 dark:text-gray-400 mt-1">{webhook.url}</p>
                                            <div className="flex items-center gap-3 mt-2">
                                                <span className={`text-xs px-2 py-1 rounded-full ${webhook.status === 'Active'
                                                    ? 'bg-green-100 text-green-800 dark:bg-green-900/50 dark:text-green-300'
                                                    : 'bg-gray-100 text-gray-800 dark:bg-gray-700 dark:text-gray-300'
                                                    }`}>
                                                    {webhook.status}
                                                </span>
                                                <span className="text-xs text-gray-500">{webhook.events.length} events</span>
                                                {webhook.failureCount > 0 && (
                                                    <span className="text-xs text-red-600 dark:text-red-400">{webhook.failureCount} failures</span>
                                                )}
                                            </div>
                                        </div>
                                        <div className="flex gap-2">
                                            <button
                                                onClick={(e) => {
                                                    e.stopPropagation();
                                                    handleTestWebhook(webhook.id);
                                                }}
                                                className="p-2 text-blue-600 hover:bg-blue-50 dark:hover:bg-blue-900/20 rounded"
                                                title="Test webhook"
                                            >
                                                <RefreshCwIcon size={16} />
                                            </button>
                                            <button
                                                onClick={(e) => {
                                                    e.stopPropagation();
                                                    toggleWebhookStatus(webhook);
                                                }}
                                                className="p-2 text-gray-600 hover:bg-gray-100 dark:hover:bg-gray-700 rounded"
                                                title={webhook.status === 'Active' ? 'Disable' : 'Enable'}
                                            >
                                                {webhook.status === 'Active' ? <CheckIcon size={16} /> : <XCircleIcon size={16} />}
                                            </button>
                                            <button
                                                onClick={(e) => {
                                                    e.stopPropagation();
                                                    handleDeleteWebhook(webhook.id);
                                                }}
                                                className="p-2 text-red-600 hover:bg-red-50 dark:hover:bg-red-900/20 rounded"
                                                title="Delete"
                                            >
                                                <TrashIcon size={16} />
                                            </button>
                                        </div>
                                    </div>
                                </div>
                            ))
                        )}
                    </div>
                </div>

                {/* Delivery History */}
                <div className="bg-white dark:bg-gray-800 rounded-lg shadow-md">
                    <div className="p-4 border-b border-gray-200 dark:border-gray-700">
                        <h2 className="text-lg font-semibold text-gray-900 dark:text-white">
                            {selectedWebhook ? `Deliveries for ${selectedWebhook.name}` : 'Select a webhook'}
                        </h2>
                    </div>
                    <div className="divide-y divide-gray-200 dark:divide-gray-700 max-h-[600px] overflow-y-auto">
                        {!selectedWebhook ? (
                            <div className="p-8 text-center text-gray-500">
                                Select a webhook to view delivery history
                            </div>
                        ) : deliveries.length === 0 ? (
                            <div className="p-8 text-center text-gray-500">
                                No deliveries yet
                            </div>
                        ) : (
                            deliveries.map(delivery => (
                                <div key={delivery.id} className="p-4">
                                    <div className="flex justify-between items-start">
                                        <div className="flex-1">
                                            <div className="flex items-center gap-2">
                                                {delivery.success ? (
                                                    <CheckCircleIcon size={16} className="text-green-600" />
                                                ) : (
                                                    <XCircleIcon size={16} className="text-red-600" />
                                                )}
                                                <span className="font-mono text-sm text-gray-900 dark:text-white">{delivery.event}</span>
                                            </div>
                                            <div className="mt-2 space-y-1">
                                                <div className="text-xs text-gray-600 dark:text-gray-400 flex items-center gap-1">
                                                    <ClockIcon size={12} />
                                                    {new Date(delivery.deliveredAt).toLocaleString()}
                                                </div>
                                                {delivery.responseStatus && (
                                                    <div className="text-xs text-gray-600 dark:text-gray-400">
                                                        Status: {delivery.responseStatus}
                                                    </div>
                                                )}
                                                {delivery.error && (
                                                    <div className="text-xs text-red-600 dark:text-red-400">
                                                        Error: {delivery.error}
                                                    </div>
                                                )}
                                            </div>
                                        </div>
                                    </div>
                                </div>
                            ))
                        )}
                    </div>
                </div>
            </div>

            {/* Create Modal */}
            {showCreateModal && (
                <CreateWebhookModal
                    availableEvents={availableEvents}
                    onClose={() => setShowCreateModal(false)}
                    onCreate={handleCreateWebhook}
                />
            )}
        </div>
    );
};

const CreateWebhookModal: React.FC<{
    availableEvents: WebhookEvent[];
    onClose: () => void;
    onCreate: (data: any) => void;
}> = ({ availableEvents, onClose, onCreate }) => {
    const [formData, setFormData] = useState({
        name: '',
        url: '',
        events: [] as WebhookEvent[]
    });

    const handleSubmit = (e: React.FormEvent) => {
        e.preventDefault();
        onCreate(formData);
    };

    const toggleEvent = (event: WebhookEvent) => {
        setFormData(prev => ({
            ...prev,
            events: prev.events.includes(event)
                ? prev.events.filter(e => e !== event)
                : [...prev.events, event]
        }));
    };

    return (
        <div className="fixed inset-0 bg-black bg-opacity-50 z-50 flex items-center justify-center" onClick={onClose}>
            <div className="bg-white dark:bg-gray-800 rounded-lg p-6 max-w-md w-full m-4" onClick={e => e.stopPropagation()}>
                <h2 className="text-xl font-bold text-gray-900 dark:text-white mb-4">Create Webhook</h2>
                <form onSubmit={handleSubmit} className="space-y-4">
                    <div>
                        <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Name</label>
                        <input
                            type="text"
                            value={formData.name}
                            onChange={e => setFormData({ ...formData, name: e.target.value })}
                            className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
                            required
                        />
                    </div>
                    <div>
                        <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">URL</label>
                        <input
                            type="url"
                            value={formData.url}
                            onChange={e => setFormData({ ...formData, url: e.target.value })}
                            placeholder="https://your-server.com/webhook"
                            className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
                            required
                        />
                    </div>
                    <div>
                        <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">Events</label>
                        <div className="space-y-2 max-h-48 overflow-y-auto">
                            {availableEvents.map(event => (
                                <label key={event} className="flex items-center">
                                    <input
                                        type="checkbox"
                                        checked={formData.events.includes(event)}
                                        onChange={() => toggleEvent(event)}
                                        className="mr-2"
                                    />
                                    <span className="text-sm text-gray-700 dark:text-gray-300 font-mono">{event}</span>
                                </label>
                            ))}
                        </div>
                    </div>
                    <div className="flex gap-2 justify-end mt-6">
                        <button
                            type="button"
                            onClick={onClose}
                            className="px-4 py-2 text-gray-700 dark:text-gray-300 border border-gray-300 dark:border-gray-600 rounded-md hover:bg-gray-50 dark:hover:bg-gray-700"
                        >
                            Cancel
                        </button>
                        <button
                            type="submit"
                            className="px-4 py-2 bg-primary-600 text-white rounded-md hover:bg-primary-700"
                            disabled={formData.events.length === 0}
                        >
                            Create
                        </button>
                    </div>
                </form>
            </div>
        </div>
    );
};

import React, { useMemo, useState } from 'react';
import { Integration } from '../types';
import { useUser } from '../contexts/UserContext';
// FIX: Added missing icons.
import { CogIcon, ShieldSearchIcon, BarChart3Icon, SlackIcon, PagerDutyIcon, JiraIcon, PlusIcon, TrashIcon } from './icons';
import { AddIntegrationModal } from './AddIntegrationModal';
import * as apiService from '../services/apiService';

interface IntegrationsMarketplaceProps {
    integrations: Integration[];
    onConfigure: (integration: Integration) => void;
    onToggle: (id: Integration['id']) => void;
    onDelete?: (id: Integration['id']) => void;
}

const integrationIcons: Record<string, React.ReactNode> = {
    slack: <SlackIcon size={32} />,
    pagerduty: <PagerDutyIcon size={32} />,
    jira: <JiraIcon size={32} />,
    splunk: <ShieldSearchIcon size={32} />,
    datadog: <BarChart3Icon size={32} />,
    crowdstrike: <ShieldSearchIcon size={32} />,
};

export const IntegrationsMarketplace: React.FC<IntegrationsMarketplaceProps> = ({ integrations, onConfigure, onToggle, onDelete }) => {
    const { hasPermission } = useUser();
    const canManage = hasPermission('manage:settings');
    const [isAddModalOpen, setIsAddModalOpen] = useState(false);

    // Refresh trigger (handled by parent usually, but we might need to force update or rely on parent props update)
    // For now, we'll assume parent updates integrations prop when we verify.
    // In a real app, we'd probably call a callback prop like onRefresh()

    const groupedIntegrations = useMemo(() => {
        return integrations.reduce((acc, integration) => {
            const cat = integration.category || 'Custom';
            if (!acc[cat]) {
                acc[cat] = [];
            }
            acc[cat].push(integration);
            return acc;
        }, {} as Record<string, Integration[]>);
    }, [integrations]);

    const categoryOrder: string[] = ['Collaboration', 'Ticketing', 'SIEM', 'Observability', 'Security', 'Community & Partners', 'Custom'];

    // Ensure all categories exist in keys to avoid render errors if empty
    const sortedCategories = [...categoryOrder, ...Object.keys(groupedIntegrations).filter(k => !categoryOrder.includes(k))];

    const handleAddIntegration = async (data: { name: string; category: string; description: string; logo?: string; apiKey?: string; apiUrl?: string }) => {
        // Generate a random ID for custom integration
        const newId = `custom-${Date.now()}`;
        const newIntegration: Partial<Integration> = {
            id: newId,
            name: data.name,
            category: data.category as any,
            description: data.description,
            isEnabled: true, // Default to enabled for custom
            config: {
                ...(data.apiUrl ? { url: data.apiUrl } : {}),
                ...(data.apiKey ? { api_key: data.apiKey } : {}),
            }
        };

        try {
            await apiService.saveIntegrationConfig(newIntegration);
            // Reload page or trigger refresh would be ideal here. 
            // For MVP, we alert user to refresh.
            window.location.reload();
        } catch (error) {
            console.error("Failed to add integration", error);
            alert("Failed to add integration");
        }
    };

    const handleDeleteIntegration = async (integration: Integration) => {
        if (!window.confirm(`Delete "${integration.name}"? This will remove its configuration and cannot be undone.`)) return;
        try {
            await apiService.deleteIntegrationConfig(integration.id);
            if (onDelete) onDelete(integration.id);
            window.location.reload();
        } catch (error) {
            console.error('Failed to delete integration', error);
            alert('Failed to delete integration.');
        }
    };

    return (
        <div className="space-y-8">
            <div className="flex justify-between items-center">
                <h2 className="text-2xl font-bold text-gray-900 dark:text-white">Integrations</h2>
                {canManage && (
                    <button
                        onClick={() => setIsAddModalOpen(true)}
                        className="flex items-center px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 transition-colors"
                    >
                        <PlusIcon size={18} className="mr-2" />
                        Add Custom Tool
                    </button>
                )}
            </div>

            {sortedCategories.map(category => (
                groupedIntegrations[category] && groupedIntegrations[category].length > 0 && (
                    <div key={category}>
                        <h3 className="text-lg font-semibold text-gray-800 dark:text-white mb-4">{category}</h3>
                        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                            {groupedIntegrations[category]?.map(integration => (
                                <div key={integration.id} className="bg-white dark:bg-gray-800 rounded-lg shadow-md border border-gray-200 dark:border-gray-700 p-6 flex flex-col transition-all hover:shadow-lg">
                                    <div className="flex-grow">
                                        <div className="flex items-center space-x-4">
                                            <div className={`flex-shrink-0 p-2 rounded-lg bg-gray-100 dark:bg-gray-700 ${integration.isEnabled ? 'text-primary-500' : 'text-gray-400'}`}>
                                                {integrationIcons[integration.id] || <CogIcon size={32} />}
                                            </div>
                                            <h4 className="text-lg font-bold text-gray-800 dark:text-gray-100">{integration.name}</h4>
                                        </div>
                                        <p className="text-sm text-gray-600 dark:text-gray-400 mt-4">{integration.description}</p>
                                    </div>

                                    <div className="mt-6 pt-4 border-t border-gray-200 dark:border-gray-700 flex justify-between items-center">
                                        <div className="flex items-center space-x-2">
                                            <button
                                                onClick={() => onConfigure(integration)}
                                                disabled={!canManage}
                                                className="flex items-center px-3 py-1.5 text-xs font-medium text-gray-700 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-500 rounded-md shadow-sm hover:bg-gray-50 dark:hover:bg-gray-600 disabled:opacity-50 disabled:cursor-not-allowed"
                                            >
                                                <CogIcon size={14} className="mr-1.5" /> Configure
                                            </button>
                                            {canManage && (
                                                <button
                                                    onClick={() => handleDeleteIntegration(integration)}
                                                    className="flex items-center p-1.5 text-gray-400 hover:text-red-600 dark:hover:text-red-400 rounded-md hover:bg-red-50 dark:hover:bg-red-900/20 transition-colors"
                                                    title={`Delete ${integration.name}`}
                                                >
                                                    <TrashIcon size={14} />
                                                </button>
                                            )}
                                        </div>
                                        <button
                                            type="button"
                                            onClick={() => onToggle(integration.id)}
                                            disabled={!canManage}
                                            className={`px-3 py-1.5 text-xs font-medium rounded-md ${integration.isEnabled
                                                ? 'bg-primary-600 text-white hover:bg-primary-700'
                                                : 'bg-gray-200 dark:bg-gray-600 text-gray-800 dark:text-gray-200 hover:bg-gray-300 dark:hover:bg-gray-500'
                                                } disabled:opacity-50 disabled:cursor-not-allowed`}
                                        >
                                            {integration.isEnabled ? 'Enabled' : 'Install'}
                                        </button>
                                    </div>
                                </div>
                            ))}
                        </div>
                    </div>
                )
            ))}

            <AddIntegrationModal
                isOpen={isAddModalOpen}
                onClose={() => setIsAddModalOpen(false)}
                onSave={handleAddIntegration}
            />
        </div>
    );
};

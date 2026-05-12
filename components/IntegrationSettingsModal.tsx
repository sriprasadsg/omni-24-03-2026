import React, { useState, useEffect } from 'react';
import { X, Save, Shield, Info, ExternalLink } from 'lucide-react';
import { Integration } from '../types';

interface IntegrationSettingsModalProps {
    isOpen: boolean;
    onClose: () => void;
    integration: Integration | null;
    onSave: (id: string, config: any, isEnabled: boolean) => Promise<void>;
}

export const IntegrationSettingsModal: React.FC<IntegrationSettingsModalProps> = ({ 
    isOpen, 
    onClose, 
    integration, 
    onSave 
}) => {
    const [config, setConfig] = useState<any>({});
    const [isEnabled, setIsEnabled] = useState(false);
    const [saving, setSaving] = useState(false);

    useEffect(() => {
        if (integration) {
            setConfig(integration.config || {});
            setIsEnabled(integration.isEnabled);
        }
    }, [integration]);

    if (!isOpen || !integration) return null;

    const handleConfigChange = (key: string, value: any) => {
        setConfig(prev => ({ ...prev, [key]: value }));
    };

    const handleSave = async () => {
        setSaving(true);
        try {
            await onSave(integration.id, config, isEnabled);
            onClose();
        } catch (error) {
            console.error("Failed to save integration settings:", error);
        } finally {
            setSaving(false);
        }
    };

    const renderConfigFields = () => {
        // Customize fields based on integration ID
        switch (integration.id) {
            case 'slack':
            case 'msteams':
                return (
                    <div className="space-y-4">
                        <div>
                            <label className="block text-xs font-bold text-slate-400 uppercase mb-1">Webhook URL</label>
                            <input 
                                type="text"
                                value={config.webhookUrl || ''}
                                onChange={(e) => handleConfigChange('webhookUrl', e.target.value)}
                                className="w-full px-4 py-2 bg-slate-50 dark:bg-slate-900 border border-slate-100 dark:border-slate-800 rounded-lg text-sm focus:ring-2 focus:ring-indigo-500 text-slate-900 dark:text-white"
                                placeholder="https://hooks.slack.com/services/..."
                            />
                        </div>
                    </div>
                );
            case 'jira':
                return (
                    <div className="space-y-4">
                        <div>
                            <label className="block text-xs font-bold text-slate-400 uppercase mb-1">Instance URL</label>
                            <input 
                                type="text"
                                value={config.apiUrl || ''}
                                onChange={(e) => handleConfigChange('apiUrl', e.target.value)}
                                className="w-full px-4 py-2 bg-slate-50 dark:bg-slate-900 border border-slate-100 dark:border-slate-800 rounded-lg text-sm focus:ring-2 focus:ring-indigo-500 text-slate-900 dark:text-white"
                                placeholder="https://your-domain.atlassian.net"
                            />
                        </div>
                        <div>
                            <label className="block text-xs font-bold text-slate-400 uppercase mb-1">API Token</label>
                            <input 
                                type="password"
                                value={config.apiToken || ''}
                                onChange={(e) => handleConfigChange('apiToken', e.target.value)}
                                className="w-full px-4 py-2 bg-slate-50 dark:bg-slate-900 border border-slate-100 dark:border-slate-800 rounded-lg text-sm focus:ring-2 focus:ring-indigo-500 text-slate-900 dark:text-white"
                                placeholder="Your Jira API Token"
                            />
                        </div>
                        <div>
                            <label className="block text-xs font-bold text-slate-400 uppercase mb-1">Project Key</label>
                            <input 
                                type="text"
                                value={config.projectKey || ''}
                                onChange={(e) => handleConfigChange('projectKey', e.target.value)}
                                className="w-full px-4 py-2 bg-slate-50 dark:bg-slate-900 border border-slate-100 dark:border-slate-800 rounded-lg text-sm focus:ring-2 focus:ring-indigo-500 text-slate-900 dark:text-white"
                                placeholder="SEC"
                            />
                        </div>
                    </div>
                );
            case 'pagerduty':
                return (
                    <div className="space-y-4">
                        <div>
                            <label className="block text-xs font-bold text-slate-400 uppercase mb-1">API Key</label>
                            <input 
                                type="password"
                                value={config.apiKey || ''}
                                onChange={(e) => handleConfigChange('apiKey', e.target.value)}
                                className="w-full px-4 py-2 bg-slate-50 dark:bg-slate-900 border border-slate-100 dark:border-slate-800 rounded-lg text-sm focus:ring-2 focus:ring-indigo-500 text-slate-900 dark:text-white"
                                placeholder="PagerDuty API Key"
                            />
                        </div>
                    </div>
                );
            case 'servicenow':
                return (
                    <div className="space-y-4">
                        <div>
                            <label className="block text-xs font-bold text-slate-400 uppercase mb-1">Instance URL</label>
                            <input 
                                type="text"
                                value={config.instanceUrl || ''}
                                onChange={(e) => handleConfigChange('instanceUrl', e.target.value)}
                                className="w-full px-4 py-2 bg-slate-50 dark:bg-slate-900 border border-slate-100 dark:border-slate-800 rounded-lg text-sm focus:ring-2 focus:ring-indigo-500 text-slate-900 dark:text-white"
                                placeholder="https://dev12345.service-now.com"
                            />
                        </div>
                        <div className="grid grid-cols-2 gap-4">
                            <div>
                                <label className="block text-xs font-bold text-slate-400 uppercase mb-1">Username</label>
                                <input 
                                    type="text"
                                    value={config.username || ''}
                                    onChange={(e) => handleConfigChange('username', e.target.value)}
                                    className="w-full px-4 py-2 bg-slate-50 dark:bg-slate-900 border border-slate-100 dark:border-slate-800 rounded-lg text-sm focus:ring-2 focus:ring-indigo-500 text-slate-900 dark:text-white"
                                />
                            </div>
                            <div>
                                <label className="block text-xs font-bold text-slate-400 uppercase mb-1">Password</label>
                                <input 
                                    type="password"
                                    value={config.password || ''}
                                    onChange={(e) => handleConfigChange('password', e.target.value)}
                                    className="w-full px-4 py-2 bg-slate-50 dark:bg-slate-900 border border-slate-100 dark:border-slate-800 rounded-lg text-sm focus:ring-2 focus:ring-indigo-500 text-slate-900 dark:text-white"
                                />
                            </div>
                        </div>
                    </div>
                );
            default:
                return (
                    <div className="p-4 bg-slate-50 dark:bg-slate-900/50 rounded-xl border border-slate-100 dark:border-slate-800">
                        <div className="flex items-center space-x-3 text-slate-500">
                            <Info className="w-5 h-5" />
                            <p className="text-sm">This integration uses a standard configuration. No additional settings required.</p>
                        </div>
                    </div>
                );
        }
    };

    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/60 backdrop-blur-sm">
            <div className="bg-white dark:bg-slate-800 w-full max-w-lg rounded-3xl shadow-2xl border border-slate-100 dark:border-slate-700 overflow-hidden animate-in fade-in zoom-in duration-200">
                {/* Header */}
                <div className="px-8 py-6 border-b border-slate-50 dark:border-slate-700 flex justify-between items-center bg-slate-50/50 dark:bg-slate-900/20">
                    <div className="flex items-center space-x-4">
                        <div className="p-3 bg-white dark:bg-slate-800 rounded-2xl border border-slate-100 dark:border-slate-700 shadow-sm">
                            <Shield className="w-6 h-6 text-indigo-600" />
                        </div>
                        <div>
                            <h2 className="text-xl font-bold text-slate-900 dark:text-white">{integration.name} Settings</h2>
                            <p className="text-xs text-slate-400 font-bold uppercase tracking-wider">{integration.category}</p>
                        </div>
                    </div>
                    <button 
                        onClick={onClose}
                        className="p-2 hover:bg-slate-100 dark:hover:bg-slate-700 rounded-xl transition-colors text-slate-400 hover:text-slate-600"
                    >
                        <X className="w-6 h-6" />
                    </button>
                </div>

                {/* Body */}
                <div className="px-8 py-8 space-y-8">
                    <div className="flex items-center justify-between p-4 bg-indigo-50/50 dark:bg-indigo-900/10 rounded-2xl border border-indigo-100/50 dark:border-indigo-800/50">
                        <div className="flex items-center space-x-3">
                            <div className={`w-3 h-3 rounded-full ${isEnabled ? 'bg-emerald-500 animate-pulse' : 'bg-slate-300'}`}></div>
                            <div>
                                <p className="text-sm font-bold text-slate-900 dark:text-white">Enable Integration</p>
                                <p className="text-xs text-slate-500">Enable or disable this connector</p>
                            </div>
                        </div>
                        <label className="relative inline-flex items-center cursor-pointer">
                            <input 
                                type="checkbox" 
                                className="sr-only peer"
                                checked={isEnabled}
                                onChange={(e) => setIsEnabled(e.target.checked)}
                            />
                            <div className="w-11 h-6 bg-slate-200 peer-focus:outline-none rounded-full peer dark:bg-slate-700 peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all dark:border-gray-600 peer-checked:bg-indigo-600"></div>
                        </label>
                    </div>

                    <div className="space-y-4">
                        <div className="flex items-center space-x-2 text-slate-900 dark:text-white">
                            <Settings className="w-5 h-5 text-indigo-500" />
                            <h3 className="font-bold">Configuration</h3>
                        </div>
                        
                        {renderConfigFields()}
                    </div>

                    {integration.description && (
                        <div className="p-4 bg-slate-50 dark:bg-slate-900/50 rounded-2xl text-xs text-slate-500 border border-slate-100 dark:border-slate-800">
                            <p className="font-bold mb-1 uppercase tracking-tight">About this integration</p>
                            {integration.description}
                        </div>
                    )}
                </div>

                {/* Footer */}
                <div className="px-8 py-6 bg-slate-50/50 dark:bg-slate-900/20 border-t border-slate-50 dark:border-slate-700 flex justify-between items-center">
                    <button 
                        className="text-sm font-bold text-slate-400 hover:text-slate-600 flex items-center"
                        onClick={() => window.open(`https://docs.omniagent.ai/integrations/${integration.id}`, '_blank')}
                    >
                        View Documentation
                        <ExternalLink className="w-3 h-3 ml-1" />
                    </button>
                    <div className="flex space-x-3">
                        <button 
                            onClick={onClose}
                            className="px-6 py-2.5 rounded-xl text-sm font-bold text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-700 transition-colors"
                        >
                            Cancel
                        </button>
                        <button 
                            onClick={handleSave}
                            disabled={saving}
                            className="px-8 py-2.5 bg-indigo-600 text-white rounded-xl text-sm font-bold hover:bg-indigo-700 transition-all shadow-lg shadow-indigo-600/20 flex items-center disabled:opacity-50"
                        >
                            {saving ? (
                                <>
                                    <RefreshCw className="w-4 h-4 mr-2 animate-spin" />
                                    Saving...
                                </>
                            ) : (
                                <>
                                    <Save className="w-4 h-4 mr-2" />
                                    Save Settings
                                </>
                            )}
                        </button>
                    </div>
                </div>
            </div>
        </div>
    );
};

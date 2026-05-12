import React, { useState, useEffect } from 'react';
import { 
    Cloud, 
    Shield, 
    Lock, 
    Server, 
    Settings, 
    CheckCircle, 
    XCircle, 
    RefreshCw, 
    ExternalLink,
    Search,
    Filter,
    Plus,
    Zap,
    Key
} from 'lucide-react';
import * as api from '../services/apiService';
import { Integration } from '../types';
import { AddIntegrationModal } from './AddIntegrationModal';
import { IntegrationSettingsModal } from './IntegrationSettingsModal';

interface Integration {
    id: string;
    name: string;
    provider: 'aws' | 'azure' | 'gcp' | 'okta' | 'syslog' | 'other';
    status: 'connected' | 'error' | 'pending';
    last_sync: string;
    events_count: number;
    description: string;
}

export const IntegrationsHub: React.FC = () => {
    const [integrations, setIntegrations] = useState<Integration[]>([]);
    const [loading, setLoading] = useState(true);
    const [filter, setFilter] = useState('all');
    const [searchQuery, setSearchQuery] = useState('');
    const [isAddModalOpen, setIsAddModalOpen] = useState(false);
    const [selectedIntegration, setSelectedIntegration] = useState<Integration | null>(null);
    const [isConfigModalOpen, setIsConfigModalOpen] = useState(false);

    const loadIntegrations = async () => {
        setLoading(true);
        try {
            const data = await api.fetchIntegrations();
            setIntegrations(data);
        } catch (error) {
            console.error("Failed to fetch integrations:", error);
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        loadIntegrations();
    }, []);

    const handleSaveIntegration = async (id: string, config: any, isEnabled: boolean) => {
        try {
            const integrationToSave = integrations.find(i => i.id === id);
            if (integrationToSave) {
                await api.saveIntegrationConfig({
                    ...integrationToSave,
                    config,
                    isEnabled
                });
                await loadIntegrations();
            }
        } catch (error) {
            console.error("Error saving integration:", error);
        }
    };

    const handleAddCustomIntegration = async (data: any) => {
        try {
            await api.saveIntegrationConfig({
                id: data.name.toLowerCase().replace(/\s+/g, '-'),
                name: data.name,
                category: data.category,
                description: data.description,
                isEnabled: true,
                config: {
                    apiUrl: data.apiUrl,
                    apiKey: data.apiKey
                }
            });
            await loadIntegrations();
        } catch (error) {
            console.error("Error adding custom integration:", error);
        }
    };

    const filteredIntegrations = integrations.filter(integ => {
        const matchesSearch = integ.name.toLowerCase().includes(searchQuery.toLowerCase()) || 
                             integ.description.toLowerCase().includes(searchQuery.toLowerCase());
        const matchesCategory = filter === 'all' || integ.category.toLowerCase() === filter.toLowerCase();
        return matchesSearch && matchesCategory;
    });

    const getProviderIcon = (id: string, category: string) => {
        const lowerId = id.toLowerCase();
        const lowerCat = category.toLowerCase();

        if (lowerId.includes('aws')) return <Cloud className="w-8 h-8 text-amber-500" />;
        if (lowerId.includes('azure')) return <Cloud className="w-8 h-8 text-blue-500" />;
        if (lowerId.includes('gcp')) return <Cloud className="w-8 h-8 text-emerald-500" />;
        if (lowerId.includes('okta')) return <Key className="w-8 h-8 text-indigo-500" />;
        if (lowerId.includes('slack')) return <Zap className="w-8 h-8 text-orange-500" />;
        if (lowerId.includes('teams')) return <Zap className="w-8 h-8 text-blue-600" />;
        if (lowerId.includes('jira')) return <Shield className="w-8 h-8 text-blue-400" />;
        
        if (lowerCat.includes('logging')) return <Database className="w-8 h-8 text-slate-500" />;
        if (lowerCat.includes('security')) return <Shield className="w-8 h-8 text-red-500" />;
        
        return <Settings className="w-8 h-8 text-slate-400" />;
    };

    const getStatusColor = (status: string) => {
        switch (status) {
            case 'connected': return 'text-emerald-500 bg-emerald-50 dark:bg-emerald-900/20';
            case 'error': return 'text-red-500 bg-red-50 dark:bg-red-900/20';
            default: return 'text-slate-500 bg-slate-50 dark:bg-slate-900/20';
        }
    };

    return (
        <div className="p-8 bg-slate-50 dark:bg-slate-900 min-h-screen">
            <div className="max-w-6xl mx-auto space-y-8">
                <div className="flex justify-between items-center">
                    <div>
                        <h1 className="text-3xl font-bold text-slate-900 dark:text-white">Integrations Hub</h1>
                        <p className="text-slate-500 mt-1">Manage and monitor all external telemetry and log sources</p>
                    </div>
                    <button 
                        onClick={() => setIsAddModalOpen(true)}
                        className="px-6 py-3 bg-indigo-600 text-white rounded-xl font-bold flex items-center hover:bg-indigo-700 transition-all shadow-lg shadow-indigo-600/20"
                    >
                        <Plus className="w-5 h-5 mr-2" />
                        Add Integration
                    </button>
                </div>

                {/* Stats Overview */}
                <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                    <div className="bg-white dark:bg-slate-800 p-6 rounded-2xl border border-slate-100 dark:border-slate-800 shadow-sm flex items-center space-x-4">
                        <div className="p-3 bg-emerald-100 dark:bg-emerald-900/30 rounded-xl">
                            <Zap className="w-6 h-6 text-emerald-600 dark:text-emerald-400" />
                        </div>
                        <div>
                            <p className="text-xs text-slate-400 font-bold uppercase">Total Events (24h)</p>
                            <p className="text-2xl font-bold text-slate-900 dark:text-white">1.24M</p>
                        </div>
                    </div>
                    <div className="bg-white dark:bg-slate-800 p-6 rounded-2xl border border-slate-100 dark:border-slate-800 shadow-sm flex items-center space-x-4">
                        <div className="p-3 bg-blue-100 dark:bg-blue-900/30 rounded-xl">
                            <Activity className="w-6 h-6 text-blue-600 dark:text-blue-400" />
                        </div>
                        <div>
                            <p className="text-xs text-slate-400 font-bold uppercase">Active Sources</p>
                            <p className="text-2xl font-bold text-slate-900 dark:text-white">14 / 16</p>
                        </div>
                    </div>
                    <div className="bg-white dark:bg-slate-800 p-6 rounded-2xl border border-slate-100 dark:border-slate-800 shadow-sm flex items-center space-x-4">
                        <div className="p-3 bg-red-100 dark:bg-red-900/30 rounded-xl">
                            <Shield className="w-6 h-6 text-red-600 dark:text-red-400" />
                        </div>
                        <div>
                            <p className="text-xs text-slate-400 font-bold uppercase">Failed Syncs</p>
                            <p className="text-2xl font-bold text-slate-900 dark:text-white">2</p>
                        </div>
                    </div>
                </div>

                <div className="flex justify-between items-center bg-white dark:bg-slate-800 p-4 rounded-xl shadow-sm border border-slate-100 dark:border-slate-800">
                    <div className="flex space-x-2">
                        {['all', 'Collaboration', 'Ticketing', 'SIEM', 'Observability', 'Security'].map(cat => (
                            <button 
                                key={cat}
                                onClick={() => setFilter(cat)}
                                className={`px-4 py-2 rounded-lg text-sm font-bold capitalize transition-all ${filter === cat ? 'bg-indigo-50 dark:bg-indigo-900/20 text-indigo-600 dark:text-indigo-400' : 'text-slate-400 hover:text-slate-600'}`}
                            >
                                {cat}
                            </button>
                        ))}
                    </div>
                    <div className="flex items-center space-x-4">
                        <div className="relative">
                            <Search className="absolute left-3 top-2.5 w-4 h-4 text-slate-400" />
                            <input 
                                type="text" 
                                placeholder="Search..." 
                                value={searchQuery}
                                onChange={(e) => setSearchQuery(e.target.value)}
                                className="pl-10 pr-4 py-2 bg-slate-50 dark:bg-slate-900 border-none rounded-lg text-sm focus:ring-2 focus:ring-indigo-500 w-64"
                            />
                        </div>
                        <button className="p-2 bg-slate-50 dark:bg-slate-900 rounded-lg text-slate-400 hover:text-slate-600 transition-colors">
                            <Filter className="w-5 h-5" />
                        </button>
                    </div>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                    {filteredIntegrations.map(integ => (
                        <div key={integ.id} className="bg-white dark:bg-slate-800 rounded-2xl p-6 border border-slate-100 dark:border-slate-800 shadow-sm hover:shadow-md transition-all group relative overflow-hidden">
                            <div className="flex justify-between items-start mb-6">
                                <div className="p-4 bg-slate-50 dark:bg-slate-900/50 rounded-2xl group-hover:bg-white transition-colors border border-transparent group-hover:border-slate-100 dark:group-hover:border-slate-700">
                                    {getProviderIcon(integ.id, integ.category)}
                                </div>
                                <span className={`px-3 py-1 rounded-full text-[10px] font-bold uppercase tracking-wider ${integ.isEnabled ? 'text-emerald-500 bg-emerald-50 dark:bg-emerald-900/20' : 'text-slate-400 bg-slate-50 dark:bg-slate-900/20'}`}>
                                    {integ.isEnabled ? 'Active' : 'Disabled'}
                                </span>
                            </div>

                            <div className="space-y-4">
                                <div>
                                    <h3 className="text-lg font-bold text-slate-900 dark:text-white flex items-center">
                                        {integ.name}
                                        <ExternalLink className="w-4 h-4 ml-2 opacity-0 group-hover:opacity-30 transition-opacity" />
                                    </h3>
                                    <p className="text-sm text-slate-500 line-clamp-2 mt-1">{integ.description}</p>
                                </div>

                                <div className="grid grid-cols-2 gap-4 pt-4 border-t border-slate-50 dark:border-slate-700">
                                    <div>
                                        <p className="text-[10px] text-slate-400 font-bold uppercase mb-1">Category</p>
                                        <p className="text-xs font-bold text-slate-900 dark:text-slate-300">
                                            {integ.category}
                                        </p>
                                    </div>
                                    <div>
                                        <p className="text-[10px] text-slate-400 font-bold uppercase mb-1">Status</p>
                                        <p className="text-xs font-bold text-slate-900 dark:text-slate-300">
                                            {integ.isEnabled ? 'Operational' : 'Idle'}
                                        </p>
                                    </div>
                                </div>
                            </div>

                            <div className="mt-6 flex space-x-2">
                                <button 
                                    onClick={() => {
                                        setSelectedIntegration(integ);
                                        setIsConfigModalOpen(true);
                                    }}
                                    className="flex-1 py-2 bg-slate-50 dark:bg-slate-900/50 text-slate-600 dark:text-slate-400 rounded-lg text-xs font-bold hover:bg-slate-100 transition-colors"
                                >
                                    Configure
                                </button>
                                <button className="flex-1 py-2 bg-indigo-600/10 text-indigo-600 rounded-lg text-xs font-bold hover:bg-indigo-600 hover:text-white transition-all flex items-center justify-center">
                                    <RefreshCw className="w-3 h-3 mr-2" />
                                    Sync
                                </button>
                            </div>
                        </div>
                    ))}
                    
                    {/* Add Placeholder */}
                    <div 
                        onClick={() => setIsAddModalOpen(true)}
                        className="bg-slate-50 dark:bg-slate-900/30 rounded-2xl border-2 border-dashed border-slate-200 dark:border-slate-800 p-6 flex flex-col items-center justify-center text-slate-400 hover:border-indigo-300 hover:bg-indigo-50/10 transition-all cursor-pointer group"
                    >
                        <div className="w-12 h-12 rounded-full bg-white dark:bg-slate-800 flex items-center justify-center mb-4 shadow-sm group-hover:scale-110 transition-transform">
                            <Plus className="w-6 h-6 text-slate-300 group-hover:text-indigo-500" />
                        </div>
                        <p className="font-bold text-sm">Request New Source</p>
                        <p className="text-xs mt-1">Connect a custom API or webhook</p>
                    </div>
                </div>

                {/* Modals */}
                <AddIntegrationModal 
                    isOpen={isAddModalOpen}
                    onClose={() => setIsAddModalOpen(false)}
                    onSave={handleAddCustomIntegration}
                />

                <IntegrationSettingsModal 
                    isOpen={isConfigModalOpen}
                    onClose={() => setIsConfigModalOpen(false)}
                    integration={selectedIntegration}
                    onSave={handleSaveIntegration}
                />
            </div>
        </div>
    );
};

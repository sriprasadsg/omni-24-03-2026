
import React, { useState, useEffect, useMemo, useContext } from 'react';
import { Integration, AlertRule, Role, ApiKey, User, Tenant, DatabaseSettings as DatabaseSettingsType, LlmSettings as LlmSettingsType, DataSource, DataSourceStatus, Permission, NewUserPayload, VoiceBotSettings } from '../types';
import { SettingsIcon, PlusCircleIcon, PencilIcon, TrashIcon, CogIcon, UsersIcon as Users2Icon, ShieldLockIcon, KeyIcon, AlertTriangleIcon, DatabaseIcon, BrainCircuitIcon, CheckIcon, XCircleIcon, DollarSignIcon, SlackIcon, PagerDutyIcon, JiraIcon, PaintbrushIcon, MailIcon, BuildingIcon, CalendarIcon, SearchIcon, FilterIcon } from './icons';
import { useUser } from '../contexts/UserContext';
import { AlertRuleModal } from './AlertRuleModal';
import { IntegrationSettingsModal } from './IntegrationSettingsModal';
import { RoleEditorModal } from './RoleEditorModal';
import { GenerateApiKeyNameModal } from './GenerateApiKeyNameModal';
import { ShowNewKeyModal } from './ShowNewKeyModal';
import { AddUserModal } from './AddUserModal';
import { AddNewTenantModal } from './AddNewTenantModal';
import { EditUserModal } from './EditUserModal';
import { DatabaseSettings } from './DatabaseSettings';
import { LlmSettings } from './LlmSettings';
import { DataSourceModal } from './DataSourceModal';
import { IntegrationsMarketplace } from './IntegrationsMarketplace';
import { TenantFeatureManagement } from './TenantFeatureManagement';
import { ThemeContext } from '../contexts/ThemeContext';
import { EmailSettings } from './EmailSettings';
import MaintenanceWindowConfig from './MaintenanceWindowConfig';
import { VoiceBotSettingsPanel } from './VoiceBotSettingsPanel';
import { SecuritySettings } from './SecuritySettings';
import * as apiService from '../services/apiService';

interface SettingsDashboardProps {
    integrations: Integration[];
    alertRules: AlertRule[];
    roles: Role[];
    users: User[];
    apiKeys: ApiKey[];
    dataSources: DataSource[];
    newlyGeneratedKey: { name: string; key: string; } | null;
    databaseSettings: DatabaseSettingsType | null;
    llmSettings: LlmSettingsType | null;
    onToggleIntegration: (id: Integration['id']) => void;
    onSaveAlertRule: (rule: AlertRule) => void;
    onDeleteAlertRule: (id: string) => void;
    onSaveIntegration: (integration: Integration) => void;
    onSaveRole: (role: Role) => void;
    onDeleteRole: (roleId: string) => void;
    onGenerateApiKey: (name: string) => void;
    onRevokeApiKey: (keyId: string) => void;
    onAcknowledgeNewKey: () => void;
    onUpdateUser: (userId: string, updates: any) => void;
    onDeleteUser: (userId: string) => void;
    onResetPassword: (userId: string, userName: string) => void;
    tenants: Tenant[];
    onAddNewUser: (user: NewUserPayload) => Promise<void>;
    onSaveInfrastructure: (updates: { db?: DatabaseSettingsType, llm?: LlmSettingsType }) => void;
    onSaveDataSource: (source: DataSource) => Promise<void>;
    onDeleteDataSource: (sourceId: string) => void;
    onTestDataSource: (sourceId: string) => Promise<void>;
    onSaveTenantFeatures: (tenantId: string, updatedFeatures: Permission[]) => void;
    onSaveTenantVoiceBotSettings?: (settings: VoiceBotSettings) => Promise<void>;
}

type SettingsView = 'users' | 'roles' | 'apiKeys' | 'integrations' | 'alerts' | 'infrastructure' | 'dataSources' | 'subscription' | 'appearance' | 'email' | 'maintenance' | 'voiceBot' | 'security';

const dataSourceStatusInfo: Record<DataSourceStatus, { icon: React.ReactNode; classes: string }> = {
    Connected: { icon: <CheckIcon size={14} />, classes: 'bg-green-100 text-green-800 dark:bg-green-900/50 dark:text-green-300' },
    Error: { icon: <AlertTriangleIcon size={14} />, classes: 'bg-red-100 text-red-800 dark:bg-red-900/50 dark:text-red-300' },
    Pending: { icon: <CogIcon size={14} className="animate-spin" />, classes: 'bg-amber-100 text-amber-800 dark:bg-amber-900/50 dark:text-amber-300' },
};

export const SettingsDashboard: React.FC<SettingsDashboardProps> = (props) => {
    const {
        integrations, alertRules, roles, users, apiKeys, dataSources, newlyGeneratedKey, databaseSettings, llmSettings,
        onToggleIntegration, onSaveAlertRule, onDeleteAlertRule, onSaveIntegration,
        onSaveRole, onDeleteRole, onGenerateApiKey, onRevokeApiKey, onAcknowledgeNewKey,
        onUpdateUser, onDeleteUser, onResetPassword, tenants, onAddNewUser, onSaveInfrastructure,
        onSaveDataSource, onDeleteDataSource, onTestDataSource, onSaveTenantFeatures,
        onSaveTenantVoiceBotSettings
    } = props;

    const { currentUser, hasPermission } = useUser();
    const { theme, toggleTheme } = useContext(ThemeContext);

    // Super Admin should have access to all settings tabs, bypass permission checks
    const isSuperAdmin = currentUser?.role === 'Super Admin';
    const canManageSettings = isSuperAdmin || hasPermission('manage:settings');
    const canManageRBAC = isSuperAdmin || hasPermission('manage:rbac');
    const canManageApiKeys = isSuperAdmin || hasPermission('manage:api_keys');
    const isTenantAdminView = !isSuperAdmin;

    const [activeView, setActiveView] = useState<SettingsView>('users');
    const [isAlertModalOpen, setIsAlertModalOpen] = useState(false);
    const [editingRule, setEditingRule] = useState<AlertRule | null>(null);
    const [configuringIntegration, setConfiguringIntegration] = useState<Integration | null>(null);
    const [isRoleModalOpen, setIsRoleModalOpen] = useState(false);
    const [editingRole, setEditingRole] = useState<Role | null>(null);
    const [isGenerateKeyModalOpen, setIsGenerateKeyModalOpen] = useState(false);
    const [isShowNewKeyModalOpen, setIsShowNewKeyModalOpen] = useState(false);
    const [isAddUserModalOpen, setIsAddUserModalOpen] = useState(false);
    const [editingUser, setEditingUser] = useState<User | null>(null);
    const [isDbSettingsModalOpen, setIsDbSettingsModalOpen] = useState(false);
    const [isLlmSettingsModalOpen, setIsLlmSettingsModalOpen] = useState(false);
    const [isDataSourceModalOpen, setIsDataSourceModalOpen] = useState(false);
    const [editingDataSource, setEditingDataSource] = useState<DataSource | null>(null);
    const [testingState, setTestingState] = useState<Record<string, { status: 'testing' | 'error', message?: string }>>({});
    const [localIntegrations, setLocalIntegrations] = useState<Integration[]>(integrations);
    const [searchQuery, setSearchQuery] = useState('');

    useEffect(() => {
        const loadConfigs = async () => {
            try {
                const configs = await apiService.fetchIntegrationConfigs();
                if (configs && configs.length > 0) {
                    // Merge with default integrations from props
                    setLocalIntegrations(prev => {
                        const merged = [...prev];
                        configs.forEach(config => {
                            const index = merged.findIndex(i => i.id === config.id);
                            if (index > -1) {
                                merged[index] = { ...merged[index], ...config };
                            }
                        });
                        return merged;
                    });
                }
            } catch (error) {
                console.error('Failed to load integration configs:', error);
            }
        };
        loadConfigs();
    }, []);


    useEffect(() => {
        if (newlyGeneratedKey) {
            setIsShowNewKeyModalOpen(true);
        }
    }, [newlyGeneratedKey]);

    useEffect(() => {
        // Default to appearance for Super Admin to show all tabs, or first available tab for others
        if (isSuperAdmin) {
            setActiveView('appearance');
        } else if (canManageSettings) {
            setActiveView('appearance');
        } else if (canManageRBAC) {
            setActiveView('users');
        } else if (canManageApiKeys) {
            setActiveView('apiKeys');
        }
    }, [canManageRBAC, canManageApiKeys, canManageSettings, isSuperAdmin]);

    const activeTenant = useMemo(() => {
        if (!currentUser) return null;
        return tenants.find(t => t.id === currentUser.tenantId);
    }, [tenants, currentUser]);


    const handleOpenAlertModal = (rule: AlertRule | null) => {
        setEditingRule(rule);
        setIsAlertModalOpen(true);
    };

    const handleSaveAlert = (rule: AlertRule) => {
        onSaveAlertRule(rule);
        setIsAlertModalOpen(false);
    };

    const handleSaveIntegrationConfig = async (updatedIntegration: Integration) => {
        try {
            await apiService.saveIntegrationConfig(updatedIntegration);
            setLocalIntegrations(prev => prev.map(i => i.id === updatedIntegration.id ? updatedIntegration : i));
            onSaveIntegration(updatedIntegration);
        } catch (error) {
            console.error('Failed to save integration config:', error);
        }
        setConfiguringIntegration(null);
    };

    const handleToggleIntegration = async (id: Integration['id']) => {
        const integration = localIntegrations.find(i => i.id === id);
        if (integration) {
            const updated = { ...integration, isEnabled: !integration.isEnabled };
            try {
                await apiService.saveIntegrationConfig(updated);
                setLocalIntegrations(prev => prev.map(i => i.id === id ? updated : i));
                onToggleIntegration(id);
            } catch (error) {
                console.error('Failed to toggle integration:', error);
            }
        }
    };

    const handleOpenRoleModal = (role: Role | null) => {
        setEditingRole(role);
        setIsRoleModalOpen(true);
    };

    const handleSaveRole = (role: Role) => {
        onSaveRole(role);
        setIsRoleModalOpen(false);
    };

    const handleGenerateKey = (name: string) => {
        onGenerateApiKey(name);
        setIsGenerateKeyModalOpen(false);
    };

    const handleUpdateUser = (userId: string, updates: { role?: string, status?: 'Active' | 'Disabled' }) => {
        onUpdateUser(userId, updates);
        setEditingUser(null);
    };

    const handleOpenDataSourceModal = (source: DataSource | null) => {
        setEditingDataSource(source);
        setIsDataSourceModalOpen(true);
    };

    const handleSaveDataSource = async (source: DataSource) => {
        await onSaveDataSource(source);
        setIsDataSourceModalOpen(false);
    };

    const handleTestDataSource = async (sourceId: string) => {
        setTestingState(prev => ({ ...prev, [sourceId]: { status: 'testing' } }));
        try {
            await onTestDataSource(sourceId);
            // Success is handled by re-render with new status prop
        } catch (error) {
            setTestingState(prev => ({ ...prev, [sourceId]: { status: 'error', message: error instanceof Error ? error.message : 'Unknown error' } }));
        } finally {
            setTimeout(() => {
                setTestingState(prev => {
                    const newState = { ...prev };
                    delete newState[sourceId];
                    return newState;
                });
            }, 5000); // Clear status after 5 seconds
        }
    };

    const availableRolesForAssignment = useMemo(() => {
        if (currentUser?.role === 'Super Admin') return roles;
        return roles.filter(r => r.name !== 'Super Admin');
    }, [roles, currentUser]);

    const filteredUsers = useMemo(() => {
        if (!searchQuery.trim()) return users;
        const query = searchQuery.toLowerCase();
        return users.filter(user => {
            return (
                user.name.toLowerCase().includes(query) ||
                user.email.toLowerCase().includes(query) ||
                user.role.toLowerCase().includes(query)
            );
        });
    }, [users, searchQuery]);


    return (
        <div className="container mx-auto">
            <h2 className="text-2xl font-semibold text-gray-800 dark:text-white mb-6">Settings & Configuration</h2>

            <div className="bg-white dark:bg-gray-800 rounded-lg shadow-md">
                <div className="border-b border-gray-200 dark:border-gray-700">
                    <nav className="-mb-px flex space-x-6 px-4 overflow-x-auto" aria-label="Tabs">
                        {canManageSettings && (
                            <button onClick={() => setActiveView('appearance')} className={`flex items-center whitespace-nowrap py-4 px-1 border-b-2 font-medium text-sm transition-colors ${activeView === 'appearance' ? 'border-primary-500 text-primary-600 dark:text-primary-400' : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300 dark:text-gray-400 dark:hover:text-gray-200 dark:hover:border-gray-600'}`}>
                                <PaintbrushIcon size={18} className="mr-2" /> Appearance
                            </button>
                        )}
                        {canManageRBAC && (
                            <>
                                <button onClick={() => setActiveView('users')} className={`flex items-center whitespace-nowrap py-4 px-1 border-b-2 font-medium text-sm transition-colors ${activeView === 'users' ? 'border-primary-500 text-primary-600 dark:text-primary-400' : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300 dark:text-gray-400 dark:hover:text-gray-200 dark:hover:border-gray-600'}`}>
                                    <Users2Icon size={18} className="mr-2" /> User Management
                                </button>
                                <button onClick={() => setActiveView('roles')} className={`flex items-center whitespace-nowrap py-4 px-1 border-b-2 font-medium text-sm transition-colors ${activeView === 'roles' ? 'border-primary-500 text-primary-600 dark:text-primary-400' : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300 dark:text-gray-400 dark:hover:text-gray-200 dark:hover:border-gray-600'}`}>
                                    <ShieldLockIcon size={18} className="mr-2" /> Roles & Permissions
                                </button>
                            </>
                        )}
                        {canManageApiKeys && (
                            <button onClick={() => setActiveView('apiKeys')} className={`flex items-center whitespace-nowrap py-4 px-1 border-b-2 font-medium text-sm transition-colors ${activeView === 'apiKeys' ? 'border-primary-500 text-primary-600 dark:text-primary-400' : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300 dark:text-gray-400 dark:hover:text-gray-200 dark:hover:border-gray-600'}`}>
                                <KeyIcon size={18} className="mr-2" /> API Keys
                            </button>
                        )}
                        <button onClick={() => setActiveView('security')} className={`flex items-center whitespace-nowrap py-4 px-1 border-b-2 font-medium text-sm transition-colors ${activeView === 'security' ? 'border-primary-500 text-primary-600 dark:text-primary-400' : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300 dark:text-gray-400 dark:hover:text-gray-200 dark:hover:border-gray-600'}`}>
                            <ShieldLockIcon size={18} className="mr-2" /> Security
                        </button>
                        {canManageSettings && (
                            <>
                                <button onClick={() => setActiveView('email')} className={`flex items-center whitespace-nowrap py-4 px-1 border-b-2 font-medium text-sm transition-colors ${activeView === 'email' ? 'border-primary-500 text-primary-600 dark:text-primary-400' : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300 dark:text-gray-400 dark:hover:text-gray-200 dark:hover:border-gray-600'}`}>
                                    <MailIcon size={18} className="mr-2" /> Email Notifications
                                </button>
                                <button onClick={() => setActiveView('integrations')} className={`flex items-center whitespace-nowrap py-4 px-1 border-b-2 font-medium text-sm transition-colors ${activeView === 'integrations' ? 'border-primary-500 text-primary-600 dark:text-primary-400' : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300 dark:text-gray-400 dark:hover:text-gray-200 dark:hover:border-gray-600'}`}>
                                    <CogIcon size={18} className="mr-2" /> Integrations
                                </button>
                                <button onClick={() => setActiveView('dataSources')} className={`flex items-center whitespace-nowrap py-4 px-1 border-b-2 font-medium text-sm transition-colors ${activeView === 'dataSources' ? 'border-primary-500 text-primary-600 dark:text-primary-400' : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300 dark:text-gray-400 dark:hover:text-gray-200 dark:hover:border-gray-600'}`}>
                                    <DatabaseIcon size={18} className="mr-2" /> Data Sources
                                </button>
                                <button onClick={() => setActiveView('alerts')} className={`flex items-center whitespace-nowrap py-4 px-1 border-b-2 font-medium text-sm transition-colors ${activeView === 'alerts' ? 'border-primary-500 text-primary-600 dark:text-primary-400' : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300 dark:text-gray-400 dark:hover:text-gray-200 dark:hover:border-gray-600'}`}>
                                    <AlertTriangleIcon size={18} className="mr-2" /> Alert Rules
                                </button>
                                <button onClick={() => setActiveView('maintenance')} className={`flex items-center whitespace-nowrap py-4 px-1 border-b-2 font-medium text-sm transition-colors ${activeView === 'maintenance' ? 'border-primary-500 text-primary-600 dark:text-primary-400' : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300 dark:text-gray-400 dark:hover:text-gray-200 dark:hover:border-gray-600'}`}>
                                    <CalendarIcon size={18} className="mr-2" /> Maintenance
                                </button>
                                {isTenantAdminView && (
                                    <button onClick={() => setActiveView('voiceBot')} className={`flex items-center whitespace-nowrap py-4 px-1 border-b-2 font-medium text-sm transition-colors ${activeView === 'voiceBot' ? 'border-primary-500 text-primary-600 dark:text-primary-400' : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300 dark:text-gray-400 dark:hover:text-gray-200 dark:hover:border-gray-600'}`}>
                                        <BrainCircuitIcon size={18} className="mr-2" /> Voice Bot
                                    </button>
                                )}
                            </>
                        )}
                        {isSuperAdmin && (
                            <button onClick={() => setActiveView('infrastructure')} className={`flex items-center whitespace-nowrap py-4 px-1 border-b-2 font-medium text-sm transition-colors ${activeView === 'infrastructure' ? 'border-primary-500 text-primary-600 dark:text-primary-400' : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300 dark:text-gray-400 dark:hover:text-gray-200 dark:hover:border-gray-600'}`}>
                                <DatabaseIcon size={18} className="mr-2" /> Infrastructure
                            </button>
                        )}
                    </nav>
                </div>

                <div className="p-4 md:p-6">
                    {activeView === 'appearance' && canManageSettings && (
                        <div>
                            <h3 className="text-lg font-semibold">Appearance</h3>
                            <p className="text-sm text-gray-500 dark:text-gray-400 mt-1 mb-4">Customize the look and feel of the platform.</p>
                            <div className="bg-gray-50 dark:bg-gray-700/50 rounded-lg border border-gray-200 dark:border-gray-600 p-4 flex items-center justify-between">
                                <div>
                                    <p className="font-semibold text-gray-800 dark:text-gray-200">Dark Mode</p>
                                    <p className="text-xs text-gray-500 dark:text-gray-400">Toggle between light and dark themes.</p>
                                </div>
                                <button
                                    type="button"
                                    className={`${theme === 'dark' ? 'bg-primary-600' : 'bg-gray-200 dark:bg-gray-600'} relative inline-flex h-6 w-11 flex-shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none focus:ring-2 focus:ring-primary-500 focus:ring-offset-2 dark:ring-offset-gray-800`}
                                    role="switch"
                                    aria-checked={theme === 'dark'}
                                    onClick={toggleTheme}
                                >
                                    <span
                                        aria-hidden="true"
                                        className={`${theme === 'dark' ? 'translate-x-5' : 'translate-x-0'} pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow ring-0 transition duration-200 ease-in-out`}
                                    />
                                </button>
                            </div>
                        </div>
                    )}
                    {activeView === 'email' && canManageSettings && (
                        <EmailSettings />
                    )}
                    {activeView === 'security' && (
                        <SecuritySettings />
                    )}
                    {activeView === 'integrations' && canManageSettings && (
                        <IntegrationsMarketplace
                            integrations={localIntegrations}
                            onConfigure={setConfiguringIntegration}
                            onToggle={handleToggleIntegration}
                        />
                    )}

                    {activeView === 'dataSources' && canManageSettings && (
                        <div>
                            <div className="flex justify-between items-center mb-4">
                                <h3 className="text-lg font-semibold">Data Sources</h3>
                                <button onClick={() => handleOpenDataSourceModal(null)} className="flex items-center px-3 py-1.5 text-xs font-medium text-white bg-primary-600 rounded-lg hover:bg-primary-700">
                                    <PlusCircleIcon size={16} className="mr-1.5" />
                                    New Data Source
                                </button>
                            </div>
                            <div className="overflow-x-auto">
                                <table className="w-full text-sm text-left text-gray-500 dark:text-gray-400">
                                    <thead className="text-xs text-gray-700 uppercase bg-gray-50 dark:bg-gray-700 dark:text-gray-400">
                                        <tr>
                                            <th scope="col" className="px-4 py-3">Name</th>
                                            <th scope="col" className="px-4 py-3">Type</th>
                                            <th scope="col" className="px-4 py-3">Status</th>
                                            <th scope="col" className="px-4 py-3">Last Tested</th>
                                            <th scope="col" className="px-4 py-3">Actions</th>
                                        </tr>
                                    </thead>
                                    <tbody>
                                        {dataSources.map(source => (
                                            <tr key={source.id} className="border-b dark:border-gray-700 hover:bg-gray-50 dark:hover:bg-gray-600/50">
                                                <td className="px-4 py-3 font-medium text-gray-900 dark:text-white">{source.name}</td>
                                                <td className="px-4 py-3">{source.type}</td>
                                                <td className="px-4 py-3">
                                                    <span className={`inline-flex items-center px-2 py-1 text-xs font-medium rounded-full ${dataSourceStatusInfo[source.status].classes}`}>
                                                        {dataSourceStatusInfo[source.status].icon}
                                                        <span className="ml-1.5">{source.status}</span>
                                                    </span>
                                                </td>
                                                <td className="px-4 py-3">{source.lastTested ? new Date(source.lastTested).toLocaleString() : 'Never'}</td>
                                                <td className="px-4 py-3">
                                                    <div className="flex items-center space-x-2">
                                                        <button
                                                            onClick={() => handleTestDataSource(source.id)}
                                                            disabled={testingState[source.id]?.status === 'testing'}
                                                            className="px-2.5 py-1 text-xs font-medium text-primary-700 bg-primary-100 rounded-md hover:bg-primary-200 dark:bg-primary-900/50 dark:text-primary-300 dark:hover:bg-primary-900 disabled:opacity-50 disabled:cursor-wait"
                                                        >
                                                            {testingState[source.id]?.status === 'testing' ? 'Testing...' : 'Test'}
                                                        </button>
                                                        <button onClick={() => handleOpenDataSourceModal(source)} className="p-1.5 text-gray-500 hover:text-primary-600"><PencilIcon size={14} /></button>
                                                        <button onClick={() => onDeleteDataSource(source.id)} className="p-1.5 text-gray-500 hover:text-red-600"><TrashIcon size={14} /></button>
                                                    </div>
                                                </td>
                                            </tr>
                                        ))}
                                    </tbody>
                                </table>
                            </div>
                        </div>
                    )}

                    {activeView === 'alerts' && canManageSettings && (
                        <div>
                            <div className="flex justify-between items-center mb-4">
                                <h3 className="text-lg font-semibold">Alerting Rules</h3>
                                {canManageSettings && (
                                    <button onClick={() => handleOpenAlertModal(null)} className="flex items-center px-3 py-1.5 text-xs font-medium text-white bg-primary-600 rounded-lg hover:bg-primary-700">
                                        <PlusCircleIcon size={16} className="mr-1.5" />
                                        New Alert Rule
                                    </button>
                                )}
                            </div>
                            <div className="overflow-x-auto">
                                <table className="w-full text-sm text-left text-gray-500 dark:text-gray-400">
                                    <thead className="text-xs text-gray-700 uppercase bg-gray-50 dark:bg-gray-700 dark:text-gray-400">
                                        <tr>
                                            <th scope="col" className="px-4 py-3">Rule Name</th>
                                            <th scope="col" className="px-4 py-3">Condition</th>
                                            <th scope="col" className="px-4 py-3">Severity</th>
                                            <th scope="col" className="px-4 py-3">Status</th>
                                            <th scope="col" className="px-4 py-3">Actions</th>
                                        </tr>
                                    </thead>
                                    <tbody>
                                        {alertRules.map(rule => (
                                            <tr key={rule.id} className="border-b dark:border-gray-700 hover:bg-gray-50 dark:hover:bg-gray-600/50">
                                                <td className="px-4 py-3 font-medium text-gray-900 dark:text-white">{rule.name}</td>
                                                <td className="px-4 py-3 font-mono text-xs">{`${rule.metric} ${rule.condition} ${rule.threshold}${rule.metric === 'cpu' || rule.metric === 'disk' ? '%' : ''} for ${rule.duration}m`}</td>
                                                <td className="px-4 py-3">{rule.severity}</td>
                                                <td className="px-4 py-3">
                                                    <span className={`px-2 py-1 text-xs font-medium rounded-full ${rule.isEnabled ? 'bg-green-100 text-green-800 dark:bg-green-900/50 dark:text-green-300' : 'bg-gray-200 text-gray-800 dark:bg-gray-700 dark:text-gray-300'}`}>
                                                        {rule.isEnabled ? 'Enabled' : 'Disabled'}
                                                    </span>
                                                </td>
                                                <td className="px-4 py-3">
                                                    {canManageSettings && (
                                                        <div className="flex items-center space-x-2">
                                                            <button onClick={() => handleOpenAlertModal(rule)} className="p-1.5 text-gray-500 hover:text-primary-600"><PencilIcon size={14} /></button>
                                                            <button onClick={() => onDeleteAlertRule(rule.id)} className="p-1.5 text-gray-500 hover:text-red-600"><TrashIcon size={14} /></button>
                                                        </div>
                                                    )}
                                                </td>
                                            </tr>
                                        ))}
                                    </tbody>
                                </table>
                            </div>
                        </div>
                    )}

                    {activeView === 'maintenance' && canManageSettings && (
                        <MaintenanceWindowConfig />
                    )}

                    {activeView === 'roles' && canManageRBAC && (
                        <div>
                            <div className="flex justify-between items-center mb-4">
                                <h3 className="text-lg font-semibold">Roles & Permissions</h3>
                                <button onClick={() => handleOpenRoleModal(null)} className="flex items-center px-3 py-1.5 text-xs font-medium text-white bg-primary-600 rounded-lg hover:bg-primary-700">
                                    <PlusCircleIcon size={16} className="mr-1.5" />
                                    New Custom Role
                                </button>
                            </div>
                            <div className="overflow-x-auto">
                                <table className="w-full text-sm text-left text-gray-500 dark:text-gray-400">
                                    <thead className="text-xs text-gray-700 uppercase bg-gray-50 dark:bg-gray-700 dark:text-gray-400">
                                        <tr>
                                            <th scope="col" className="px-4 py-3">Role Name</th>
                                            <th scope="col" className="px-4 py-3">Description</th>
                                            <th scope="col" className="px-4 py-3">Actions</th>
                                        </tr>
                                    </thead>
                                    <tbody>
                                        {roles.map(role => (
                                            <tr key={role.id} className="border-b dark:border-gray-700 hover:bg-gray-50 dark:hover:bg-gray-600/50">
                                                <td className="px-4 py-3 font-medium text-gray-900 dark:text-white">
                                                    <div className="flex items-center">
                                                        <span>{role.name}</span>
                                                        <span className="ml-2 px-2 py-0.5 text-xs font-semibold rounded-full bg-primary-100 text-primary-800 dark:bg-primary-900/50 dark:text-primary-300">
                                                            {role.permissions.length}
                                                        </span>
                                                    </div>
                                                </td>
                                                <td className="px-4 py-3 text-xs max-w-sm">{role.description}</td>
                                                <td className="px-4 py-3">
                                                    <div className="flex items-center space-x-2">
                                                        <button
                                                            onClick={() => handleOpenRoleModal(role)}
                                                            className="p-1.5 text-gray-500 hover:text-primary-600 disabled:text-gray-400 disabled:dark:text-gray-500 disabled:cursor-not-allowed"
                                                            disabled={!role.isEditable}
                                                            title={role.isEditable ? "Edit role" : "Built-in roles cannot be edited."}
                                                        >
                                                            <PencilIcon size={14} />
                                                        </button>
                                                        {role.isEditable ? (
                                                            <button onClick={() => onDeleteRole(role.id)} className="p-1.5 text-gray-500 hover:text-red-600" title="Delete role">
                                                                <TrashIcon size={14} />
                                                            </button>
                                                        ) : (
                                                            <span title="This built-in role cannot be deleted.">
                                                                <ShieldLockIcon size={14} className="p-0.5 text-gray-400 dark:text-gray-500" />
                                                            </span>
                                                        )}
                                                    </div>
                                                </td>
                                            </tr>
                                        ))}
                                    </tbody>
                                </table>
                            </div>
                        </div>
                    )}

                    {activeView === 'users' && canManageRBAC && (
                        <div>
                            <div className="flex flex-col md:flex-row justify-between items-start md:items-center mb-6 space-y-4 md:space-y-0">
                                <div>
                                    <h3 className="text-lg font-semibold text-gray-800 dark:text-white">User Management</h3>
                                    <p className="text-sm text-gray-500 dark:text-gray-400">Manage user accounts, roles, and platform access across all tenants.</p>
                                </div>
                                <div className="flex items-center space-x-3 w-full md:w-auto">
                                    <div className="relative flex-grow md:flex-initial">
                                        <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                                            <SearchIcon size={18} className="text-gray-400" />
                                        </div>
                                        <input
                                            type="text"
                                            placeholder="Search users, roles, or tenants..."
                                            value={searchQuery}
                                            onChange={(e) => setSearchQuery(e.target.value)}
                                            className="block w-full pl-10 pr-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-gray-50 dark:bg-gray-700 text-gray-900 dark:text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-transparent sm:text-sm transition-all"
                                        />
                                    </div>
                                    {canManageRBAC && (
                                        <button onClick={() => setIsAddUserModalOpen(true)} className="flex items-center px-4 py-2 text-sm font-medium text-white bg-primary-600 rounded-lg hover:bg-primary-700 shadow-sm transition-colors">
                                            <PlusCircleIcon size={18} className="mr-2" />
                                            New User
                                        </button>
                                    )}
                                </div>
                            </div>
                            <div className="overflow-x-auto border border-gray-200 dark:border-gray-700 rounded-xl shadow-sm">
                                <table className="w-full text-sm text-left text-gray-500 dark:text-gray-400">
                                    <thead className="text-xs text-gray-700 uppercase bg-gray-50 dark:bg-gray-700 dark:text-gray-400">
                                        <tr>
                                            <th scope="col" className="px-4 py-3">User</th>
                                            <th scope="col" className="px-4 py-3">Email</th>
                                            {currentUser?.role === 'Super Admin' && (
                                                <th scope="col" className="px-4 py-3">Tenant</th>
                                            )}
                                            <th scope="col" className="px-4 py-3">Role</th>
                                            <th scope="col" className="px-4 py-3">Status</th>
                                            <th scope="col" className="px-4 py-3">Actions</th>
                                        </tr>
                                    </thead>
                                    <tbody>
                                        {filteredUsers.length > 0 ? (
                                            filteredUsers.map(user => {
                                                const isCurrentUser = currentUser?.id === user.id;
                                                const tenantName = user.tenantName || tenants.find(t => t.id === user.tenantId)?.name || 'Unknown';
                                                return (
                                                    <tr key={user.id} className={`border-b dark:border-gray-700 hover:bg-gray-50 dark:hover:bg-gray-600/50 transition-opacity ${user.status === 'Disabled' ? 'opacity-50' : ''}`}>
                                                        <td className="px-4 py-3 font-medium text-gray-900 dark:text-white">
                                                            <div className="flex items-center">
                                                                <img src={user.avatar} alt={user.name} className="h-8 w-8 rounded-full object-cover mr-3" />
                                                                <span>{user.name}</span>
                                                            </div>
                                                        </td>
                                                        <td className="px-4 py-3 text-xs">{user.email}</td>
                                                        {currentUser?.role === 'Super Admin' && (
                                                            <td className="px-4 py-3 text-xs">
                                                                <div className="flex items-center">
                                                                    <BuildingIcon size={14} className="mr-1.5 text-gray-400" />
                                                                    {tenantName}
                                                                </div>
                                                            </td>
                                                        )}
                                                        <td className="px-4 py-3">
                                                            <span className="px-2 py-1 text-xs font-medium rounded-full bg-gray-100 text-gray-800 dark:bg-gray-900/50 dark:text-gray-300">{user.role}</span>
                                                        </td>
                                                        <td className="px-4 py-3">
                                                            <span className={`px-2 py-1 text-xs font-medium rounded-full ${user.status === 'Active' ? 'bg-green-100 text-green-800 dark:bg-green-900/50 dark:text-green-300' : 'bg-gray-200 text-gray-800 dark:bg-gray-700 dark:text-gray-300'}`}>
                                                                {user.status}
                                                            </span>
                                                        </td>
                                                        <td className="px-4 py-3">
                                                            <div className="flex items-center space-x-2">
                                                                <button
                                                                    onClick={() => setEditingUser(user)}
                                                                    disabled={isCurrentUser && user.role === 'Super Admin'}
                                                                    title={isCurrentUser && user.role === 'Super Admin' ? "Super Admin role cannot be changed." : "Edit user"}
                                                                    className="flex items-center px-2.5 py-1 text-xs font-medium text-primary-700 bg-primary-100 rounded-md hover:bg-primary-200 dark:bg-primary-900/50 dark:text-primary-300 dark:hover:bg-primary-900 disabled:opacity-50 disabled:cursor-not-allowed"
                                                                >
                                                                    <PencilIcon size={12} className="mr-1.5" />
                                                                    Edit
                                                                </button>
                                                                <button
                                                                    onClick={() => onResetPassword(user.id, user.name)}
                                                                    disabled={isCurrentUser}
                                                                    title={isCurrentUser ? "You cannot reset your own password here." : "Reset user password"}
                                                                    className="flex items-center px-2.5 py-1 text-xs font-medium text-amber-700 bg-amber-100 rounded-md hover:bg-amber-200 dark:bg-amber-900/50 dark:text-amber-300 dark:hover:bg-amber-900 disabled:opacity-50 disabled:cursor-not-allowed"
                                                                >
                                                                    <KeyIcon size={12} className="mr-1.5" />
                                                                    Reset Password
                                                                </button>
                                                                <button
                                                                    onClick={() => onDeleteUser(user.id)}
                                                                    disabled={isCurrentUser}
                                                                    title={isCurrentUser ? "You cannot delete your own account." : "Delete user"}
                                                                    className="flex items-center px-2.5 py-1 text-xs font-medium text-red-700 bg-red-100 rounded-md hover:bg-red-200 dark:bg-red-900/50 dark:text-red-300 dark:hover:bg-red-900 disabled:opacity-50 disabled:cursor-not-allowed"
                                                                >
                                                                    <TrashIcon size={12} className="mr-1.5" />
                                                                    Delete
                                                                </button>
                                                            </div>
                                                        </td>
                                                    </tr>
                                                )
                                            })
                                        ) : (
                                            <tr>
                                                <td colSpan={currentUser?.role === 'Super Admin' ? 6 : 5} className="px-4 py-12 text-center text-gray-500 dark:text-gray-400">
                                                    <div className="flex flex-col items-center">
                                                        <SearchIcon size={48} className="mb-4 opacity-20" />
                                                        <p className="text-lg font-medium">No users found matching "{searchQuery}"</p>
                                                        <button onClick={() => setSearchQuery('')} className="mt-2 text-primary-600 hover:text-primary-500 font-medium">Clear search</button>
                                                    </div>
                                                </td>
                                            </tr>
                                        )}
                                    </tbody>
                                </table>
                            </div>
                        </div>
                    )}


                    {activeView === 'apiKeys' && canManageApiKeys && (
                        <div>
                            <div className="flex justify-between items-center mb-4">
                                <div>
                                    <h3 className="text-lg font-semibold">API Keys</h3>
                                    <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">Manage API keys for programmatic access to the platform.</p>
                                </div>
                                <button onClick={() => setIsGenerateKeyModalOpen(true)} className="flex items-center px-3 py-1.5 text-xs font-medium text-white bg-primary-600 rounded-lg hover:bg-primary-700">
                                    <PlusCircleIcon size={16} className="mr-1.5" />
                                    Generate New Key
                                </button>
                            </div>
                            <div className="overflow-x-auto">
                                <table className="w-full text-sm text-left text-gray-500 dark:text-gray-400">
                                    <thead className="text-xs text-gray-700 uppercase bg-gray-50 dark:bg-gray-700 dark:text-gray-400">
                                        <tr>
                                            <th scope="col" className="px-4 py-3">Name</th>
                                            <th scope="col" className="px-4 py-3">Key</th>
                                            <th scope="col" className="px-4 py-3">Created</th>
                                            <th scope="col" className="px-4 py-3">Actions</th>
                                        </tr>
                                    </thead>
                                    <tbody>
                                        {apiKeys.map(key => (
                                            <tr key={key.id} className="border-b dark:border-gray-700 hover:bg-gray-50 dark:hover:bg-gray-600/50">
                                                <td className="px-4 py-3 font-medium text-gray-900 dark:text-white">{key.name}</td>
                                                <td className="px-4 py-3 font-mono text-xs">{`${key.key.substring(0, 11)}...${key.key.slice(-4)}`}</td>
                                                <td className="px-4 py-3 text-xs">{new Date(key.createdAt).toLocaleDateString()}</td>
                                                <td className="px-4 py-3">
                                                    <button onClick={() => onRevokeApiKey(key.id)} className="flex items-center text-xs font-medium text-red-600 hover:text-red-800 dark:text-red-400 dark:hover:text-red-300">
                                                        <TrashIcon size={14} className="mr-1" /> Revoke
                                                    </button>
                                                </td>
                                            </tr>
                                        ))}
                                    </tbody>
                                </table>
                            </div>
                        </div>
                    )}

                    {activeView === 'infrastructure' && isSuperAdmin && (
                        <div className="space-y-6">
                            <div className="bg-white dark:bg-gray-800 rounded-lg shadow-md border border-gray-200 dark:border-gray-700 p-6 flex flex-col md:flex-row justify-between items-start md:items-center">
                                <div className="flex-grow">
                                    <div className="flex items-center space-x-4">
                                        <div className="flex-shrink-0"><DatabaseIcon size={32} className="text-primary-500" /></div>
                                        <div>
                                            <h4 className="text-lg font-bold text-gray-800 dark:text-gray-100">Database Connection</h4>
                                            <p className="text-sm text-gray-600 dark:text-gray-400 mt-1">Configure the primary database connection for the platform.</p>
                                        </div>
                                    </div>
                                </div>
                                <div className="mt-4 md:mt-0 md:ml-6 flex-shrink-0">
                                    <button onClick={() => setIsDbSettingsModalOpen(true)} className="flex items-center px-4 py-2 text-sm font-medium text-gray-700 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-500 rounded-md shadow-sm hover:bg-gray-50 dark:hover:bg-gray-600">
                                        <CogIcon size={16} className="mr-2" /> Configure
                                    </button>
                                </div>
                            </div>
                            <div className="bg-white dark:bg-gray-800 rounded-lg shadow-md border border-gray-200 dark:border-gray-700 p-6 flex flex-col md:flex-row justify-between items-start md:items-center">
                                <div className="flex-grow">
                                    <div className="flex items-center space-x-4">
                                        <div className="flex-shrink-0"><BrainCircuitIcon size={32} className="text-primary-500" /></div>
                                        <div>
                                            <h4 className="text-lg font-bold text-gray-800 dark:text-gray-100">LLM Provider</h4>
                                            <p className="text-sm text-gray-600 dark:text-gray-400 mt-1">Manage the Large Language Model integration for AI features.</p>
                                        </div>
                                    </div>
                                </div>
                                <div className="mt-4 md:mt-0 md:ml-6 flex-shrink-0">
                                    <button onClick={() => setIsLlmSettingsModalOpen(true)} className="flex items-center px-4 py-2 text-sm font-medium text-gray-700 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-500 rounded-md shadow-sm hover:bg-gray-50 dark:hover:bg-gray-600">
                                        <CogIcon size={16} className="mr-2" /> Configure
                                    </button>
                                </div>
                            </div>

                            <VoiceBotSettingsPanel
                                settings={llmSettings?.voiceBotSettings || null}
                                isAdmin={true}
                                onSave={(settings) => {
                                    if (llmSettings) {
                                        onSaveInfrastructure({ llm: { ...llmSettings, voiceBotSettings: settings } });
                                    } else {
                                        // Default fallback if LLM Settings are somehow null
                                        onSaveInfrastructure({ llm: { provider: 'Gemini', apiKey: '', model: 'gemini-2.0-flash', voiceBotSettings: settings } as LlmSettingsType });
                                    }
                                }}
                            />
                        </div>
                    )}

                    {activeView === 'voiceBot' && isTenantAdminView && activeTenant && (
                        <VoiceBotSettingsPanel
                            settings={activeTenant.voiceBotSettings || null}
                            isAdmin={false}
                            onSave={async (settings) => {
                                if (onSaveTenantVoiceBotSettings) {
                                    await onSaveTenantVoiceBotSettings(settings);
                                }
                            }}
                        />
                    )}
                </div>
            </div>

            {isAlertModalOpen && (
                <AlertRuleModal
                    isOpen={isAlertModalOpen}
                    onClose={() => setIsAlertModalOpen(false)}
                    onSave={handleSaveAlert}
                    rule={editingRule}
                />
            )}
            <IntegrationSettingsModal
                isOpen={!!configuringIntegration}
                onClose={() => setConfiguringIntegration(null)}
                integration={configuringIntegration}
                onSave={handleSaveIntegrationConfig}
            />
            {isRoleModalOpen && (
                <RoleEditorModal
                    isOpen={isRoleModalOpen}
                    onClose={() => setIsRoleModalOpen(false)}
                    onSave={handleSaveRole}
                    role={editingRole}
                    allRoles={roles}
                />
            )}
            <GenerateApiKeyNameModal
                isOpen={isGenerateKeyModalOpen}
                onClose={() => setIsGenerateKeyModalOpen(false)}
                onGenerate={handleGenerateKey}
            />
            <ShowNewKeyModal
                isOpen={isShowNewKeyModalOpen}
                onClose={() => {
                    setIsShowNewKeyModalOpen(false);
                    onAcknowledgeNewKey();
                }}
                apiKey={newlyGeneratedKey}
            />
            {editingUser && (
                <EditUserModal
                    user={editingUser}
                    roles={availableRolesForAssignment}
                    onClose={() => setEditingUser(null)}
                    onSave={handleUpdateUser}
                />
            )}
            {isAddUserModalOpen && (
                <AddUserModal
                    isOpen={isAddUserModalOpen}
                    onClose={() => setIsAddUserModalOpen(false)}
                    onSave={onAddNewUser}
                    roles={roles}
                    tenants={tenants}
                />
            )}
            {databaseSettings && (
                <DatabaseSettings
                    isOpen={isDbSettingsModalOpen}
                    onClose={() => setIsDbSettingsModalOpen(false)}
                    settings={databaseSettings}
                    onSave={(updatedSettings) => {
                        onSaveInfrastructure({ db: updatedSettings });
                        setIsDbSettingsModalOpen(false);
                    }}
                />
            )}
            {llmSettings && (
                <LlmSettings
                    isOpen={isLlmSettingsModalOpen}
                    onClose={() => setIsLlmSettingsModalOpen(false)}
                    settings={llmSettings}
                    onSave={(updatedSettings) => {
                        onSaveInfrastructure({ llm: updatedSettings });
                        setIsLlmSettingsModalOpen(false);
                    }}
                />
            )}
            <DataSourceModal
                isOpen={isDataSourceModalOpen}
                onClose={() => setIsDataSourceModalOpen(false)}
                onSave={handleSaveDataSource}
                dataSource={editingDataSource}
            />
        </div>
    );
};

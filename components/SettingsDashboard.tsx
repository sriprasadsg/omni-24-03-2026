
import React, { useState, useEffect, useMemo, useContext } from 'react';
import { Integration, AlertRule, Role, ApiKey, User, Tenant, DatabaseSettings as DatabaseSettingsType, LlmSettings as LlmSettingsType, DataSource, Permission, NewUserPayload, VoiceBotSettings } from '../types';
import { CogIcon, UsersIcon as Users2Icon, ShieldLockIcon, KeyIcon, AlertTriangleIcon, DatabaseIcon, BrainCircuitIcon, PaintbrushIcon, MailIcon, CalendarIcon } from './icons';
import { useUser } from '../contexts/UserContext';
import { SettingsUsersTab } from './SettingsUsersTab';
import { SettingsRolesTab } from './SettingsRolesTab';
import { SettingsDataSourcesTab } from './SettingsDataSourcesTab';
import { SettingsAlertRulesTab } from './SettingsAlertRulesTab';
import { SettingsApiKeysTab } from './SettingsApiKeysTab';
import { SettingsInfrastructureTab } from './SettingsInfrastructureTab';
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

    const handleSaveIntegrationConfig = async (id: string, config: any, isEnabled: boolean) => {
        const base = localIntegrations.find(i => i.id === id);
        const updatedIntegration: Integration = { ...(base as Integration), id, config, isEnabled };
        try {
            await apiService.saveIntegrationConfig(updatedIntegration);
            setLocalIntegrations(prev => prev.map(i => i.id === id ? updatedIntegration : i));
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
                        <SettingsDataSourcesTab
                            dataSources={dataSources}
                            testingState={testingState}
                            onNew={() => handleOpenDataSourceModal(null)}
                            onEdit={handleOpenDataSourceModal}
                            onDelete={onDeleteDataSource}
                            onTest={handleTestDataSource}
                        />
                    )}

                    {activeView === 'alerts' && canManageSettings && (
                        <SettingsAlertRulesTab
                            alertRules={alertRules}
                            canManageSettings={canManageSettings}
                            onNew={() => handleOpenAlertModal(null)}
                            onEdit={handleOpenAlertModal}
                            onDelete={onDeleteAlertRule}
                        />
                    )}

                    {activeView === 'maintenance' && canManageSettings && (
                        <MaintenanceWindowConfig />
                    )}

                    {activeView === 'roles' && canManageRBAC && (
                        <SettingsRolesTab
                            roles={roles}
                            canManageSettings={canManageSettings}
                            onNew={() => handleOpenRoleModal(null)}
                            onEdit={handleOpenRoleModal}
                            onDelete={onDeleteRole}
                        />
                    )}

                    {activeView === 'users' && canManageRBAC && (
                        <SettingsUsersTab
                            users={users}
                            roles={roles}
                            tenants={tenants}
                            filteredUsers={filteredUsers}
                            searchQuery={searchQuery}
                            canManageRBAC={canManageRBAC}
                            onSearchChange={setSearchQuery}
                            onEditUser={setEditingUser}
                            onDeleteUser={onDeleteUser}
                            onResetPassword={onResetPassword}
                            onAddUser={() => setIsAddUserModalOpen(true)}
                        />
                    )}

                    {activeView === 'apiKeys' && canManageApiKeys && (
                        <SettingsApiKeysTab
                            apiKeys={apiKeys}
                            onGenerate={() => setIsGenerateKeyModalOpen(true)}
                            onRevoke={onRevokeApiKey}
                        />
                    )}

                    {activeView === 'infrastructure' && isSuperAdmin && (
                        <SettingsInfrastructureTab
                            llmSettings={llmSettings}
                            onOpenDb={() => setIsDbSettingsModalOpen(true)}
                            onOpenLlm={() => setIsLlmSettingsModalOpen(true)}
                            onSaveVoiceBot={(settings) => {
                                if (llmSettings) {
                                    onSaveInfrastructure({ llm: { ...llmSettings, voiceBotSettings: settings } });
                                } else {
                                    onSaveInfrastructure({ llm: { provider: 'Gemini', apiKey: '', model: 'gemini-2.0-flash', voiceBotSettings: settings } as LlmSettingsType });
                                }
                            }}
                        />
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

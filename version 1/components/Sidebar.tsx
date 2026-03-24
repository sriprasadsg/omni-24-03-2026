
import React from 'react';
import { BotIcon, DashboardIcon, ShieldCheckIcon, ServerIcon, DatabaseIcon, ShieldAlertIcon, ShieldZapIcon, BarChart3Icon, SettingsIcon, BuildingIcon, ArrowLeftIcon, CloudShieldIcon, DollarSignIcon, ClipboardListIcon, FileTextIcon, UsersIcon, WorkflowIcon, GitPullRequestDraftIcon, BookKeyIcon, LightbulbIcon, GitMergeIcon, DnaIcon, NetworkIcon, PuzzleIcon, GaugeIcon, BombIcon } from './icons';
import { AppView } from '../types';
import { useUser } from '../contexts/UserContext';
import { Permission } from '../types';

interface SidebarProps {
  isOpen: boolean;
  currentView: AppView;
  setCurrentView: (view: AppView) => void;
  isViewingTenant: boolean;
  onBackToTenants: () => void;
}

const NavLink: React.FC<{ icon: React.ReactNode; label: string; active?: boolean; onClick: () => void; disabled?: boolean; }> = ({ icon, label, active, onClick, disabled }) => (
    <button 
        onClick={onClick} 
        disabled={disabled}
        className={`w-full flex items-center px-4 py-3 text-sm font-medium rounded-lg transition-colors duration-200 ${
            active
                ? 'bg-primary-500 text-white'
                : 'text-gray-600 dark:text-gray-400 hover:bg-gray-200 dark:hover:bg-gray-700'
        } ${disabled ? 'opacity-50 cursor-not-allowed' : ''}`}
        title={label}
    >
        {icon}
        {label && <span className="ml-3">{label}</span>}
    </button>
);

export const Sidebar: React.FC<SidebarProps> = ({ isOpen, currentView, setCurrentView, isViewingTenant, onBackToTenants }) => {
  const { hasPermission, currentUser } = useUser();

  const allNavItems: { view: AppView, label: string, icon: React.ReactNode, permission: Permission }[] = [
      { view: 'dashboard', label: 'Dashboard', icon: <DashboardIcon size={20} />, permission: 'view:dashboard' },
      { view: 'proactiveInsights', label: 'Proactive Insights', icon: <LightbulbIcon size={20} />, permission: 'view:insights' },
      { view: 'distributedTracing', label: 'Distributed Tracing', icon: <GitMergeIcon size={20} />, permission: 'view:tracing' },
      { view: 'reporting', label: 'Reporting', icon: <BarChart3Icon size={20} />, permission: 'view:reporting' },
      { view: 'logExplorer', label: 'Log Explorer', icon: <FileTextIcon size={20} />, permission: 'view:logs' },
      { view: 'networkObservability', label: 'Network Observability', icon: <NetworkIcon size={20} />, permission: 'view:network' },
      { view: 'agents', label: 'Agents', icon: <ServerIcon size={20} />, permission: 'view:agents' },
      { view: 'assetManagement', label: 'Assets', icon: <DatabaseIcon size={20} />, permission: 'view:assets' },
      { view: 'patchManagement', label: 'Patching', icon: <ShieldAlertIcon size={20} />, permission: 'view:patching' },
      { view: 'cloudSecurity', label: 'Cloud Security', icon: <CloudShieldIcon size={20} />, permission: 'view:cloud_security' },
      { view: 'security', label: 'Security', icon: <ShieldZapIcon size={20} />, permission: 'view:security' },
      { view: 'threatHunting', label: 'Threat Hunting', icon: <UsersIcon size={20} />, permission: 'view:threat_hunting' },
      { view: 'dataSecurity', label: 'Data Security (DSPM)', icon: <DnaIcon size={20} />, permission: 'view:dspm' },
      { view: 'attackPath', label: 'Attack Path Analysis', icon: <NetworkIcon size={20} />, permission: 'view:attack_path' },
      { view: 'devsecops', label: 'DevSecOps', icon: <GitPullRequestDraftIcon size={20} />, permission: 'view:devsecops' },
      { view: 'doraMetrics', label: 'DORA Metrics', icon: <GaugeIcon size={20} />, permission: 'view:dora_metrics' },
      { view: 'serviceCatalog', label: 'Service Catalog (IDP)', icon: <PuzzleIcon size={20} />, permission: 'view:service_catalog' },
      { view: 'chaosEngineering', label: 'Chaos Engineering', icon: <BombIcon size={20} />, permission: 'view:chaos' },
      { view: 'compliance', label: 'Compliance', icon: <ShieldCheckIcon size={20} />, permission: 'view:compliance' },
      { view: 'aiGovernance', label: 'AI Governance', icon: <BotIcon size={20} />, permission: 'view:ai_governance' },
      { view: 'automation', label: 'Automation', icon: <WorkflowIcon size={20} />, permission: 'view:automation' },
      { view: 'developer_hub', label: 'Developer Hub', icon: <BookKeyIcon size={20} />, permission: 'view:developer_hub' },
      { view: 'finops', label: 'FinOps & Billing', icon: <DollarSignIcon size={20} />, permission: 'view:finops' },
      { view: 'auditLog', label: 'Audit Log', icon: <ClipboardListIcon size={20} />, permission: 'view:audit_log' },
      { view: 'settings', label: 'Settings', icon: <SettingsIcon size={20} />, permission: 'manage:settings' },
      { view: 'tenantManagement', label: 'Tenants', icon: <BuildingIcon size={20} />, permission: 'manage:tenants' },
  ];

  const visibleNavItems = allNavItems.filter(item => {
    // Hide tenant management link when already viewing a specific tenant.
    if (isViewingTenant && item.permission === 'manage:tenants') {
        return false;
    }
    // For all users (including Super Admin in global or tenant view),
    // visibility is determined by their permissions.
    return hasPermission(item.permission);
  });

  return (
    <aside className={`flex-shrink-0 bg-white dark:bg-gray-800 border-r border-gray-200 dark:border-gray-700 flex flex-col transition-all duration-300 ${isOpen ? 'w-64' : 'w-20'}`}>
        <div className="flex items-center justify-center h-16 border-b border-gray-200 dark:border-gray-700">
            <BotIcon className="text-primary-500" size={32} />
            {isOpen && <span className="ml-2 text-xl font-bold text-gray-800 dark:text-white">Omni-Agent AI</span>}
        </div>
        <nav className="flex-1 px-4 py-4 space-y-2 overflow-y-auto">
            {currentUser?.role === 'Super Admin' && isViewingTenant && (
                <button onClick={onBackToTenants} className="w-full flex items-center px-4 py-3 text-sm font-medium rounded-lg bg-amber-100 dark:bg-amber-900/50 text-amber-800 dark:text-amber-200 mb-2 hover:bg-amber-200 dark:hover:bg-amber-900">
                    <ArrowLeftIcon size={20} />
                    {isOpen && <span className="ml-3">Back to Tenant List</span>}
                </button>
            )}
            {visibleNavItems.map(item => (
                <NavLink 
                    key={item.view}
                    icon={item.icon} 
                    label={isOpen ? item.label : ''} 
                    active={currentView === item.view}
                    onClick={() => setCurrentView(item.view)}
                />
            ))}
        </nav>
        <div className="px-4 py-4 border-t border-gray-200 dark:border-gray-700">
        </div>
    </aside>
  );
};
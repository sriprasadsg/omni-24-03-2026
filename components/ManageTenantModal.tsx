import React, { useState, useEffect } from 'react';
import { Tenant, Permission, SubscriptionTier } from '../types';
import { TrashIcon } from './icons';
import { SUBSCRIPTION_TIERS } from '../constants';

interface ManageTenantModalProps {
  isOpen: boolean;
  onClose: () => void;
  tenant: Tenant | null;
  onSave: (tenantId: string, updates: { features: Permission[], tier: SubscriptionTier }) => void;
  onDelete: (tenantId: string) => void;
}

// Initial Static Map
const staticFeatureMap: Record<string, string> = {
  'view:dashboard': 'Main Dashboard',
  'view:reporting': 'Reporting & Analytics',
  'export:reports': 'Export Reports',
  'view:agents': 'Agent Fleet Management',
  'view:software_deployment': 'Software Deployment Hub',
  'view:agent_logs': 'View Agent Logs',
  'remediate:agents': 'Agent Remediation',
  'view:assets': 'Asset Management',
  'view:patching': 'Patch Management',
  'manage:patches': 'Deploy Patches',
  'view:security': 'Security Operations',
  'manage:security_cases': 'Manage Security Cases',
  'manage:security_playbooks': 'Manage SOAR Playbooks',
  'investigate:security': 'Threat Intelligence',
  'view:compliance': 'Compliance Management',
  'manage:compliance_evidence': 'Manage Compliance Evidence',
  'view:ai_governance': 'AI Governance',
  'manage:ai_risks': 'Manage AI Risks',
  'manage:settings': 'System Settings',
  'manage:tenants': 'Tenant Management',
  'view:cloud_security': 'Cloud Security',
  'view:finops': 'FinOps & Billing',
  'view:audit_log': 'Audit Log',
  'manage:rbac': 'Role & Permission Management',
  'manage:api_keys': 'API Key Management',
  'view:logs': 'Log Explorer',
  'view:threat_hunting': 'Threat Hunting',
  'view:profile': 'User Profile',
  'view:automation': 'Automation Workflows',
  'manage:automation': 'Manage Automations',
  'view:devsecops': 'DevSecOps Dashboard',
  'view:developer_hub': 'Developer Hub',
  'view:insights': 'Proactive Insights',
  'view:tracing': 'Distributed Tracing',
  'view:dspm': 'Data Security (DSPM)',
  'view:attack_path': 'Attack Path Analysis',
  'view:service_catalog': 'Service Catalog (IDP)',
  'view:dora_metrics': 'DORA Metrics',
  'view:chaos': 'Chaos Engineering',
  'view:network': 'Network Observability',
  'manage:pricing': 'Service Pricing Management',
};

const permissionGroups: { name: string; permissions: string[] }[] = [
  { name: 'General', permissions: ['view:reporting', 'export:reports'] },
  { name: 'Administration', permissions: ['manage:settings', 'manage:rbac', 'manage:api_keys', 'view:finops', 'view:profile'] },
  { name: 'Security & Compliance', permissions: ['view:security', 'manage:security_cases', 'manage:security_playbooks', 'investigate:security', 'view:cloud_security', 'view:patching', 'manage:patches', 'view:threat_hunting', 'view:compliance', 'manage:compliance_evidence', 'view:audit_log'] },
  { name: 'Observability', permissions: ['view:agents', 'view:software_deployment', 'view:agent_logs', 'remediate:agents', 'view:assets', 'view:logs', 'view:insights', 'view:tracing', 'view:network'] },
  { name: 'AI Governance', permissions: ['view:ai_governance', 'manage:ai_risks'] },
  { name: 'Automation', permissions: ['view:automation', 'manage:automation'] },
  { name: 'Developer Tools', permissions: ['view:devsecops', 'view:developer_hub'] },
  { name: 'Advanced Platform', permissions: ['view:dspm', 'view:attack_path', 'view:service_catalog', 'view:dora_metrics', 'view:chaos'] },
];

const allToggleableFeatures = permissionGroups.flatMap(g => g.permissions);

export const ManageTenantModal: React.FC<ManageTenantModalProps> = ({ isOpen, onClose, tenant, onSave, onDelete }) => {
  const [enabledFeatures, setEnabledFeatures] = useState<Set<string>>(new Set());
  const [currentTier, setCurrentTier] = useState<SubscriptionTier>('Custom');
  const [dynamicServices, setDynamicServices] = useState<any[]>([]);

  useEffect(() => {
    if (tenant) {
      setEnabledFeatures(new Set(tenant.enabledFeatures || []));
      setCurrentTier(tenant.subscriptionTier);
    }
  }, [tenant]);

  // Fetch dynamic services
  useEffect(() => {
    const fetchServices = async () => {
      try {
        const res = await fetch('/api/finops/pricing');
        if (res.ok) {
          const data = await res.json();
          setDynamicServices(data);
        }
      } catch (e) {
        console.error("Failed to fetch services", e);
      }
    };
    if (isOpen) fetchServices();
  }, [isOpen]);

  // Effect to sync tier with permissions
  useEffect(() => {
    if (!tenant) return;
    const currentPermissions = Array.from(enabledFeatures).filter(p => !(p as string).startsWith('service:')).sort();

    let matchedTier: SubscriptionTier = 'Custom';

    for (const tier in SUBSCRIPTION_TIERS) {
      const tierKey = tier as Exclude<SubscriptionTier, 'Custom'>;
      const tierPermissions = [...SUBSCRIPTION_TIERS[tierKey].permissions].sort();
      if (JSON.stringify(currentPermissions) === JSON.stringify(tierPermissions)) {
        matchedTier = tierKey;
        break;
      }
    }
    // Only update if standard permissions define a tier, ignoring services for tier detecion
    if (currentTier !== matchedTier && matchedTier !== 'Custom') {
      // Optional: Logic to allow 'Custom' even if it matches a tier, 
      // but here we auto-detect tier.
      // setCurrentTier(matchedTier); 
      // NOTE: We skip auto-switching to avoid overriding custom service selections
    }
  }, [enabledFeatures, tenant, currentTier]);

  const handleFeatureToggle = (feature: string) => {
    setEnabledFeatures(prev => {
      const newSet = new Set(prev);
      if (newSet.has(feature)) {
        newSet.delete(feature);
      } else {
        newSet.add(feature);
      }
      return newSet;
    });
  };

  const handleToggleAll = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.checked) {
      const all = new Set(allToggleableFeatures);
      // Don't auto-select services for "Select All" to avoid massive billing
      setEnabledFeatures(all);
    } else {
      // Clear only standard features
      const newSet = new Set(enabledFeatures);
      allToggleableFeatures.forEach(f => newSet.delete(f));
      setEnabledFeatures(newSet);
    }
  };

  const handleTierChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    const newTier = e.target.value as SubscriptionTier;
    setCurrentTier(newTier);
    if (newTier !== 'Custom') {
      const tierPermissions = SUBSCRIPTION_TIERS[newTier as Exclude<SubscriptionTier, 'Custom'>].permissions;
      // Preserve existing service selections when switching tier base
      const currentServices = Array.from(enabledFeatures).filter(f => (f as string).startsWith('service:'));
      setEnabledFeatures(new Set([...tierPermissions, ...currentServices]));
    }
  };

  const handleSave = () => {
    if (tenant) {
      const finalFeatures = new Set(enabledFeatures);
      finalFeatures.add('view:dashboard');
      // cast to Permission[] assuming backend accepts string[], verify Permission type if strict
      onSave(tenant.id, { features: Array.from(finalFeatures) as Permission[], tier: currentTier });
    }
  };

  const handleDelete = () => {
    if (tenant) {
      if (window.confirm(`Are you sure you want to delete the tenant "${tenant.name}"? This action is irreversible and will permanently delete all associated data.`)) {
        onDelete(tenant.id);
      }
    }
  }

  if (!isOpen || !tenant) return null;

  const allSelected = allToggleableFeatures.every(f => enabledFeatures.has(f));

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 z-50 flex justify-center items-center" onClick={onClose}>
      <div className="bg-white dark:bg-gray-800 rounded-lg shadow-xl w-full max-w-2xl p-6 m-4 max-h-[90vh] flex flex-col" onClick={e => e.stopPropagation()}>
        <h2 className="text-xl font-bold text-gray-900 dark:text-white mb-4 flex-shrink-0">Manage Tenant: <span className="text-primary-600 dark:text-primary-400">{tenant.name}</span></h2>

        <div className="flex-grow overflow-y-auto pr-2 space-y-4">
          <div>
            <h3 className="text-sm font-medium text-gray-500 dark:text-gray-400 mb-2">Subscription Tier</h3>
            <p className="text-xs text-gray-500 dark:text-gray-400 mb-3">Select a base subscription tier.</p>
            <select
              value={currentTier}
              onChange={handleTierChange}
              className="mt-1 block w-full px-3 py-2 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-md shadow-sm sm:text-sm dark:text-white"
            >
              {(Object.keys(SUBSCRIPTION_TIERS) as Exclude<SubscriptionTier, 'Custom'>[]).map(tier => (
                <option key={tier} value={tier}>{SUBSCRIPTION_TIERS[tier].name}</option>
              ))}
              <option value="Custom">Custom</option>
            </select>
          </div>

          <div>
            {/* Dynamic Services Section */}
            {dynamicServices.length > 0 && (
              <div className="mb-6">
                <h3 className="text-sm font-bold text-gray-800 dark:text-white mb-2 flex items-center">
                  <span className="bg-green-100 text-green-800 text-xs font-semibold mr-2 px-2.5 py-0.5 rounded dark:bg-green-900 dark:text-green-300">Add-on</span>
                  Billable Services
                </h3>
                <div className="p-3 bg-green-50 dark:bg-gray-700/50 rounded-lg border border-green-200 dark:border-gray-600">
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-4 gap-y-2">
                    {dynamicServices.map(service => {
                      // Permission ID convention: service:{id}
                      const permId = `service:${service.id}`;
                      return (
                        <label key={service.id} className="flex items-center space-x-3">
                          <input
                            type="checkbox"
                            checked={enabledFeatures.has(permId)}
                            onChange={() => handleFeatureToggle(permId)}
                            className="h-4 w-4 rounded border-gray-300 text-green-600 focus:ring-green-500"
                          />
                          <div className="flex flex-col">
                            <span className="text-sm font-medium text-gray-900 dark:text-white">{service.name}</span>
                            <span className="text-xs text-gray-500 dark:text-gray-400">
                              ${service.price} / {service.unit.replace(/_/g, ' ')}
                            </span>
                          </div>
                        </label>
                      );
                    })}
                  </div>
                </div>
              </div>
            )}

            <h3 className="text-sm font-medium text-gray-500 dark:text-gray-400 mb-2">Standard Features</h3>
            <div className="p-3 bg-gray-50 dark:bg-gray-700/50 rounded-md border border-gray-200 dark:border-gray-600">
              <label className="flex items-center space-x-3 font-semibold">
                <input
                  type="checkbox"
                  checked={allSelected}
                  onChange={handleToggleAll}
                  className="h-4 w-4 rounded border-gray-300 text-primary-600 focus:ring-primary-500"
                />
                <span className="text-sm text-gray-800 dark:text-gray-200">Enable All Standard Features</span>
              </label>
            </div>

            <div className="mt-4 space-y-4">
              {permissionGroups.map(group => (
                <div key={group.name} role="group" aria-labelledby={`group-label-${group.name}`} className="p-3 bg-gray-50 dark:bg-gray-700/50 rounded-lg border border-gray-200 dark:border-gray-600">
                  <h4 id={`group-label-${group.name}`} className="font-semibold text-sm text-gray-800 dark:text-gray-200 mb-2">{group.name}</h4>
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-4 gap-y-2">
                    {group.permissions.map(feature => (
                      <label key={feature} className="flex items-center space-x-3">
                        <input
                          type="checkbox"
                          checked={enabledFeatures.has(feature)}
                          onChange={() => handleFeatureToggle(feature)}
                          className="h-4 w-4 rounded border-gray-300 text-primary-600 focus:ring-primary-500"
                        />
                        <span className="text-sm text-gray-600 dark:text-gray-400">{staticFeatureMap[feature] || feature}</span>
                      </label>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          </div>

          <div className="pt-4">
            <h3 className="text-sm font-medium text-red-600 dark:text-red-400 mb-2">Danger Zone</h3>
            <div className="p-4 bg-red-50 dark:bg-red-900/50 rounded-lg border border-red-200 dark:border-red-800 flex justify-between items-center">
              <div>
                <p className="font-semibold text-red-800 dark:text-red-200">Delete this Tenant</p>
                <p className="text-xs text-red-700 dark:text-red-300">This action is irreversible and will permanently delete all associated data.</p>
              </div>
              <button
                onClick={handleDelete}
                className="flex items-center px-3 py-1.5 text-xs font-medium text-white bg-red-600 rounded-lg hover:bg-red-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-red-500"
              >
                <TrashIcon size={14} className="mr-1.5" />
                Delete Tenant
              </button>
            </div>
          </div>

        </div>

        <div className="mt-6 flex-shrink-0 flex justify-end space-x-3 pt-4 border-t border-gray-200 dark:border-gray-700">
          <button type="button" onClick={onClose}
            className="px-4 py-2 text-sm font-medium text-gray-700 bg-white dark:bg-gray-700 dark:text-gray-200 border border-gray-300 dark:border-gray-600 rounded-md shadow-sm hover:bg-gray-50 dark:hover:bg-gray-600 focus:outline-none"
          >
            Cancel
          </button>
          <button type="button" onClick={handleSave}
            className="px-4 py-2 text-sm font-medium text-white bg-primary-600 rounded-lg hover:bg-primary-700 focus:outline-none"
          >
            Save Changes
          </button>
        </div>
      </div>
    </div>
  );
};

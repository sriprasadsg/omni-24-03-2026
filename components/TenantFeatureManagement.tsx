import React, { useState, useEffect } from 'react';
import { Tenant, Permission } from '../types';
import { CheckIcon, SaveIcon } from './icons';

interface TenantFeatureManagementProps {
  tenant: Tenant;
  onSave: (updates: { features: Permission[] }) => Promise<void>;
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
  'view:agent_capabilities': 'Agent Capabilities Dashboard',
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
  { name: 'Observability', permissions: ['view:agents', 'view:agent_capabilities', 'view:software_deployment', 'view:agent_logs', 'remediate:agents', 'view:assets', 'view:logs', 'view:insights', 'view:tracing', 'view:network'] },
  { name: 'AI Governance', permissions: ['view:ai_governance', 'manage:ai_risks'] },
  { name: 'Automation', permissions: ['view:automation', 'manage:automation'] },
  { name: 'Developer Tools', permissions: ['view:devsecops', 'view:developer_hub'] },
  { name: 'Advanced Platform', permissions: ['view:dspm', 'view:attack_path', 'view:service_catalog', 'view:dora_metrics', 'view:chaos'] },
];

export const TenantFeatureManagement: React.FC<TenantFeatureManagementProps> = ({ tenant, onSave }) => {
  const [enabledFeatures, setEnabledFeatures] = useState<Set<string>>(new Set());
  const [isSaving, setIsSaving] = useState(false);
  const [message, setMessage] = useState('');
  const [dynamicServices, setDynamicServices] = useState<any[]>([]);

  useEffect(() => {
    if (tenant) {
      setEnabledFeatures(new Set(tenant.enabledFeatures || []));
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
    fetchServices();
  }, []);

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

  const handleSave = async () => {
    setIsSaving(true);
    try {
      const finalFeatures = new Set(enabledFeatures);
      finalFeatures.add('view:dashboard');
      await onSave({ features: Array.from(finalFeatures) as Permission[] });
      setMessage('Features updated successfully');
      setTimeout(() => setMessage(''), 3000);
    } catch (error) {
      console.error('Failed to save features', error);
      setMessage('Failed to save features');
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <div className="bg-white dark:bg-gray-800 rounded-lg shadow p-6">
      <div className="flex justify-between items-center mb-6">
        <div>
          <h2 className="text-lg font-medium text-gray-900 dark:text-white">Feature Management</h2>
          <p className="text-sm text-gray-500 dark:text-gray-400">Enable or disable specific features for this tenant.</p>
        </div>
        <button
          onClick={handleSave}
          disabled={isSaving}
          className="inline-flex items-center px-4 py-2 border border-transparent rounded-md shadow-sm text-sm font-medium text-white bg-primary-600 hover:bg-primary-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-primary-500 disabled:opacity-50"
        >
          {isSaving ? 'Saving...' : (
            <>
              <SaveIcon className="-ml-1 mr-2 h-5 w-5" />
              Save Changes
            </>
          )}
        </button>
      </div>

      {message && (
        <div className={`mb-4 p-4 rounded-md ${message.includes('Failed') ? 'bg-red-50 text-red-700' : 'bg-green-50 text-green-700'} flex items-center`}>
          {!message.includes('Failed') && <CheckIcon className="mr-2 h-5 w-5" />}
          {message}
        </div>
      )}

      {/* Dynamic Services Section */}
      {dynamicServices.length > 0 && (
        <div className="mb-8">
          <h3 className="text-base font-semibold text-gray-800 dark:text-white mb-3 flex items-center">
            <span className="bg-green-100 text-green-800 text-xs font-semibold mr-2 px-2.5 py-0.5 rounded dark:bg-green-900 dark:text-green-300">Add-on</span>
            Billable Services
          </h3>
          <div className="bg-green-50 dark:bg-gray-700/50 rounded-lg border border-green-200 dark:border-gray-600 p-4">
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {dynamicServices.map(service => {
                // Permission ID convention: service:{id}
                const permId = `service:${service.id}`;
                return (
                  <label key={service.id} className="relative flex items-start py-2">
                    <div className="min-w-0 flex-1 text-sm">
                      <div className="font-medium text-gray-900 dark:text-white select-none">{service.name}</div>
                      <p className="text-gray-500 dark:text-gray-400 select-none">${service.price} / {service.unit.replace(/_/g, ' ')}</p>
                    </div>
                    <div className="ml-3 flex items-center h-5">
                      <input
                        type="checkbox"
                        checked={enabledFeatures.has(permId)}
                        onChange={() => handleFeatureToggle(permId)}
                        className="focus:ring-green-500 h-4 w-4 text-green-600 border-gray-300 rounded"
                      />
                    </div>
                  </label>
                );
              })}
            </div>
          </div>
        </div>
      )}

      <div className="space-y-6">
        {permissionGroups.map(group => (
          <div key={group.name} className="border-b border-gray-200 dark:border-gray-700 pb-6 last:border-0">
            <h3 className="text-base font-semibold text-gray-900 dark:text-white mb-4">{group.name}</h3>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {group.permissions.map(feature => (
                <label key={feature} className="relative flex items-start py-2">
                  <div className="min-w-0 flex-1 text-sm">
                    <div className="font-medium text-gray-700 dark:text-gray-300 select-none">
                      {staticFeatureMap[feature] || feature}
                    </div>
                  </div>
                  <div className="ml-3 flex items-center h-5">
                    <input
                      type="checkbox"
                      checked={enabledFeatures.has(feature)}
                      onChange={() => handleFeatureToggle(feature)}
                      className="focus:ring-primary-500 h-4 w-4 text-primary-600 border-gray-300 rounded"
                    />
                  </div>
                </label>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};

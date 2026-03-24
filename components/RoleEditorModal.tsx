
import React, { useState, useEffect, useMemo } from 'react';
import { Role, Permission } from '../types';
import { XIcon, ShieldLockIcon } from './icons';
import { useUser } from '../contexts/UserContext';

interface RoleEditorModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSave: (role: Role) => void;
  role: Role | null;
  allRoles: Role[];
}

const featureMap: Partial<Record<Permission, string>> = {
  'view:dashboard': 'Main Dashboard',
  'view:reporting': 'Reporting & Analytics',
  'export:reports': 'Export Reports',
  'view:agents': 'Agent Fleet Management',
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
};

const permissionGroups: { name: string; permissions: Permission[] }[] = [
  { name: 'General', permissions: ['view:dashboard', 'view:reporting', 'export:reports'] },
  { name: 'Administration', permissions: ['manage:settings', 'manage:rbac', 'manage:api_keys', 'view:finops', 'manage:tenants', 'view:profile'] },
  { name: 'Security', permissions: ['view:security', 'manage:security_cases', 'manage:security_playbooks', 'investigate:security', 'view:cloud_security', 'view:patching', 'manage:patches', 'view:threat_hunting'] },
  { name: 'Observability', permissions: ['view:agents', 'view:agent_logs', 'remediate:agents', 'view:assets', 'view:logs', 'view:insights', 'view:tracing', 'view:network'] },
  { name: 'AI Governance', permissions: ['view:ai_governance', 'manage:ai_risks'] },
  { name: 'Compliance', permissions: ['view:compliance', 'manage:compliance_evidence', 'view:audit_log'] },
  { name: 'Automation', permissions: ['view:automation', 'manage:automation'] },
  { name: 'Developer Tools', permissions: ['view:devsecops', 'view:developer_hub'] },
  { name: 'Advanced Platform', permissions: ['view:dspm', 'view:attack_path', 'view:service_catalog', 'view:dora_metrics', 'view:chaos'] },
];


export const RoleEditorModal: React.FC<RoleEditorModalProps> = ({ isOpen, onClose, onSave, role, allRoles }) => {
  const { currentUser, enabledFeatures } = useUser();
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [permissions, setPermissions] = useState<Set<Permission>>(new Set());
  const [nameError, setNameError] = useState<string | null>(null);

  useEffect(() => {
    if (role) {
      setName(role.name);
      setDescription(role.description);
      setPermissions(new Set(role.permissions));
    } else {
      setName('');
      setDescription('');
      setPermissions(new Set());
    }
    setNameError(null); // Reset error when modal opens or role changes
  }, [role, isOpen]);

  const handlePermissionChange = (permission: Permission, isChecked: boolean) => {
    setPermissions(prev => {
      const newSet = new Set(prev);
      if (isChecked) {
        newSet.add(permission);
      } else {
        newSet.delete(permission);
      }
      return newSet;
    });
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim()) return;

    // Validation for unique role name (case-insensitive)
    const isNameTaken = allRoles.some(
      r => r.name.toLowerCase() === name.trim().toLowerCase() && r.id !== role?.id
    );

    if (isNameTaken) {
      setNameError('A role with this name already exists.');
      return;
    }

    const roleToSave: Role = {
      id: role?.id || `role-${Date.now()}`,
      name: name.trim(),
      description: description.trim(),
      permissions: Array.from(permissions),
      isEditable: role?.isEditable ?? true,
      tenantId: role?.tenantId ?? 'custom',
    };
    onSave(roleToSave);
  };

  const availablePermissionGroups = useMemo(() => {
    // Super Admin sees all permissions, except for tenant management which is a special case not assignable to tenant roles.
    if (currentUser?.role === 'Super Admin') {
      return permissionGroups.map(group => ({
        ...group,
        permissions: group.permissions.filter(p => p !== 'manage:tenants')
      }));
    }

    // Tenant Admins only see permissions enabled for their tenant
    const tenantPermissions = new Set(enabledFeatures);
    return permissionGroups.map(group => ({
      ...group,
      permissions: group.permissions.filter(p => tenantPermissions.has(p))
    })).filter(group => group.permissions.length > 0);
  }, [enabledFeatures, currentUser]);

  if (!isOpen) return null;

  const isBuiltIn = role ? !role.isEditable : false;

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 z-50 flex justify-center items-center" onClick={onClose}>
      <div className="bg-white dark:bg-gray-800 rounded-lg shadow-xl w-full max-w-2xl p-6 m-4 max-h-[90vh] flex flex-col" onClick={e => e.stopPropagation()}>
        <div className="flex justify-between items-center mb-4 flex-shrink-0">
          <h2 className="text-xl font-bold text-gray-900 dark:text-white">{role ? `Edit Role: ${role.name}` : 'Create New Role'}</h2>
          <button onClick={onClose} className="p-1 rounded-full text-gray-400 hover:bg-gray-200 dark:hover:bg-gray-700 focus:outline-none">
            <XIcon size={20} />
          </button>
        </div>
        <form onSubmit={handleSubmit} className="flex-grow overflow-y-auto pr-2 -mr-2">
          {isBuiltIn && (
            <div className="p-3 mb-4 bg-blue-50 dark:bg-blue-900/50 rounded-lg flex items-start text-sm text-blue-800 dark:text-blue-300 border border-blue-200 dark:border-blue-800">
              <ShieldLockIcon size={18} className="mr-2.5 mt-0.5 flex-shrink-0 text-blue-500" />
              <div>
                <span className="font-semibold">This is a built-in role.</span>
                <p className="text-blue-700 dark:text-blue-400">Its name, description, and permissions cannot be modified to ensure system stability.</p>
              </div>
            </div>
          )}
          <div className="space-y-4">
            <div>
              <label htmlFor="name" className="block text-sm font-medium text-gray-700 dark:text-gray-300">Role Name</label>
              <input type="text" name="name" id="name" value={name}
                onChange={e => {
                  setName(e.target.value);
                  if (nameError) setNameError(null);
                }}
                required
                disabled={isBuiltIn}
                className={`mt-1 block w-full px-3 py-2 bg-white dark:bg-gray-700 border rounded-md shadow-sm sm:text-sm disabled:bg-gray-100 dark:disabled:bg-gray-700/50 ${nameError ? 'border-red-500 focus:ring-red-500 focus:border-red-500' : 'border-gray-300 dark:border-gray-600 focus:outline-none focus:ring-primary-500 focus:border-primary-500'}`}
              />
              {nameError && <p className="mt-1 text-xs text-red-500">{nameError}</p>}
            </div>
            <div>
              <label htmlFor="description" className="block text-sm font-medium text-gray-700 dark:text-gray-300">Description</label>
              <textarea name="description" id="description" value={description} onChange={e => setDescription(e.target.value)} rows={2} required disabled={isBuiltIn}
                className="mt-1 block w-full px-3 py-2 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-md shadow-sm focus:outline-none focus:ring-primary-500 focus:border-primary-500 sm:text-sm disabled:bg-gray-100 dark:disabled:bg-gray-700/50"
              ></textarea>
            </div>
            <div className="pt-2">
              <h3 className="text-sm font-medium text-gray-700 dark:text-gray-300">Permissions</h3>
              <div className="mt-2 space-y-4">
                {availablePermissionGroups.map(group => (
                  <div key={group.name} role="group" aria-labelledby={`group-label-${group.name}`} className="p-3 bg-gray-50 dark:bg-gray-700/50 rounded-lg border border-gray-200 dark:border-gray-600">
                    <h4 id={`group-label-${group.name}`} className="font-semibold text-sm text-gray-800 dark:text-gray-200 mb-2">{group.name}</h4>
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-4 gap-y-2">
                      {group.permissions.map(p => (
                        <label key={p} className={`flex items-center space-x-3 ${isBuiltIn ? 'cursor-not-allowed' : ''}`}>
                          <input
                            type="checkbox"
                            checked={permissions.has(p)}
                            onChange={e => handlePermissionChange(p, e.target.checked)}
                            disabled={isBuiltIn}
                            className="h-4 w-4 rounded border-gray-300 text-primary-600 focus:ring-primary-500 disabled:opacity-50"
                          />
                          <span className={`text-sm ${isBuiltIn ? 'text-gray-400 dark:text-gray-500' : 'text-gray-600 dark:text-gray-400'}`}>{featureMap[p]}</span>
                        </label>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
          <div className="mt-6 flex-shrink-0 flex justify-end space-x-3 pt-4 border-t border-gray-200 dark:border-gray-700">
            <button type="button" onClick={onClose}
              className="px-4 py-2 text-sm font-medium text-gray-700 bg-white dark:bg-gray-700 dark:text-gray-200 border border-gray-300 dark:border-gray-600 rounded-md shadow-sm hover:bg-gray-50 dark:hover:bg-gray-600 focus:outline-none"
            >
              Cancel
            </button>
            <button type="submit"
              disabled={isBuiltIn}
              className="px-4 py-2 text-sm font-medium text-white bg-primary-600 rounded-lg hover:bg-primary-700 focus:outline-none disabled:bg-primary-400/50 disabled:cursor-not-allowed"
            >
              {role ? 'Save Changes' : 'Create Role'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};

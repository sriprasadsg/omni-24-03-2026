import React, { useState, useEffect } from 'react';
import { Permission } from '../types';
import { AlertTriangleIcon } from './icons';
import { Modal } from './Modal';
import { ApiRole, RoleApiError, createRole, updateRole, fetchPermissionCatalogue } from '../services/roleApi';
import { showToast } from '../utils/toast';

interface RoleEditorModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSave: (saved: ApiRole) => void;
  role: ApiRole | null;
  allRoles: ApiRole[];
  tenantId?: string | null;
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

export const RoleEditorModal: React.FC<RoleEditorModalProps> = ({ isOpen, onClose, onSave, role, allRoles, tenantId }) => {
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [available, setAvailable] = useState<string[]>([]);
  const [nameError, setNameError] = useState<string | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    setName(role ? role.name : '');
    setDescription(role ? role.description : '');
    setSelected(new Set(role ? role.permissions : []));
    setNameError(null);
    setSaveError(null);
    setSaving(false);
  }, [role, isOpen]);

  useEffect(() => {
    if (!isOpen) return;
    let cancelled = false;
    fetchPermissionCatalogue(tenantId ?? undefined)
      .then(c => { if (!cancelled) setAvailable(c.permissions); })
      .catch(() => { if (!cancelled) setAvailable([]); });
    return () => { cancelled = true; };
  }, [isOpen, tenantId]);

  const toggle = (permission: string, checked: boolean) => {
    setSelected(prev => {
      const next = new Set(prev);
      if (checked) next.add(permission); else next.delete(permission);
      return next;
    });
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (saving || !name.trim()) return;
    const duplicate = allRoles.some(r => r.name.toLowerCase() === name.trim().toLowerCase() && r.id !== role?.id);
    if (duplicate) {
      setNameError('A role with this name already exists.');
      return;
    }
    const permissions = Array.from(selected);
    setSaving(true);
    setSaveError(null);
    try {
      const saved = role
        ? await updateRole(role.id, { description: description.trim(), permissions }, tenantId ?? undefined)
        : await createRole({ name: name.trim(), description: description.trim(), permissions, tenantId: tenantId ?? undefined });
      onSave(saved);
      showToast(`Role "${saved.name}" saved.`, 'success');
    } catch (err) {
      const message = err instanceof Error ? err.message : '';
      if (err instanceof RoleApiError && err.status === 409 && message) {
        setNameError(message);
      } else {
        setSaveError(message
          ? `Couldn't save the role: ${message}. Your changes are still here, fix the issue and try again.`
          : "Couldn't save the role. Check your connection and try again.");
      }
    } finally {
      setSaving(false);
    }
  };

  const footer = (
    <>
      <button type="button" onClick={onClose}
        className="px-4 py-2 text-sm font-medium text-gray-700 bg-white dark:bg-gray-700 dark:text-gray-200 border border-gray-300 dark:border-gray-600 rounded-md shadow-sm hover:bg-gray-50 dark:hover:bg-gray-600 focus:outline-none"
      >
        Cancel
      </button>
      <button type="submit" form="role-editor-form" disabled={saving}
        className="px-4 py-2 text-sm font-medium text-white bg-primary-600 rounded-lg hover:bg-primary-700 focus:outline-none disabled:bg-primary-400/50 disabled:cursor-not-allowed"
      >
        {saving ? 'Saving...' : role ? 'Save Changes' : 'Create Role'}
      </button>
    </>
  );

  return (
    <Modal isOpen={isOpen} onClose={onClose} title={role ? `Edit Role: ${role.name}` : 'Create New Role'} size="2xl" footer={footer}>
      <form id="role-editor-form" onSubmit={handleSubmit}>
        <div className="space-y-4">
          <div>
            <label htmlFor="name" className="block text-sm font-medium text-gray-700 dark:text-gray-300">Role Name</label>
            <input type="text" name="name" id="name" value={name}
              onChange={e => { setName(e.target.value); if (nameError) setNameError(null); }}
              required disabled={!!role || saving}
              aria-describedby={role ? 'name-help' : undefined}
              className={`mt-1 block w-full px-3 py-2 bg-white dark:bg-gray-700 border rounded-md shadow-sm sm:text-sm overflow-x-auto disabled:bg-gray-100 dark:disabled:bg-gray-700/50 ${nameError ? 'border-red-500 focus:ring-red-500 focus:border-red-500' : 'border-gray-300 dark:border-gray-600 focus:outline-none focus:ring-primary-500 focus:border-primary-500'}`}
            />
            {role && <p id="name-help" className="mt-1 text-xs text-gray-500 dark:text-gray-400">A role's name can't be changed. To rename, create a new role and reassign its users.</p>}
            {nameError && <p role="alert" className="mt-1 text-xs text-red-500">{nameError}</p>}
          </div>
          <div>
            <label htmlFor="description" className="block text-sm font-medium text-gray-700 dark:text-gray-300">Description</label>
            <textarea name="description" id="description" value={description} onChange={e => setDescription(e.target.value)} rows={2} required disabled={saving}
              className="mt-1 block w-full px-3 py-2 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-md shadow-sm focus:outline-none focus:ring-primary-500 focus:border-primary-500 sm:text-sm disabled:bg-gray-100 dark:disabled:bg-gray-700/50"
            ></textarea>
          </div>
          <div className="pt-2">
            <h3 className="text-sm font-medium text-gray-700 dark:text-gray-300">Permissions</h3>
            <div className="mt-2 grid grid-cols-1 sm:grid-cols-2 gap-x-4 gap-y-2">
              {available.map(p => (
                <label key={p} className="flex items-center space-x-3">
                  <input type="checkbox" checked={selected.has(p)} onChange={e => toggle(p, e.target.checked)} disabled={saving}
                    className="h-4 w-4 rounded border-gray-300 text-primary-600 focus:ring-primary-500 disabled:opacity-50" />
                  {featureMap[p as Permission]
                    ? <span className="text-sm text-gray-600 dark:text-gray-400">{featureMap[p as Permission]}</span>
                    : <span className="font-mono text-xs text-gray-600 dark:text-gray-400">{p}</span>}
                </label>
              ))}
            </div>
          </div>
          {saveError && (
            <div role="alert" className="rounded-lg border border-red-200 bg-red-50 text-red-700 dark:border-red-900/50 dark:bg-red-900/20 dark:text-red-300 p-3 text-sm flex items-start">
              <AlertTriangleIcon size={16} className="mr-2 mt-0.5 flex-shrink-0" />
              <span>{saveError}</span>
            </div>
          )}
        </div>
      </form>
    </Modal>
  );
};

import React, { useState, useEffect } from 'react';
import { authFetch } from '../services/apiService';
import { Tenant, Permission, SubscriptionTier } from '../types';
import { TrashIcon } from './icons';
import { SUBSCRIPTION_TIERS } from '../constants';
import { Modal } from './Modal';
import { TenantLicensePanel } from './TenantLicensePanel';
import { TenantEnrollmentKeysPanel } from './TenantEnrollmentKeysPanel';
import { TenantAllowlistPanel } from './TenantAllowlistPanel';
import featureSwitches from '../shared/tenant-feature-switches.json';

interface ManageTenantModalProps {
  isOpen: boolean;
  onClose: () => void;
  tenant: Tenant | null;
  onSave: (tenantId: string, updates: { features: Permission[], tier: SubscriptionTier, purchasedFrameworks: string[] }) => void;
  onDelete: (tenantId: string) => void;
}

// The tenant feature switches (spec C6): one list, also read by the server
// (backend/tenant_features.py), which removes switched-off features from every
// user of the tenant. A feature with a parent only counts while its parent is on.
type FeatureSwitch = { permission: string; label: string; parent?: string };
const permissionGroups: { name: string; features: FeatureSwitch[] }[] = featureSwitches.groups;
const switchByPermission = new Map(permissionGroups.flatMap(g => g.features).map(f => [f.permission, f]));
const allToggleableFeatures = [...switchByPermission.keys()];

export const ManageTenantModal: React.FC<ManageTenantModalProps> = ({ isOpen, onClose, tenant, onSave, onDelete }) => {
  const [enabledFeatures, setEnabledFeatures] = useState<Set<string>>(new Set());
  const [currentTier, setCurrentTier] = useState<SubscriptionTier>('Custom');
  const [dynamicServices, setDynamicServices] = useState<any[]>([]);
  // Compliance frameworks the tenant purchased: kept apart from the price list, so a
  // failed price fetch can never clear them on save.
  const [purchased, setPurchased] = useState<Set<string>>(new Set());
  const [frameworkQuery, setFrameworkQuery] = useState('');

  useEffect(() => {
    if (tenant) {
      setEnabledFeatures(new Set(tenant.enabledFeatures || []));
      setCurrentTier(tenant.subscriptionTier);
      setPurchased(new Set(tenant.purchasedFrameworks || []));
    }
  }, [tenant]);

  // Fetch dynamic services
  useEffect(() => {
    const fetchServices = async () => {
      try {
        const res = await authFetch('/api/finops/pricing');
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
      onSave(tenant.id, { features: Array.from(finalFeatures) as Permission[], tier: currentTier, purchasedFrameworks: Array.from(purchased) });
    }
  };

  const handleDelete = () => {
    if (tenant) {
      if (window.confirm(`Are you sure you want to delete the tenant "${tenant.name}"? This action is irreversible and will permanently delete all associated data.`)) {
        onDelete(tenant.id);
      }
    }
  }

  if (!tenant) return null;

  const allSelected = allToggleableFeatures.every(f => enabledFeatures.has(f));
  // Per-framework prices come from Service Pricing Configuration (entries with a frameworkId).
  const billableServices = dynamicServices.filter(service => !service.frameworkId);
  const frameworkPrices = dynamicServices.filter(service => service.frameworkId);
  const shownFrameworks = frameworkPrices.filter(f => f.name.toLowerCase().includes(frameworkQuery.trim().toLowerCase()));
  const monthlyFrameworkTotal = frameworkPrices.filter(f => purchased.has(f.frameworkId)).reduce((sum, f) => sum + Number(f.price || 0), 0);
  const togglePurchased = (frameworkId: string) => setPurchased(prev => {
    const next = new Set(prev);
    if (next.has(frameworkId)) next.delete(frameworkId); else next.add(frameworkId);
    return next;
  });

  const footer = (
    <>
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
    </>
  );

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title={<>Manage Tenant: <span className="text-primary-600 dark:text-primary-400">{tenant.name}</span></>}
      size="2xl"
      footer={footer}
    >
        <div className="space-y-4">
          <TenantLicensePanel tenantId={tenant.id} />
          {/* Tenant Management is super-admin only, so these panels can manage (spec C4). */}
          <TenantEnrollmentKeysPanel tenantId={tenant.id} canManage />
          <TenantAllowlistPanel tenantId={tenant.id} canManage />
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
            {billableServices.length > 0 && (
              <div className="mb-6">
                <h3 className="text-sm font-bold text-gray-800 dark:text-white mb-2 flex items-center">
                  <span className="bg-green-100 text-green-800 text-xs font-semibold mr-2 px-2.5 py-0.5 rounded dark:bg-green-900 dark:text-green-300">Add-on</span>
                  Billable Services
                </h3>
                <div className="p-3 bg-green-50 dark:bg-gray-700/50 rounded-lg border border-green-200 dark:border-gray-600">
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-4 gap-y-2">
                    {billableServices.map(service => {
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

            <div className="mb-6">
              <h3 className="text-sm font-bold text-gray-800 dark:text-white mb-1">Compliance Frameworks</h3>
              <p className="text-xs text-gray-500 dark:text-gray-400 mb-2">
                Tick the frameworks this tenant purchased. Each is billed monthly at its price in Service Pricing
                Configuration, and the tenant's users see only the ticked frameworks.
              </p>
              <div className="flex flex-wrap items-center gap-2 mb-2">
                <input
                  type="search"
                  value={frameworkQuery}
                  onChange={e => setFrameworkQuery(e.target.value)}
                  placeholder="Search frameworks"
                  aria-label="Search frameworks"
                  className="flex-1 min-w-[10rem] px-3 py-1.5 text-sm bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-md dark:text-white"
                />
                <button type="button" onClick={() => setPurchased(new Set(frameworkPrices.map(f => f.frameworkId)))}
                  className="px-2 py-1 text-xs border border-gray-300 dark:border-gray-600 rounded-md text-gray-700 dark:text-gray-200">Select all</button>
                <button type="button" onClick={() => setPurchased(new Set())}
                  className="px-2 py-1 text-xs border border-gray-300 dark:border-gray-600 rounded-md text-gray-700 dark:text-gray-200">Clear</button>
              </div>
              <p className="text-xs font-medium text-gray-700 dark:text-gray-300 mb-2" aria-live="polite">
                {purchased.size} selected · ${monthlyFrameworkTotal.toFixed(2)} / month
              </p>
              <div className="p-3 bg-gray-50 dark:bg-gray-700/50 rounded-lg border border-gray-200 dark:border-gray-600 max-h-64 overflow-y-auto">
                {frameworkPrices.length === 0 ? (
                  <p className="text-sm text-gray-500 dark:text-gray-400">Framework prices could not be loaded. Purchases are unchanged.</p>
                ) : (
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-4 gap-y-2">
                    {shownFrameworks.map(framework => (
                      <label key={framework.frameworkId} className="flex items-center space-x-3">
                        <input
                          type="checkbox"
                          checked={purchased.has(framework.frameworkId)}
                          onChange={() => togglePurchased(framework.frameworkId)}
                          className="h-4 w-4 rounded border-gray-300 text-primary-600 focus:ring-primary-500"
                        />
                        <span className="flex flex-col">
                          <span className="text-sm text-gray-800 dark:text-gray-200">{framework.name}</span>
                          <span className="text-xs text-gray-500 dark:text-gray-400">${Number(framework.price).toFixed(2)} / month</span>
                        </span>
                      </label>
                    ))}
                  </div>
                )}
              </div>
            </div>

            <h3 className="text-sm font-medium text-gray-500 dark:text-gray-400 mb-1">Standard Features</h3>
            <p className="text-xs text-gray-500 dark:text-gray-400 mb-2">
              Switched-off features are removed for everyone in this tenant, in the menu and in the API, within 30 seconds.
              Only Overview, Tickets, AI Assistant, My Tasks and Notification Prefs follow the user's role alone.
            </p>
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
                    {group.features.map(feature => {
                      const parentOff = !!feature.parent && !enabledFeatures.has(feature.parent);
                      return (
                        <label key={feature.permission} className={`flex items-center space-x-3 ${parentOff ? 'opacity-50' : ''}`}
                          title={parentOff ? `Needs ${switchByPermission.get(feature.parent!)?.label ?? feature.parent}` : undefined}>
                          <input
                            type="checkbox"
                            checked={enabledFeatures.has(feature.permission) && !parentOff}
                            disabled={parentOff}
                            onChange={() => handleFeatureToggle(feature.permission)}
                            className="h-4 w-4 rounded border-gray-300 text-primary-600 focus:ring-primary-500"
                          />
                          <span className="text-sm text-gray-600 dark:text-gray-400">{feature.label}</span>
                        </label>
                      );
                    })}
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
    </Modal>
  );
};

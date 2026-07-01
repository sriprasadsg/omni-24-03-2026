import React, { useState, useEffect, useCallback } from 'react';
import { apiService } from '../services/apiService';

interface ProtectionPolicy {
  id: string;
  name: string;
  description: string;
  platform: string;
  require_pin: boolean;
  pin_length: number;
  block_copy_paste: boolean;
  block_screenshots: boolean;
  block_backup: boolean;
  require_managed_browser: boolean;
  wipe_on_jailbreak: boolean;
  enabled: boolean;
  assigned_apps: string[];
  assigned_groups: string[];
}

interface ConfigPolicy {
  id: string;
  name: string;
  description: string;
  platform: string;
  target_app: string;
  config_items: { key: string; value: string; value_type: string }[];
  enabled: boolean;
}

interface ManagedApp {
  id: string;
  app_name: string;
  platform: string;
  bundle_id: string;
  wipe_pending?: boolean;
}

const TABS = ['protection', 'config', 'apps'] as const;
type Tab = typeof TABS[number];

const Toggle = ({ checked, onChange }: { checked: boolean; onChange: (v: boolean) => void }) => (
  <button
    onClick={() => onChange(!checked)}
    className={`relative inline-flex h-5 w-9 items-center rounded-full transition-colors ${checked ? 'bg-blue-600' : 'bg-slate-600'}`}
  >
    <span className={`inline-block h-3.5 w-3.5 transform rounded-full bg-white transition-transform ${checked ? 'translate-x-5' : 'translate-x-1'}`} />
  </button>
);

export default function MAMDashboard() {
  const [tab, setTab] = useState<Tab>('protection');
  const [protectionPolicies, setProtectionPolicies] = useState<ProtectionPolicy[]>([]);
  const [configPolicies, setConfigPolicies] = useState<ConfigPolicy[]>([]);
  const [managedApps, setManagedApps] = useState<ManagedApp[]>([]);
  const [loading, setLoading] = useState(false);
  const [showCreateProtection, setShowCreateProtection] = useState(false);
  const [showCreateConfig, setShowCreateConfig] = useState(false);
  const [wiping, setWiping] = useState<string | null>(null);

  const [newProtection, setNewProtection] = useState({
    name: '', description: '', platform: 'all',
    require_pin: true, pin_length: 6, block_copy_paste: false,
    block_screenshots: false, block_backup: false,
    require_managed_browser: false, wipe_on_jailbreak: true, wipe_after_failed_pins: 10,
  });

  const [newConfig, setNewConfig] = useState({
    name: '', description: '', platform: 'all', target_app: '',
    config_items: [{ key: '', value: '', value_type: 'string' }],
  });

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const [prot, conf, apps] = await Promise.all([
        apiService.get('/api/mam/protection-policies'),
        apiService.get('/api/mam/config-policies'),
        apiService.get('/api/mam/managed-apps'),
      ]);
      setProtectionPolicies(Array.isArray(prot) ? prot : []);
      setConfigPolicies(Array.isArray(conf) ? conf : []);
      setManagedApps(Array.isArray(apps) ? apps : []);
    } catch {
      // empty state
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { loadData(); }, [loadData]);

  const createProtectionPolicy = async () => {
    try {
      const created = await apiService.post('/api/mam/protection-policies', newProtection);
      setProtectionPolicies(prev => [created, ...prev]);
      setShowCreateProtection(false);
    } catch { /* error */ }
  };

  const createConfigPolicy = async () => {
    try {
      const created = await apiService.post('/api/mam/config-policies', newConfig);
      setConfigPolicies(prev => [created, ...prev]);
      setShowCreateConfig(false);
    } catch { /* error */ }
  };

  const wipeApp = async (appId: string) => {
    setWiping(appId);
    try {
      await apiService.post(`/api/mam/managed-apps/${appId}/wipe-data`, {});
      setManagedApps(prev => prev.map(a => a.id === appId ? { ...a, wipe_pending: true } : a));
    } finally {
      setWiping(null);
    }
  };

  const PLATFORMS = ['all', 'ios', 'android', 'windows'];

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">Mobile Application Management</h1>
          <p className="text-slate-400 text-sm mt-1">App protection policies, configuration policies, and corporate data protection</p>
        </div>
        <button
          onClick={() => tab === 'protection' ? setShowCreateProtection(true) : tab === 'config' ? setShowCreateConfig(true) : undefined}
          className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg text-sm"
        >
          + New Policy
        </button>
      </div>

      <div className="flex border border-slate-700 rounded-lg overflow-hidden w-fit">
        {TABS.map(t => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`px-4 py-2 text-sm font-medium transition-colors ${tab === t ? 'bg-blue-600 text-white' : 'text-slate-400 hover:text-white hover:bg-slate-700'}`}
          >
            {t === 'protection' ? `Protection Policies (${protectionPolicies.length})` :
             t === 'config' ? `Config Policies (${configPolicies.length})` :
             `Managed Apps (${managedApps.length})`}
          </button>
        ))}
      </div>

      {loading ? <div className="text-slate-400 text-center py-12">Loading...</div> : (
        <>
          {tab === 'protection' && (
            <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
              {protectionPolicies.length === 0 && (
                <div className="col-span-full text-slate-400 text-center py-12">No protection policies yet</div>
              )}
              {protectionPolicies.map(policy => (
                <div key={policy.id} className="bg-slate-800 rounded-xl border border-slate-700 p-5">
                  <div className="flex items-start justify-between mb-3">
                    <div>
                      <h3 className="text-white font-semibold">{policy.name}</h3>
                      <span className="text-slate-400 text-xs">{policy.platform}</span>
                    </div>
                    <span className={`px-2 py-0.5 rounded text-xs ${policy.enabled ? 'bg-green-900/50 text-green-300' : 'bg-slate-700 text-slate-400'}`}>
                      {policy.enabled ? 'Enabled' : 'Disabled'}
                    </span>
                  </div>
                  <div className="space-y-1.5 text-sm">
                    {[
                      ['PIN Required', policy.require_pin],
                      ['Block Copy/Paste', policy.block_copy_paste],
                      ['Block Screenshots', policy.block_screenshots],
                      ['Block Backup', policy.block_backup],
                      ['Managed Browser', policy.require_managed_browser],
                      ['Wipe on Jailbreak', policy.wipe_on_jailbreak],
                    ].map(([label, val]) => (
                      <div key={label as string} className="flex justify-between text-slate-300">
                        <span>{label as string}</span>
                        <span className={val ? 'text-green-400' : 'text-slate-500'}>{val ? 'On' : 'Off'}</span>
                      </div>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          )}

          {tab === 'config' && (
            <div className="space-y-3">
              {configPolicies.length === 0 && (
                <div className="text-slate-400 text-center py-12">No configuration policies yet</div>
              )}
              {configPolicies.map(policy => (
                <div key={policy.id} className="bg-slate-800 rounded-xl border border-slate-700 p-5">
                  <div className="flex items-center justify-between mb-3">
                    <div>
                      <h3 className="text-white font-semibold">{policy.name}</h3>
                      <span className="text-slate-400 text-xs">{policy.target_app || 'All apps'} · {policy.platform}</span>
                    </div>
                    <span className={`px-2 py-0.5 rounded text-xs ${policy.enabled ? 'bg-green-900/50 text-green-300' : 'bg-slate-700 text-slate-400'}`}>
                      {policy.config_items?.length || 0} settings
                    </span>
                  </div>
                  <div className="space-y-1">
                    {(policy.config_items || []).map((item, i) => (
                      <div key={i} className="flex gap-4 text-sm font-mono">
                        <span className="text-blue-400">{item.key}</span>
                        <span className="text-slate-400">=</span>
                        <span className="text-slate-300">{item.value}</span>
                      </div>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          )}

          {tab === 'apps' && (
            <div className="bg-slate-800 rounded-xl border border-slate-700 overflow-hidden">
              {managedApps.length === 0 ? (
                <div className="text-slate-400 text-center py-12">No managed apps enrolled</div>
              ) : (
                <table className="w-full text-sm">
                  <thead className="border-b border-slate-700">
                    <tr className="text-left text-slate-400">
                      <th className="px-4 py-3">App Name</th>
                      <th className="px-4 py-3">Platform</th>
                      <th className="px-4 py-3">Bundle ID</th>
                      <th className="px-4 py-3">Status</th>
                      <th className="px-4 py-3">Action</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-700/50">
                    {managedApps.map(app => (
                      <tr key={app.id} className="hover:bg-slate-700/30">
                        <td className="px-4 py-3 text-white font-medium">{app.app_name}</td>
                        <td className="px-4 py-3 text-slate-300">{app.platform}</td>
                        <td className="px-4 py-3 text-slate-400 font-mono text-xs">{app.bundle_id}</td>
                        <td className="px-4 py-3">
                          {app.wipe_pending ? (
                            <span className="px-2 py-0.5 rounded text-xs bg-orange-900/50 text-orange-300">Wipe Pending</span>
                          ) : (
                            <span className="px-2 py-0.5 rounded text-xs bg-green-900/50 text-green-300">Active</span>
                          )}
                        </td>
                        <td className="px-4 py-3">
                          <button
                            onClick={() => wipeApp(app.id)}
                            disabled={wiping === app.id || app.wipe_pending}
                            className="px-3 py-1 bg-red-700 hover:bg-red-600 text-white rounded text-xs disabled:opacity-50"
                          >
                            {wiping === app.id ? 'Wiping...' : 'Selective Wipe'}
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          )}
        </>
      )}

      {showCreateProtection && (
        <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50">
          <div className="bg-slate-800 rounded-xl border border-slate-700 p-6 w-full max-w-lg">
            <h2 className="text-white font-bold text-lg mb-4">New Protection Policy</h2>
            <div className="space-y-4">
              <input value={newProtection.name} onChange={e => setNewProtection(p => ({ ...p, name: e.target.value }))}
                placeholder="Policy name" className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded-lg text-white text-sm" />
              <select value={newProtection.platform} onChange={e => setNewProtection(p => ({ ...p, platform: e.target.value }))}
                className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded-lg text-white text-sm">
                {PLATFORMS.map(pl => <option key={pl} value={pl}>{pl}</option>)}
              </select>
              <div className="space-y-3">
                {([
                  ['require_pin', 'Require PIN'],
                  ['block_copy_paste', 'Block Copy/Paste'],
                  ['block_screenshots', 'Block Screenshots'],
                  ['block_backup', 'Block Backup'],
                  ['require_managed_browser', 'Require Managed Browser'],
                  ['wipe_on_jailbreak', 'Wipe on Jailbreak/Root'],
                ] as [keyof typeof newProtection, string][]).map(([key, label]) => (
                  <div key={key} className="flex items-center justify-between">
                    <span className="text-slate-300 text-sm">{label}</span>
                    <Toggle checked={!!newProtection[key]} onChange={v => setNewProtection(p => ({ ...p, [key]: v }))} />
                  </div>
                ))}
              </div>
            </div>
            <div className="flex gap-3 mt-6">
              <button onClick={createProtectionPolicy} className="flex-1 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg text-sm">Create</button>
              <button onClick={() => setShowCreateProtection(false)} className="flex-1 py-2 bg-slate-700 hover:bg-slate-600 text-white rounded-lg text-sm">Cancel</button>
            </div>
          </div>
        </div>
      )}

      {showCreateConfig && (
        <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50">
          <div className="bg-slate-800 rounded-xl border border-slate-700 p-6 w-full max-w-lg">
            <h2 className="text-white font-bold text-lg mb-4">New Config Policy</h2>
            <div className="space-y-4">
              <input value={newConfig.name} onChange={e => setNewConfig(p => ({ ...p, name: e.target.value }))}
                placeholder="Policy name" className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded-lg text-white text-sm" />
              <input value={newConfig.target_app} onChange={e => setNewConfig(p => ({ ...p, target_app: e.target.value }))}
                placeholder="Target app (bundle ID or name)" className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded-lg text-white text-sm" />
              <div className="space-y-2">
                <label className="text-slate-400 text-xs">Configuration Items</label>
                {newConfig.config_items.map((item, i) => (
                  <div key={i} className="flex gap-2">
                    <input value={item.key} onChange={e => setNewConfig(p => ({ ...p, config_items: p.config_items.map((ci, idx) => idx === i ? { ...ci, key: e.target.value } : ci) }))}
                      placeholder="Key" className="flex-1 px-3 py-2 bg-slate-700 border border-slate-600 rounded-lg text-white text-sm" />
                    <input value={item.value} onChange={e => setNewConfig(p => ({ ...p, config_items: p.config_items.map((ci, idx) => idx === i ? { ...ci, value: e.target.value } : ci) }))}
                      placeholder="Value" className="flex-1 px-3 py-2 bg-slate-700 border border-slate-600 rounded-lg text-white text-sm" />
                  </div>
                ))}
                <button onClick={() => setNewConfig(p => ({ ...p, config_items: [...p.config_items, { key: '', value: '', value_type: 'string' }] }))}
                  className="text-blue-400 text-xs hover:underline">+ Add item</button>
              </div>
            </div>
            <div className="flex gap-3 mt-6">
              <button onClick={createConfigPolicy} className="flex-1 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg text-sm">Create</button>
              <button onClick={() => setShowCreateConfig(false)} className="flex-1 py-2 bg-slate-700 hover:bg-slate-600 text-white rounded-lg text-sm">Cancel</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

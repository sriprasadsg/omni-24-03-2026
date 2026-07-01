import React, { useState, useEffect, useCallback } from 'react';
import { Cookie, Settings, BarChart2, Shield, Save, ToggleLeft, ToggleRight } from 'lucide-react';

interface CookieItem { name: string; provider: string; purpose: string; expiry: string; }
interface Category { id: string; name: string; description: string; required: boolean; cookies: CookieItem[]; }
interface Config { tenantId: string; categories: Category[]; version: string; bannerTitle: string; bannerText: string; privacyPolicyUrl: string; }
interface Stats { total: number; byCategory: Record<string, number>; byCategoryPct: Record<string, number>; fullConsent: number; fullConsentPct: number; necessaryOnly: number; }

const authHeader = () => ({ Authorization: `Bearer ${localStorage.getItem('token')}`, 'Content-Type': 'application/json' });

export default function CookieConsentDashboard() {
  const [config, setConfig] = useState<Config | null>(null);
  const [stats, setStats] = useState<Stats | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [activeTab, setActiveTab] = useState<'overview' | 'config' | 'records'>('overview');
  const [records, setRecords] = useState<any[]>([]);

  const tenantId = (() => {
    try { const t = localStorage.getItem('token'); if (!t) return ''; const p = JSON.parse(atob(t.split('.')[1])); return p.tenant_id || ''; } catch { return ''; }
  })();

  const fetchAll = useCallback(async () => {
    setLoading(true);
    try {
      const [cfgRes, statsRes] = await Promise.all([
        fetch(`/api/cookie-consent/config?tenant_id=${tenantId}`, { headers: authHeader() }),
        fetch('/api/cookie-consent/stats', { headers: authHeader() }),
      ]);
      if (cfgRes.ok) setConfig(await cfgRes.json());
      if (statsRes.ok) setStats(await statsRes.json());
    } finally { setLoading(false); }
  }, [tenantId]);

  useEffect(() => { fetchAll(); }, [fetchAll]);

  const fetchRecords = async () => {
    const res = await fetch('/api/cookie-consent/records', { headers: authHeader() });
    if (res.ok) setRecords(await res.json());
  };

  useEffect(() => { if (activeTab === 'records') fetchRecords(); }, [activeTab]);

  const saveConfig = async () => {
    if (!config) return;
    setSaving(true);
    try {
      const res = await fetch('/api/cookie-consent/config', { method: 'PUT', headers: authHeader(), body: JSON.stringify(config) });
      if (res.ok) setConfig(await res.json());
    } finally { setSaving(false); }
  };

  const updateCategory = (idx: number, patch: Partial<Category>) => {
    if (!config) return;
    setConfig({ ...config, categories: config.categories.map((c, i) => i === idx ? { ...c, ...patch } : c) });
  };

  if (loading) return <div className="flex justify-center py-12"><div className="w-8 h-8 border-4 border-primary-500 border-t-transparent rounded-full animate-spin" /></div>;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="text-xl font-semibold text-gray-900 dark:text-white flex items-center gap-2">
          <Cookie className="w-5 h-5 text-primary-500" /> Cookie Consent Management
        </h2>
      </div>

      {stats && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          {[
            { label: 'Total Consents', value: stats.total },
            { label: 'Full Consent', value: `${stats.fullConsentPct}%` },
            { label: 'Necessary Only', value: stats.necessaryOnly },
            { label: 'Categories', value: config?.categories.length || 0 },
          ].map(({ label, value }) => (
            <div key={label} className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-4">
              <p className="text-xs text-gray-500 dark:text-gray-400">{label}</p>
              <p className="text-2xl font-bold text-gray-900 dark:text-white mt-1">{value}</p>
            </div>
          ))}
        </div>
      )}

      {stats && stats.byCategoryPct && Object.keys(stats.byCategoryPct).length > 0 && (
        <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-5">
          <h3 className="font-medium text-gray-900 dark:text-white mb-4 flex items-center gap-2"><BarChart2 className="w-4 h-4 text-primary-500" /> Consent Rate by Category</h3>
          <div className="space-y-3">
            {Object.entries(stats.byCategoryPct).map(([cat, pct]) => (
              <div key={cat}>
                <div className="flex justify-between text-sm mb-1">
                  <span className="text-gray-700 dark:text-gray-300 capitalize">{cat}</span>
                  <span className="text-gray-500 dark:text-gray-400">{pct}%</span>
                </div>
                <div className="h-2 bg-gray-200 dark:bg-gray-700 rounded-full overflow-hidden">
                  <div className="h-full bg-primary-500 rounded-full transition-all" style={{ width: `${pct}%` }} />
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="flex gap-1 border-b border-gray-200 dark:border-gray-700">
        {(['overview', 'config', 'records'] as const).map(tab => (
          <button key={tab} onClick={() => setActiveTab(tab)} className={`px-4 py-2 text-sm font-medium capitalize border-b-2 -mb-px transition-colors ${activeTab === tab ? 'border-primary-500 text-primary-600 dark:text-primary-400' : 'border-transparent text-gray-500 hover:text-gray-700 dark:hover:text-gray-300'}`}>{tab}</button>
        ))}
      </div>

      {activeTab === 'config' && config && (
        <div className="space-y-5">
          <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-5 space-y-4">
            <h3 className="font-medium text-gray-900 dark:text-white">Banner Settings</h3>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-xs text-gray-500 dark:text-gray-400 mb-1">Banner Title</label>
                <input value={config.bannerTitle} onChange={e => setConfig({ ...config, bannerTitle: e.target.value })} className="w-full px-3 py-2 text-sm border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-white rounded-lg" />
              </div>
              <div>
                <label className="block text-xs text-gray-500 dark:text-gray-400 mb-1">Privacy Policy URL</label>
                <input value={config.privacyPolicyUrl} onChange={e => setConfig({ ...config, privacyPolicyUrl: e.target.value })} className="w-full px-3 py-2 text-sm border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-white rounded-lg" placeholder="https://…" />
              </div>
              <div className="col-span-2">
                <label className="block text-xs text-gray-500 dark:text-gray-400 mb-1">Banner Text</label>
                <textarea value={config.bannerText} onChange={e => setConfig({ ...config, bannerText: e.target.value })} rows={2} className="w-full px-3 py-2 text-sm border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-white rounded-lg" />
              </div>
            </div>
          </div>
          <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-5">
            <h3 className="font-medium text-gray-900 dark:text-white mb-4">Cookie Categories</h3>
            <div className="space-y-4">
              {config.categories.map((cat, idx) => (
                <div key={cat.id} className="p-4 bg-gray-50 dark:bg-gray-700/40 rounded-lg">
                  <div className="flex items-start justify-between">
                    <div className="flex-1">
                      <div className="flex items-center gap-2">
                        <Shield className="w-4 h-4 text-primary-500" />
                        <span className="font-medium text-gray-900 dark:text-white text-sm">{cat.name}</span>
                        {cat.required && <span className="text-xs bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-400 px-2 py-0.5 rounded-full">Required</span>}
                      </div>
                      <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">{cat.description}</p>
                    </div>
                    {!cat.required && (
                      <button onClick={() => updateCategory(idx, { required: !cat.required })} className="ml-3 text-gray-400 hover:text-primary-500">
                        {cat.required ? <ToggleRight className="w-5 h-5" /> : <ToggleLeft className="w-5 h-5" />}
                      </button>
                    )}
                  </div>
                  <div className="mt-2 space-y-1">
                    {cat.cookies.map((ck, ci) => (
                      <div key={ci} className="text-xs text-gray-500 dark:text-gray-400 flex gap-3 pl-6">
                        <span className="font-mono">{ck.name}</span>
                        <span>{ck.provider}</span>
                        <span className="text-gray-400">{ck.expiry}</span>
                      </div>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          </div>
          <button onClick={saveConfig} disabled={saving} className="flex items-center gap-2 px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 disabled:opacity-50 text-sm">
            <Save className="w-4 h-4" />{saving ? 'Saving…' : 'Save Configuration'}
          </button>
        </div>
      )}

      {activeTab === 'records' && (
        <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 overflow-hidden">
          <table className="min-w-full divide-y divide-gray-200 dark:divide-gray-700 text-sm">
            <thead className="bg-gray-50 dark:bg-gray-900/50">
              <tr>
                {['Session ID', 'Consented Categories', 'IP', 'Date'].map(h => (
                  <th key={h} className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-200 dark:divide-gray-700">
              {records.length === 0 ? (
                <tr><td colSpan={4} className="text-center py-8 text-gray-400 dark:text-gray-500 text-sm">No consent records yet.</td></tr>
              ) : records.slice(0, 100).map(r => (
                <tr key={r.id} className="hover:bg-gray-50 dark:hover:bg-gray-700/30">
                  <td className="px-4 py-3 font-mono text-xs text-gray-500 dark:text-gray-400">{r.sessionId?.slice(0, 12)}…</td>
                  <td className="px-4 py-3 text-xs">{(r.consentedCategories || []).join(', ') || <span className="text-gray-400 italic">none</span>}</td>
                  <td className="px-4 py-3 text-xs text-gray-500 dark:text-gray-400">{r.ipAddress}</td>
                  <td className="px-4 py-3 text-xs text-gray-500 dark:text-gray-400">{r.created_at ? new Date(r.created_at).toLocaleDateString() : ''}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {activeTab === 'overview' && config && (
        <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-5">
          <h3 className="font-medium text-gray-900 dark:text-white mb-3">Active Configuration</h3>
          <div className="grid grid-cols-2 gap-3 text-sm">
            <div><span className="text-gray-500 dark:text-gray-400">Version:</span> <span className="text-gray-900 dark:text-white ml-1">{config.version}</span></div>
            <div><span className="text-gray-500 dark:text-gray-400">Categories:</span> <span className="text-gray-900 dark:text-white ml-1">{config.categories.length}</span></div>
            <div className="col-span-2"><span className="text-gray-500 dark:text-gray-400">Banner:</span> <span className="text-gray-900 dark:text-white ml-1">{config.bannerTitle}</span></div>
          </div>
        </div>
      )}
    </div>
  );
}

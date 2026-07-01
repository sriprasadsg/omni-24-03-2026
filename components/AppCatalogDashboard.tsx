import React, { useState, useEffect } from 'react';
import { authFetch } from '../services/apiService';
import { showToast } from '../utils/toast';

interface CatalogApp {
  id: string;
  name: string;
  vendor: string;
  category: string;
  description: string;
  platforms: string[];
  latest_version: string;
  silent_install: string;
  download_url?: string;
  source: 'builtin' | 'custom';
}

interface Summary { total_apps: number; builtin_apps: number; custom_apps: number; }

const PLATFORM_BADGE: Record<string, string> = {
  windows: 'bg-blue-900/40 text-blue-300',
  macos: 'bg-gray-700 text-gray-300',
  linux: 'bg-orange-900/40 text-orange-300',
};

const BLANK_FORM = { name: '', vendor: '', category: 'Custom', description: '', platforms: ['windows'], latest_version: '', silent_install: '', download_url: '' };

export default function AppCatalogDashboard() {
  const [apps, setApps] = useState<CatalogApp[]>([]);
  const [categories, setCategories] = useState<string[]>([]);
  const [summary, setSummary] = useState<Summary | null>(null);
  const [catFilter, setCatFilter] = useState('all');
  const [platformFilter, setPlatformFilter] = useState('all');
  const [search, setSearch] = useState('');
  const [showAdd, setShowAdd] = useState(false);
  const [form, setForm] = useState({ ...BLANK_FORM });
  const [saving, setSaving] = useState(false);
  const [selected, setSelected] = useState<CatalogApp | null>(null);

  useEffect(() => { loadAll(); }, []);
  useEffect(() => { loadApps(); }, [catFilter, platformFilter, search]);

  async function loadAll() {
    const [cRes, sumRes] = await Promise.all([
      authFetch('/api/app-catalog/categories'),
      authFetch('/api/app-catalog/summary'),
    ]);
    const [c, s] = await Promise.all([cRes.json(), sumRes.json()]);
    setCategories(c.categories || []);
    setSummary(s);
    loadApps();
  }

  async function loadApps() {
    const params = new URLSearchParams();
    if (catFilter !== 'all') params.set('category', catFilter);
    if (platformFilter !== 'all') params.set('platform', platformFilter);
    if (search) params.set('search', search);
    const r = await authFetch(`/api/app-catalog/apps?${params}`);
    const d = await r.json();
    setApps(d.apps || []);
  }

  async function addApp() {
    setSaving(true);
    try {
      const r = await authFetch('/api/app-catalog/apps', {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(form),
      });
      if (r.ok) {
        showToast('App added to catalog', 'success');
        setShowAdd(false);
        setForm({ ...BLANK_FORM });
        loadAll();
      } else { const d = await r.json(); showToast(d.detail || 'Failed', 'error'); }
    } finally { setSaving(false); }
  }

  async function deleteApp(id: string) {
    if (!confirm('Remove this custom app?')) return;
    const r = await authFetch(`/api/app-catalog/apps/${id}`, { method: 'DELETE' });
    if (r.ok) { showToast('App removed', 'success'); loadAll(); }
    else { const d = await r.json(); showToast(d.detail || 'Failed', 'error'); }
  }

  function togglePlatform(p: string) {
    setForm(f => ({
      ...f,
      platforms: f.platforms.includes(p) ? f.platforms.filter(x => x !== p) : [...f.platforms, p],
    }));
  }

  return (
    <div className="p-6 bg-gray-900 min-h-screen text-white">
      <div className="flex justify-between items-start mb-6">
        <div>
          <h1 className="text-2xl font-bold">Application Catalog</h1>
          <p className="text-gray-400 text-sm mt-1">Browse and manage third-party applications for deployment and patching</p>
        </div>
        <button onClick={() => setShowAdd(true)} className="px-4 py-2 text-sm bg-blue-700 hover:bg-blue-600 rounded-lg">+ Add Custom App</button>
      </div>

      {/* Summary */}
      {summary && (
        <div className="grid grid-cols-3 gap-3 mb-6 max-w-md">
          <div className="bg-gray-800 rounded-lg p-4 text-center">
            <div className="text-2xl font-bold text-white">{summary.total_apps}</div>
            <div className="text-xs text-gray-400 mt-1">Total Apps</div>
          </div>
          <div className="bg-gray-800 rounded-lg p-4 text-center">
            <div className="text-2xl font-bold text-blue-400">{summary.builtin_apps}</div>
            <div className="text-xs text-gray-400 mt-1">Built-in</div>
          </div>
          <div className="bg-gray-800 rounded-lg p-4 text-center">
            <div className="text-2xl font-bold text-green-400">{summary.custom_apps}</div>
            <div className="text-xs text-gray-400 mt-1">Custom</div>
          </div>
        </div>
      )}

      {/* Filters */}
      <div className="flex flex-wrap gap-3 mb-4">
        <input value={search} onChange={e => setSearch(e.target.value)} placeholder="Search apps..."
          className="bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm w-64 focus:outline-none focus:border-blue-500" />
        <select value={catFilter} onChange={e => setCatFilter(e.target.value)}
          className="bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-blue-500">
          <option value="all">All Categories</option>
          {categories.map(c => <option key={c} value={c}>{c}</option>)}
        </select>
        <select value={platformFilter} onChange={e => setPlatformFilter(e.target.value)}
          className="bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-blue-500">
          <option value="all">All Platforms</option>
          <option value="windows">Windows</option>
          <option value="macos">macOS</option>
          <option value="linux">Linux</option>
        </select>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* App grid */}
        <div className="lg:col-span-2">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            {apps.length === 0 && <div className="col-span-2 text-center text-gray-500 py-12">No apps found</div>}
            {apps.map(app => (
              <div key={app.id} onClick={() => setSelected(app)}
                className={`bg-gray-800 rounded-lg p-4 border cursor-pointer hover:border-blue-600 transition-colors ${selected?.id === app.id ? 'border-blue-500' : 'border-gray-700'}`}>
                <div className="flex justify-between items-start">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="font-medium text-white truncate">{app.name}</span>
                      {app.source === 'custom' && <span className="text-xs bg-green-900/40 text-green-400 px-1.5 py-0.5 rounded">custom</span>}
                    </div>
                    <div className="text-xs text-gray-400 mt-0.5">{app.vendor}</div>
                  </div>
                  {app.source === 'custom' && (
                    <button onClick={e => { e.stopPropagation(); deleteApp(app.id); }} className="text-xs text-red-400 hover:text-red-300 ml-2 shrink-0">Remove</button>
                  )}
                </div>
                <div className="flex items-center gap-2 mt-2 flex-wrap">
                  <span className="text-xs bg-gray-700 text-gray-300 px-2 py-0.5 rounded">{app.category}</span>
                  {app.latest_version && <span className="text-xs text-gray-500">v{app.latest_version}</span>}
                  {app.platforms.slice(0, 2).map(p => (
                    <span key={p} className={`text-xs px-1.5 py-0.5 rounded ${PLATFORM_BADGE[p] || 'bg-gray-700 text-gray-300'}`}>{p}</span>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Detail panel */}
        <div>
          {selected ? (
            <div className="bg-gray-800 rounded-lg p-4 border border-gray-700 sticky top-6">
              <div className="flex justify-between items-start mb-3">
                <div>
                  <h3 className="font-semibold text-white">{selected.name}</h3>
                  <p className="text-gray-400 text-xs mt-0.5">{selected.vendor}</p>
                </div>
                <span className="text-xs bg-gray-700 text-gray-300 px-2 py-0.5 rounded">{selected.category}</span>
              </div>
              {selected.description && <p className="text-gray-400 text-sm mb-3">{selected.description}</p>}
              <div className="space-y-2 text-sm">
                {selected.latest_version && (
                  <div><span className="text-gray-500">Latest Version:</span> <span className="text-gray-300 ml-1 font-mono">{selected.latest_version}</span></div>
                )}
                <div><span className="text-gray-500">Platforms:</span>
                  <div className="flex gap-1 mt-1 flex-wrap">
                    {selected.platforms.map(p => (
                      <span key={p} className={`text-xs px-2 py-0.5 rounded ${PLATFORM_BADGE[p] || 'bg-gray-700 text-gray-300'}`}>{p}</span>
                    ))}
                  </div>
                </div>
                {selected.silent_install && (
                  <div>
                    <span className="text-gray-500 block">Silent Install Args:</span>
                    <code className="text-xs text-green-400 font-mono mt-1 block bg-gray-900 px-2 py-1 rounded">{selected.silent_install}</code>
                  </div>
                )}
                {selected.download_url && (
                  <div><span className="text-gray-500">Download:</span> <span className="text-xs text-blue-400 ml-1 break-all">{selected.download_url}</span></div>
                )}
              </div>
            </div>
          ) : (
            <div className="bg-gray-800 rounded-lg p-8 border border-gray-700 text-center text-gray-500 text-sm">
              Select an app to view details
            </div>
          )}
        </div>
      </div>

      {/* Add Custom App Modal */}
      {showAdd && (
        <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50 p-4">
          <div className="bg-gray-800 rounded-xl p-6 w-full max-w-md border border-gray-700 max-h-[90vh] overflow-y-auto">
            <h2 className="text-lg font-semibold mb-4">Add Custom Application</h2>
            <div className="space-y-3">
              {[
                { key: 'name', label: 'App Name *', placeholder: 'e.g. InternalTool' },
                { key: 'vendor', label: 'Vendor', placeholder: 'e.g. Acme Corp' },
                { key: 'category', label: 'Category', placeholder: 'e.g. Security' },
                { key: 'description', label: 'Description', placeholder: 'Short description' },
                { key: 'latest_version', label: 'Latest Version', placeholder: 'e.g. 3.2.1' },
                { key: 'silent_install', label: 'Silent Install Args', placeholder: 'e.g. /S /quiet' },
                { key: 'download_url', label: 'Download URL', placeholder: 'https://...' },
              ].map(f => (
                <div key={f.key}>
                  <label className="text-xs text-gray-400 block mb-1">{f.label}</label>
                  <input value={(form as any)[f.key]} onChange={e => setForm(p => ({ ...p, [f.key]: e.target.value }))}
                    placeholder={f.placeholder}
                    className="w-full bg-gray-700 border border-gray-600 rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-blue-500" />
                </div>
              ))}
              <div>
                <label className="text-xs text-gray-400 block mb-2">Platforms</label>
                <div className="flex gap-3">
                  {['windows', 'macos', 'linux'].map(p => (
                    <label key={p} className="flex items-center gap-1.5 text-sm cursor-pointer">
                      <input type="checkbox" checked={form.platforms.includes(p)} onChange={() => togglePlatform(p)} className="accent-blue-500" />
                      <span className="text-gray-300 capitalize">{p}</span>
                    </label>
                  ))}
                </div>
              </div>
            </div>
            <div className="flex gap-2 mt-4 justify-end">
              <button onClick={() => setShowAdd(false)} className="px-4 py-2 text-sm text-gray-400 hover:text-white">Cancel</button>
              <button onClick={addApp} disabled={saving || !form.name}
                className="px-4 py-2 text-sm bg-blue-700 hover:bg-blue-600 rounded-lg disabled:opacity-50">
                {saving ? 'Adding…' : 'Add App'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

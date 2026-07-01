import React, { useState, useEffect } from 'react';
import { authFetch } from '../services/apiService';
import { showToast } from '../utils/toast';

interface BranchSite {
  id: string;
  name: string;
  description: string;
  city: string;
  country: string;
  timezone: string;
  ip_ranges: string[];
  contact_name: string;
  contact_email: string;
  total_agents: number;
  online_agents: number;
  offline_agents: number;
  patch_compliance_pct: number;
  patches_installed: number;
  patches_total: number;
}

interface Summary { total_sites: number; agents_assigned_to_sites: number; }

const BLANK_FORM = { name: '', description: '', city: '', country: '', timezone: 'UTC', ip_ranges: '', contact_name: '', contact_email: '' };

export default function BranchSitesDashboard() {
  const [sites, setSites] = useState<BranchSite[]>([]);
  const [summary, setSummary] = useState<Summary | null>(null);
  const [selected, setSelected] = useState<BranchSite | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [editSite, setEditSite] = useState<BranchSite | null>(null);
  const [form, setForm] = useState({ ...BLANK_FORM });
  const [saving, setSaving] = useState(false);

  useEffect(() => { loadAll(); }, []);

  async function loadAll() {
    try {
      const [sRes, sumRes] = await Promise.all([
        authFetch('/api/branch-sites'),
        authFetch('/api/branch-sites/summary'),
      ]);
      const [s, sum] = await Promise.all([sRes.json(), sumRes.json()]);
      setSites(s.sites || []);
      setSummary(sum);
    } catch (e) { console.error(e); }
  }

  function openCreate() {
    setEditSite(null);
    setForm({ ...BLANK_FORM });
    setShowForm(true);
  }

  function openEdit(site: BranchSite) {
    setEditSite(site);
    setForm({
      name: site.name, description: site.description, city: site.city,
      country: site.country, timezone: site.timezone,
      ip_ranges: site.ip_ranges.join(', '), contact_name: site.contact_name,
      contact_email: site.contact_email,
    });
    setShowForm(true);
  }

  async function saveSite() {
    setSaving(true);
    try {
      const payload = { ...form, ip_ranges: form.ip_ranges.split(',').map(s => s.trim()).filter(Boolean) };
      const url = editSite ? `/api/branch-sites/${editSite.id}` : '/api/branch-sites';
      const method = editSite ? 'PATCH' : 'POST';
      const r = await authFetch(url, { method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
      if (r.ok) {
        showToast(editSite ? 'Site updated' : 'Site created', 'success');
        setShowForm(false);
        setEditSite(null);
        loadAll();
      } else { const d = await r.json(); showToast(d.detail || 'Failed', 'error'); }
    } finally { setSaving(false); }
  }

  async function deleteSite(id: string) {
    if (!confirm('Delete this site?')) return;
    const r = await authFetch(`/api/branch-sites/${id}`, { method: 'DELETE' });
    if (r.ok) { showToast('Site deleted', 'success'); setSelected(null); loadAll(); }
    else { const d = await r.json(); showToast(d.detail || 'Cannot delete', 'error'); }
  }

  function patchColor(pct: number) {
    if (pct >= 90) return 'text-green-400';
    if (pct >= 70) return 'text-yellow-400';
    return 'text-red-400';
  }

  return (
    <div className="p-6 bg-gray-900 min-h-screen text-white">
      <div className="flex justify-between items-start mb-6">
        <div>
          <h1 className="text-2xl font-bold">Branch Sites &amp; Remote Offices</h1>
          <p className="text-gray-400 text-sm mt-1">Group endpoints by physical location and monitor per-site health and compliance</p>
        </div>
        <button onClick={openCreate} className="px-4 py-2 text-sm bg-blue-700 hover:bg-blue-600 rounded-lg">+ Add Site</button>
      </div>

      {/* Summary */}
      {summary && (
        <div className="grid grid-cols-2 gap-3 mb-6 max-w-sm">
          <div className="bg-gray-800 rounded-lg p-4 text-center">
            <div className="text-2xl font-bold text-white">{summary.total_sites}</div>
            <div className="text-xs text-gray-400 mt-1">Total Sites</div>
          </div>
          <div className="bg-gray-800 rounded-lg p-4 text-center">
            <div className="text-2xl font-bold text-blue-400">{summary.agents_assigned_to_sites}</div>
            <div className="text-xs text-gray-400 mt-1">Assigned Agents</div>
          </div>
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Site list */}
        <div className="lg:col-span-2">
          {sites.length === 0 && (
            <div className="text-center text-gray-500 py-16 bg-gray-800 rounded-lg">
              <div className="text-4xl mb-3">🏢</div>
              <div>No sites configured yet</div>
              <button onClick={openCreate} className="mt-4 px-4 py-2 text-sm bg-blue-700 hover:bg-blue-600 rounded-lg">Add your first site</button>
            </div>
          )}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            {sites.map(site => (
              <div key={site.id} onClick={() => setSelected(site)}
                className={`bg-gray-800 rounded-lg p-4 border cursor-pointer hover:border-blue-600 transition-colors ${selected?.id === site.id ? 'border-blue-500' : 'border-gray-700'}`}>
                <div className="flex justify-between items-start">
                  <div>
                    <h3 className="font-medium text-white">{site.name}</h3>
                    <p className="text-gray-400 text-xs mt-0.5">{[site.city, site.country].filter(Boolean).join(', ') || 'No location set'}</p>
                  </div>
                  <div className="flex gap-1">
                    <button onClick={e => { e.stopPropagation(); openEdit(site); }} className="text-xs text-blue-400 hover:text-blue-300 px-1">Edit</button>
                    <button onClick={e => { e.stopPropagation(); deleteSite(site.id); }} className="text-xs text-red-400 hover:text-red-300 px-1">Delete</button>
                  </div>
                </div>
                <div className="mt-3 grid grid-cols-3 gap-2 text-xs">
                  <div className="text-center">
                    <div className="font-semibold text-white">{site.total_agents}</div>
                    <div className="text-gray-500">Agents</div>
                  </div>
                  <div className="text-center">
                    <div className="font-semibold text-green-400">{site.online_agents}</div>
                    <div className="text-gray-500">Online</div>
                  </div>
                  <div className="text-center">
                    <div className={`font-semibold ${patchColor(site.patch_compliance_pct)}`}>{site.patch_compliance_pct}%</div>
                    <div className="text-gray-500">Patched</div>
                  </div>
                </div>
                {site.total_agents > 0 && (
                  <div className="mt-2">
                    <div className="w-full bg-gray-700 rounded-full h-1.5">
                      <div className={`h-1.5 rounded-full ${site.patch_compliance_pct >= 90 ? 'bg-green-500' : site.patch_compliance_pct >= 70 ? 'bg-yellow-500' : 'bg-red-500'}`}
                        style={{ width: `${site.patch_compliance_pct}%` }} />
                    </div>
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>

        {/* Site detail panel */}
        <div>
          {selected ? (
            <div className="bg-gray-800 rounded-lg p-4 border border-gray-700 sticky top-6">
              <h2 className="font-semibold text-white text-lg">{selected.name}</h2>
              {selected.description && <p className="text-gray-400 text-sm mt-1">{selected.description}</p>}
              <div className="mt-4 space-y-2 text-sm">
                {selected.city && <div><span className="text-gray-500">City:</span> <span className="text-gray-300 ml-1">{selected.city}</span></div>}
                {selected.country && <div><span className="text-gray-500">Country:</span> <span className="text-gray-300 ml-1">{selected.country}</span></div>}
                <div><span className="text-gray-500">Timezone:</span> <span className="text-gray-300 ml-1">{selected.timezone}</span></div>
                {selected.ip_ranges.length > 0 && (
                  <div><span className="text-gray-500">IP Ranges:</span> <span className="text-gray-300 ml-1 font-mono text-xs">{selected.ip_ranges.join(', ')}</span></div>
                )}
                {selected.contact_name && <div><span className="text-gray-500">Contact:</span> <span className="text-gray-300 ml-1">{selected.contact_name}</span></div>}
                {selected.contact_email && <div><span className="text-gray-500">Email:</span> <span className="text-gray-300 ml-1 text-xs">{selected.contact_email}</span></div>}
              </div>
              <div className="mt-4 pt-4 border-t border-gray-700 grid grid-cols-2 gap-3 text-sm">
                <div className="bg-gray-900 rounded p-3 text-center">
                  <div className="text-xl font-bold text-white">{selected.total_agents}</div>
                  <div className="text-xs text-gray-500 mt-0.5">Total Agents</div>
                </div>
                <div className="bg-gray-900 rounded p-3 text-center">
                  <div className="text-xl font-bold text-green-400">{selected.online_agents}</div>
                  <div className="text-xs text-gray-500 mt-0.5">Online</div>
                </div>
                <div className="bg-gray-900 rounded p-3 text-center">
                  <div className={`text-xl font-bold ${patchColor(selected.patch_compliance_pct)}`}>{selected.patch_compliance_pct}%</div>
                  <div className="text-xs text-gray-500 mt-0.5">Patch Compliance</div>
                </div>
                <div className="bg-gray-900 rounded p-3 text-center">
                  <div className="text-xl font-bold text-red-400">{selected.offline_agents}</div>
                  <div className="text-xs text-gray-500 mt-0.5">Offline</div>
                </div>
              </div>
            </div>
          ) : (
            <div className="bg-gray-800 rounded-lg p-8 border border-gray-700 text-center text-gray-500 text-sm">
              Select a site to view details
            </div>
          )}
        </div>
      </div>

      {/* Create/Edit Modal */}
      {showForm && (
        <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50 p-4">
          <div className="bg-gray-800 rounded-xl p-6 w-full max-w-md border border-gray-700 max-h-[90vh] overflow-y-auto">
            <h2 className="text-lg font-semibold mb-4">{editSite ? 'Edit Site' : 'Add Branch Site'}</h2>
            <div className="space-y-3">
              {[
                { key: 'name', label: 'Site Name *', placeholder: 'e.g. London Office' },
                { key: 'description', label: 'Description', placeholder: 'Optional' },
                { key: 'city', label: 'City', placeholder: 'e.g. London' },
                { key: 'country', label: 'Country', placeholder: 'e.g. United Kingdom' },
                { key: 'timezone', label: 'Timezone', placeholder: 'e.g. Europe/London' },
                { key: 'ip_ranges', label: 'IP Ranges (comma-separated)', placeholder: 'e.g. 10.1.0.0/16, 192.168.1.0/24' },
                { key: 'contact_name', label: 'Site Contact Name', placeholder: 'IT contact person' },
                { key: 'contact_email', label: 'Contact Email', placeholder: 'it-contact@company.com' },
              ].map(f => (
                <div key={f.key}>
                  <label className="text-xs text-gray-400 block mb-1">{f.label}</label>
                  <input value={(form as any)[f.key]} onChange={e => setForm(p => ({ ...p, [f.key]: e.target.value }))}
                    placeholder={f.placeholder}
                    className="w-full bg-gray-700 border border-gray-600 rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-blue-500" />
                </div>
              ))}
            </div>
            <div className="flex gap-2 mt-4 justify-end">
              <button onClick={() => { setShowForm(false); setEditSite(null); }} className="px-4 py-2 text-sm text-gray-400 hover:text-white">Cancel</button>
              <button onClick={saveSite} disabled={saving || !form.name}
                className="px-4 py-2 text-sm bg-blue-700 hover:bg-blue-600 rounded-lg disabled:opacity-50">
                {saving ? 'Saving…' : (editSite ? 'Update' : 'Create')}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

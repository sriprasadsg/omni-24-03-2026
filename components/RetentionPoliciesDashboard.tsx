import React, { useState, useEffect, useCallback } from 'react';

const API = '/api/retention-tiers';

type Tier = 'hot' | 'warm' | 'cold' | 'archive' | 'compliance';

interface Policy {
  id: string;
  name: string;
  tier: Tier;
  retention_days: number;
  applies_to: string;
  legal_hold: boolean;
  created_at: string;
  updated_at: string;
}

interface Stats {
  tier_counts: Record<Tier, number>;
  legal_hold_count: number;
  total: number;
}

const TIERS: Tier[] = ['hot', 'warm', 'cold', 'archive', 'compliance'];

const TIER_STYLE: Record<Tier, { bg: string; text: string; border: string }> = {
  hot: { bg: 'bg-red-500/20', text: 'text-red-400', border: 'border-red-500/30' },
  warm: { bg: 'bg-orange-500/20', text: 'text-orange-400', border: 'border-orange-500/30' },
  cold: { bg: 'bg-blue-500/20', text: 'text-blue-400', border: 'border-blue-500/30' },
  archive: { bg: 'bg-slate-500/20', text: 'text-slate-300', border: 'border-slate-500/30' },
  compliance: { bg: 'bg-purple-500/20', text: 'text-purple-400', border: 'border-purple-500/30' },
};

const UNKNOWN_TIER_STYLE = { bg: 'bg-slate-500/20', text: 'text-slate-300', border: 'border-slate-500/30' };

const TIER_DESC: Record<Tier, string> = {
  hot: 'Frequently accessed — fast retrieval, highest cost',
  warm: 'Occasionally accessed — moderate cost',
  cold: 'Rarely accessed — low cost, slower retrieval',
  archive: 'Long-term storage — very low cost',
  compliance: 'Regulatory retention — immutable with legal hold support',
};

const emptyForm = { name: '', tier: 'hot' as Tier, retention_days: 90, applies_to: 'all', legal_hold: false };

const authH = () => ({ Authorization: `Bearer ${sessionStorage.getItem('token')}`, 'Content-Type': 'application/json' });

export default function RetentionPoliciesDashboard() {
  const [tab, setTab] = useState<'policies' | 'stats'>('policies');
  const [policies, setPolicies] = useState<Policy[]>([]);
  const [stats, setStats] = useState<Stats | null>(null);
  const [loading, setLoading] = useState(false);
  const [showModal, setShowModal] = useState(false);
  const [editId, setEditId] = useState<string | null>(null);
  const [form, setForm] = useState({ ...emptyForm });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  const loadPolicies = useCallback(async () => {
    setLoading(true);
    try {
      const r = await fetch(`${API}/`, { headers: authH() });
      if (r.ok) setPolicies(await r.json());
    } catch { /* ignore */ }
    setLoading(false);
  }, []);

  const loadStats = useCallback(async () => {
    try {
      const r = await fetch(`${API}/stats`, { headers: authH() });
      if (r.ok) setStats(await r.json());
    } catch { /* ignore */ }
  }, []);

  useEffect(() => { loadPolicies(); loadStats(); }, [loadPolicies, loadStats]);

  const openCreate = () => { setEditId(null); setForm({ ...emptyForm }); setError(''); setShowModal(true); };
  const openEdit = (p: Policy) => { setEditId(p.id); setForm({ name: p.name, tier: p.tier, retention_days: p.retention_days, applies_to: p.applies_to, legal_hold: p.legal_hold }); setError(''); setShowModal(true); };

  const save = async () => {
    if (!form.name.trim()) { setError('Name is required'); return; }
    setSaving(true);
    setError('');
    try {
      const url = editId ? `${API}/${editId}` : `${API}/`;
      const r = await fetch(url, { method: editId ? 'PUT' : 'POST', headers: authH(), body: JSON.stringify(form) });
      if (!r.ok) { const d = await r.json(); setError(d.detail || 'Save failed'); setSaving(false); return; }
      setShowModal(false);
      await loadPolicies();
      await loadStats();
    } catch { setError('Network error'); }
    setSaving(false);
  };

  const del = async (id: string) => {
    if (!confirm('Delete this policy?')) return;
    try {
      await fetch(`${API}/${id}`, { method: 'DELETE', headers: authH() });
      await loadPolicies();
      await loadStats();
    } catch { /* ignore */ }
  };

  const toggleHold = async (id: string) => {
    try {
      await fetch(`${API}/${id}/legal-hold`, { method: 'POST', headers: authH() });
      await loadPolicies();
    } catch { /* ignore */ }
  };

  const fmt = (iso: string) => new Date(iso).toLocaleDateString();

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="text-2xl font-bold text-white">Retention Policies</h2>
        <button onClick={openCreate} className="px-4 py-2 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-700 transition-colors">
          + New Policy
        </button>
      </div>

      <div className="flex rounded-lg overflow-hidden border border-slate-700 w-fit">
        {(['policies', 'stats'] as const).map(t => (
          <button key={t} onClick={() => setTab(t)}
            className={`px-4 py-2 text-sm font-medium capitalize transition-colors ${tab === t ? 'bg-blue-600 text-white' : 'bg-slate-800 text-slate-300 hover:bg-slate-700'}`}>
            {t}
          </button>
        ))}
      </div>

      {tab === 'policies' && (
        <div className="bg-slate-800/50 border border-slate-700 rounded-xl overflow-hidden">
          {loading ? <p className="text-slate-400 text-sm p-6 text-center animate-pulse">Loading...</p>
            : policies.length === 0 ? <p className="text-slate-400 text-sm p-8 text-center">No retention policies. Create one to get started.</p>
              : (
                <table className="w-full text-sm">
                  <thead><tr className="border-b border-slate-700 text-slate-400 text-xs">
                    <th className="text-left p-3">Name</th>
                    <th className="text-left p-3">Tier</th>
                    <th className="text-left p-3">Retention</th>
                    <th className="text-left p-3">Applies To</th>
                    <th className="text-left p-3">Legal Hold</th>
                    <th className="text-left p-3">Updated</th>
                    <th className="text-left p-3">Actions</th>
                  </tr></thead>
                  <tbody>
                    {policies.map(p => {
                      const s = TIER_STYLE[p.tier] || UNKNOWN_TIER_STYLE;
                      return (
                        <tr key={p.id} className="border-b border-slate-700/50 hover:bg-slate-700/30 transition-colors">
                          <td className="p-3 font-medium text-white">{p.name}</td>
                          <td className="p-3"><span className={`text-xs px-2 py-0.5 rounded-full border capitalize ${s.bg} ${s.text} ${s.border}`}>{p.tier}</span></td>
                          <td className="p-3 text-slate-300">{p.retention_days}d</td>
                          <td className="p-3 text-slate-300">{p.applies_to}</td>
                          <td className="p-3">
                            <button onClick={() => toggleHold(p.id)}
                              className={`text-xs px-2 py-0.5 rounded border transition-colors ${p.legal_hold ? 'bg-yellow-500/20 text-yellow-400 border-yellow-500/30' : 'bg-slate-700 text-slate-400 border-slate-600 hover:bg-yellow-500/10'}`}>
                              {p.legal_hold ? 'Active' : 'Off'}
                            </button>
                          </td>
                          <td className="p-3 text-slate-400">{fmt(p.updated_at)}</td>
                          <td className="p-3">
                            <div className="flex gap-2">
                              <button onClick={() => openEdit(p)} className="text-xs text-blue-400 hover:text-blue-300">Edit</button>
                              <button onClick={() => del(p.id)} disabled={p.legal_hold} className="text-xs text-red-400 hover:text-red-300 disabled:opacity-40">Delete</button>
                            </div>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              )}
        </div>
      )}

      {tab === 'stats' && stats && (
        <div className="space-y-4">
          <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
            <div className="bg-yellow-500/10 border border-yellow-500/20 rounded-xl p-4 text-center">
              <div className="text-3xl font-bold text-yellow-400">{stats.legal_hold_count}</div>
              <div className="text-xs text-yellow-400/70 mt-1">Legal Hold Active</div>
            </div>
            <div className="bg-slate-800 border border-slate-700 rounded-xl p-4 text-center">
              <div className="text-3xl font-bold text-white">{stats.total}</div>
              <div className="text-xs text-slate-400 mt-1">Total Policies</div>
            </div>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {TIERS.map(t => {
              const s = TIER_STYLE[t];
              return (
                <div key={t} className={`border rounded-xl p-4 ${s.bg} ${s.border}`}>
                  <div className={`text-xl font-bold ${s.text} capitalize`}>{t}</div>
                  <div className={`text-3xl font-bold ${s.text} mt-1`}>{stats.tier_counts[t] || 0}</div>
                  <div className="text-xs text-slate-400 mt-1">{TIER_DESC[t]}</div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {showModal && (
        <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50 p-4">
          <div className="bg-slate-900 border border-slate-700 rounded-2xl w-full max-w-md p-6 space-y-4">
            <div className="flex items-center justify-between">
              <h3 className="text-lg font-bold text-white">{editId ? 'Edit Policy' : 'New Retention Policy'}</h3>
              <button onClick={() => setShowModal(false)} className="text-slate-400 hover:text-white text-xl">&times;</button>
            </div>
            {error && <p className="text-red-400 text-sm">{error}</p>}
            <div className="space-y-3">
              <div><label className="text-xs text-slate-400">Name</label>
                <input value={form.name} onChange={e => setForm(f => ({ ...f, name: e.target.value }))}
                  className="w-full mt-1 bg-slate-800 border border-slate-600 rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:border-blue-500" /></div>
              <div><label className="text-xs text-slate-400">Tier</label>
                <select value={form.tier} onChange={e => setForm(f => ({ ...f, tier: e.target.value as Tier }))}
                  className="w-full mt-1 bg-slate-800 border border-slate-600 rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:border-blue-500">
                  {TIERS.map(t => <option key={t} value={t} className="capitalize">{t}</option>)}
                </select></div>
              <div><label className="text-xs text-slate-400">Retention Days</label>
                <input type="number" min={1} value={form.retention_days} onChange={e => setForm(f => ({ ...f, retention_days: parseInt(e.target.value) || 1 }))}
                  className="w-full mt-1 bg-slate-800 border border-slate-600 rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:border-blue-500" /></div>
              <div><label className="text-xs text-slate-400">Applies To</label>
                <select value={form.applies_to} onChange={e => setForm(f => ({ ...f, applies_to: e.target.value }))}
                  className="w-full mt-1 bg-slate-800 border border-slate-600 rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:border-blue-500">
                  <option value="all">All Log Sources</option>
                  <option value="security_events">Security Events</option>
                  <option value="audit_logs">Audit Logs</option>
                  <option value="network_events">Network Events</option>
                  <option value="endpoint_logs">Endpoint Logs</option>
                </select></div>
              <div className="flex items-center gap-2">
                <input type="checkbox" id="legalhold" checked={form.legal_hold} onChange={e => setForm(f => ({ ...f, legal_hold: e.target.checked }))} className="rounded" />
                <label htmlFor="legalhold" className="text-sm text-slate-300">Enable Legal Hold</label>
              </div>
            </div>
            <div className="flex gap-3 pt-2">
              <button onClick={() => setShowModal(false)} className="flex-1 py-2 rounded-lg border border-slate-600 text-slate-300 text-sm hover:bg-slate-800 transition-colors">Cancel</button>
              <button onClick={save} disabled={saving}
                className="flex-1 py-2 rounded-lg bg-blue-600 text-white text-sm font-medium hover:bg-blue-700 disabled:opacity-50 transition-colors">
                {saving ? 'Saving...' : editId ? 'Update' : 'Create'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

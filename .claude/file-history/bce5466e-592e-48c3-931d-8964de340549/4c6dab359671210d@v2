import React, { useState, useEffect } from 'react';
import { Shield, ShieldAlert, Plus, Edit2, Trash2, Play, ToggleLeft, ToggleRight, AlertTriangle, CheckCircle, BarChart2, RefreshCw } from 'lucide-react';

const API = import.meta.env.VITE_API_BASE_URL || '';
const authHeader = () => ({ Authorization: `Bearer ${localStorage.getItem('auth_token')}` });

const SEVERITY_COLORS: Record<string, string> = {
  critical: 'bg-red-500/20 text-red-400 border-red-500/30',
  high: 'bg-orange-500/20 text-orange-400 border-orange-500/30',
  medium: 'bg-yellow-500/20 text-yellow-400 border-yellow-500/30',
  low: 'bg-blue-500/20 text-blue-400 border-blue-500/30',
  informational: 'bg-slate-500/20 text-slate-400 border-slate-500/30',
};

const MITRE_TACTICS = [
  'Initial Access','Execution','Persistence','Privilege Escalation','Defense Evasion',
  'Credential Access','Discovery','Lateral Movement','Collection','Exfiltration',
  'Command and Control','Impact',
];

interface Condition { field: string; operator: string; value: string; }
interface Rule {
  id: string; name: string; description: string; severity: string; rule_type: string;
  enabled: boolean; conditions: Condition[]; time_window_minutes: number; threshold_count: number;
  mitre_tactics: string[]; mitre_techniques: string; tags: string; trigger_count: number;
  last_triggered?: string; created_at: string;
}

const emptyRule = (): Partial<Rule> => ({
  name: '', description: '', severity: 'medium', rule_type: 'query', enabled: true,
  conditions: [{ field: '', operator: 'equals', value: '' }],
  time_window_minutes: 60, threshold_count: 1, mitre_tactics: [], mitre_techniques: '', tags: '',
});

export default function DetectionRulesDashboard() {
  const [tab, setTab] = useState<'rules' | 'create' | 'stats'>('rules');
  const [rules, setRules] = useState<Rule[]>([]);
  const [stats, setStats] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [form, setForm] = useState<Partial<Rule>>(emptyRule());
  const [editId, setEditId] = useState<string | null>(null);
  const [testResult, setTestResult] = useState<any>(null);
  const [testingId, setTestingId] = useState<string | null>(null);
  const [filterSev, setFilterSev] = useState('');
  const [filterEnabled, setFilterEnabled] = useState('');

  const load = async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (filterSev) params.set('severity', filterSev);
      if (filterEnabled !== '') params.set('enabled', filterEnabled);
      const r = await fetch(`${API}/api/detection-rules/?${params}`, { headers: authHeader() });
      const d = await r.json();
      setRules(d.rules || d || []);
    } catch { setRules([]); }
    setLoading(false);
  };

  const loadStats = async () => {
    try {
      const r = await fetch(`${API}/api/detection-rules/stats`, { headers: authHeader() });
      setStats(await r.json());
    } catch { setStats(null); }
  };

  useEffect(() => { load(); loadStats(); }, [filterSev, filterEnabled]);

  const save = async () => {
    const url = editId ? `${API}/api/detection-rules/${editId}` : `${API}/api/detection-rules/`;
    const method = editId ? 'PUT' : 'POST';
    await fetch(url, { method, headers: { ...authHeader(), 'Content-Type': 'application/json' }, body: JSON.stringify(form) });
    setForm(emptyRule()); setEditId(null); setTab('rules'); load(); loadStats();
  };

  const del = async (id: string) => {
    if (!confirm('Delete this rule?')) return;
    await fetch(`${API}/api/detection-rules/${id}`, { method: 'DELETE', headers: authHeader() });
    load(); loadStats();
  };

  const toggle = async (id: string, enabled: boolean) => {
    const ep = enabled ? 'disable' : 'enable';
    await fetch(`${API}/api/detection-rules/${id}/${ep}`, { method: 'POST', headers: authHeader() });
    load();
  };

  const testRule = async (id: string) => {
    setTestingId(id);
    const r = await fetch(`${API}/api/detection-rules/${id}/test`, { method: 'POST', headers: authHeader() });
    setTestResult(await r.json());
    setTestingId(null);
  };

  const startEdit = (rule: Rule) => {
    setForm({ ...rule, mitre_techniques: rule.mitre_techniques || '', tags: Array.isArray(rule.tags) ? (rule.tags as any[]).join(', ') : rule.tags || '' });
    setEditId(rule.id); setTab('create');
  };

  const addCondition = () => setForm(f => ({ ...f, conditions: [...(f.conditions || []), { field: '', operator: 'equals', value: '' }] }));
  const removeCondition = (i: number) => setForm(f => ({ ...f, conditions: (f.conditions || []).filter((_, idx) => idx !== i) }));
  const updateCondition = (i: number, key: keyof Condition, val: string) =>
    setForm(f => ({ ...f, conditions: (f.conditions || []).map((c, idx) => idx === i ? { ...c, [key]: val } : c) }));

  return (
    <div className="p-6 text-white">
      <div className="flex items-center gap-3 mb-6">
        <ShieldAlert className="text-orange-400" size={28} />
        <h1 className="text-2xl font-bold">Detection Rules</h1>
        <span className="ml-auto text-sm text-slate-400">{rules.length} rules</span>
      </div>

      <div className="flex gap-2 mb-6">
        {(['rules','create','stats'] as const).map(t => (
          <button key={t} onClick={() => { setTab(t); if (t === 'stats') loadStats(); }}
            className={`px-4 py-2 rounded-lg text-sm font-medium capitalize ${tab === t ? 'bg-orange-600 text-white' : 'bg-slate-700 text-slate-300 hover:bg-slate-600'}`}>
            {t === 'create' ? (editId ? 'Edit Rule' : 'Create Rule') : t}
          </button>
        ))}
      </div>

      {tab === 'rules' && (
        <>
          <div className="flex gap-3 mb-4">
            <select value={filterSev} onChange={e => setFilterSev(e.target.value)} className="bg-slate-700 text-slate-200 rounded px-3 py-1.5 text-sm">
              <option value="">All Severities</option>
              {['critical','high','medium','low','informational'].map(s => <option key={s} value={s}>{s}</option>)}
            </select>
            <select value={filterEnabled} onChange={e => setFilterEnabled(e.target.value)} className="bg-slate-700 text-slate-200 rounded px-3 py-1.5 text-sm">
              <option value="">All States</option>
              <option value="true">Enabled</option>
              <option value="false">Disabled</option>
            </select>
            <button onClick={load} className="ml-auto p-2 bg-slate-700 rounded hover:bg-slate-600"><RefreshCw size={16} /></button>
            <button onClick={() => { setForm(emptyRule()); setEditId(null); setTab('create'); }} className="flex items-center gap-2 px-4 py-2 bg-orange-600 rounded-lg text-sm hover:bg-orange-700">
              <Plus size={16} /> New Rule
            </button>
          </div>
          {loading ? <div className="text-center py-10 text-slate-400">Loading...</div> : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead><tr className="text-slate-400 border-b border-slate-700">
                  <th className="text-left py-3 px-4">Name</th><th className="text-left py-3 px-4">Severity</th>
                  <th className="text-left py-3 px-4">Type</th><th className="text-left py-3 px-4">Triggers</th>
                  <th className="text-left py-3 px-4">State</th><th className="text-left py-3 px-4">Actions</th>
                </tr></thead>
                <tbody>{rules.map(r => (
                  <tr key={r.id} className="border-b border-slate-800 hover:bg-slate-800/40">
                    <td className="py-3 px-4">
                      <div className="font-medium">{r.name}</div>
                      <div className="text-xs text-slate-500">{r.description?.slice(0, 60)}...</div>
                    </td>
                    <td className="py-3 px-4"><span className={`px-2 py-0.5 rounded-full text-xs border ${SEVERITY_COLORS[r.severity] || ''}`}>{r.severity}</span></td>
                    <td className="py-3 px-4 text-slate-400">{r.rule_type}</td>
                    <td className="py-3 px-4 text-slate-300">{r.trigger_count || 0}</td>
                    <td className="py-3 px-4">
                      <button onClick={() => toggle(r.id, r.enabled)} className={r.enabled ? 'text-green-400' : 'text-slate-500'}>
                        {r.enabled ? <ToggleRight size={22} /> : <ToggleLeft size={22} />}
                      </button>
                    </td>
                    <td className="py-3 px-4">
                      <div className="flex gap-2">
                        <button onClick={() => startEdit(r)} className="p-1.5 bg-blue-600/20 rounded hover:bg-blue-600/40 text-blue-400"><Edit2 size={14} /></button>
                        <button onClick={() => testRule(r.id)} disabled={testingId === r.id} className="p-1.5 bg-green-600/20 rounded hover:bg-green-600/40 text-green-400"><Play size={14} /></button>
                        <button onClick={() => del(r.id)} className="p-1.5 bg-red-600/20 rounded hover:bg-red-600/40 text-red-400"><Trash2 size={14} /></button>
                      </div>
                    </td>
                  </tr>
                ))}</tbody>
              </table>
              {testResult && (
                <div className="mt-4 p-4 bg-slate-800 rounded-lg">
                  <div className="flex items-center gap-2 mb-2">
                    {testResult.matched ? <CheckCircle className="text-green-400" size={18} /> : <AlertTriangle className="text-yellow-400" size={18} />}
                    <span className="font-medium">Test Result: {testResult.matched ? `${testResult.match_count} matches` : 'No matches'}</span>
                    <button onClick={() => setTestResult(null)} className="ml-auto text-slate-500 text-sm">Dismiss</button>
                  </div>
                  {testResult.sample_matches?.length > 0 && <div className="text-xs text-slate-400 mt-1">{testResult.sample_matches.length} sample events shown.</div>}
                </div>
              )}
            </div>
          )}
        </>
      )}

      {tab === 'create' && (
        <div className="max-w-2xl space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <div><label className="block text-xs text-slate-400 mb-1">Rule Name</label>
              <input value={form.name || ''} onChange={e => setForm(f => ({ ...f, name: e.target.value }))} className="w-full bg-slate-700 rounded px-3 py-2 text-sm" placeholder="e.g. Password Spray Detection" /></div>
            <div><label className="block text-xs text-slate-400 mb-1">Severity</label>
              <select value={form.severity || 'medium'} onChange={e => setForm(f => ({ ...f, severity: e.target.value }))} className="w-full bg-slate-700 rounded px-3 py-2 text-sm">
                {['critical','high','medium','low','informational'].map(s => <option key={s} value={s}>{s}</option>)}
              </select></div>
          </div>
          <div><label className="block text-xs text-slate-400 mb-1">Description</label>
            <textarea value={form.description || ''} onChange={e => setForm(f => ({ ...f, description: e.target.value }))} className="w-full bg-slate-700 rounded px-3 py-2 text-sm h-20" /></div>
          <div className="grid grid-cols-3 gap-4">
            <div><label className="block text-xs text-slate-400 mb-1">Rule Type</label>
              <select value={form.rule_type || 'query'} onChange={e => setForm(f => ({ ...f, rule_type: e.target.value }))} className="w-full bg-slate-700 rounded px-3 py-2 text-sm">
                {['query','threshold','anomaly'].map(t => <option key={t} value={t}>{t}</option>)}
              </select></div>
            <div><label className="block text-xs text-slate-400 mb-1">Time Window (min)</label>
              <input type="number" value={form.time_window_minutes || 60} onChange={e => setForm(f => ({ ...f, time_window_minutes: +e.target.value }))} className="w-full bg-slate-700 rounded px-3 py-2 text-sm" /></div>
            <div><label className="block text-xs text-slate-400 mb-1">Threshold Count</label>
              <input type="number" value={form.threshold_count || 1} onChange={e => setForm(f => ({ ...f, threshold_count: +e.target.value }))} className="w-full bg-slate-700 rounded px-3 py-2 text-sm" /></div>
          </div>
          <div>
            <div className="flex items-center justify-between mb-2"><label className="text-xs text-slate-400">Conditions</label>
              <button onClick={addCondition} className="text-xs text-blue-400 flex items-center gap-1"><Plus size={12} />Add</button></div>
            {(form.conditions || []).map((c, i) => (
              <div key={i} className="flex gap-2 mb-2">
                <input value={c.field} onChange={e => updateCondition(i, 'field', e.target.value)} placeholder="Field" className="flex-1 bg-slate-700 rounded px-3 py-1.5 text-sm" />
                <select value={c.operator} onChange={e => updateCondition(i, 'operator', e.target.value)} className="bg-slate-700 rounded px-3 py-1.5 text-sm">
                  {['equals','contains','greater_than','less_than','regex'].map(o => <option key={o} value={o}>{o}</option>)}
                </select>
                <input value={c.value} onChange={e => updateCondition(i, 'value', e.target.value)} placeholder="Value" className="flex-1 bg-slate-700 rounded px-3 py-1.5 text-sm" />
                <button onClick={() => removeCondition(i)} className="text-red-400"><Trash2 size={14} /></button>
              </div>
            ))}
          </div>
          <div><label className="block text-xs text-slate-400 mb-1">MITRE Tactics</label>
            <div className="flex flex-wrap gap-2">{MITRE_TACTICS.map(t => (
              <label key={t} className="flex items-center gap-1 text-xs cursor-pointer">
                <input type="checkbox" checked={(form.mitre_tactics || []).includes(t)}
                  onChange={e => setForm(f => ({ ...f, mitre_tactics: e.target.checked ? [...(f.mitre_tactics || []), t] : (f.mitre_tactics || []).filter(x => x !== t) }))} />
                <span className="text-slate-300">{t}</span>
              </label>
            ))}</div></div>
          <div className="grid grid-cols-2 gap-4">
            <div><label className="block text-xs text-slate-400 mb-1">MITRE Techniques (comma-separated)</label>
              <input value={form.mitre_techniques || ''} onChange={e => setForm(f => ({ ...f, mitre_techniques: e.target.value }))} className="w-full bg-slate-700 rounded px-3 py-2 text-sm" placeholder="T1110, T1078" /></div>
            <div><label className="block text-xs text-slate-400 mb-1">Tags (comma-separated)</label>
              <input value={form.tags || ''} onChange={e => setForm(f => ({ ...f, tags: e.target.value }))} className="w-full bg-slate-700 rounded px-3 py-2 text-sm" placeholder="identity, brute-force" /></div>
          </div>
          <div className="flex gap-3 pt-2">
            <button onClick={save} className="px-6 py-2 bg-orange-600 rounded-lg hover:bg-orange-700 text-sm font-medium">
              {editId ? 'Update Rule' : 'Create Rule'}
            </button>
            <button onClick={() => { setForm(emptyRule()); setEditId(null); setTab('rules'); }} className="px-6 py-2 bg-slate-700 rounded-lg text-sm">Cancel</button>
          </div>
        </div>
      )}

      {tab === 'stats' && stats && (
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          {[
            { label: 'Total Rules', value: stats.total, icon: <Shield size={20} />, color: 'text-blue-400' },
            { label: 'Enabled', value: stats.enabled, icon: <CheckCircle size={20} />, color: 'text-green-400' },
            { label: 'Disabled', value: stats.disabled, icon: <ToggleLeft size={20} />, color: 'text-slate-400' },
            { label: 'Triggers (24h)', value: stats.triggers_last_24h || 0, icon: <AlertTriangle size={20} />, color: 'text-orange-400' },
          ].map(k => (
            <div key={k.label} className="bg-slate-800 rounded-xl p-5 flex items-center gap-4">
              <span className={k.color}>{k.icon}</span>
              <div><div className="text-2xl font-bold">{k.value}</div><div className="text-sm text-slate-400">{k.label}</div></div>
            </div>
          ))}
          {stats.by_severity && (
            <div className="col-span-2 lg:col-span-4 bg-slate-800 rounded-xl p-5">
              <h3 className="text-sm font-medium text-slate-300 mb-3 flex items-center gap-2"><BarChart2 size={16} /> By Severity</h3>
              {Object.entries(stats.by_severity as Record<string,number>).map(([sev, count]) => (
                <div key={sev} className="flex items-center gap-3 mb-2 text-sm">
                  <span className={`w-20 text-right ${SEVERITY_COLORS[sev]?.split(' ')[1]}`}>{sev}</span>
                  <div className="flex-1 bg-slate-700 rounded-full h-2">
                    <div className="bg-orange-500 h-2 rounded-full" style={{ width: `${Math.min(100, (count / (stats.total || 1)) * 100)}%` }} />
                  </div>
                  <span className="text-slate-400 w-8">{count}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

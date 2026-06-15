import React, { useState, useEffect } from 'react';
import { authFetch } from '../services/apiService';
import { showToast } from '../utils/toast';

interface CaPolicy {
  id: string;
  name: string;
  description: string;
  enabled: boolean;
  priority: number;
  action: string;
  conditions: {
    device_trust_below?: number;
    session_risk_above?: number;
    require_location_known?: boolean;
    allowed_hours_start?: number;
    allowed_hours_end?: number;
    user_groups?: string[];
    platforms?: string[];
  };
  hit_count: number;
  last_triggered: string | null;
  created_at: string;
}

interface Summary { total: number; enabled: number; deny_policies: number; mfa_policies: number; }

const ACTION_STYLES: Record<string, string> = {
  allow: 'bg-green-900/40 text-green-300',
  deny: 'bg-red-900/40 text-red-300',
  require_mfa: 'bg-yellow-900/40 text-yellow-300',
  require_compliant_device: 'bg-blue-900/40 text-blue-300',
};

const BLANK_FORM = {
  name: '', description: '', enabled: true, priority: 100, action: 'deny',
  conditions: {
    device_trust_below: '' as any, session_risk_above: '' as any,
    require_location_known: false, allowed_hours_start: '' as any, allowed_hours_end: '' as any,
    user_groups: '', platforms: '',
  },
};

export default function ConditionalAccessDashboard() {
  const [policies, setPolicies] = useState<CaPolicy[]>([]);
  const [summary, setSummary] = useState<Summary | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [editPolicy, setEditPolicy] = useState<CaPolicy | null>(null);
  const [form, setForm] = useState({ ...BLANK_FORM });
  const [saving, setSaving] = useState(false);
  const [testCtx, setTestCtx] = useState({ device_trust_score: '80', session_risk_score: '20', location_known: true, platform: 'windows' });
  const [testResult, setTestResult] = useState<any>(null);

  useEffect(() => { loadAll(); }, []);

  async function loadAll() {
    try {
      const [pRes, sRes] = await Promise.all([
        authFetch('/api/conditional-access/policies'),
        authFetch('/api/conditional-access/summary'),
      ]);
      const [p, s] = await Promise.all([pRes.json(), sRes.json()]);
      setPolicies(p.policies || []);
      setSummary(s);
    } catch (e) { console.error(e); }
  }

  function openCreate() {
    setEditPolicy(null);
    setForm({ ...BLANK_FORM });
    setShowForm(true);
  }

  function openEdit(p: CaPolicy) {
    setEditPolicy(p);
    setForm({
      name: p.name, description: p.description, enabled: p.enabled,
      priority: p.priority, action: p.action,
      conditions: {
        device_trust_below: p.conditions.device_trust_below ?? '',
        session_risk_above: p.conditions.session_risk_above ?? '',
        require_location_known: p.conditions.require_location_known ?? false,
        allowed_hours_start: p.conditions.allowed_hours_start ?? '',
        allowed_hours_end: p.conditions.allowed_hours_end ?? '',
        user_groups: (p.conditions.user_groups || []).join(', '),
        platforms: (p.conditions.platforms || []).join(', '),
      },
    });
    setShowForm(true);
  }

  function buildPayload() {
    const c = form.conditions;
    return {
      name: form.name, description: form.description, enabled: form.enabled,
      priority: Number(form.priority), action: form.action,
      conditions: {
        device_trust_below: c.device_trust_below !== '' ? Number(c.device_trust_below) : undefined,
        session_risk_above: c.session_risk_above !== '' ? Number(c.session_risk_above) : undefined,
        require_location_known: c.require_location_known,
        allowed_hours_start: c.allowed_hours_start !== '' ? Number(c.allowed_hours_start) : undefined,
        allowed_hours_end: c.allowed_hours_end !== '' ? Number(c.allowed_hours_end) : undefined,
        user_groups: c.user_groups ? c.user_groups.split(',').map((s: string) => s.trim()).filter(Boolean) : [],
        platforms: c.platforms ? c.platforms.split(',').map((s: string) => s.trim()).filter(Boolean) : [],
      },
    };
  }

  async function savePolicy() {
    setSaving(true);
    try {
      const url = editPolicy ? `/api/conditional-access/policies/${editPolicy.id}` : '/api/conditional-access/policies';
      const method = editPolicy ? 'PATCH' : 'POST';
      const r = await authFetch(url, {
        method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(buildPayload()),
      });
      if (r.ok) {
        showToast(editPolicy ? 'Policy updated' : 'Policy created', 'success');
        setShowForm(false);
        loadAll();
      } else {
        const d = await r.json();
        showToast(d.detail || 'Failed', 'error');
      }
    } finally { setSaving(false); }
  }

  async function deletePolicy(id: string) {
    if (!confirm('Delete this policy?')) return;
    const r = await authFetch(`/api/conditional-access/policies/${id}`, { method: 'DELETE' });
    if (r.ok) { showToast('Policy deleted', 'success'); loadAll(); }
  }

  async function toggleEnabled(p: CaPolicy) {
    await authFetch(`/api/conditional-access/policies/${p.id}`, {
      method: 'PATCH', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ enabled: !p.enabled }),
    });
    loadAll();
  }

  async function runTest() {
    const r = await authFetch('/api/conditional-access/evaluate', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ...testCtx, device_trust_score: Number(testCtx.device_trust_score), session_risk_score: Number(testCtx.session_risk_score) }),
    });
    const d = await r.json();
    setTestResult(d);
  }

  function setCondition(key: string, value: any) {
    setForm(f => ({ ...f, conditions: { ...f.conditions, [key]: value } }));
  }

  return (
    <div className="p-6 bg-gray-900 min-h-screen text-white">
      <div className="flex justify-between items-start mb-6">
        <div>
          <h1 className="text-2xl font-bold">Conditional Access</h1>
          <p className="text-gray-400 text-sm mt-1">Evaluate and enforce access policies based on device trust, session risk, and context</p>
        </div>
        <button onClick={openCreate} className="px-4 py-2 text-sm bg-blue-700 hover:bg-blue-600 rounded-lg">+ New Policy</button>
      </div>

      {/* Summary */}
      {summary && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-6">
          {[
            { label: 'Total Policies', value: summary.total, color: 'text-white' },
            { label: 'Enabled', value: summary.enabled, color: 'text-green-400' },
            { label: 'Deny Actions', value: summary.deny_policies, color: 'text-red-400' },
            { label: 'MFA Required', value: summary.mfa_policies, color: 'text-yellow-400' },
          ].map(c => (
            <div key={c.label} className="bg-gray-800 rounded-lg p-4 text-center">
              <div className={`text-2xl font-bold ${c.color}`}>{c.value}</div>
              <div className="text-xs text-gray-400 mt-1">{c.label}</div>
            </div>
          ))}
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Policy list */}
        <div className="lg:col-span-2">
          <h2 className="text-sm font-medium text-gray-400 uppercase mb-3">Policies (evaluated in priority order)</h2>
          <div className="space-y-3">
            {policies.length === 0 && <div className="text-gray-500 text-sm py-8 text-center bg-gray-800 rounded-lg">No policies configured — all access is allowed by default</div>}
            {policies.map(p => (
              <div key={p.id} className={`bg-gray-800 rounded-lg p-4 border ${p.enabled ? 'border-gray-700' : 'border-gray-800 opacity-60'}`}>
                <div className="flex items-start justify-between">
                  <div className="flex items-center gap-3">
                    <span className="text-xs text-gray-500 w-8 text-right font-mono">#{p.priority}</span>
                    <div>
                      <div className="flex items-center gap-2">
                        <span className="font-medium text-white">{p.name}</span>
                        <span className={`px-2 py-0.5 rounded-full text-xs ${ACTION_STYLES[p.action] || 'bg-gray-700 text-gray-300'}`}>
                          {p.action.replace(/_/g, ' ')}
                        </span>
                        {!p.enabled && <span className="text-xs text-gray-600">(disabled)</span>}
                      </div>
                      {p.description && <p className="text-gray-400 text-xs mt-0.5">{p.description}</p>}
                      <div className="flex gap-4 mt-1.5 text-xs text-gray-500">
                        {p.conditions.device_trust_below != null && <span>Trust &lt; {p.conditions.device_trust_below}%</span>}
                        {p.conditions.session_risk_above != null && <span>Risk &gt; {p.conditions.session_risk_above}%</span>}
                        {p.conditions.require_location_known && <span>Unknown location</span>}
                        {p.hit_count > 0 && <span className="text-blue-400">{p.hit_count} hits</span>}
                      </div>
                    </div>
                  </div>
                  <div className="flex gap-2 shrink-0 ml-4">
                    <button onClick={() => toggleEnabled(p)} className="text-xs text-gray-400 hover:text-white">{p.enabled ? 'Disable' : 'Enable'}</button>
                    <button onClick={() => openEdit(p)} className="text-xs text-blue-400 hover:text-blue-300">Edit</button>
                    <button onClick={() => deletePolicy(p.id)} className="text-xs text-red-400 hover:text-red-300">Delete</button>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Policy tester */}
        <div>
          <h2 className="text-sm font-medium text-gray-400 uppercase mb-3">Policy Tester</h2>
          <div className="bg-gray-800 rounded-lg p-4 space-y-3">
            <div>
              <label className="text-xs text-gray-400 block mb-1">Device Trust Score (0–100)</label>
              <input type="number" value={testCtx.device_trust_score} onChange={e => setTestCtx(c => ({ ...c, device_trust_score: e.target.value }))}
                className="w-full bg-gray-700 border border-gray-600 rounded px-3 py-2 text-sm" />
            </div>
            <div>
              <label className="text-xs text-gray-400 block mb-1">Session Risk Score (0–100)</label>
              <input type="number" value={testCtx.session_risk_score} onChange={e => setTestCtx(c => ({ ...c, session_risk_score: e.target.value }))}
                className="w-full bg-gray-700 border border-gray-600 rounded px-3 py-2 text-sm" />
            </div>
            <div>
              <label className="text-xs text-gray-400 block mb-1">Platform</label>
              <select value={testCtx.platform} onChange={e => setTestCtx(c => ({ ...c, platform: e.target.value }))}
                className="w-full bg-gray-700 border border-gray-600 rounded px-3 py-2 text-sm">
                {['windows', 'macos', 'linux', 'ios', 'android'].map(p => <option key={p} value={p}>{p}</option>)}
              </select>
            </div>
            <label className="flex items-center gap-2 text-sm cursor-pointer">
              <input type="checkbox" checked={testCtx.location_known} onChange={e => setTestCtx(c => ({ ...c, location_known: e.target.checked }))} className="accent-blue-500" />
              <span className="text-gray-300">Location Known</span>
            </label>
            <button onClick={runTest} className="w-full py-2 text-sm bg-indigo-700 hover:bg-indigo-600 rounded-lg">Evaluate</button>
            {testResult && (
              <div className={`rounded-lg p-3 text-sm ${testResult.decision === 'allow' ? 'bg-green-900/30 border border-green-700' : testResult.decision === 'deny' ? 'bg-red-900/30 border border-red-700' : 'bg-yellow-900/30 border border-yellow-700'}`}>
                <div className="font-medium capitalize">{testResult.decision.replace(/_/g, ' ')}</div>
                <div className="text-xs text-gray-400 mt-1">{testResult.reason}</div>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Create/Edit Modal */}
      {showForm && (
        <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50 p-4">
          <div className="bg-gray-800 rounded-xl p-6 w-full max-w-lg border border-gray-700 max-h-[90vh] overflow-y-auto">
            <h2 className="text-lg font-semibold mb-4">{editPolicy ? 'Edit Policy' : 'New Conditional Access Policy'}</h2>
            <div className="space-y-3">
              <div>
                <label className="text-xs text-gray-400 block mb-1">Name *</label>
                <input value={form.name} onChange={e => setForm(f => ({ ...f, name: e.target.value }))}
                  className="w-full bg-gray-700 border border-gray-600 rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-blue-500" />
              </div>
              <div>
                <label className="text-xs text-gray-400 block mb-1">Description</label>
                <input value={form.description} onChange={e => setForm(f => ({ ...f, description: e.target.value }))}
                  className="w-full bg-gray-700 border border-gray-600 rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-blue-500" />
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="text-xs text-gray-400 block mb-1">Action</label>
                  <select value={form.action} onChange={e => setForm(f => ({ ...f, action: e.target.value }))}
                    className="w-full bg-gray-700 border border-gray-600 rounded-lg px-3 py-2 text-sm">
                    <option value="allow">Allow</option>
                    <option value="deny">Deny</option>
                    <option value="require_mfa">Require MFA</option>
                    <option value="require_compliant_device">Require Compliant Device</option>
                  </select>
                </div>
                <div>
                  <label className="text-xs text-gray-400 block mb-1">Priority (lower = first)</label>
                  <input type="number" value={form.priority} onChange={e => setForm(f => ({ ...f, priority: e.target.value as any }))}
                    className="w-full bg-gray-700 border border-gray-600 rounded-lg px-3 py-2 text-sm" />
                </div>
              </div>
              <p className="text-xs text-gray-500 font-medium uppercase pt-1">Conditions (all filled conditions must match)</p>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="text-xs text-gray-400 block mb-1">Device Trust Below (%)</label>
                  <input type="number" placeholder="e.g. 70" value={form.conditions.device_trust_below} onChange={e => setCondition('device_trust_below', e.target.value)}
                    className="w-full bg-gray-700 border border-gray-600 rounded-lg px-3 py-2 text-sm" />
                </div>
                <div>
                  <label className="text-xs text-gray-400 block mb-1">Session Risk Above (%)</label>
                  <input type="number" placeholder="e.g. 60" value={form.conditions.session_risk_above} onChange={e => setCondition('session_risk_above', e.target.value)}
                    className="w-full bg-gray-700 border border-gray-600 rounded-lg px-3 py-2 text-sm" />
                </div>
                <div>
                  <label className="text-xs text-gray-400 block mb-1">Allowed Hours Start (0–23)</label>
                  <input type="number" placeholder="e.g. 8" value={form.conditions.allowed_hours_start} onChange={e => setCondition('allowed_hours_start', e.target.value)}
                    className="w-full bg-gray-700 border border-gray-600 rounded-lg px-3 py-2 text-sm" />
                </div>
                <div>
                  <label className="text-xs text-gray-400 block mb-1">Allowed Hours End (0–23)</label>
                  <input type="number" placeholder="e.g. 18" value={form.conditions.allowed_hours_end} onChange={e => setCondition('allowed_hours_end', e.target.value)}
                    className="w-full bg-gray-700 border border-gray-600 rounded-lg px-3 py-2 text-sm" />
                </div>
              </div>
              <div>
                <label className="text-xs text-gray-400 block mb-1">Platforms (comma-separated: windows, macos, linux, ios, android)</label>
                <input value={form.conditions.platforms} onChange={e => setCondition('platforms', e.target.value)} placeholder="Leave blank for all"
                  className="w-full bg-gray-700 border border-gray-600 rounded-lg px-3 py-2 text-sm" />
              </div>
              <label className="flex items-center gap-2 text-sm cursor-pointer">
                <input type="checkbox" checked={form.conditions.require_location_known} onChange={e => setCondition('require_location_known', e.target.checked)} className="accent-blue-500" />
                <span className="text-gray-300">Trigger on unknown location</span>
              </label>
              <label className="flex items-center gap-2 text-sm cursor-pointer">
                <input type="checkbox" checked={form.enabled} onChange={e => setForm(f => ({ ...f, enabled: e.target.checked }))} className="accent-blue-500" />
                <span className="text-gray-300">Enabled</span>
              </label>
            </div>
            <div className="flex gap-2 mt-4 justify-end">
              <button onClick={() => setShowForm(false)} className="px-4 py-2 text-sm text-gray-400 hover:text-white">Cancel</button>
              <button onClick={savePolicy} disabled={saving || !form.name}
                className="px-4 py-2 text-sm bg-blue-700 hover:bg-blue-600 rounded-lg disabled:opacity-50">
                {saving ? 'Saving…' : (editPolicy ? 'Update' : 'Create')}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

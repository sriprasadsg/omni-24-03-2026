import React, { useState, useEffect, useCallback } from 'react';

const API = '/api/active-response';

type Mode = 'automatic' | 'manual' | 'supervised';

interface Rule {
  id: string;
  name: string;
  description: string;
  trigger: string;
  trigger_threshold: number;
  actions: string[];
  mode: Mode;
  enabled: boolean;
  timeout_seconds: number;
  execution_count: number;
  created_at: string;
}

interface Execution {
  id: string;
  agent_id: string;
  action: string;
  status: 'queued' | 'running' | 'completed' | 'failed';
  mode: string;
  triggered_by: string;
  triggered_at: string;
  reason?: string;
}

interface Stats {
  total_rules: number;
  enabled_rules: number;
  total_executions: number;
  top_actions: { action: string; count: number }[];
  rules_by_mode: Record<string, number>;
}

const MODE_STYLE: Record<Mode, string> = {
  automatic: 'bg-red-500/20 text-red-400 border-red-500/30',
  supervised: 'bg-yellow-500/20 text-yellow-400 border-yellow-500/30',
  manual: 'bg-blue-500/20 text-blue-400 border-blue-500/30',
};

const STATUS_STYLE: Record<string, string> = {
  completed: 'text-emerald-400',
  failed: 'text-red-400',
  running: 'text-yellow-400',
  queued: 'text-slate-400',
};

const ACTION_LABELS: Record<string, string> = {
  block_ip: 'Block IP', unblock_ip: 'Unblock IP',
  disable_user: 'Disable User', enable_user: 'Enable User',
  kill_process: 'Kill Process', quarantine_host: 'Quarantine Host',
  isolate_agent: 'Isolate Agent', unisolate_agent: 'Unisolate Agent',
  run_sca_scan: 'Run SCA Scan', collect_forensics: 'Collect Forensics',
  send_alert: 'Send Alert', create_ticket: 'Create Ticket',
};

const TRIGGER_LABELS: Record<string, string> = {
  alert_severity_critical: 'Critical Alert', alert_severity_high: 'High Alert',
  failed_login_threshold: 'Failed Login Threshold', malware_detected: 'Malware Detected',
  fim_change_critical: 'FIM Critical Change', port_scan_detected: 'Port Scan',
  brute_force_detected: 'Brute Force', new_process_suspicious: 'Suspicious Process',
  ransomware_indicator: 'Ransomware Indicator', lateral_movement_detected: 'Lateral Movement',
};

const MOCK_STATS: Stats = {
  total_rules: 6, enabled_rules: 4, total_executions: 89,
  top_actions: [
    { action: 'block_ip', count: 34 }, { action: 'isolate_agent', count: 18 },
    { action: 'kill_process', count: 15 }, { action: 'disable_user', count: 12 },
    { action: 'send_alert', count: 10 },
  ],
  rules_by_mode: { supervised: 3, automatic: 2, manual: 1 },
};

const MOCK_RULES: Rule[] = [
  { id: 'r1', name: 'Block Brute Force IPs', description: 'Block source IPs on brute force detection', trigger: 'brute_force_detected', trigger_threshold: 5, actions: ['block_ip', 'send_alert'], mode: 'automatic', enabled: true, timeout_seconds: 300, execution_count: 34, created_at: '2026-05-01T00:00:00Z' },
  { id: 'r2', name: 'Quarantine Malware Host', description: 'Isolate agent when malware is confirmed', trigger: 'malware_detected', trigger_threshold: 1, actions: ['isolate_agent', 'collect_forensics', 'create_ticket'], mode: 'supervised', enabled: true, timeout_seconds: 600, execution_count: 18, created_at: '2026-05-02T00:00:00Z' },
  { id: 'r3', name: 'Kill Suspicious Process', description: 'Terminate suspicious processes automatically', trigger: 'new_process_suspicious', trigger_threshold: 1, actions: ['kill_process', 'send_alert'], mode: 'automatic', enabled: true, timeout_seconds: 60, execution_count: 15, created_at: '2026-05-03T00:00:00Z' },
  { id: 'r4', name: 'Ransomware Response', description: 'Full isolation on ransomware indicators', trigger: 'ransomware_indicator', trigger_threshold: 1, actions: ['isolate_agent', 'disable_user', 'create_ticket'], mode: 'supervised', enabled: true, timeout_seconds: 120, execution_count: 3, created_at: '2026-05-10T00:00:00Z' },
];

const MOCK_EXECUTIONS: Execution[] = [
  { id: 'e1', agent_id: 'ag1', action: 'block_ip', status: 'completed', mode: 'automatic', triggered_by: 'system', triggered_at: '2026-06-11T14:25:00Z', reason: 'Brute force detected' },
  { id: 'e2', agent_id: 'ag2', action: 'isolate_agent', status: 'completed', mode: 'supervised', triggered_by: 'admin@corp.com', triggered_at: '2026-06-11T12:15:00Z', reason: 'Malware confirmed' },
  { id: 'e3', agent_id: 'ag3', action: 'kill_process', status: 'failed', mode: 'automatic', triggered_by: 'system', triggered_at: '2026-06-10T18:32:00Z' },
];

const token = () => localStorage.getItem('token') ?? '';
const h = () => ({ Authorization: `Bearer ${token()}` });
const jh = () => ({ ...h(), 'Content-Type': 'application/json' });

export default function ActiveResponseDashboard() {
  const [tab, setTab] = useState<'rules' | 'history' | 'execute'>('rules');
  const [stats, setStats] = useState<Stats>(MOCK_STATS);
  const [rules, setRules] = useState<Rule[]>(MOCK_RULES);
  const [executions, setExecutions] = useState<Execution[]>(MOCK_EXECUTIONS);
  const [validTriggers, setValidTriggers] = useState<string[]>(Object.keys(TRIGGER_LABELS));
  const [validActions, setValidActions] = useState<string[]>(Object.keys(ACTION_LABELS));
  const [showCreate, setShowCreate] = useState(false);
  const [form, setForm] = useState({ name: '', description: '', trigger: '', threshold: 1, actions: [] as string[], mode: 'supervised' as Mode, timeout: 300 });
  const [execForm, setExecForm] = useState({ agent_id: '', action: '', reason: '' });
  const [saving, setSaving] = useState(false);
  const [execMsg, setExecMsg] = useState('');

  const load = useCallback(async () => {
    try {
      const [s, r, e, t] = await Promise.all([
        fetch(`${API}/stats`, { headers: h() }).then(x => x.ok ? x.json() : null),
        fetch(`${API}/rules`, { headers: h() }).then(x => x.ok ? x.json() : null),
        fetch(`${API}/executions?limit=50`, { headers: h() }).then(x => x.ok ? x.json() : null),
        fetch(`${API}/triggers`, { headers: h() }).then(x => x.ok ? x.json() : null),
      ]);
      if (s) setStats(s);
      if (r && r.length > 0) setRules(r);
      if (e && e.length > 0) setExecutions(e);
      if (t) { setValidTriggers(t.triggers); setValidActions(t.actions); }
    } catch { /* use mock */ }
  }, []);

  useEffect(() => { load(); }, [load]);

  const createRule = async () => {
    if (!form.name || !form.trigger || form.actions.length === 0) return;
    setSaving(true);
    try {
      const r = await fetch(`${API}/rules`, {
        method: 'POST',
        headers: jh(),
        body: JSON.stringify({ name: form.name, description: form.description, trigger: form.trigger, trigger_threshold: form.threshold, actions: form.actions, mode: form.mode, timeout_seconds: form.timeout }),
      });
      if (r.ok) {
        const rule = await r.json();
        setRules(prev => [rule, ...prev]);
        setShowCreate(false);
        setForm({ name: '', description: '', trigger: '', threshold: 1, actions: [], mode: 'supervised', timeout: 300 });
      }
    } catch { /* ignore */ }
    setSaving(false);
  };

  const toggleRule = async (rule: Rule) => {
    try {
      const r = await fetch(`${API}/rules/${rule.id}`, {
        method: 'PUT', headers: jh(),
        body: JSON.stringify({ enabled: !rule.enabled }),
      });
      if (r.ok) setRules(prev => prev.map(x => x.id === rule.id ? { ...x, enabled: !x.enabled } : x));
    } catch { /* ignore */ }
  };

  const deleteRule = async (id: string) => {
    try {
      await fetch(`${API}/rules/${id}`, { method: 'DELETE', headers: h() });
      setRules(prev => prev.filter(r => r.id !== id));
    } catch { /* ignore */ }
  };

  const executeAction = async () => {
    if (!execForm.agent_id || !execForm.action) return;
    setSaving(true);
    try {
      const r = await fetch(`${API}/execute`, {
        method: 'POST', headers: jh(),
        body: JSON.stringify({ agent_id: execForm.agent_id, action: execForm.action, reason: execForm.reason }),
      });
      const d = await r.json();
      setExecMsg(`Execution queued: ${d.action} on ${d.agent_id}`);
      setExecForm({ agent_id: '', action: '', reason: '' });
      load();
    } catch { setExecMsg('Execution failed'); }
    setSaving(false);
    setTimeout(() => setExecMsg(''), 5000);
  };

  const toggleAction = (action: string) =>
    setForm(prev => ({
      ...prev,
      actions: prev.actions.includes(action) ? prev.actions.filter(a => a !== action) : [...prev.actions, action],
    }));

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="text-2xl font-bold text-white">Active Response</h2>
        <span className="text-sm text-slate-400">{stats.enabled_rules} of {stats.total_rules} rules active</span>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {[
          { label: 'Total Rules', value: stats.total_rules, cls: 'text-blue-400' },
          { label: 'Active Rules', value: stats.enabled_rules, cls: 'text-emerald-400' },
          { label: 'Executions', value: stats.total_executions, cls: 'text-yellow-400' },
          { label: 'Auto Rules', value: stats.rules_by_mode['automatic'] ?? 0, cls: 'text-red-400' },
        ].map(k => (
          <div key={k.label} className="bg-slate-800 border border-slate-700 rounded-xl p-4 text-center">
            <div className={`text-2xl font-bold ${k.cls}`}>{k.value}</div>
            <div className="text-xs text-slate-400 mt-1">{k.label}</div>
          </div>
        ))}
      </div>

      {stats.rules_by_mode['automatic'] > 0 && (
        <div className="bg-yellow-500/10 border border-yellow-500/30 rounded-xl px-4 py-3 text-yellow-300 text-sm">
          ⚠ {stats.rules_by_mode['automatic']} rule(s) set to <strong>automatic</strong> mode — actions execute without approval. Test carefully before enabling in production.
        </div>
      )}

      <div className="flex rounded-lg overflow-hidden border border-slate-700 w-fit">
        {(['rules', 'history', 'execute'] as const).map(t => (
          <button key={t} onClick={() => setTab(t)}
            className={`px-4 py-2 text-sm font-medium capitalize transition-colors ${tab === t ? 'bg-blue-600 text-white' : 'bg-slate-800 text-slate-300 hover:bg-slate-700'}`}>
            {t === 'execute' ? 'Manual Execute' : t}
          </button>
        ))}
      </div>

      {tab === 'rules' && (
        <div className="space-y-4">
          <button onClick={() => setShowCreate(true)}
            className="px-4 py-2 rounded-lg bg-blue-600 text-white text-sm font-medium hover:bg-blue-700 transition-colors">
            + New Rule
          </button>
          <div className="space-y-3">
            {rules.map(rule => (
              <div key={rule.id} className="bg-slate-800 border border-slate-700 rounded-xl p-4 space-y-3">
                <div className="flex items-start justify-between">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="font-semibold text-white">{rule.name}</span>
                      <span className={`text-xs px-2 py-0.5 rounded-full border capitalize ${MODE_STYLE[rule.mode]}`}>{rule.mode}</span>
                      <span className={`text-xs px-2 py-0.5 rounded-full border ${rule.enabled ? 'bg-emerald-500/20 text-emerald-400 border-emerald-500/30' : 'bg-slate-700/50 text-slate-400 border-slate-600/30'}`}>
                        {rule.enabled ? 'Enabled' : 'Disabled'}
                      </span>
                    </div>
                    <p className="text-xs text-slate-400 mt-1">{rule.description}</p>
                  </div>
                  <div className="flex items-center gap-2 shrink-0 ml-4">
                    <button onClick={() => toggleRule(rule)}
                      className="text-xs px-2 py-1 rounded bg-slate-700 text-slate-300 hover:bg-slate-600 transition-colors">
                      {rule.enabled ? 'Pause' : 'Enable'}
                    </button>
                    <button onClick={() => deleteRule(rule.id)}
                      className="text-xs text-slate-500 hover:text-red-400 transition-colors">Delete</button>
                  </div>
                </div>
                <div className="flex flex-wrap gap-4 text-xs text-slate-400">
                  <span>Trigger: <span className="text-slate-200">{TRIGGER_LABELS[rule.trigger] ?? rule.trigger}</span> (≥{rule.trigger_threshold}×)</span>
                  <span>Executions: <span className="text-slate-200">{rule.execution_count}</span></span>
                  <span>Timeout: <span className="text-slate-200">{rule.timeout_seconds}s</span></span>
                </div>
                <div className="flex flex-wrap gap-1">
                  {rule.actions.map(a => (
                    <span key={a} className="text-xs px-2 py-0.5 rounded bg-blue-600/20 text-blue-400 border border-blue-600/30">
                      {ACTION_LABELS[a] ?? a}
                    </span>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {tab === 'history' && (
        <div className="bg-slate-800 border border-slate-700 rounded-xl overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-slate-700 text-slate-400 text-xs">
                <th className="px-4 py-2 text-left">Action</th>
                <th className="px-4 py-2 text-left">Agent</th>
                <th className="px-4 py-2 text-left">Mode</th>
                <th className="px-4 py-2 text-left">Status</th>
                <th className="px-4 py-2 text-left">Triggered By</th>
                <th className="px-4 py-2 text-left">Time</th>
              </tr>
            </thead>
            <tbody>
              {executions.map(e => (
                <tr key={e.id} className="border-b border-slate-700/50 hover:bg-slate-700/30">
                  <td className="px-4 py-3 text-slate-200 text-xs">{ACTION_LABELS[e.action] ?? e.action}</td>
                  <td className="px-4 py-3 text-slate-400 font-mono text-xs truncate max-w-xs">{e.agent_id}</td>
                  <td className="px-4 py-3">
                    <span className={`text-xs px-1.5 py-0.5 rounded capitalize ${MODE_STYLE[e.mode as Mode] ?? 'bg-slate-700 text-slate-300 border-slate-600 border'}`}>{e.mode}</span>
                  </td>
                  <td className={`px-4 py-3 text-xs font-medium capitalize ${STATUS_STYLE[e.status]}`}>{e.status}</td>
                  <td className="px-4 py-3 text-slate-400 text-xs">{e.triggered_by}</td>
                  <td className="px-4 py-3 text-slate-400 text-xs">{new Date(e.triggered_at).toLocaleString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {tab === 'execute' && (
        <div className="max-w-lg space-y-4">
          {execMsg && <div className="bg-blue-500/20 border border-blue-500/30 text-blue-300 text-sm px-4 py-2 rounded-lg">{execMsg}</div>}
          <div className="bg-slate-800 border border-slate-700 rounded-xl p-5 space-y-4">
            <h3 className="text-sm font-semibold text-white">Execute Action Manually</h3>
            <div className="space-y-1">
              <label className="text-xs text-slate-400">Agent ID</label>
              <input value={execForm.agent_id} onChange={e => setExecForm(p => ({ ...p, agent_id: e.target.value }))}
                placeholder="Agent UUID"
                className="w-full bg-slate-700 border border-slate-600 rounded-lg px-3 py-2 text-white text-sm font-mono focus:outline-none focus:border-blue-500" />
            </div>
            <div className="space-y-1">
              <label className="text-xs text-slate-400">Action</label>
              <select value={execForm.action} onChange={e => setExecForm(p => ({ ...p, action: e.target.value }))}
                className="w-full bg-slate-700 border border-slate-600 rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:border-blue-500">
                <option value="">Select action…</option>
                {validActions.map(a => <option key={a} value={a}>{ACTION_LABELS[a] ?? a}</option>)}
              </select>
            </div>
            <div className="space-y-1">
              <label className="text-xs text-slate-400">Reason / Notes</label>
              <input value={execForm.reason} onChange={e => setExecForm(p => ({ ...p, reason: e.target.value }))}
                placeholder="Why are you triggering this action?"
                className="w-full bg-slate-700 border border-slate-600 rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:border-blue-500" />
            </div>
            <button onClick={executeAction} disabled={saving || !execForm.agent_id || !execForm.action}
              className="w-full py-2 rounded-lg bg-red-600 text-white text-sm font-medium hover:bg-red-700 transition-colors disabled:opacity-50">
              {saving ? 'Executing…' : 'Execute Action'}
            </button>
          </div>
        </div>
      )}

      {showCreate && (
        <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50 p-4" onClick={() => setShowCreate(false)}>
          <div className="bg-slate-900 border border-slate-700 rounded-2xl w-full max-w-lg p-6 space-y-4 max-h-[90vh] overflow-y-auto"
            onClick={e => e.stopPropagation()}>
            <div className="flex items-center justify-between">
              <h3 className="text-lg font-bold text-white">New Active Response Rule</h3>
              <button onClick={() => setShowCreate(false)} className="text-slate-400 hover:text-white">&times;</button>
            </div>
            <div className="space-y-3">
              {[
                { label: 'Rule Name *', key: 'name', placeholder: 'Block Brute Force IPs' },
                { label: 'Description', key: 'description', placeholder: 'Optional description' },
              ].map(f => (
                <div key={f.key} className="space-y-1">
                  <label className="text-xs text-slate-400">{f.label}</label>
                  <input value={(form as any)[f.key]} onChange={e => setForm(p => ({ ...p, [f.key]: e.target.value }))}
                    placeholder={f.placeholder}
                    className="w-full bg-slate-800 border border-slate-600 rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:border-blue-500" />
                </div>
              ))}
              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-1">
                  <label className="text-xs text-slate-400">Trigger *</label>
                  <select value={form.trigger} onChange={e => setForm(p => ({ ...p, trigger: e.target.value }))}
                    className="w-full bg-slate-800 border border-slate-600 rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:border-blue-500">
                    <option value="">Select trigger…</option>
                    {validTriggers.map(t => <option key={t} value={t}>{TRIGGER_LABELS[t] ?? t}</option>)}
                  </select>
                </div>
                <div className="space-y-1">
                  <label className="text-xs text-slate-400">Mode *</label>
                  <select value={form.mode} onChange={e => setForm(p => ({ ...p, mode: e.target.value as Mode }))}
                    className="w-full bg-slate-800 border border-slate-600 rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:border-blue-500">
                    <option value="supervised">Supervised (approval required)</option>
                    <option value="automatic">Automatic (no approval)</option>
                    <option value="manual">Manual (UI trigger only)</option>
                  </select>
                </div>
              </div>
              <div className="space-y-1">
                <label className="text-xs text-slate-400">Actions * (select one or more)</label>
                <div className="flex flex-wrap gap-2">
                  {validActions.map(a => (
                    <label key={a} className="flex items-center gap-1.5 cursor-pointer">
                      <input type="checkbox" checked={form.actions.includes(a)} onChange={() => toggleAction(a)} className="w-3 h-3" />
                      <span className="text-xs text-slate-300">{ACTION_LABELS[a] ?? a}</span>
                    </label>
                  ))}
                </div>
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-1">
                  <label className="text-xs text-slate-400">Trigger Threshold</label>
                  <input type="number" value={form.threshold} min={1}
                    onChange={e => setForm(p => ({ ...p, threshold: parseInt(e.target.value) || 1 }))}
                    className="w-full bg-slate-800 border border-slate-600 rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:border-blue-500" />
                </div>
                <div className="space-y-1">
                  <label className="text-xs text-slate-400">Timeout (seconds)</label>
                  <input type="number" value={form.timeout} min={10} max={3600}
                    onChange={e => setForm(p => ({ ...p, timeout: parseInt(e.target.value) || 300 }))}
                    className="w-full bg-slate-800 border border-slate-600 rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:border-blue-500" />
                </div>
              </div>
            </div>
            <div className="flex gap-3 pt-2">
              <button onClick={() => setShowCreate(false)} className="flex-1 py-2 rounded-lg border border-slate-600 text-slate-300 text-sm hover:bg-slate-800 transition-colors">Cancel</button>
              <button onClick={createRule} disabled={saving || !form.name || !form.trigger || form.actions.length === 0}
                className="flex-1 py-2 rounded-lg bg-blue-600 text-white text-sm font-medium hover:bg-blue-700 transition-colors disabled:opacity-50">
                {saving ? 'Creating…' : 'Create Rule'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

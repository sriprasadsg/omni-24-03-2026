import React, { useState, useEffect, useCallback } from 'react';

const API = '/api/config-drift';

interface DriftStats {
  total_baselines: number;
  open_drifts: number;
  agents_with_drift: number;
  by_severity: { critical: number; high: number; medium: number; low: number };
}

interface Snapshot {
  id: string;
  agent_id: string;
  hostname: string;
  platform: string;
  captured_at: string;
  monitored_keys: string[];
  drift_count: number;
}

interface DriftItem {
  key: string;
  expected: string;
  actual: string;
  severity: 'critical' | 'high' | 'medium' | 'low';
  detected_at: string;
}

interface AgentDrift {
  agent_id: string;
  hostname: string;
  baseline_captured_at: string;
  drift_count: number;
  drift_items: DriftItem[];
}

const SEV_STYLE: Record<string, string> = {
  critical: 'bg-red-500/20 text-red-400 border-red-500/30',
  high: 'bg-orange-500/20 text-orange-400 border-orange-500/30',
  medium: 'bg-yellow-500/20 text-yellow-400 border-yellow-500/30',
  low: 'bg-blue-500/20 text-blue-400 border-blue-500/30',
};

const MOCK_STATS: DriftStats = {
  total_baselines: 8,
  open_drifts: 23,
  agents_with_drift: 5,
  by_severity: { critical: 4, high: 9, medium: 10, low: 0 },
};

const MOCK_SNAPSHOTS: Snapshot[] = [
  { id: 's1', agent_id: 'a1', hostname: 'web-server-01', platform: 'linux', captured_at: '2026-06-01T09:00:00Z', monitored_keys: [], drift_count: 7 },
  { id: 's2', agent_id: 'a2', hostname: 'db-server-01', platform: 'linux', captured_at: '2026-06-01T09:00:00Z', monitored_keys: [], drift_count: 0 },
  { id: 's3', agent_id: 'a3', hostname: 'workstation-ceo', platform: 'windows', captured_at: '2026-06-02T08:00:00Z', monitored_keys: [], drift_count: 4 },
  { id: 's4', agent_id: 'a4', hostname: 'dev-laptop-01', platform: 'linux', captured_at: '2026-06-03T10:00:00Z', monitored_keys: [], drift_count: 12 },
];

const token = () => sessionStorage.getItem('token') ?? '';
const h = () => ({ Authorization: `Bearer ${token()}` });
const jh = () => ({ ...h(), 'Content-Type': 'application/json' });

export default function ConfigDriftDashboard() {
  const [stats, setStats] = useState<DriftStats>(MOCK_STATS);
  const [snapshots, setSnapshots] = useState<Snapshot[]>(MOCK_SNAPSHOTS);
  const [selected, setSelected] = useState<AgentDrift | null>(null);
  const [remediating, setRemediating] = useState('');
  const [msg, setMsg] = useState('');

  const load = useCallback(async () => {
    try {
      const [s, snaps] = await Promise.all([
        fetch(`${API}/stats`, { headers: h() }).then(r => r.ok ? r.json() : null),
        fetch(`${API}/snapshots`, { headers: h() }).then(r => r.ok ? r.json() : null),
      ]);
      if (s) setStats(s);
      if (snaps && Array.isArray(snaps) && snaps.length > 0) setSnapshots(snaps);
    } catch { /* use mock */ }
  }, []);

  const loadDrift = useCallback(async (agentId: string) => {
    try {
      const r = await fetch(`${API}/drift/${agentId}`, { headers: h() });
      if (r.ok) setSelected(await r.json());
      else setSelected({ agent_id: agentId, hostname: agentId, baseline_captured_at: '', drift_count: 0, drift_items: [] });
    } catch { /* ignore */ }
  }, []);

  const remediate = async (agentId: string) => {
    setRemediating(agentId);
    try {
      const r = await fetch(`${API}/remediate/${agentId}`, {
        method: 'POST',
        headers: jh(),
        body: JSON.stringify({ notes: 'Marked remediated from dashboard' }),
      });
      const d = await r.json();
      setMsg(`Remediated ${d.remediated_count} drift events for ${agentId}`);
      setSnapshots(prev => prev.map(s => s.agent_id === agentId ? { ...s, drift_count: 0 } : s));
      setSelected(null);
    } catch { setMsg('Remediation failed'); }
    setRemediating('');
    setTimeout(() => setMsg(''), 4000);
  };

  useEffect(() => { load(); }, [load]);

  const totalDrift = Object.values(stats.by_severity).reduce((a, b) => a + b, 0);

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="text-2xl font-bold text-white">Configuration Drift Detection</h2>
        <button onClick={load} className="text-sm text-slate-400 hover:text-white transition-colors">Refresh</button>
      </div>

      {msg && (
        <div className="bg-emerald-500/20 border border-emerald-500/30 text-emerald-300 text-sm px-4 py-2 rounded-lg">{msg}</div>
      )}

      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {[
          { label: 'Baselines', value: stats.total_baselines, cls: 'text-blue-400' },
          { label: 'Open Drifts', value: stats.open_drifts, cls: stats.open_drifts > 0 ? 'text-red-400' : 'text-emerald-400' },
          { label: 'Agents Affected', value: stats.agents_with_drift, cls: 'text-orange-400' },
          { label: 'Critical', value: stats.by_severity.critical, cls: 'text-red-500' },
        ].map(k => (
          <div key={k.label} className="bg-slate-800 border border-slate-700 rounded-xl p-4 text-center">
            <div className={`text-2xl font-bold ${k.cls}`}>{k.value}</div>
            <div className="text-xs text-slate-400 mt-1">{k.label}</div>
          </div>
        ))}
      </div>

      {totalDrift > 0 && (
        <div className="bg-slate-800 border border-slate-700 rounded-xl p-4 space-y-2">
          <div className="text-xs text-slate-400 font-semibold uppercase tracking-wide">Drift by Severity</div>
          <div className="flex gap-2 h-3">
            {(['critical', 'high', 'medium', 'low'] as const).map(s => {
              const w = Math.round((stats.by_severity[s] / totalDrift) * 100);
              const colors = { critical: 'bg-red-500', high: 'bg-orange-500', medium: 'bg-yellow-500', low: 'bg-blue-500' };
              return w > 0 ? <div key={s} className={`${colors[s]} rounded`} style={{ width: `${w}%` }} title={`${s}: ${stats.by_severity[s]}`} /> : null;
            })}
          </div>
          <div className="flex flex-wrap gap-3 text-xs text-slate-400">
            {(['critical', 'high', 'medium', 'low'] as const).map(s => (
              <span key={s}><span className="capitalize">{s}</span>: {stats.by_severity[s]}</span>
            ))}
          </div>
        </div>
      )}

      <div className="bg-slate-800 border border-slate-700 rounded-xl overflow-hidden">
        <div className="p-4 border-b border-slate-700">
          <h3 className="text-sm font-semibold text-white">Agent Baselines</h3>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-slate-700 text-slate-400 text-xs">
                <th className="px-4 py-2 text-left">Hostname</th>
                <th className="px-4 py-2 text-left">Platform</th>
                <th className="px-4 py-2 text-left">Baseline Captured</th>
                <th className="px-4 py-2 text-right">Open Drifts</th>
                <th className="px-4 py-2 text-center">Actions</th>
              </tr>
            </thead>
            <tbody>
              {snapshots.map(s => (
                <tr key={s.id} className="border-b border-slate-700/50 hover:bg-slate-700/30">
                  <td className="px-4 py-3 text-slate-200 font-mono text-xs">{s.hostname}</td>
                  <td className="px-4 py-3">
                    <span className="text-xs px-1.5 py-0.5 rounded bg-slate-700 text-slate-300 capitalize">{s.platform}</span>
                  </td>
                  <td className="px-4 py-3 text-slate-400 text-xs">{new Date(s.captured_at).toLocaleString()}</td>
                  <td className="px-4 py-3 text-right">
                    <span className={`text-sm font-bold ${s.drift_count > 0 ? 'text-red-400' : 'text-emerald-400'}`}>
                      {s.drift_count}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-center">
                    <div className="flex items-center justify-center gap-2">
                      <button onClick={() => loadDrift(s.agent_id)}
                        className="text-xs px-2 py-1 rounded bg-blue-600/20 text-blue-400 border border-blue-600/30 hover:bg-blue-600/30 transition-colors">
                        View Drift
                      </button>
                      {s.drift_count > 0 && (
                        <button onClick={() => remediate(s.agent_id)} disabled={remediating === s.agent_id}
                          className="text-xs px-2 py-1 rounded bg-emerald-600/20 text-emerald-400 border border-emerald-600/30 hover:bg-emerald-600/30 transition-colors disabled:opacity-50">
                          {remediating === s.agent_id ? '…' : 'Remediate'}
                        </button>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {selected && (
        <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50 p-4" onClick={() => setSelected(null)}>
          <div className="bg-slate-900 border border-slate-700 rounded-2xl w-full max-w-2xl p-6 space-y-4 max-h-[80vh] overflow-y-auto"
            onClick={e => e.stopPropagation()}>
            <div className="flex items-center justify-between">
              <h3 className="text-lg font-bold text-white">Drift Detail — {selected.hostname}</h3>
              <button onClick={() => setSelected(null)} className="text-slate-400 hover:text-white">&times;</button>
            </div>
            <div className="text-xs text-slate-400">
              Baseline: {selected.baseline_captured_at ? new Date(selected.baseline_captured_at).toLocaleString() : 'N/A'}
              {' · '}{selected.drift_count} drift{selected.drift_count !== 1 ? 's' : ''}
            </div>
            {selected.drift_items.length === 0 ? (
              <div className="text-slate-400 text-sm text-center py-8">No drift detected vs baseline.</div>
            ) : (
              <div className="space-y-2">
                {selected.drift_items.map((item, i) => (
                  <div key={i} className="bg-slate-800 border border-slate-700 rounded-lg p-3 space-y-1">
                    <div className="flex items-center gap-2">
                      <span className={`text-xs px-2 py-0.5 rounded-full border capitalize ${SEV_STYLE[item.severity]}`}>{item.severity}</span>
                      <span className="text-sm text-white font-mono">{item.key}</span>
                    </div>
                    <div className="flex gap-4 text-xs">
                      <span className="text-slate-400">Expected: <span className="text-emerald-400 font-mono">{item.expected}</span></span>
                      <span className="text-slate-400">Actual: <span className="text-red-400 font-mono">{item.actual}</span></span>
                    </div>
                  </div>
                ))}
              </div>
            )}
            <button onClick={() => remediate(selected.agent_id)} disabled={!!remediating}
              className="w-full py-2 rounded-lg bg-emerald-600 text-white text-sm font-medium hover:bg-emerald-700 transition-colors disabled:opacity-50">
              Mark All Remediated
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

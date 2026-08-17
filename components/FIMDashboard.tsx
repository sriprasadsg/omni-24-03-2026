import React, { useState, useEffect, useCallback } from 'react';

const API = '/api/fim';

type Platform = 'linux' | 'windows' | 'macos';
type ChangeType = 'added' | 'modified' | 'deleted' | 'permissions' | 'ownership';

interface FimPath {
  id: string;
  path: string;
  platform: Platform;
  recursive: boolean;
  check_interval_seconds: number;
  alert_on: ChangeType[];
  ignore_patterns: string[];
  enabled: boolean;
  created_at: string;
}

interface FimAlert {
  id: string;
  agent_id: string;
  hostname?: string;
  path: string;
  change_type: ChangeType;
  severity: 'critical' | 'high' | 'medium' | 'low';
  old_hash?: string;
  new_hash?: string;
  old_size?: number;
  new_size?: number;
  detected_at: string;
}

interface Stats {
  total_monitored_paths: number;
  total_alerts: number;
  by_change_type: Record<string, number>;
  by_severity: Record<string, number>;
  agents_monitored: number;
}

const CHANGE_TYPES: ChangeType[] = ['added', 'modified', 'deleted', 'permissions', 'ownership'];

const CHANGE_STYLE: Record<string, string> = {
  added: 'bg-emerald-500/20 text-emerald-400 border-emerald-500/30',
  modified: 'bg-yellow-500/20 text-yellow-400 border-yellow-500/30',
  deleted: 'bg-red-500/20 text-red-400 border-red-500/30',
  permissions: 'bg-orange-500/20 text-orange-400 border-orange-500/30',
  ownership: 'bg-purple-500/20 text-purple-400 border-purple-500/30',
};

const SEV_STYLE: Record<string, string> = {
  critical: 'text-red-400',
  high: 'text-orange-400',
  medium: 'text-yellow-400',
  low: 'text-blue-400',
};

const MOCK_STATS: Stats = {
  total_monitored_paths: 24,
  total_alerts: 47,
  by_change_type: { modified: 28, added: 12, deleted: 5, permissions: 2 },
  by_severity: { critical: 8, high: 19, medium: 16, low: 4 },
  agents_monitored: 6,
};

const MOCK_PATHS: FimPath[] = [
  { id: 'p1', path: '/etc/', platform: 'linux', recursive: true, check_interval_seconds: 300, alert_on: ['added', 'modified', 'deleted'], ignore_patterns: [], enabled: true, created_at: '2026-05-01T00:00:00Z' },
  { id: 'p2', path: '/var/www/', platform: 'linux', recursive: true, check_interval_seconds: 300, alert_on: ['added', 'modified', 'deleted'], ignore_patterns: ['*.log', '*.tmp'], enabled: true, created_at: '2026-05-01T00:00:00Z' },
  { id: 'p3', path: 'C:\\Windows\\System32\\', platform: 'windows', recursive: false, check_interval_seconds: 600, alert_on: ['modified', 'deleted'], ignore_patterns: [], enabled: true, created_at: '2026-05-02T00:00:00Z' },
  { id: 'p4', path: '/bin/', platform: 'linux', recursive: false, check_interval_seconds: 300, alert_on: ['added', 'modified', 'deleted'], ignore_patterns: [], enabled: true, created_at: '2026-05-03T00:00:00Z' },
];

const MOCK_ALERTS: FimAlert[] = [
  { id: 'a1', agent_id: 'ag1', hostname: 'web-server-01', path: '/etc/passwd', change_type: 'modified', severity: 'critical', detected_at: '2026-06-11T14:23:00Z' },
  { id: 'a2', agent_id: 'ag2', hostname: 'db-server-01', path: '/var/www/html/shell.php', change_type: 'added', severity: 'critical', detected_at: '2026-06-11T12:10:00Z' },
  { id: 'a3', agent_id: 'ag1', hostname: 'web-server-01', path: '/etc/crontab', change_type: 'modified', severity: 'high', detected_at: '2026-06-11T09:45:00Z' },
  { id: 'a4', agent_id: 'ag3', hostname: 'workstation-01', path: 'C:\\Windows\\System32\\cmd.exe', change_type: 'modified', severity: 'high', detected_at: '2026-06-10T18:30:00Z' },
];

const token = () => sessionStorage.getItem('token') ?? '';
const h = () => ({ Authorization: `Bearer ${token()}` });
const jh = () => ({ ...h(), 'Content-Type': 'application/json' });

export default function FIMDashboard() {
  const [tab, setTab] = useState<'overview' | 'paths' | 'alerts'>('overview');
  const [stats, setStats] = useState<Stats>(MOCK_STATS);
  const [paths, setPaths] = useState<FimPath[]>(MOCK_PATHS);
  const [alerts, setAlerts] = useState<FimAlert[]>(MOCK_ALERTS);
  const [showAdd, setShowAdd] = useState(false);
  const [form, setForm] = useState({ path: '', platform: 'linux' as Platform, recursive: true, interval: 300, alert_on: ['added', 'modified', 'deleted'] as ChangeType[], ignore: '' });
  const [saving, setSaving] = useState(false);
  const [filterPlatform, setFilterPlatform] = useState('');
  const [filterSev, setFilterSev] = useState('');
  const [seedMsg, setSeedMsg] = useState('');

  const load = useCallback(async () => {
    try {
      const [s, p, a] = await Promise.all([
        fetch(`${API}/stats`, { headers: h() }).then(r => r.ok ? r.json() : null),
        fetch(`${API}/paths`, { headers: h() }).then(r => r.ok ? r.json() : null),
        fetch(`${API}/alerts?limit=100`, { headers: h() }).then(r => r.ok ? r.json() : null),
      ]);
      if (s) setStats(s);
      if (p && p.length > 0) setPaths(p);
      if (a && a.length > 0) setAlerts(a);
    } catch { /* use mock */ }
  }, []);

  useEffect(() => { load(); }, [load]);

  const addPath = async () => {
    setSaving(true);
    try {
      const r = await fetch(`${API}/paths`, {
        method: 'POST',
        headers: jh(),
        body: JSON.stringify({
          path: form.path,
          platform: form.platform,
          recursive: form.recursive,
          check_interval_seconds: form.interval,
          alert_on: form.alert_on,
          ignore_patterns: form.ignore.split(',').map(s => s.trim()).filter(Boolean),
        }),
      });
      if (r.ok) {
        const p = await r.json();
        setPaths(prev => [p, ...prev]);
        setShowAdd(false);
        setForm({ path: '', platform: 'linux', recursive: true, interval: 300, alert_on: ['added', 'modified', 'deleted'], ignore: '' });
      }
    } catch { /* ignore */ }
    setSaving(false);
  };

  const deletePath = async (id: string) => {
    try {
      await fetch(`${API}/paths/${id}`, { method: 'DELETE', headers: h() });
      setPaths(prev => prev.filter(p => p.id !== id));
    } catch { /* ignore */ }
  };

  const togglePath = async (p: FimPath) => {
    try {
      const r = await fetch(`${API}/paths/${p.id}`, {
        method: 'PUT',
        headers: jh(),
        body: JSON.stringify({ enabled: !p.enabled }),
      });
      if (r.ok) setPaths(prev => prev.map(x => x.id === p.id ? { ...x, enabled: !x.enabled } : x));
    } catch { /* ignore */ }
  };

  const seedDefaults = async (platform: Platform) => {
    try {
      const r = await fetch(`${API}/paths/seed-defaults?platform=${platform}`, { method: 'POST', headers: h() });
      const d = await r.json();
      setSeedMsg(`Added ${d.added} default paths for ${platform}`);
      load();
    } catch { setSeedMsg('Failed to seed defaults'); }
    setTimeout(() => setSeedMsg(''), 4000);
  };

  const visiblePaths = paths.filter(p => !filterPlatform || p.platform === filterPlatform);
  const visibleAlerts = alerts.filter(a => !filterSev || a.severity === filterSev);

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="text-2xl font-bold text-white">File Integrity Monitoring</h2>
        <span className="text-sm text-slate-400">{stats.agents_monitored} agents monitored</span>
      </div>

      {seedMsg && <div className="bg-emerald-500/20 border border-emerald-500/30 text-emerald-300 text-sm px-4 py-2 rounded-lg">{seedMsg}</div>}

      <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
        {[
          { label: 'Monitored Paths', value: stats.total_monitored_paths, cls: 'text-blue-400' },
          { label: 'Total Alerts', value: stats.total_alerts, cls: 'text-red-400' },
          { label: 'Critical', value: stats.by_severity['critical'] ?? 0, cls: 'text-red-500' },
          { label: 'High', value: stats.by_severity['high'] ?? 0, cls: 'text-orange-400' },
          { label: 'Agents', value: stats.agents_monitored, cls: 'text-slate-300' },
        ].map(k => (
          <div key={k.label} className="bg-slate-800 border border-slate-700 rounded-xl p-4 text-center">
            <div className={`text-2xl font-bold ${k.cls}`}>{k.value}</div>
            <div className="text-xs text-slate-400 mt-1">{k.label}</div>
          </div>
        ))}
      </div>

      <div className="flex rounded-lg overflow-hidden border border-slate-700 w-fit">
        {(['overview', 'paths', 'alerts'] as const).map(t => (
          <button key={t} onClick={() => setTab(t)}
            className={`px-4 py-2 text-sm font-medium capitalize transition-colors ${tab === t ? 'bg-blue-600 text-white' : 'bg-slate-800 text-slate-300 hover:bg-slate-700'}`}>
            {t}
          </button>
        ))}
      </div>

      {tab === 'overview' && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <div className="bg-slate-800 border border-slate-700 rounded-xl p-4 space-y-3">
            <h3 className="text-sm font-semibold text-white">Changes by Type</h3>
            {Object.entries(stats.by_change_type).map(([type, count]) => (
              <div key={type} className="flex items-center gap-3">
                <span className={`text-xs px-2 py-0.5 rounded-full border capitalize shrink-0 ${CHANGE_STYLE[type] ?? 'bg-slate-700 text-slate-300 border-slate-600'}`}>{type}</span>
                <div className="flex-1 bg-slate-700 rounded-full h-2">
                  <div className="bg-blue-500 h-2 rounded-full" style={{ width: `${Math.min(100, (count / stats.total_alerts) * 100)}%` }} />
                </div>
                <span className="text-xs text-slate-400 w-6 text-right">{count}</span>
              </div>
            ))}
          </div>
          <div className="bg-slate-800 border border-slate-700 rounded-xl p-4 space-y-3">
            <h3 className="text-sm font-semibold text-white">Recent Alerts</h3>
            {MOCK_ALERTS.slice(0, 4).map(a => (
              <div key={a.id} className="flex items-start gap-2">
                <span className={`text-xs font-bold ${SEV_STYLE[a.severity]} shrink-0`}>{a.severity.toUpperCase()}</span>
                <div className="min-w-0">
                  <div className="text-xs text-white font-mono truncate">{a.path}</div>
                  <div className="text-xs text-slate-400">{a.hostname} · {new Date(a.detected_at).toLocaleString()}</div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {tab === 'paths' && (
        <div className="space-y-4">
          <div className="flex items-center gap-3">
            <select value={filterPlatform} onChange={e => setFilterPlatform(e.target.value)}
              className="bg-slate-800 border border-slate-700 text-slate-300 text-sm rounded-lg px-3 py-1.5">
              <option value="">All Platforms</option>
              <option value="linux">Linux</option>
              <option value="windows">Windows</option>
              <option value="macos">macOS</option>
            </select>
            <div className="flex gap-2 ml-auto">
              {(['linux', 'windows', 'macos'] as Platform[]).map(plat => (
                <button key={plat} onClick={() => seedDefaults(plat)}
                  className="text-xs px-3 py-1.5 rounded-lg bg-slate-700 text-slate-300 hover:bg-slate-600 transition-colors capitalize">
                  Seed {plat} defaults
                </button>
              ))}
              <button onClick={() => setShowAdd(true)}
                className="px-4 py-1.5 rounded-lg bg-blue-600 text-white text-sm font-medium hover:bg-blue-700 transition-colors">
                + Add Path
              </button>
            </div>
          </div>

          <div className="bg-slate-800 border border-slate-700 rounded-xl overflow-hidden">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-slate-700 text-slate-400 text-xs">
                  <th className="px-4 py-2 text-left">Path</th>
                  <th className="px-4 py-2 text-left">Platform</th>
                  <th className="px-4 py-2 text-left">Recursive</th>
                  <th className="px-4 py-2 text-left">Alert On</th>
                  <th className="px-4 py-2 text-right">Interval</th>
                  <th className="px-4 py-2 text-center">Status</th>
                  <th className="px-4 py-2 text-center">Actions</th>
                </tr>
              </thead>
              <tbody>
                {visiblePaths.map(p => (
                  <tr key={p.id} className="border-b border-slate-700/50 hover:bg-slate-700/30">
                    <td className="px-4 py-3 font-mono text-xs text-slate-200 max-w-xs truncate">{p.path}</td>
                    <td className="px-4 py-3">
                      <span className="text-xs px-1.5 py-0.5 rounded bg-slate-700 text-slate-300 capitalize">{p.platform}</span>
                    </td>
                    <td className="px-4 py-3 text-xs text-slate-400">{p.recursive ? 'Yes' : 'No'}</td>
                    <td className="px-4 py-3">
                      <div className="flex flex-wrap gap-1">
                        {p.alert_on.map(t => (
                          <span key={t} className={`text-xs px-1.5 py-0.5 rounded-full border capitalize ${CHANGE_STYLE[t]}`}>{t}</span>
                        ))}
                      </div>
                    </td>
                    <td className="px-4 py-3 text-right text-xs text-slate-400">{p.check_interval_seconds}s</td>
                    <td className="px-4 py-3 text-center">
                      <button onClick={() => togglePath(p)}
                        className={`text-xs px-2 py-0.5 rounded-full border ${p.enabled ? 'bg-emerald-500/20 text-emerald-400 border-emerald-500/30' : 'bg-slate-700/50 text-slate-400 border-slate-600/30'}`}>
                        {p.enabled ? 'Active' : 'Paused'}
                      </button>
                    </td>
                    <td className="px-4 py-3 text-center">
                      <button onClick={() => deletePath(p.id)} className="text-slate-500 hover:text-red-400 text-xs transition-colors">Remove</button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {tab === 'alerts' && (
        <div className="space-y-4">
          <div className="flex gap-3">
            <select value={filterSev} onChange={e => setFilterSev(e.target.value)}
              className="bg-slate-800 border border-slate-700 text-slate-300 text-sm rounded-lg px-3 py-1.5">
              <option value="">All Severities</option>
              <option value="critical">Critical</option>
              <option value="high">High</option>
              <option value="medium">Medium</option>
              <option value="low">Low</option>
            </select>
          </div>
          <div className="bg-slate-800 border border-slate-700 rounded-xl overflow-hidden">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-slate-700 text-slate-400 text-xs">
                  <th className="px-4 py-2 text-left">Severity</th>
                  <th className="px-4 py-2 text-left">Path</th>
                  <th className="px-4 py-2 text-left">Change</th>
                  <th className="px-4 py-2 text-left">Agent</th>
                  <th className="px-4 py-2 text-left">Detected</th>
                </tr>
              </thead>
              <tbody>
                {visibleAlerts.map(a => (
                  <tr key={a.id} className="border-b border-slate-700/50 hover:bg-slate-700/30">
                    <td className={`px-4 py-3 text-xs font-bold uppercase ${SEV_STYLE[a.severity]}`}>{a.severity}</td>
                    <td className="px-4 py-3 font-mono text-xs text-slate-200 max-w-xs truncate">{a.path}</td>
                    <td className="px-4 py-3">
                      <span className={`text-xs px-2 py-0.5 rounded-full border capitalize ${CHANGE_STYLE[a.change_type]}`}>{a.change_type}</span>
                    </td>
                    <td className="px-4 py-3 text-xs text-slate-400">{a.hostname ?? a.agent_id}</td>
                    <td className="px-4 py-3 text-xs text-slate-400">{new Date(a.detected_at).toLocaleString()}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {showAdd && (
        <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50 p-4">
          <div className="bg-slate-900 border border-slate-700 rounded-2xl w-full max-w-lg p-6 space-y-4">
            <div className="flex items-center justify-between">
              <h3 className="text-lg font-bold text-white">Add Monitored Path</h3>
              <button onClick={() => setShowAdd(false)} className="text-slate-400 hover:text-white">&times;</button>
            </div>
            <div className="space-y-3">
              <div>
                <label className="text-xs text-slate-400">Path *</label>
                <input value={form.path} onChange={e => setForm(p => ({ ...p, path: e.target.value }))}
                  placeholder="/etc/ or C:\Windows\System32\"
                  className="w-full mt-1 bg-slate-800 border border-slate-600 rounded-lg px-3 py-2 text-white text-sm font-mono focus:outline-none focus:border-blue-500" />
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="text-xs text-slate-400">Platform</label>
                  <select value={form.platform} onChange={e => setForm(p => ({ ...p, platform: e.target.value as Platform }))}
                    className="w-full mt-1 bg-slate-800 border border-slate-600 rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:border-blue-500">
                    <option value="linux">Linux</option>
                    <option value="windows">Windows</option>
                    <option value="macos">macOS</option>
                  </select>
                </div>
                <div>
                  <label className="text-xs text-slate-400">Check Interval (seconds)</label>
                  <input type="number" value={form.interval} onChange={e => setForm(p => ({ ...p, interval: parseInt(e.target.value) || 300 }))}
                    min={60} className="w-full mt-1 bg-slate-800 border border-slate-600 rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:border-blue-500" />
                </div>
              </div>
              <div>
                <label className="text-xs text-slate-400">Alert On</label>
                <div className="flex flex-wrap gap-2 mt-1">
                  {CHANGE_TYPES.map(ct => (
                    <label key={ct} className="flex items-center gap-1.5 cursor-pointer">
                      <input type="checkbox" checked={form.alert_on.includes(ct)}
                        onChange={e => setForm(p => ({
                          ...p,
                          alert_on: e.target.checked ? [...p.alert_on, ct] : p.alert_on.filter(x => x !== ct)
                        }))} className="w-3 h-3" />
                      <span className="text-xs text-slate-300 capitalize">{ct}</span>
                    </label>
                  ))}
                </div>
              </div>
              <div>
                <label className="text-xs text-slate-400">Ignore Patterns (comma-separated)</label>
                <input value={form.ignore} onChange={e => setForm(p => ({ ...p, ignore: e.target.value }))}
                  placeholder="*.log, *.tmp, *.swp"
                  className="w-full mt-1 bg-slate-800 border border-slate-600 rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:border-blue-500" />
              </div>
              <label className="flex items-center gap-2 cursor-pointer">
                <input type="checkbox" checked={form.recursive} onChange={e => setForm(p => ({ ...p, recursive: e.target.checked }))} />
                <span className="text-sm text-slate-300">Recursive monitoring</span>
              </label>
            </div>
            <div className="flex gap-3 pt-2">
              <button onClick={() => setShowAdd(false)} className="flex-1 py-2 rounded-lg border border-slate-600 text-slate-300 text-sm hover:bg-slate-800 transition-colors">Cancel</button>
              <button onClick={addPath} disabled={saving || !form.path.trim()}
                className="flex-1 py-2 rounded-lg bg-blue-600 text-white text-sm font-medium hover:bg-blue-700 transition-colors disabled:opacity-50">
                {saving ? 'Adding…' : 'Add Path'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

import React, { useState, useEffect, useCallback } from 'react';
import { authFetch } from '../services/apiService';

interface TimelineEvent {
  id: string;
  timestamp: string;
  event_type: string;
  asset: string;
  user?: string;
  technique_id?: string;
  technique_name?: string;
  tactic?: string;
  severity: 'critical' | 'high' | 'medium' | 'low';
  description: string;
  details?: Record<string, unknown>;
}

const SEV_COLOR: Record<string, string> = {
  critical: 'border-red-500 bg-red-500/10 text-red-400',
  high: 'border-orange-500 bg-orange-500/10 text-orange-400',
  medium: 'border-yellow-500 bg-yellow-500/10 text-yellow-400',
  low: 'border-blue-500 bg-blue-500/10 text-blue-400',
};

const SEV_DOT: Record<string, string> = {
  critical: 'bg-red-500',
  high: 'bg-orange-500',
  medium: 'bg-yellow-500',
  low: 'bg-blue-500',
};

const TACTICS = ['All', 'Initial Access', 'Privilege Escalation', 'Lateral Movement', 'Discovery', 'Exfiltration', 'Command and Control', 'Persistence'];
const SEVERITIES = ['all', 'critical', 'high', 'medium', 'low'];
const RANGES = [{ label: '1h', hours: 1 }, { label: '6h', hours: 6 }, { label: '24h', hours: 24 }, { label: '7d', hours: 168 }];

export default function AttackTimelineDashboard() {
  const [events, setEvents] = useState<TimelineEvent[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [range, setRange] = useState(24);
  const [sevFilter, setSevFilter] = useState('all');
  const [tacticFilter, setTacticFilter] = useState('All');
  const [expanded, setExpanded] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const r = await authFetch(`/api/advanced-hunting/timeline?hours=${range}`);
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const data = await r.json();
      setEvents(Array.isArray(data) ? data : []);
    } catch (e: any) {
      // Never fall back to sample events: a security timeline must only show real ones
      setEvents([]);
      setError(e?.message || 'Request failed');
    }
    setLoading(false);
  }, [range]);

  useEffect(() => { load(); }, [load]);

  const visible = events.filter(e => {
    if (sevFilter !== 'all' && e.severity !== sevFilter) return false;
    if (tacticFilter !== 'All' && e.tactic !== tacticFilter) return false;
    return true;
  }).sort((a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime());

  const fmt = (iso: string) => new Date(iso).toLocaleString();

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="text-2xl font-bold text-white">Attack Timeline</h2>
        <div className="flex items-center gap-2 text-sm text-slate-400">
          <div className={`w-2 h-2 rounded-full ${loading ? 'bg-yellow-400 animate-pulse' : 'bg-emerald-400'}`} />
          {loading ? 'Loading...' : `${visible.length} events`}
        </div>
      </div>

      {/* Filters */}
      <div className="flex flex-wrap gap-3">
        <div className="flex rounded-lg overflow-hidden border border-slate-700">
          {RANGES.map(r => (
            <button key={r.hours} onClick={() => setRange(r.hours)}
              className={`px-3 py-1.5 text-sm font-medium transition-colors ${range === r.hours ? 'bg-blue-600 text-white' : 'bg-slate-800 text-slate-300 hover:bg-slate-700'}`}>
              {r.label}
            </button>
          ))}
        </div>
        <select value={sevFilter} onChange={e => setSevFilter(e.target.value)}
          className="bg-slate-800 border border-slate-700 text-slate-300 text-sm rounded-lg px-3 py-1.5 capitalize">
          {SEVERITIES.map(s => <option key={s} value={s} className="capitalize">{s}</option>)}
        </select>
        <select value={tacticFilter} onChange={e => setTacticFilter(e.target.value)}
          className="bg-slate-800 border border-slate-700 text-slate-300 text-sm rounded-lg px-3 py-1.5">
          {TACTICS.map(t => <option key={t} value={t}>{t}</option>)}
        </select>
      </div>

      {/* KPI bar */}
      <div className="grid grid-cols-4 gap-3">
        {(['critical', 'high', 'medium', 'low'] as const).map(s => (
          <div key={s} className={`rounded-xl border p-3 text-center ${SEV_COLOR[s]}`}>
            <div className="text-2xl font-bold">{events.filter(e => e.severity === s).length}</div>
            <div className="text-xs capitalize mt-0.5 opacity-80">{s}</div>
          </div>
        ))}
      </div>

      {/* Timeline */}
      <div className="relative">
        <div className="absolute left-4 top-0 bottom-0 w-0.5 bg-slate-700" />
        <div className="space-y-3 pl-10">
          {error && <p className="text-red-400 text-sm py-8 text-center">Could not load the attack timeline ({error}).</p>}
          {!error && !loading && events.length === 0 && <p className="text-slate-400 text-sm py-8 text-center">No security events in this time range.</p>}
          {!error && events.length > 0 && visible.length === 0 && <p className="text-slate-400 text-sm py-8 text-center">No events match the current filters.</p>}
          {visible.map(ev => (
            <div key={ev.id} className="relative">
              <div className={`absolute -left-6 top-4 w-3 h-3 rounded-full border-2 border-slate-900 ${SEV_DOT[ev.severity]}`} />
              <div className="bg-slate-800 border border-slate-700 rounded-xl overflow-hidden">
                <button className="w-full text-left p-4" onClick={() => setExpanded(expanded === ev.id ? null : ev.id)}>
                  <div className="flex items-start justify-between gap-3">
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className="font-semibold text-white text-sm">{ev.event_type}</span>
                        {ev.technique_id && (
                          <span className="text-xs bg-slate-700 text-slate-300 px-1.5 py-0.5 rounded font-mono">{ev.technique_id}</span>
                        )}
                        <span className={`text-xs px-2 py-0.5 rounded-full capitalize ${SEV_COLOR[ev.severity]}`}>{ev.severity}</span>
                      </div>
                      <div className="text-sm text-slate-300 mt-1 truncate">{ev.description}</div>
                    </div>
                    <div className="text-right text-xs text-slate-500 flex-shrink-0">
                      <div>{fmt(ev.timestamp)}</div>
                      <div className="mt-0.5">{ev.asset}</div>
                    </div>
                  </div>
                </button>
                {expanded === ev.id && (
                  <div className="border-t border-slate-700 px-4 pb-4 pt-3 space-y-2 text-sm">
                    <div className="grid grid-cols-2 gap-3">
                      {ev.user && <div><span className="text-slate-400">User: </span><span className="text-slate-200">{ev.user}</span></div>}
                      {ev.tactic && <div><span className="text-slate-400">Tactic: </span><span className="text-slate-200">{ev.tactic}</span></div>}
                      {ev.technique_name && <div><span className="text-slate-400">Technique: </span><span className="text-slate-200">{ev.technique_name}</span></div>}
                      <div><span className="text-slate-400">Asset: </span><span className="text-slate-200">{ev.asset}</span></div>
                    </div>
                    {ev.details && (
                      <pre className="mt-2 text-xs text-slate-400 bg-slate-900 rounded p-2 overflow-x-auto">{JSON.stringify(ev.details, null, 2)}</pre>
                    )}
                  </div>
                )}
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

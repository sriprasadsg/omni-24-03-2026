import React, { useState, useEffect } from 'react';
import { authFetch } from '../services/apiService';

interface QueryLog {
  id: string;
  database: string;
  user: string;
  user_privilege: string;
  operation: string;
  table: string;
  rows_affected: number;
  rows_returned: number;
  duration_ms: number;
  source_ip: string;
  timestamp: string;
  risk_score: number;
  triggered_rules: { id: string; name: string; severity: string }[];
}

interface DAMAlert {
  id: string;
  rule_name: string;
  severity: string;
  user: string;
  database: string;
  table: string;
  operation: string;
  detected_at: string;
  status: string;
}

interface Summary {
  queries_24h: number;
  risky_queries_24h: number;
  open_alerts: number;
  critical_alerts: number;
}

const OP_COLORS: Record<string, string> = {
  SELECT: 'bg-blue-900/40 text-blue-300',
  INSERT: 'bg-green-900/40 text-green-300',
  UPDATE: 'bg-yellow-900/40 text-yellow-300',
  DELETE: 'bg-red-900/40 text-red-300',
  ALTER: 'bg-purple-900/40 text-purple-300',
  DROP: 'bg-red-900/70 text-red-200',
  TRUNCATE: 'bg-red-900/70 text-red-200',
};

const SEV_COLORS: Record<string, string> = {
  critical: 'text-red-400 border-red-700',
  high: 'text-orange-400 border-orange-700',
  medium: 'text-yellow-400 border-yellow-700',
  low: 'text-gray-400 border-gray-600',
};

export default function DAMDashboard() {
  const [queries, setQueries] = useState<QueryLog[]>([]);
  const [alerts, setAlerts] = useState<DAMAlert[]>([]);
  const [summary, setSummary] = useState<Summary | null>(null);
  const [tab, setTab] = useState<'queries' | 'alerts'>('alerts');
  const [seeding, setSeeding] = useState(false);

  useEffect(() => { loadAll(); }, []);

  async function loadAll() {
    try {
      const [qRes, aRes, sRes] = await Promise.all([
        authFetch('/api/dam/queries?limit=50'),
        authFetch('/api/dam/alerts?limit=50'),
        authFetch('/api/dam/summary'),
      ]);
      const [q, a, s] = await Promise.all([qRes.json(), aRes.json(), sRes.json()]);
      setQueries(q.queries || []);
      setAlerts(a.alerts || []);
      setSummary(s);
    } catch (err) { console.error(err); }
  }

  async function seedData() {
    setSeeding(true);
    try {
      await authFetch('/api/dam/seed', { method: 'POST' });
      loadAll();
    } finally { setSeeding(false); }
  }

  const riskBar = (score: number) => (
    <div className="flex items-center gap-2">
      <div className="w-16 bg-gray-700 rounded-full h-1.5">
        <div className={`h-1.5 rounded-full ${score >= 0.8 ? 'bg-red-500' : score >= 0.5 ? 'bg-yellow-500' : 'bg-green-500'}`}
          style={{ width: `${score * 100}%` }} />
      </div>
      <span className={`text-xs ${score >= 0.8 ? 'text-red-400' : score >= 0.5 ? 'text-yellow-400' : 'text-gray-400'}`}>
        {Math.round(score * 100)}
      </span>
    </div>
  );

  return (
    <div className="p-6 bg-gray-900 min-h-screen text-white">
      <div className="flex justify-between items-center mb-6">
        <div>
          <h1 className="text-2xl font-bold">Database Activity Monitor</h1>
          <p className="text-gray-400 text-sm mt-1">Query logging, behavioral analysis, and anomaly detection across all databases</p>
        </div>
        <button onClick={seedData} disabled={seeding}
          className="bg-gray-700 hover:bg-gray-600 disabled:opacity-50 px-4 py-2 rounded-lg text-sm">
          {seeding ? 'Seeding…' : 'Load Demo Data'}
        </button>
      </div>

      {summary && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-6">
          {[
            { label: 'Queries (24h)', value: summary.queries_24h, color: 'text-blue-400' },
            { label: 'Risky Queries', value: summary.risky_queries_24h, color: summary.risky_queries_24h > 0 ? 'text-orange-400' : 'text-green-400' },
            { label: 'Open Alerts', value: summary.open_alerts, color: summary.open_alerts > 0 ? 'text-yellow-400' : 'text-green-400' },
            { label: 'Critical Alerts', value: summary.critical_alerts, color: summary.critical_alerts > 0 ? 'text-red-400' : 'text-green-400' },
          ].map(c => (
            <div key={c.label} className="bg-gray-800 rounded-xl p-4 border border-gray-700 text-center">
              <div className={`text-3xl font-bold ${c.color}`}>{c.value}</div>
              <div className="text-xs text-gray-400 mt-1">{c.label}</div>
            </div>
          ))}
        </div>
      )}

      <div className="flex gap-2 mb-4">
        {(['alerts', 'queries'] as const).map(t => (
          <button key={t} onClick={() => setTab(t)}
            className={`px-3 py-1.5 rounded-lg text-sm font-medium capitalize ${tab === t ? 'bg-blue-600 text-white' : 'bg-gray-800 text-gray-400 hover:text-white'}`}>
            {t} ({t === 'queries' ? queries.length : alerts.length})
          </button>
        ))}
      </div>

      {tab === 'alerts' && (
        alerts.length === 0 ? (
          <div className="text-center py-12 text-gray-500 bg-gray-800 rounded-xl border border-gray-700">
            <div className="text-4xl mb-3">✅</div>
            <p>No alerts — load demo data to see DAM in action</p>
          </div>
        ) : (
          <div className="space-y-2">
            {alerts.map(alert => (
              <div key={alert.id} className={`bg-gray-800 rounded-xl p-4 border ${alert.severity === 'critical' ? 'border-red-800' : 'border-gray-700'}`}>
                <div className="flex items-start justify-between">
                  <div className="flex-1">
                    <div className="flex items-center gap-2 mb-1">
                      <span className={`text-xs px-2 py-0.5 rounded border font-medium capitalize ${SEV_COLORS[alert.severity] || ''}`}>
                        {alert.severity}
                      </span>
                      <span className="text-sm font-medium">{alert.rule_name}</span>
                    </div>
                    <div className="flex gap-4 text-xs text-gray-400">
                      <span>User: <span className="text-white">{alert.user}</span></span>
                      <span>DB: <span className="text-blue-300">{alert.database}</span></span>
                      <span>Table: <span className="text-purple-300">{alert.table}</span></span>
                      <span className={`px-1.5 rounded text-xs font-bold ${OP_COLORS[alert.operation] || 'bg-gray-700 text-gray-300'}`}>
                        {alert.operation}
                      </span>
                    </div>
                    <p className="text-xs text-gray-500 mt-1">{new Date(alert.detected_at).toLocaleString()}</p>
                  </div>
                  <span className={`text-xs capitalize ml-4 ${alert.status === 'open' ? 'text-yellow-400' : 'text-green-400'}`}>
                    {alert.status}
                  </span>
                </div>
              </div>
            ))}
          </div>
        )
      )}

      {tab === 'queries' && (
        queries.length === 0 ? (
          <div className="text-center py-12 text-gray-500 bg-gray-800 rounded-xl border border-gray-700">
            <p>No query logs yet</p>
          </div>
        ) : (
          <div className="space-y-1">
            <div className="grid grid-cols-12 text-xs text-gray-500 uppercase tracking-wide px-4 pb-2">
              <span className="col-span-1">Op</span>
              <span className="col-span-2">User</span>
              <span className="col-span-2">Database</span>
              <span className="col-span-2">Table</span>
              <span className="col-span-1">Rows</span>
              <span className="col-span-1">Time</span>
              <span className="col-span-2">Risk</span>
              <span className="col-span-1">When</span>
            </div>
            {queries.map(q => (
              <div key={q.id} className={`bg-gray-800 rounded-lg px-4 py-2 border grid grid-cols-12 items-center gap-1 text-sm ${q.risk_score >= 0.5 ? 'border-yellow-900/50' : 'border-gray-700'}`}>
                <span className={`col-span-1 text-xs px-1.5 py-0.5 rounded font-bold ${OP_COLORS[q.operation] || 'bg-gray-700 text-gray-300'}`}>
                  {q.operation.slice(0, 3)}
                </span>
                <span className="col-span-2 text-gray-300 truncate">{q.user}</span>
                <span className="col-span-2 text-blue-300 truncate">{q.database}</span>
                <span className="col-span-2 text-purple-300 truncate">{q.table}</span>
                <span className="col-span-1 text-gray-400">{(q.rows_affected || q.rows_returned).toLocaleString()}</span>
                <span className="col-span-1 text-gray-500">{q.duration_ms}ms</span>
                <span className="col-span-2">{riskBar(q.risk_score)}</span>
                <span className="col-span-1 text-gray-600 text-xs">{new Date(q.timestamp).toLocaleTimeString()}</span>
              </div>
            ))}
          </div>
        )
      )}
    </div>
  );
}

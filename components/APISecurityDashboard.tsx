import React, { useState, useEffect } from 'react';
import { authFetch } from '../services/apiService';

interface APIEndpoint {
  id: string;
  method: string;
  path: string;
  name: string;
  tags: string[];
  request_count_24h: number;
  avg_latency_ms: number;
  error_rate: number;
  auth_required: boolean;
  risk_score: number;
}

interface APIAlert {
  id: string;
  type: string;
  severity: string;
  message: string;
  endpoint_id: string;
  detected_at: string;
  status: string;
}

interface Summary {
  total_endpoints: number;
  unauthenticated: number;
  high_risk: number;
  open_alerts: number;
}

const METHOD_COLORS: Record<string, string> = {
  GET: 'bg-blue-900/40 text-blue-300',
  POST: 'bg-green-900/40 text-green-300',
  PUT: 'bg-yellow-900/40 text-yellow-300',
  PATCH: 'bg-orange-900/40 text-orange-300',
  DELETE: 'bg-red-900/40 text-red-300',
};

const SEV_COLORS: Record<string, string> = {
  critical: 'bg-red-900/40 text-red-300 border-red-700',
  high: 'bg-orange-900/40 text-orange-300 border-orange-700',
  medium: 'bg-yellow-900/40 text-yellow-300 border-yellow-700',
  low: 'bg-gray-700 text-gray-300 border-gray-600',
};

export default function APISecurityDashboard() {
  const [endpoints, setEndpoints] = useState<APIEndpoint[]>([]);
  const [alerts, setAlerts] = useState<APIAlert[]>([]);
  const [summary, setSummary] = useState<Summary | null>(null);
  const [tab, setTab] = useState<'endpoints' | 'alerts'>('endpoints');
  const [discovering, setDiscovering] = useState(false);
  const [severityFilter, setSeverityFilter] = useState('');

  useEffect(() => { loadAll(); }, []);

  async function loadAll() {
    try {
      const [eRes, aRes, sRes] = await Promise.all([
        authFetch('/api/api-security/endpoints'),
        authFetch('/api/api-security/alerts'),
        authFetch('/api/api-security/summary'),
      ]);
      const [e, a, s] = await Promise.all([eRes.json(), aRes.json(), sRes.json()]);
      setEndpoints(e.endpoints || []);
      setAlerts(a.alerts || []);
      setSummary(s);
    } catch (err) { console.error(err); }
  }

  async function discover() {
    setDiscovering(true);
    try {
      await authFetch('/api/api-security/discover', { method: 'POST' });
      loadAll();
    } finally { setDiscovering(false); }
  }

  const riskColor = (score: number) =>
    score >= 0.7 ? 'text-red-400' : score >= 0.4 ? 'text-yellow-400' : 'text-green-400';

  const filteredAlerts = severityFilter ? alerts.filter(a => a.severity === severityFilter) : alerts;

  return (
    <div className="p-6 bg-gray-900 min-h-screen text-white">
      <div className="flex justify-between items-center mb-6">
        <div>
          <h1 className="text-2xl font-bold">API Security</h1>
          <p className="text-gray-400 text-sm mt-1">Inventory, risk scoring, and abuse detection for all API endpoints</p>
        </div>
        <button onClick={discover} disabled={discovering}
          className="bg-blue-600 hover:bg-blue-700 disabled:opacity-50 px-4 py-2 rounded-lg text-sm font-medium">
          {discovering ? 'Scanning…' : '🔍 Discover Endpoints'}
        </button>
      </div>

      {summary && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-6">
          {[
            { label: 'Total Endpoints', value: summary.total_endpoints, color: 'text-blue-400' },
            { label: 'Unauthenticated', value: summary.unauthenticated, color: summary.unauthenticated > 0 ? 'text-red-400' : 'text-green-400' },
            { label: 'High Risk', value: summary.high_risk, color: summary.high_risk > 0 ? 'text-orange-400' : 'text-green-400' },
            { label: 'Open Alerts', value: summary.open_alerts, color: summary.open_alerts > 0 ? 'text-yellow-400' : 'text-green-400' },
          ].map(c => (
            <div key={c.label} className="bg-gray-800 rounded-xl p-4 border border-gray-700 text-center">
              <div className={`text-3xl font-bold ${c.color}`}>{c.value}</div>
              <div className="text-xs text-gray-400 mt-1">{c.label}</div>
            </div>
          ))}
        </div>
      )}

      <div className="flex gap-2 mb-4">
        {(['endpoints', 'alerts'] as const).map(t => (
          <button key={t} onClick={() => setTab(t)}
            className={`px-3 py-1.5 rounded-lg text-sm font-medium capitalize ${tab === t ? 'bg-blue-600 text-white' : 'bg-gray-800 text-gray-400 hover:text-white'}`}>
            {t} ({t === 'endpoints' ? endpoints.length : alerts.length})
          </button>
        ))}
      </div>

      {tab === 'endpoints' && (
        endpoints.length === 0 ? (
          <div className="text-center py-16 text-gray-500 bg-gray-800 rounded-xl border border-gray-700">
            <div className="text-4xl mb-3">🔌</div>
            <p>No endpoints discovered yet — click "Discover Endpoints" to scan</p>
          </div>
        ) : (
          <div className="space-y-1">
            <div className="grid grid-cols-12 text-xs text-gray-500 uppercase tracking-wide px-4 pb-2">
              <span className="col-span-1">Method</span>
              <span className="col-span-5">Path</span>
              <span className="col-span-2">Requests/24h</span>
              <span className="col-span-1">Latency</span>
              <span className="col-span-1">Error %</span>
              <span className="col-span-1">Auth</span>
              <span className="col-span-1">Risk</span>
            </div>
            {endpoints.map(ep => (
              <div key={ep.id} className={`bg-gray-800 rounded-lg px-4 py-2.5 border grid grid-cols-12 items-center gap-2 ${ep.risk_score >= 0.7 ? 'border-red-900/50' : 'border-gray-700'}`}>
                <span className={`col-span-1 text-xs px-1.5 py-0.5 rounded font-bold ${METHOD_COLORS[ep.method] || 'bg-gray-700 text-gray-300'}`}>
                  {ep.method}
                </span>
                <span className="col-span-5 font-mono text-sm text-gray-200 truncate">{ep.path}</span>
                <span className="col-span-2 text-sm text-gray-300">{ep.request_count_24h.toLocaleString()}</span>
                <span className="col-span-1 text-sm text-gray-400">{ep.avg_latency_ms}ms</span>
                <span className={`col-span-1 text-sm ${ep.error_rate > 0.05 ? 'text-red-400' : 'text-gray-400'}`}>
                  {(ep.error_rate * 100).toFixed(1)}%
                </span>
                <span className={`col-span-1 text-xs ${ep.auth_required ? 'text-green-400' : 'text-red-400'}`}>
                  {ep.auth_required ? '✓' : '✗ Open'}
                </span>
                <span className={`col-span-1 text-sm font-bold ${riskColor(ep.risk_score)}`}>
                  {Math.round(ep.risk_score * 100)}
                </span>
              </div>
            ))}
          </div>
        )
      )}

      {tab === 'alerts' && (
        <div className="space-y-3">
          <div className="flex gap-2 mb-2">
            {['', 'critical', 'high', 'medium', 'low'].map(s => (
              <button key={s} onClick={() => setSeverityFilter(s)}
                className={`px-3 py-1 rounded text-xs font-medium capitalize ${severityFilter === s ? 'bg-blue-600 text-white' : 'bg-gray-800 text-gray-400 hover:text-white'}`}>
                {s || 'All'}
              </button>
            ))}
          </div>
          {filteredAlerts.length === 0 ? (
            <div className="text-center py-12 text-gray-500 bg-gray-800 rounded-xl border border-gray-700">
              <div className="text-4xl mb-3">✅</div><p>No alerts</p>
            </div>
          ) : (
            filteredAlerts.map(alert => (
              <div key={alert.id} className={`bg-gray-800 rounded-xl p-4 border ${alert.severity === 'critical' ? 'border-red-800' : 'border-gray-700'}`}>
                <div className="flex items-start justify-between">
                  <div>
                    <div className="flex items-center gap-2 mb-1">
                      <span className={`text-xs px-2 py-0.5 rounded border font-medium capitalize ${SEV_COLORS[alert.severity] || ''}`}>
                        {alert.severity}
                      </span>
                      <span className="text-xs text-gray-500 capitalize">{alert.type.replace(/_/g, ' ')}</span>
                    </div>
                    <p className="text-sm text-white">{alert.message}</p>
                    <p className="text-xs text-gray-500 mt-1">{new Date(alert.detected_at).toLocaleString()}</p>
                  </div>
                  <span className={`text-xs px-2 py-0.5 rounded capitalize ${alert.status === 'open' ? 'text-yellow-400' : 'text-green-400'}`}>
                    {alert.status}
                  </span>
                </div>
              </div>
            ))
          )}
        </div>
      )}
    </div>
  );
}

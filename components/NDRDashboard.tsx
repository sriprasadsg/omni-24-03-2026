import React, { useState, useEffect } from 'react';
import { authFetch } from '../services/apiService';

interface Anomaly {
  id: string;
  type: string;
  severity: string;
  description: string;
  src_ip: string;
  dst_ip: string;
  protocol: string;
  confidence: number;
  bytes: number;
  detected_at: string;
  status: string;
  mitre_technique: string;
}

interface TrafficSummary {
  flows_24h: number;
  open_anomalies: number;
  critical_anomalies: number;
  protocols_monitored: number;
  detection_running: boolean;
}

const SEV_COLORS: Record<string, string> = {
  critical: 'bg-red-900/40 text-red-300 border-red-700',
  high: 'bg-orange-900/40 text-orange-300 border-orange-700',
  medium: 'bg-yellow-900/40 text-yellow-300 border-yellow-700',
  low: 'bg-gray-700 text-gray-300 border-gray-600',
};

const TYPE_ICONS: Record<string, string> = {
  lateral_movement: '↔️',
  data_exfiltration: '📤',
  port_scan: '🔍',
  dns_tunneling: '🕳️',
  c2_beacon: '📡',
  brute_force: '🔓',
  protocol_anomaly: '⚠️',
  bandwidth_spike: '📈',
  new_external_connection: '🌐',
};

export default function NDRDashboard() {
  const [anomalies, setAnomalies] = useState<Anomaly[]>([]);
  const [summary, setSummary] = useState<TrafficSummary | null>(null);
  const [severityFilter, setSeverityFilter] = useState('');
  const [detecting, setDetecting] = useState(false);
  const [seeding, setSeeding] = useState(false);

  useEffect(() => { loadAll(); }, [severityFilter]);

  async function loadAll() {
    try {
      const [aRes, sRes] = await Promise.all([
        authFetch(`/api/ndr/anomalies${severityFilter ? `?severity=${severityFilter}` : ''}`),
        authFetch('/api/ndr/summary'),
      ]);
      const [a, s] = await Promise.all([aRes.json(), sRes.json()]);
      setAnomalies(a.anomalies || []);
      setSummary(s);
    } catch (err) { console.error(err); }
  }

  async function runDetection() {
    setDetecting(true);
    try {
      await authFetch('/api/ndr/detect', { method: 'POST' });
      loadAll();
    } finally { setDetecting(false); }
  }

  async function seedData() {
    setSeeding(true);
    try {
      await authFetch('/api/ndr/seed', { method: 'POST' });
      loadAll();
    } finally { setSeeding(false); }
  }

  function formatBytes(b: number) {
    if (b > 1024 * 1024) return `${(b / 1024 / 1024).toFixed(1)} MB`;
    if (b > 1024) return `${(b / 1024).toFixed(1)} KB`;
    return `${b} B`;
  }

  return (
    <div className="p-6 bg-gray-900 min-h-screen text-white">
      <div className="flex justify-between items-center mb-6">
        <div>
          <h1 className="text-2xl font-bold">Network Detection & Response</h1>
          <p className="text-gray-400 text-sm mt-1">Behavioral traffic analysis, anomaly detection, and east-west threat hunting</p>
        </div>
        <div className="flex gap-2">
          <button onClick={seedData} disabled={seeding}
            className="bg-gray-700 hover:bg-gray-600 disabled:opacity-50 px-3 py-2 rounded-lg text-sm">
            {seeding ? 'Seeding…' : 'Demo Data'}
          </button>
          <button onClick={runDetection} disabled={detecting}
            className="bg-blue-600 hover:bg-blue-700 disabled:opacity-50 px-4 py-2 rounded-lg text-sm font-medium">
            {detecting ? 'Detecting…' : '🔍 Run Detection'}
          </button>
        </div>
      </div>

      {summary && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-6">
          {[
            { label: 'Flows (24h)', value: summary.flows_24h.toLocaleString(), color: 'text-blue-400' },
            { label: 'Open Anomalies', value: summary.open_anomalies, color: summary.open_anomalies > 0 ? 'text-yellow-400' : 'text-green-400' },
            { label: 'Critical', value: summary.critical_anomalies, color: summary.critical_anomalies > 0 ? 'text-red-400' : 'text-green-400' },
            { label: 'Protocols', value: summary.protocols_monitored, color: 'text-purple-400' },
          ].map(c => (
            <div key={c.label} className="bg-gray-800 rounded-xl p-4 border border-gray-700 text-center">
              <div className={`text-3xl font-bold ${c.color}`}>{c.value}</div>
              <div className="text-xs text-gray-400 mt-1">{c.label}</div>
            </div>
          ))}
        </div>
      )}

      {summary?.detection_running && (
        <div className="bg-green-900/20 border border-green-700/50 rounded-xl p-3 mb-4 flex items-center gap-2">
          <span className="w-2 h-2 rounded-full bg-green-400 animate-pulse" />
          <span className="text-green-300 text-sm">Detection engine active — monitoring all network flows in real time</span>
        </div>
      )}

      <div className="flex gap-2 mb-4">
        {['', 'critical', 'high', 'medium', 'low'].map(s => (
          <button key={s} onClick={() => setSeverityFilter(s)}
            className={`px-3 py-1 rounded text-xs font-medium capitalize ${severityFilter === s ? 'bg-blue-600 text-white' : 'bg-gray-800 text-gray-400 hover:text-white'}`}>
            {s || 'All'}
          </button>
        ))}
      </div>

      {anomalies.length === 0 ? (
        <div className="text-center py-16 text-gray-500 bg-gray-800 rounded-xl border border-gray-700">
          <div className="text-5xl mb-4">🌐</div>
          <p className="text-lg">No anomalies detected</p>
          <p className="text-sm mt-2">Load demo data or run detection to see network anomalies</p>
        </div>
      ) : (
        <div className="space-y-3">
          {anomalies.map(a => (
            <div key={a.id} className={`bg-gray-800 rounded-xl p-5 border ${a.severity === 'critical' ? 'border-red-800' : 'border-gray-700'}`}>
              <div className="flex items-start justify-between mb-3">
                <div className="flex items-center gap-3">
                  <span className="text-2xl">{TYPE_ICONS[a.type] || '⚠️'}</span>
                  <div>
                    <div className="flex items-center gap-2">
                      <span className={`text-xs px-2 py-0.5 rounded border font-medium capitalize ${SEV_COLORS[a.severity] || ''}`}>
                        {a.severity}
                      </span>
                      <span className="text-xs text-gray-400 bg-gray-700 px-2 py-0.5 rounded font-mono">{a.mitre_technique}</span>
                    </div>
                    <p className="text-sm font-medium mt-1">{a.description}</p>
                  </div>
                </div>
                <span className={`text-xs capitalize px-2 py-0.5 rounded ${a.status === 'open' ? 'text-yellow-400 bg-yellow-900/20' : 'text-gray-400'}`}>
                  {a.status}
                </span>
              </div>
              <div className="grid grid-cols-2 md:grid-cols-5 gap-3 text-xs">
                <div><span className="text-gray-500">Source IP</span><p className="text-white font-mono">{a.src_ip}</p></div>
                <div><span className="text-gray-500">Dest IP</span><p className="text-white font-mono">{a.dst_ip}</p></div>
                <div><span className="text-gray-500">Protocol</span><p className="text-blue-300">{a.protocol}</p></div>
                <div><span className="text-gray-500">Transfer</span><p className="text-white">{formatBytes(a.bytes)}</p></div>
                <div><span className="text-gray-500">Confidence</span>
                  <div className="flex items-center gap-1 mt-0.5">
                    <div className="w-16 bg-gray-700 rounded-full h-1.5">
                      <div className="h-1.5 rounded-full bg-blue-500" style={{ width: `${a.confidence * 100}%` }} />
                    </div>
                    <span className="text-white">{Math.round(a.confidence * 100)}%</span>
                  </div>
                </div>
              </div>
              <p className="text-xs text-gray-500 mt-2">{new Date(a.detected_at).toLocaleString()}</p>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

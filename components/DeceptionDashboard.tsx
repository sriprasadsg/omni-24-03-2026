import React, { useState, useEffect } from 'react';
import { authFetch } from '../services/apiService';

interface Honeytoken {
  id: string;
  type: string;
  label: string;
  description: string;
  token_value: string;
  deploy_location: string;
  created_at: string;
  last_triggered: string | null;
  trigger_count: number;
  active: boolean;
}

interface DeceptionAlert {
  id: string;
  honeytoken_type: string;
  honeytoken_label: string;
  source_ip: string;
  user_agent: string;
  triggered_at: string;
  severity: string;
  description: string;
  status: string;
}

interface Summary {
  total_honeytokens: number;
  active_honeytokens: number;
  total_alerts: number;
  open_alerts: number;
  agent_hits_detected: number;
  honeytoken_types: string[];
}

const TYPE_ICONS: Record<string, string> = {
  aws_key: '🔑',
  api_key: '🗝️',
  url_token: '🌐',
  dns_token: '📡',
  document_token: '📄',
};

const TYPE_LABELS: Record<string, string> = {
  aws_key: 'AWS Key',
  api_key: 'API Key',
  url_token: 'URL Token',
  dns_token: 'DNS Token',
  document_token: 'Document',
};

export default function DeceptionDashboard() {
  const [summary, setSummary] = useState<Summary | null>(null);
  const [honeytokens, setHoneytokens] = useState<Honeytoken[]>([]);
  const [alerts, setAlerts] = useState<DeceptionAlert[]>([]);
  const [tab, setTab] = useState<'overview' | 'honeytokens' | 'alerts'>('overview');
  const [showCreate, setShowCreate] = useState(false);
  const [form, setForm] = useState({ type: 'api_key', label: '', description: '', deploy_location: '' });
  const [creating, setCreating] = useState(false);
  const [newToken, setNewToken] = useState<Honeytoken | null>(null);

  useEffect(() => {
    loadAll();
    const iv = setInterval(loadAll, 30000);
    return () => clearInterval(iv);
  }, []);

  async function loadAll() {
    try {
      const [sRes, tRes, aRes] = await Promise.all([
        authFetch('/api/deception/summary'),
        authFetch('/api/deception/honeytokens'),
        authFetch('/api/deception/alerts?limit=50'),
      ]);
      const [s, t, a] = await Promise.all([sRes.json(), tRes.json(), aRes.json()]);
      setSummary(s);
      setHoneytokens(t.honeytokens || []);
      setAlerts(a.alerts || []);
    } catch (e) {
      console.error('Failed to load deception data', e);
    }
  }

  async function createToken() {
    if (!form.label.trim()) return;
    setCreating(true);
    try {
      const r = await authFetch('/api/deception/honeytokens', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(form),
      });
      const d = await r.json();
      setNewToken(d.honeytoken);
      setHoneytokens(prev => [d.honeytoken, ...prev]);
      setForm({ type: 'api_key', label: '', description: '', deploy_location: '' });
      setShowCreate(false);
      if (summary) setSummary({ ...summary, total_honeytokens: summary.total_honeytokens + 1, active_honeytokens: summary.active_honeytokens + 1 });
    } finally {
      setCreating(false);
    }
  }

  async function deleteToken(id: string) {
    await authFetch(`/api/deception/honeytokens/${id}`, { method: 'DELETE' });
    setHoneytokens(prev => prev.filter(t => t.id !== id));
  }

  return (
    <div className="p-6 bg-gray-900 min-h-screen text-white">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2">
            <span>Deception Technology</span>
            {summary && summary.open_alerts > 0 && (
              <span className="bg-red-600 text-white text-xs px-2 py-0.5 rounded-full animate-pulse">
                {summary.open_alerts} ACTIVE
              </span>
            )}
          </h1>
          <p className="text-gray-400 text-sm mt-1">Honeytokens, canary files, and honeypot detection</p>
        </div>
        <button onClick={() => setShowCreate(true)} className="bg-red-700 hover:bg-red-600 px-4 py-2 rounded-lg text-sm font-medium">
          + Deploy Honeytoken
        </button>
      </div>

      {/* Summary Cards */}
      {summary && (
        <div className="grid grid-cols-2 md:grid-cols-5 gap-4 mb-6">
          {[
            { label: 'Total Tokens', value: summary.total_honeytokens, color: 'text-blue-400' },
            { label: 'Active', value: summary.active_honeytokens, color: 'text-green-400' },
            { label: 'Total Alerts', value: summary.total_alerts, color: 'text-yellow-400' },
            { label: 'Open Alerts', value: summary.open_alerts, color: summary.open_alerts > 0 ? 'text-red-400 animate-pulse' : 'text-gray-400' },
            { label: 'Agent Hits', value: summary.agent_hits_detected, color: 'text-purple-400' },
          ].map(card => (
            <div key={card.label} className="bg-gray-800 rounded-xl p-4 border border-gray-700 text-center">
              <div className={`text-3xl font-bold ${card.color}`}>{card.value}</div>
              <div className="text-gray-400 text-xs mt-1">{card.label}</div>
            </div>
          ))}
        </div>
      )}

      {/* Tabs */}
      <div className="flex gap-1 mb-6 bg-gray-800 rounded-lg p-1 w-fit">
        {(['overview', 'honeytokens', 'alerts'] as const).map(t => (
          <button key={t} onClick={() => setTab(t)}
            className={`px-4 py-1.5 rounded-md text-sm capitalize transition-colors ${
              tab === t ? 'bg-blue-600 text-white' : 'text-gray-400 hover:text-white'
            }`}>{t}</button>
        ))}
      </div>

      {/* Create Modal */}
      {showCreate && (
        <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50">
          <div className="bg-gray-800 rounded-xl p-6 w-full max-w-md border border-gray-600">
            <h3 className="font-bold text-lg mb-4">Deploy New Honeytoken</h3>
            <div className="space-y-3">
              <div>
                <label className="text-sm text-gray-400 block mb-1">Token Type</label>
                <div className="grid grid-cols-2 gap-2">
                  {Object.entries(TYPE_LABELS).map(([id, name]) => (
                    <label key={id} className={`flex items-center gap-2 p-2 rounded-lg border cursor-pointer text-sm ${
                      form.type === id ? 'border-red-500 bg-red-900/20' : 'border-gray-600 hover:border-gray-400'
                    }`}>
                      <input type="radio" name="type" value={id} checked={form.type === id}
                        onChange={() => setForm(p => ({ ...p, type: id }))} />
                      <span>{TYPE_ICONS[id]}</span> {name}
                    </label>
                  ))}
                </div>
              </div>
              <div>
                <label className="text-sm text-gray-400 block mb-1">Label *</label>
                <input value={form.label} onChange={e => setForm(p => ({ ...p, label: e.target.value }))}
                  placeholder="e.g. Finance S3 Backup Key"
                  className="w-full bg-gray-700 border border-gray-600 rounded px-3 py-2 text-sm text-white" />
              </div>
              <div>
                <label className="text-sm text-gray-400 block mb-1">Deploy Location</label>
                <input value={form.deploy_location} onChange={e => setForm(p => ({ ...p, deploy_location: e.target.value }))}
                  placeholder="e.g. /etc/config/backup.env"
                  className="w-full bg-gray-700 border border-gray-600 rounded px-3 py-2 text-sm text-white" />
              </div>
            </div>
            <div className="flex gap-3 mt-5">
              <button onClick={createToken} disabled={creating || !form.label.trim()}
                className="flex-1 bg-red-700 hover:bg-red-600 disabled:opacity-50 px-4 py-2 rounded-lg text-sm font-medium">
                {creating ? 'Creating...' : 'Create & Deploy'}
              </button>
              <button onClick={() => setShowCreate(false)}
                className="px-4 py-2 rounded-lg border border-gray-600 hover:border-gray-400 text-sm">Cancel</button>
            </div>
          </div>
        </div>
      )}

      {/* New token reveal */}
      {newToken && (
        <div className="bg-yellow-900/30 border border-yellow-600 rounded-xl p-4 mb-6">
          <div className="flex justify-between items-start">
            <div>
              <h3 className="font-semibold text-yellow-300">Honeytoken Created — Copy Now</h3>
              <p className="text-sm text-gray-300 mt-1">This is the only time the full token value is shown.</p>
              <div className="mt-2 bg-gray-900 rounded px-3 py-2 font-mono text-sm text-green-300 break-all">
                {newToken.token_value}
              </div>
              <p className="text-xs text-gray-400 mt-2">
                Deploy this in: <span className="text-white">{newToken.deploy_location || '(not specified)'}</span>
              </p>
            </div>
            <button onClick={() => setNewToken(null)} className="text-gray-400 hover:text-white ml-4">✕</button>
          </div>
        </div>
      )}

      {/* Overview Tab */}
      {tab === 'overview' && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <div className="bg-gray-800 rounded-xl p-5 border border-gray-700">
            <h3 className="font-semibold mb-4">How It Works</h3>
            <div className="space-y-3 text-sm text-gray-300">
              {[
                ['🪤', 'Canary Files', 'Fake credential files deployed on endpoints — any access triggers a Critical alert'],
                ['🔑', 'Honeytokens', 'Fake credentials embedded in configs — any use triggers an immediate alert'],
                ['🌐', 'Honeypot Ports', 'Agents listen on unused ports — any connection is suspicious'],
                ['🔔', 'Zero False Positives', 'Nothing legitimate ever touches these — every hit is a real threat'],
              ].map(([icon, title, desc]) => (
                <div key={title as string} className="flex gap-3">
                  <span className="text-xl">{icon}</span>
                  <div><div className="font-medium">{title as string}</div><div className="text-gray-400">{desc as string}</div></div>
                </div>
              ))}
            </div>
          </div>

          <div className="bg-gray-800 rounded-xl p-5 border border-gray-700">
            <h3 className="font-semibold mb-4">Recent Alerts</h3>
            {alerts.length === 0 ? (
              <div className="text-center py-8 text-gray-500">
                <div className="text-3xl mb-2">✅</div>
                <p className="text-sm">No deception alerts — your environment is clean</p>
              </div>
            ) : (
              <div className="space-y-2">
                {alerts.slice(0, 5).map(alert => (
                  <div key={alert.id} className="bg-red-900/20 border border-red-800 rounded-lg p-3">
                    <div className="flex justify-between items-start">
                      <div>
                        <div className="text-sm font-medium text-red-300">{alert.honeytoken_label}</div>
                        <div className="text-xs text-gray-400 mt-0.5">from {alert.source_ip}</div>
                      </div>
                      <span className="text-xs text-red-400 font-bold">{alert.severity}</span>
                    </div>
                    <div className="text-xs text-gray-400 mt-1">
                      {new Date(alert.triggered_at).toLocaleString()}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}

      {/* Honeytokens Tab */}
      {tab === 'honeytokens' && (
        <div className="space-y-3">
          {honeytokens.length === 0 ? (
            <div className="text-center py-16 text-gray-500">
              <div className="text-5xl mb-4">🪤</div>
              <p>No honeytokens deployed yet</p>
              <button onClick={() => setShowCreate(true)} className="mt-3 bg-red-700 hover:bg-red-600 px-4 py-2 rounded text-sm">
                Deploy First Honeytoken
              </button>
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {honeytokens.map(token => (
                <div key={token.id} className={`bg-gray-800 rounded-xl p-4 border ${
                  token.trigger_count > 0 ? 'border-red-600' : token.active ? 'border-gray-700' : 'border-gray-800 opacity-60'
                }`}>
                  <div className="flex justify-between items-start mb-2">
                    <div className="flex items-center gap-2">
                      <span className="text-lg">{TYPE_ICONS[token.type]}</span>
                      <div>
                        <div className="font-medium text-sm">{token.label}</div>
                        <div className="text-xs text-gray-400">{TYPE_LABELS[token.type]}</div>
                      </div>
                    </div>
                    <span className={`text-xs px-2 py-0.5 rounded-full ${
                      !token.active ? 'bg-gray-700 text-gray-400' :
                      token.trigger_count > 0 ? 'bg-red-900 text-red-300' :
                      'bg-green-900 text-green-300'
                    }`}>
                      {!token.active ? 'Inactive' : token.trigger_count > 0 ? `${token.trigger_count} HITS` : 'Armed'}
                    </span>
                  </div>

                  <div className="text-xs font-mono text-gray-300 bg-gray-900 rounded px-2 py-1 mb-2 truncate">
                    {token.token_value}
                  </div>

                  {token.deploy_location && (
                    <div className="text-xs text-gray-400 mb-2">📍 {token.deploy_location}</div>
                  )}

                  {token.last_triggered && (
                    <div className="text-xs text-red-300 mb-2">
                      Last triggered: {new Date(token.last_triggered).toLocaleString()}
                    </div>
                  )}

                  <div className="flex gap-2 mt-3">
                    <button onClick={() => deleteToken(token.id)}
                      className="flex-1 bg-gray-700 hover:bg-red-900 px-3 py-1 rounded text-xs text-gray-300 hover:text-red-300 transition-colors">
                      Delete
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Alerts Tab */}
      {tab === 'alerts' && (
        <div className="space-y-3">
          {alerts.length === 0 ? (
            <div className="text-center py-16 text-gray-500">
              <div className="text-5xl mb-4">🛡️</div>
              <p>No deception alerts — your honeytokens have not been triggered</p>
            </div>
          ) : (
            alerts.map(alert => (
              <div key={alert.id} className="bg-gray-800 rounded-xl p-4 border border-red-800">
                <div className="flex justify-between items-start mb-2">
                  <div>
                    <div className="flex items-center gap-2">
                      <span className="text-red-400 font-bold text-sm">CRITICAL ALERT</span>
                      <span className="text-xs text-gray-400">• {alert.honeytoken_type}</span>
                    </div>
                    <div className="font-medium mt-0.5">{alert.description}</div>
                  </div>
                  <span className={`text-xs px-2 py-0.5 rounded-full ${
                    alert.status === 'open' ? 'bg-red-900 text-red-300' : 'bg-gray-700 text-gray-400'
                  }`}>{alert.status}</span>
                </div>
                <div className="grid grid-cols-2 md:grid-cols-3 gap-3 mt-2 text-xs text-gray-400">
                  <div><span className="text-gray-500">Source IP:</span> <span className="text-white">{alert.source_ip}</span></div>
                  <div><span className="text-gray-500">Token:</span> <span className="text-white">{alert.honeytoken_label}</span></div>
                  <div><span className="text-gray-500">Time:</span> <span className="text-white">{new Date(alert.triggered_at).toLocaleString()}</span></div>
                </div>
                {alert.user_agent && (
                  <div className="text-xs text-gray-500 mt-1 truncate">UA: {alert.user_agent}</div>
                )}
              </div>
            ))
          )}
        </div>
      )}
    </div>
  );
}

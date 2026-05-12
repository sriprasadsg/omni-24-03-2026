import React, { useState, useEffect } from 'react';
import { authFetch } from '../services/apiService';

interface UserProfile {
  id: string;
  user_name: string;
  user_email: string;
  department: string;
  role: string;
  risk_score: number;
  risk_level: string;
  active_indicators: { id: string; name: string; category: string }[];
  last_activity: string;
  alert_count: number;
}

interface ITAlert {
  id: string;
  user_name: string;
  user_email: string;
  indicator_name: string;
  category: string;
  severity: string;
  risk_score: number;
  description: string;
  detected_at: string;
  status: string;
}

interface Summary {
  total_users_monitored: number;
  high_risk_users: number;
  open_alerts: number;
  critical_alerts: number;
}

const RISK_COLORS: Record<string, string> = {
  critical: 'text-red-400 bg-red-900/20 border-red-700',
  high: 'text-orange-400 bg-orange-900/20 border-orange-700',
  medium: 'text-yellow-400 bg-yellow-900/20 border-yellow-700',
  low: 'text-green-400 bg-green-900/20 border-green-700',
};

const CAT_ICONS: Record<string, string> = {
  data_exfiltration: '📤',
  access: '🔐',
  behavioral: '👁️',
};

export default function InsiderThreatDashboard() {
  const [profiles, setProfiles] = useState<UserProfile[]>([]);
  const [alerts, setAlerts] = useState<ITAlert[]>([]);
  const [summary, setSummary] = useState<Summary | null>(null);
  const [tab, setTab] = useState<'alerts' | 'users'>('alerts');
  const [riskFilter, setRiskFilter] = useState('');
  const [seeding, setSeeding] = useState(false);

  useEffect(() => { loadAll(); }, [riskFilter]);

  async function loadAll() {
    try {
      const [pRes, aRes, sRes] = await Promise.all([
        authFetch(`/api/insider-threat/profiles${riskFilter ? `?risk_level=${riskFilter}` : ''}`),
        authFetch('/api/insider-threat/alerts'),
        authFetch('/api/insider-threat/summary'),
      ]);
      const [p, a, s] = await Promise.all([pRes.json(), aRes.json(), sRes.json()]);
      setProfiles(p.profiles || []);
      setAlerts(a.alerts || []);
      setSummary(s);
    } catch (err) { console.error(err); }
  }

  async function seedData() {
    setSeeding(true);
    try {
      await authFetch('/api/insider-threat/seed', { method: 'POST' });
      loadAll();
    } finally { setSeeding(false); }
  }

  async function updateAlertStatus(id: string, status: string) {
    await authFetch(`/api/insider-threat/alerts/${id}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ status }),
    });
    loadAll();
  }

  const riskBar = (score: number, level: string) => (
    <div className="flex items-center gap-2">
      <div className="w-20 bg-gray-700 rounded-full h-2">
        <div className={`h-2 rounded-full ${level === 'critical' ? 'bg-red-500' : level === 'high' ? 'bg-orange-500' : level === 'medium' ? 'bg-yellow-500' : 'bg-green-500'}`}
          style={{ width: `${score}%` }} />
      </div>
      <span className="text-sm font-bold">{score}</span>
    </div>
  );

  return (
    <div className="p-6 bg-gray-900 min-h-screen text-white">
      <div className="flex justify-between items-center mb-6">
        <div>
          <h1 className="text-2xl font-bold">Insider Threat Detection</h1>
          <p className="text-gray-400 text-sm mt-1">Behavioral risk scoring, exfiltration indicators, and user activity monitoring</p>
        </div>
        <button onClick={seedData} disabled={seeding}
          className="bg-gray-700 hover:bg-gray-600 disabled:opacity-50 px-4 py-2 rounded-lg text-sm">
          {seeding ? 'Loading…' : 'Load Demo Data'}
        </button>
      </div>

      {summary && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-6">
          {[
            { label: 'Users Monitored', value: summary.total_users_monitored, color: 'text-blue-400' },
            { label: 'High Risk Users', value: summary.high_risk_users, color: summary.high_risk_users > 0 ? 'text-red-400' : 'text-green-400' },
            { label: 'Open Alerts', value: summary.open_alerts, color: summary.open_alerts > 0 ? 'text-yellow-400' : 'text-green-400' },
            { label: 'Critical', value: summary.critical_alerts, color: summary.critical_alerts > 0 ? 'text-red-400' : 'text-green-400' },
          ].map(c => (
            <div key={c.label} className="bg-gray-800 rounded-xl p-4 border border-gray-700 text-center">
              <div className={`text-3xl font-bold ${c.color}`}>{c.value}</div>
              <div className="text-xs text-gray-400 mt-1">{c.label}</div>
            </div>
          ))}
        </div>
      )}

      <div className="flex gap-2 mb-4">
        {(['alerts', 'users'] as const).map(t => (
          <button key={t} onClick={() => setTab(t)}
            className={`px-3 py-1.5 rounded-lg text-sm font-medium capitalize ${tab === t ? 'bg-blue-600 text-white' : 'bg-gray-800 text-gray-400 hover:text-white'}`}>
            {t} ({t === 'alerts' ? alerts.length : profiles.length})
          </button>
        ))}
        {tab === 'users' && (
          <div className="ml-auto flex gap-1">
            {['', 'critical', 'high', 'medium', 'low'].map(r => (
              <button key={r} onClick={() => setRiskFilter(r)}
                className={`px-2 py-0.5 rounded text-xs capitalize ${riskFilter === r ? 'bg-blue-600 text-white' : 'bg-gray-800 text-gray-400 hover:text-white'}`}>
                {r || 'All'}
              </button>
            ))}
          </div>
        )}
      </div>

      {tab === 'alerts' && (
        alerts.length === 0 ? (
          <div className="text-center py-12 text-gray-500 bg-gray-800 rounded-xl border border-gray-700">
            <div className="text-4xl mb-3">👁️</div>
            <p>No insider threat alerts — load demo data to see detections</p>
          </div>
        ) : (
          <div className="space-y-3">
            {alerts.map(a => (
              <div key={a.id} className={`bg-gray-800 rounded-xl p-4 border ${a.severity === 'critical' ? 'border-red-800' : 'border-gray-700'}`}>
                <div className="flex items-start justify-between">
                  <div className="flex-1">
                    <div className="flex items-center gap-2 mb-1">
                      <span>{CAT_ICONS[a.category] || '⚠️'}</span>
                      <span className={`text-xs px-2 py-0.5 rounded border font-medium capitalize ${RISK_COLORS[a.severity]?.split(' ').slice(0, 3).join(' ') || ''}`}>
                        {a.severity}
                      </span>
                      <span className="text-xs text-gray-400 capitalize">{a.category.replace(/_/g, ' ')}</span>
                    </div>
                    <p className="text-sm font-medium">{a.description}</p>
                    <div className="flex gap-4 mt-1 text-xs text-gray-400">
                      <span>User: <span className="text-white">{a.user_name}</span></span>
                      <span>Risk Score: <span className="text-orange-300 font-bold">{a.risk_score}</span></span>
                      <span>{new Date(a.detected_at).toLocaleString()}</span>
                    </div>
                  </div>
                  <div className="flex gap-2 ml-4">
                    {a.status === 'open' && (
                      <button onClick={() => updateAlertStatus(a.id, 'investigating')}
                        className="bg-blue-900/40 hover:bg-blue-900/70 border border-blue-700 px-2 py-1 rounded text-xs text-blue-300">
                        Investigate
                      </button>
                    )}
                    {a.status !== 'resolved' && (
                      <button onClick={() => updateAlertStatus(a.id, 'resolved')}
                        className="bg-green-900/30 hover:bg-green-900/60 border border-green-700 px-2 py-1 rounded text-xs text-green-300">
                        Resolve
                      </button>
                    )}
                    <span className={`text-xs capitalize px-2 py-1 rounded ${a.status === 'open' ? 'text-yellow-400' : a.status === 'investigating' ? 'text-blue-400' : 'text-green-400'}`}>
                      {a.status}
                    </span>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )
      )}

      {tab === 'users' && (
        profiles.length === 0 ? (
          <div className="text-center py-12 text-gray-500 bg-gray-800 rounded-xl border border-gray-700">
            <p>No user profiles — load demo data</p>
          </div>
        ) : (
          <div className="space-y-2">
            {profiles.map(p => (
              <div key={p.id} className={`bg-gray-800 rounded-xl p-4 border ${RISK_COLORS[p.risk_level] ? `border ${RISK_COLORS[p.risk_level].split(' ').pop()}` : 'border-gray-700'}`}>
                <div className="flex items-center justify-between">
                  <div className="flex-1">
                    <div className="flex items-center gap-3 mb-1">
                      <div className={`text-xs px-2 py-0.5 rounded border font-medium capitalize ${RISK_COLORS[p.risk_level] || ''}`}>
                        {p.risk_level}
                      </div>
                      <span className="font-medium">{p.user_name}</span>
                      <span className="text-gray-400 text-sm">{p.department}</span>
                    </div>
                    <div className="flex gap-4 text-xs text-gray-400 mb-2">
                      <span>{p.user_email}</span>
                      <span>{p.role}</span>
                      <span>{p.alert_count} alerts</span>
                      <span>Last seen: {new Date(p.last_activity).toLocaleDateString()}</span>
                    </div>
                    {p.active_indicators.length > 0 && (
                      <div className="flex flex-wrap gap-1">
                        {p.active_indicators.slice(0, 4).map(ind => (
                          <span key={ind.id} className="text-xs bg-gray-700 text-gray-300 px-2 py-0.5 rounded">
                            {CAT_ICONS[ind.category]} {ind.name}
                          </span>
                        ))}
                        {p.active_indicators.length > 4 && (
                          <span className="text-xs text-gray-500">+{p.active_indicators.length - 4} more</span>
                        )}
                      </div>
                    )}
                  </div>
                  <div className="ml-6 text-right">
                    {riskBar(p.risk_score, p.risk_level)}
                    <span className="text-xs text-gray-500 mt-1">risk score</span>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )
      )}
    </div>
  );
}

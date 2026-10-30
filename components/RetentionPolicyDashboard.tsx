import React, { useState, useEffect } from 'react';
import { authFetch } from '../services/apiService';

interface Policy {
  collection: string;
  retention_days: number;
  description: string;
  /** Phase 82: the caller's own tenant only; waiting means the nightly and manual runs only count this type. */
  gate?: { waiting: boolean; reason?: string | null };
  managedBy?: string;
  editable?: boolean;
}

interface CleanupResult {
  ran_at: string;
  result: Record<string, any>;
}

export default function RetentionPolicyDashboard() {
  const [policies, setPolicies] = useState<Policy[]>([]);
  const [stats, setStats] = useState<any>(null);
  const [running, setRunning] = useState(false);
  const [lastResult, setLastResult] = useState<CleanupResult | null>(null);
  const [editing, setEditing] = useState<string | null>(null);
  const [editDays, setEditDays] = useState<number>(90);
  const [shortened, setShortened] = useState<string | null>(null);

  useEffect(() => { loadAll(); }, []);

  async function loadAll() {
    try {
      const [pRes, sRes] = await Promise.all([
        authFetch('/api/retention/policies'),
        authFetch('/api/retention/stats'),
      ]);
      const [p, s] = await Promise.all([pRes.json(), sRes.json()]);
      const raw: Policy[] = p.policies || [];
      const seen = new Set<string>();
      setPolicies(raw.filter(pol => seen.has(pol.collection) ? false : (seen.add(pol.collection), true)));
      setStats(s);
    } catch (e) { console.error(e); }
  }

  async function runCleanup() {
    if (!confirm("Run data retention cleanup now? This permanently deletes data older than each policy threshold, except data types still waiting for a platform administrator's confirmation, which are only counted. Audit logs are not affected.")) return;
    setRunning(true);
    try {
      const r = await authFetch('/api/retention/run', { method: 'POST' });
      const d = await r.json();
      setLastResult(d);
      loadAll();
    } finally { setRunning(false); }
  }

  async function savePolicy(collection: string) {
    const previous = policies.find(p => p.collection === collection)?.retention_days;
    setShortened(null);
    const res = await authFetch(`/api/retention/policies/${collection}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ retention_days: editDays }),
    });
    // D-19: only a shorter period that the server holds for confirmation gets the notice; lengthening gets none.
    try {
      const saved = res.ok ? await res.json() : null;
      if (saved?.countOnlyUntilConfirmed === true && typeof previous === 'number' && editDays < previous) {
        setShortened(collection);
      }
    } catch { /* an unreadable answer shows no notice */ }
    setEditing(null);
    loadAll();
  }

  const COLLECTION_ICONS: Record<string, string> = {
    audit_logs: '📋',
    metrics: '📊',
    notifications: '🔔',
    security_events: '🛡️',
    alerts: '⚠️',
  };

  const RETENTION_COLOR = (days: number) => {
    if (days <= 30) return 'text-yellow-700 dark:text-yellow-400';
    if (days <= 90) return 'text-blue-600 dark:text-blue-400';
    return 'text-green-600 dark:text-green-400';
  };

  return (
    <div className="p-6 bg-transparent dark:bg-gray-900 min-h-screen text-gray-900 dark:text-white">
      <div className="flex justify-between items-center mb-6">
        <div>
          <h1 className="text-2xl font-bold">Data Retention Policies</h1>
          <p className="text-gray-600 dark:text-gray-400 text-sm mt-1">Configure how long each data collection is stored before automatic purging</p>
        </div>
        <button onClick={runCleanup} disabled={running}
          className="bg-red-700 hover:bg-red-600 disabled:opacity-50 px-4 py-2 rounded-lg text-sm font-medium text-white">
          {running ? 'Running Cleanup…' : '🗑 Run Cleanup Now'}
        </button>
      </div>

      {stats && (
        <div className="grid grid-cols-2 md:grid-cols-3 gap-4 mb-6">
          <div className="bg-white dark:bg-gray-800 rounded-xl p-4 border border-gray-200 dark:border-gray-700 text-center">
            <div className="text-3xl font-bold text-blue-600 dark:text-blue-400">{stats.policies}</div>
            <div className="text-xs text-gray-600 dark:text-gray-400 mt-1">Active Policies</div>
          </div>
          <div className="bg-white dark:bg-gray-800 rounded-xl p-4 border border-gray-200 dark:border-gray-700 text-center">
            <div className="text-3xl font-bold text-purple-600 dark:text-purple-400">{stats.collections?.length || 0}</div>
            <div className="text-xs text-gray-600 dark:text-gray-400 mt-1">Collections Managed</div>
          </div>
          <div className="bg-white dark:bg-gray-800 rounded-xl p-4 border border-gray-200 dark:border-gray-700 text-center">
            <div className={`text-3xl font-bold ${stats.last_cleanup ? 'text-green-600 dark:text-green-400' : 'text-gray-500'}`}>
              {stats.last_cleanup ? new Date(stats.last_cleanup).toLocaleDateString() : 'Never'}
            </div>
            <div className="text-xs text-gray-600 dark:text-gray-400 mt-1">Last Cleanup</div>
          </div>
        </div>
      )}

      {lastResult && (
        <div className="bg-green-100 dark:bg-green-900/20 border border-green-200 dark:border-green-700 rounded-xl p-4 mb-6">
          <p className="text-green-700 dark:text-green-300 font-medium text-sm mb-2">✓ Cleanup completed at {new Date(lastResult.ran_at).toLocaleString()}</p>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
            {Object.entries(lastResult.result || {}).map(([k, v]) => (
              k !== 'status' && (
                <div key={k} className="bg-green-100 dark:bg-green-900/30 rounded px-3 py-2">
                  <div className="text-green-800 dark:text-green-200 text-lg font-bold">{String(v)}</div>
                  <div className="text-xs text-green-600 dark:text-green-400 capitalize">{k.replace(/_/g, ' ')}</div>
                </div>
              )
            ))}
          </div>
        </div>
      )}

      <div className="space-y-3">
        <h2 className="text-sm font-semibold text-gray-600 dark:text-gray-400 uppercase tracking-wide mb-3">Collection Policies</h2>
        {policies.map(policy => (
          <div key={policy.collection} className="bg-white dark:bg-gray-800 rounded-xl p-5 border border-gray-200 dark:border-gray-700">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                <span className="text-2xl">{COLLECTION_ICONS[policy.collection] || '🗄️'}</span>
                <div>
                  <h3 className="font-medium capitalize">{policy.collection.replace(/_/g, ' ')}</h3>
                  <p className="text-sm text-gray-600 dark:text-gray-400">{policy.description}</p>
                </div>
              </div>
              <div className="flex items-center gap-4">
                {editing === policy.collection ? (
                  <div className="flex items-center gap-2">
                    <input
                      type="number" min={1} max={3650} value={editDays}
                      onChange={e => setEditDays(Number(e.target.value))}
                      className="w-24 bg-gray-100 dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded px-2 py-1 text-sm text-gray-900 dark:text-white text-center"
                    />
                    <span className="text-sm text-gray-600 dark:text-gray-400">days</span>
                    <button onClick={() => savePolicy(policy.collection)}
                      className="bg-blue-600 hover:bg-blue-700 px-3 py-1 rounded text-xs text-white">Save</button>
                    <button onClick={() => setEditing(null)}
                      className="text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white text-xs">Cancel</button>
                  </div>
                ) : (
                  <>
                    <div className="text-right">
                      <span className={`text-2xl font-bold ${RETENTION_COLOR(policy.retention_days)}`}>
                        {policy.retention_days}
                      </span>
                      <span className="text-gray-600 dark:text-gray-400 text-sm ml-1">days</span>
                    </div>
                    {policy.editable !== false && policy.collection !== 'audit_logs' && (
                      <button onClick={() => { setEditing(policy.collection); setEditDays(policy.retention_days); setShortened(null); }}
                        className="bg-gray-100 dark:bg-gray-700 hover:bg-gray-200 dark:hover:bg-gray-600 px-3 py-1.5 rounded text-xs">
                        Edit
                      </button>
                    )}
                  </>
                )}
              </div>
            </div>
            {policy.collection === 'audit_logs' && (
              <p className="mt-3 text-xs text-gray-600 dark:text-gray-400 break-words">
                Audit logs are kept by the audit ledger's own schedule, not by this cleanup.
              </p>
            )}
            {policy.gate?.waiting && (
              <p className="mt-3 text-xs text-gray-600 dark:text-gray-400 break-words">
                Waiting for a platform administrator to confirm before old records are deleted. Until then, the nightly run and Run Cleanup Now only count them.
              </p>
            )}
            {shortened === policy.collection && (
              <div className="mt-3 bg-yellow-100 dark:bg-yellow-900/20 border border-yellow-200 dark:border-yellow-700/50 rounded-lg p-3">
                <p className="text-yellow-800 dark:text-yellow-300 text-sm break-words">
                  Saved. Because this shortens the period, the next cleanup run, nightly or manual, only counts what would be deleted. A platform administrator confirms before anything is removed.
                </p>
              </div>
            )}
          </div>
        ))}
      </div>

      <div className="mt-6 bg-yellow-100 dark:bg-yellow-900/20 border border-yellow-200 dark:border-yellow-700/50 rounded-xl p-4">
        <p className="text-yellow-800 dark:text-yellow-300 text-sm font-medium mb-1">⚠ Retention Policy Guidelines</p>
        <ul className="text-xs text-yellow-800 dark:text-yellow-200/70 space-y-1 list-disc list-inside">
          <li>Audit logs must be retained for at least 90 days per SOC 2 requirements</li>
          <li>Security events retention of 365+ days recommended for forensic investigations</li>
          <li>GDPR Article 5(1)(e) requires data not be kept longer than necessary</li>
          <li>Cleanup runs automatically every night at 02:00 UTC.</li>
        </ul>
      </div>
    </div>
  );
}

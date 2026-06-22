import React, { useState, useEffect } from 'react';
import { authFetch, fetchComplianceFrameworks } from '../services/apiService';
import type { ComplianceFramework } from '../types';
import { showToast } from '../utils/toast';

interface ScheduledReport {
  id: string;
  name: string;
  report_type: string;
  frequency: string;
  delivery_channel: string;
  recipients: string[];
  enabled: boolean;
  // Backend uses last_run / next_run (not last_run_at / next_run_at)
  last_run: string | null;
  next_run: string | null;
  last_run_at?: string | null; // legacy alias
  next_run_at?: string | null; // legacy alias
  last_error?: string | null;
  created_at: string;
  run_count: number;
  framework_id?: string | null;
  framework_name?: string | null;
}

interface DeliveryLog {
  id: string;
  run_at: string;
  status: 'success' | 'failure';
  recipients: string[];
  error: string | null;
  format: string;
  filename: string | null;
}

function relativeTime(isoStr: string | null | undefined): string {
  if (!isoStr) return '—';
  const diff = Date.now() - new Date(isoStr).getTime();
  const future = diff < 0;
  const abs = Math.abs(diff);
  const mins = Math.floor(abs / 60_000);
  const hrs  = Math.floor(abs / 3_600_000);
  const days = Math.floor(abs / 86_400_000);
  let label: string;
  if (abs < 60_000)       label = 'just now';
  else if (mins < 60)     label = `${mins}m`;
  else if (hrs < 24)      label = `${hrs}h`;
  else                    label = `${days}d`;
  if (label === 'just now') return label;
  return future ? `in ${label}` : `${label} ago`;
}

const REPORT_TYPES = [
  'security_summary', 'vulnerability_report', 'compliance_status',
  'incident_report', 'agent_health', 'threat_intelligence', 'executive_summary',
  'compliance_summary', 'custom_framework',
];

const FREQUENCIES = ['daily', 'weekly', 'monthly', 'quarterly'];
const CHANNELS = ['email', 'webhook', 'slack', 'teams'];

const FREQ_COLORS: Record<string, string> = {
  daily: 'text-blue-300',
  weekly: 'text-purple-300',
  monthly: 'text-green-300',
  quarterly: 'text-orange-300',
};

const CHANNEL_ICONS: Record<string, string> = {
  email: '📧',
  webhook: '🔗',
  slack: '💬',
  teams: '🟦',
};

export default function ScheduledReportsDashboard() {
  const [reports, setReports] = useState<ScheduledReport[]>([]);
  const [showCreate, setShowCreate] = useState(false);
  const [running, setRunning] = useState<string | null>(null);
  const [form, setForm] = useState({
    name: '',
    report_type: 'security_summary',
    frequency: 'weekly',
    delivery_channel: 'email',
    recipients: '',
    webhook_url: '',
    framework_id: '',
  });
  const [saving, setSaving] = useState(false);
  const [loadError, setLoadError] = useState(false);
  const [frameworks, setFrameworks] = useState<ComplianceFramework[]>([]);
  const [historyOpen, setHistoryOpen] = useState<Record<string, boolean>>({});
  const [historyLogs, setHistoryLogs] = useState<Record<string, DeliveryLog[]>>({});
  const [historyLoading, setHistoryLoading] = useState<Record<string, boolean>>({});
  const [historyError, setHistoryError] = useState<Record<string, boolean>>({});

  useEffect(() => {
    loadReports();
    fetchComplianceFrameworks().then(setFrameworks);
  }, []);

  async function loadReports() {
    try {
      const r = await authFetch('/api/reports/scheduled');
      const d = await r.json();
      setReports(d.reports || []);
      setLoadError(false);
    } catch (e) { console.error(e); setLoadError(true); }
  }

  async function createReport() {
    setSaving(true);
    try {
      const body: Record<string, any> = {
        name: form.name,
        report_type: form.report_type,
        frequency: form.frequency,
        delivery_channel: form.delivery_channel,
        recipients: form.recipients.split(',').map(s => s.trim()).filter(Boolean),
      };
      if (form.webhook_url) body.webhook_url = form.webhook_url;
      if (form.framework_id) {
        body.framework_id = form.framework_id;
        body.framework_name = frameworks.find(f => f.id === form.framework_id)?.name ?? '';
      }
      const r = await authFetch('/api/reports/scheduled', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      if (r.ok) {
        loadReports();
        setShowCreate(false);
        setForm({ name: '', report_type: 'security_summary', frequency: 'weekly', delivery_channel: 'email', recipients: '', webhook_url: '', framework_id: '' });
      }
      else { const d = await r.json(); showToast(d.detail || 'Failed', 'error'); }
    } finally { setSaving(false); }
  }

  async function toggleReport(id: string, enabled: boolean) {
    await authFetch(`/api/reports/scheduled/${id}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ enabled: !enabled }),
    });
    loadReports();
  }

  async function runNow(id: string) {
    setRunning(id);
    try {
      await authFetch(`/api/reports/scheduled/${id}/run-now`, { method: 'POST' });
      loadReports();
    } finally { setRunning(null); }
  }

  async function deleteReport(id: string) {
    if (!confirm('Delete this scheduled report?')) return;
    await authFetch(`/api/reports/scheduled/${id}`, { method: 'DELETE' });
    loadReports();
  }

  async function toggleHistory(id: string) {
    const opening = !historyOpen[id];
    setHistoryOpen(prev => ({ ...prev, [id]: opening }));
    if (opening && !historyLogs[id]) {
      setHistoryLoading(prev => ({ ...prev, [id]: true }));
      try {
        const r = await authFetch(`/api/reports/scheduled/${id}/history`);
        const d = await r.json();
        setHistoryLogs(prev => ({ ...prev, [id]: d.logs || [] }));
      } catch { setHistoryError(prev => ({ ...prev, [id]: true })); }
      finally { setHistoryLoading(prev => ({ ...prev, [id]: false })); }
    }
  }

  return (
    <div className="p-6 bg-gray-900 min-h-screen text-white">
      <div className="flex justify-between items-center mb-6">
        <div>
          <h1 className="text-2xl font-bold">Scheduled Reports</h1>
          <p className="text-gray-400 text-sm mt-1">Automated report delivery via email, webhook, Slack, and Teams</p>
        </div>
        <button onClick={() => setShowCreate(true)} className="bg-blue-600 hover:bg-blue-700 px-4 py-2 rounded-lg text-sm font-medium">
          + Schedule Report
        </button>
      </div>

      {loadError && (
        <div className="mb-4 p-3 bg-red-900/30 border border-red-700 rounded-lg flex items-center justify-between text-sm text-red-400">
          <span>Failed to load scheduled reports.</span>
          <button className="underline ml-2" onClick={() => loadReports()}>Retry</button>
        </div>
      )}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-6">
        {FREQUENCIES.map(f => {
          const count = reports.filter(r => r.frequency === f).length;
          return (
            <div key={f} className="bg-gray-800 rounded-xl p-4 border border-gray-700 text-center">
              <div className={`text-2xl font-bold ${FREQ_COLORS[f]}`}>{count}</div>
              <div className="text-xs text-gray-400 mt-1 capitalize">{f}</div>
            </div>
          );
        })}
      </div>

      {reports.length === 0 ? (
        <div className="text-center py-20 text-gray-500 bg-gray-800 rounded-xl border border-gray-700">
          <div className="text-5xl mb-4">📊</div>
          <p className="text-lg">No scheduled reports yet</p>
          <p className="text-sm mt-2">Set up automated reports delivered to email, Slack, or your SIEM</p>
          <button onClick={() => setShowCreate(true)} className="mt-4 bg-blue-600 hover:bg-blue-700 px-6 py-2 rounded-lg text-sm">
            Schedule First Report
          </button>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {reports.map(rep => (
            <div key={rep.id} className="bg-gray-800 rounded-xl p-5 border border-gray-700 hover:border-gray-500 transition-colors">
              <div className="flex justify-between items-start mb-3">
                <div>
                  <h3 className="font-semibold">{rep.name}</h3>
                  <p className="text-xs text-gray-400 capitalize mt-0.5">{rep.report_type.replace(/_/g, ' ')}</p>
                  {rep.framework_name && (
                    <p className="text-xs text-gray-500 mt-0.5">{rep.framework_name}</p>
                  )}
                </div>
                <button
                  onClick={() => toggleReport(rep.id, rep.enabled)}
                  className={`relative inline-flex h-5 w-9 rounded-full transition-colors ${rep.enabled ? 'bg-green-500' : 'bg-gray-600'}`}
                >
                  <span className={`inline-block h-4 w-4 mt-0.5 rounded-full bg-white transition-transform ${rep.enabled ? 'translate-x-4' : 'translate-x-0.5'}`} />
                </button>
              </div>

              <div className="flex items-center gap-3 mb-3 text-sm">
                <span className={`font-medium capitalize ${FREQ_COLORS[rep.frequency]}`}>{rep.frequency}</span>
                <span className="text-gray-500">·</span>
                <span><span aria-hidden="true">{CHANNEL_ICONS[rep.delivery_channel]}</span> {rep.delivery_channel}</span>
              </div>

              {rep.recipients.length > 0 && (
                <p className="text-xs text-gray-400 mb-2 truncate">{rep.recipients.join(', ')}</p>
              )}

              <div className="text-xs space-y-1.5 mb-3">
                {/* Last delivery */}
                <div className="flex items-center justify-between">
                  <span className="text-gray-500">Last run</span>
                  <span className={`font-medium ${rep.last_error ? 'text-red-400' : 'text-gray-300'}`}>
                    {rep.last_error
                      ? <span title={rep.last_error}>⚠ {relativeTime(rep.last_run || rep.last_run_at)}</span>
                      : relativeTime(rep.last_run || rep.last_run_at)}
                  </span>
                </div>
                {/* Next run */}
                {(() => {
                  const nxt = rep.next_run || rep.next_run_at;
                  const hoursUntil = nxt ? (new Date(nxt).getTime() - Date.now()) / 3_600_000 : Infinity;
                  const urgentClass = hoursUntil < 1 ? 'text-red-400 font-bold' : hoursUntil < 24 ? 'text-amber-300 font-medium' : 'text-gray-300';
                  return (
                    <div className="flex items-center justify-between">
                      <span className="text-gray-500">Next run</span>
                      <span className={urgentClass}>
                        {hoursUntil < 24 && hoursUntil > 0 && '⏰ '}
                        {relativeTime(nxt)}
                      </span>
                    </div>
                  );
                })()}
                <div className="flex items-center justify-between">
                  <span className="text-gray-500">Total runs</span>
                  <span className="text-gray-300">{rep.run_count}</span>
                </div>
              </div>

              <div className="flex gap-2">
                <button onClick={() => runNow(rep.id)} disabled={running === rep.id}
                  className="flex-1 bg-gray-700 hover:bg-gray-600 disabled:opacity-50 px-3 py-2.5 rounded text-xs">
                  {running === rep.id ? 'Running...' : 'Run Now'}
                </button>
                <button onClick={() => toggleHistory(rep.id)}
                  className="bg-gray-700 hover:bg-gray-600 px-3 py-2.5 rounded text-xs">
                  {historyOpen[rep.id] ? 'Hide' : 'History'}
                </button>
                <button onClick={() => deleteReport(rep.id)}
                  className="bg-red-900/40 hover:bg-red-900/70 px-3 py-2.5 rounded text-xs text-red-300">
                  Delete
                </button>
              </div>
              {historyOpen[rep.id] && (
                <div className="mt-3 border-t border-gray-700 pt-3">
                  {historyLoading[rep.id] ? (
                    <p className="text-xs text-gray-500">Loading...</p>
                  ) : historyError[rep.id] ? (
                    <p className="text-xs text-red-400">Failed to load history —{' '}
                      <button className="underline" onClick={() => { setHistoryError(prev => ({ ...prev, [rep.id]: false })); setHistoryLogs(prev => { const n = {...prev}; delete n[rep.id]; return n; }); toggleHistory(rep.id); }}>Retry</button>
                    </p>
                  ) : !historyLogs[rep.id]?.length ? (
                    <p className="text-xs text-gray-500">No delivery history yet</p>
                  ) : (
                    <table className="w-full text-xs text-gray-300">
                      <thead>
                        <tr className="text-gray-500 border-b border-gray-700">
                          <th className="pb-1 text-left">Date / Time</th>
                          <th className="pb-1 text-left">Status</th>
                          <th className="pb-1 text-left">Recipients</th>
                          <th className="pb-1 text-left">Error</th>
                        </tr>
                      </thead>
                      <tbody>
                        {historyLogs[rep.id].map(log => (
                          <tr key={log.id} className="border-b border-gray-800">
                            <td className="py-1">{new Date(log.run_at).toLocaleString()}</td>
                            <td className="py-1">
                              {log.status === 'success'
                                ? <span className="text-green-400 font-medium">Success</span>
                                : <span className="text-red-400 font-medium">Failed</span>}
                            </td>
                            <td className="py-1">{log.recipients?.join(', ') || '—'}</td>
                            <td className="py-1" title={log.error || ''}>
                              {log.error ? log.error.slice(0, 60) + (log.error.length > 60 ? '…' : '') : '—'}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  )}
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {showCreate && (
        <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50 p-4">
          <div className="bg-gray-800 rounded-xl w-full max-w-lg border border-gray-600 max-h-[90vh] overflow-y-auto">
            <div className="p-6">
              <div className="flex justify-between items-center mb-5">
                <h3 className="font-bold text-lg">Schedule New Report</h3>
                <button onClick={() => setShowCreate(false)} className="text-gray-400 hover:text-white" aria-label="Close">✕</button>
              </div>
              <div className="space-y-4">
                <div>
                  <label className="text-sm text-gray-400 block mb-1">Report Name *</label>
                  <input value={form.name} onChange={e => setForm(p => ({ ...p, name: e.target.value }))}
                    placeholder="e.g. Weekly Security Summary"
                    className="w-full bg-gray-700 border border-gray-600 rounded px-3 py-2 text-sm text-white" />
                </div>
                <div>
                  <label className="text-sm text-gray-400 block mb-1">Report Type *</label>
                  <select value={form.report_type} onChange={e => setForm(p => ({ ...p, report_type: e.target.value }))}
                    className="w-full bg-gray-700 border border-gray-600 rounded px-3 py-2 text-sm text-white">
                    {REPORT_TYPES.map(t => <option key={t} value={t}>{t.replace(/_/g, ' ')}</option>)}
                  </select>
                </div>
                {(form.report_type === 'compliance_summary' || form.report_type === 'custom_framework') && (
                  <div>
                    <label className="text-sm text-gray-400 block mb-1">Compliance Framework</label>
                    <select value={form.framework_id} onChange={e => setForm(p => ({ ...p, framework_id: e.target.value }))}
                      className="w-full bg-gray-700 border border-gray-600 rounded px-3 py-2 text-sm text-white">
                      <option value="" disabled>Select framework...</option>
                      {frameworks.map(f => <option key={f.id} value={f.id}>{f.name}</option>)}
                    </select>
                  </div>
                )}
                <div>
                  <label className="text-sm text-gray-400 block mb-2">Frequency</label>
                  <div className="grid grid-cols-4 gap-2">
                    {FREQUENCIES.map(f => (
                      <label key={f} className={`flex items-center justify-center p-2 rounded border cursor-pointer text-sm font-medium capitalize transition-colors ${form.frequency === f ? 'border-blue-500 bg-blue-900/20 text-blue-300' : 'border-gray-600 text-gray-400 hover:border-gray-400'}`}>
                        <input type="radio" name="frequency" value={f} checked={form.frequency === f}
                          onChange={() => setForm(p => ({ ...p, frequency: f }))} className="sr-only" />
                        {f}
                      </label>
                    ))}
                  </div>
                </div>
                <div>
                  <label className="text-sm text-gray-400 block mb-2">Delivery Channel</label>
                  <div className="grid grid-cols-4 gap-2">
                    {CHANNELS.map(c => (
                      <label key={c} className={`flex items-center justify-center gap-1 p-2 rounded border cursor-pointer text-sm transition-colors ${form.delivery_channel === c ? 'border-blue-500 bg-blue-900/20 text-blue-300' : 'border-gray-600 text-gray-400 hover:border-gray-400'}`}>
                        <input type="radio" name="channel" value={c} checked={form.delivery_channel === c}
                          onChange={() => setForm(p => ({ ...p, delivery_channel: c }))} className="sr-only" />
                        <span aria-hidden="true">{CHANNEL_ICONS[c]}</span> {c}
                      </label>
                    ))}
                  </div>
                </div>
                {(form.delivery_channel === 'email') && (
                  <div>
                    <label className="text-sm text-gray-400 block mb-1">Recipients (comma-separated)</label>
                    <input value={form.recipients} onChange={e => setForm(p => ({ ...p, recipients: e.target.value }))}
                      placeholder="admin@company.com, security@company.com"
                      className="w-full bg-gray-700 border border-gray-600 rounded px-3 py-2 text-sm text-white" />
                  </div>
                )}
                {(form.delivery_channel === 'webhook' || form.delivery_channel === 'slack' || form.delivery_channel === 'teams') && (
                  <div>
                    <label className="text-sm text-gray-400 block mb-1">Webhook URL *</label>
                    <input value={form.webhook_url} onChange={e => setForm(p => ({ ...p, webhook_url: e.target.value }))}
                      placeholder="https://..."
                      className="w-full bg-gray-700 border border-gray-600 rounded px-3 py-2 text-sm text-white" />
                  </div>
                )}
                <div className="flex gap-3 pt-2">
                  <button onClick={createReport} disabled={saving || !form.name}
                    className="flex-1 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 px-4 py-2 rounded-lg text-sm font-medium">
                    {saving ? 'Saving...' : 'Schedule Report'}
                  </button>
                  <button onClick={() => setShowCreate(false)} className="px-4 py-2 rounded-lg border border-gray-600 text-sm">Cancel</button>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

import React, { useState, useEffect } from 'react';
import { authFetch } from '../services/apiService';

interface ScheduledReport {
  id: string;
  name: string;
  report_type: string;
  frequency: string;
  delivery_channel: string;
  recipients: string[];
  enabled: boolean;
  last_run_at: string | null;
  next_run_at: string | null;
  created_at: string;
  run_count: number;
}

const REPORT_TYPES = [
  'security_summary', 'vulnerability_report', 'compliance_status',
  'incident_report', 'agent_health', 'threat_intelligence', 'executive_summary',
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
  });
  const [saving, setSaving] = useState(false);

  useEffect(() => { loadReports(); }, []);

  async function loadReports() {
    try {
      const r = await authFetch('/api/reports/scheduled');
      const d = await r.json();
      setReports(d.reports || []);
    } catch (e) { console.error(e); }
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
      const r = await authFetch('/api/reports/scheduled', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      if (r.ok) { loadReports(); setShowCreate(false); setForm({ name: '', report_type: 'security_summary', frequency: 'weekly', delivery_channel: 'email', recipients: '', webhook_url: '' }); }
      else { const d = await r.json(); alert(d.detail || 'Failed'); }
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
      await authFetch(`/api/reports/scheduled/${id}/run`, { method: 'POST' });
      loadReports();
    } finally { setRunning(null); }
  }

  async function deleteReport(id: string) {
    if (!confirm('Delete this scheduled report?')) return;
    await authFetch(`/api/reports/scheduled/${id}`, { method: 'DELETE' });
    loadReports();
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
                <span>{CHANNEL_ICONS[rep.delivery_channel]} {rep.delivery_channel}</span>
              </div>

              {rep.recipients.length > 0 && (
                <p className="text-xs text-gray-400 mb-2 truncate">{rep.recipients.join(', ')}</p>
              )}

              <div className="text-xs text-gray-500 space-y-0.5 mb-3">
                {rep.last_run_at && <p>Last run: {new Date(rep.last_run_at).toLocaleString()}</p>}
                {rep.next_run_at && <p>Next run: {new Date(rep.next_run_at).toLocaleString()}</p>}
                <p>Runs: {rep.run_count}</p>
              </div>

              <div className="flex gap-2">
                <button onClick={() => runNow(rep.id)} disabled={running === rep.id}
                  className="flex-1 bg-gray-700 hover:bg-gray-600 disabled:opacity-50 px-3 py-1.5 rounded text-xs">
                  {running === rep.id ? 'Running...' : 'Run Now'}
                </button>
                <button onClick={() => deleteReport(rep.id)}
                  className="bg-red-900/40 hover:bg-red-900/70 px-3 py-1.5 rounded text-xs text-red-300">
                  Delete
                </button>
              </div>
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
                <button onClick={() => setShowCreate(false)} className="text-gray-400 hover:text-white">✕</button>
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
                        {CHANNEL_ICONS[c]} {c}
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

import React, { useState, useEffect } from 'react';
import { authFetch } from '../services/apiService';
import { showToast } from '../utils/toast';

const API_BASE = '/api';

type IncidentStatus = 'Open' | 'In Progress' | 'Contained' | 'Resolved' | 'Closed';
type IncidentSeverity = 'Critical' | 'High' | 'Medium' | 'Low';

interface Incident {
  id: string;
  title: string;
  severity: IncidentSeverity;
  status: IncidentStatus;
  assignee?: string;
  createdAt: string;
  updatedAt?: string;
  description?: string;
  affectedAssets?: string[];
  playbook?: string;
}

const SEVERITY_COLOR: Record<IncidentSeverity, string> = {
  Critical: 'bg-red-100 text-red-800 dark:bg-red-900/50 dark:text-red-300',
  High: 'bg-orange-100 text-orange-800 dark:bg-orange-900/50 dark:text-orange-300',
  Medium: 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/50 dark:text-yellow-300',
  Low: 'bg-green-100 text-green-800 dark:bg-green-900/50 dark:text-green-300',
};

const STATUS_COLOR: Record<IncidentStatus, string> = {
  Open: 'bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300',
  'In Progress': 'bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-300',
  Contained: 'bg-purple-100 text-purple-700 dark:bg-purple-900/40 dark:text-purple-300',
  Resolved: 'bg-green-100 text-green-700 dark:bg-green-900/40 dark:text-green-300',
  Closed: 'bg-gray-100 text-gray-600 dark:bg-gray-700 dark:text-gray-400',
};

const PLAYBOOK_STEPS: Record<string, string[]> = {
  ransomware: [
    'Isolate affected endpoints from network',
    'Preserve memory dumps and forensic artifacts',
    'Identify patient-zero via EDR telemetry',
    'Block C2 IOCs at perimeter firewall',
    'Notify legal and executive stakeholders',
    'Initiate backup restoration from known-good snapshot',
    'Conduct full malware scan after recovery',
    'Document timeline and submit to threat intel',
  ],
  phishing: [
    'Quarantine malicious email across all mailboxes',
    'Reset credentials for targeted accounts',
    'Check for lateral movement via auth logs',
    'Block sender domain and URL at email gateway',
    'Notify affected users',
    'Review MFA status for impacted accounts',
    'Submit phishing artifacts to threat intelligence',
  ],
  data_breach: [
    'Identify scope of exposed data',
    'Revoke compromised credentials immediately',
    'Preserve logs for forensic review',
    'Notify DPO and legal team',
    'Assess regulatory notification requirements (GDPR/HIPAA)',
    'Patch the exploited vulnerability',
    'Implement additional monitoring on sensitive data stores',
  ],
  ddos: [
    'Enable upstream traffic scrubbing / CDN protection',
    'Apply rate limiting at load balancer',
    'Identify attack signature and source ASNs',
    'Notify upstream ISP for blackhole routing if needed',
    'Scale out backend capacity',
    'Monitor service recovery and document attack vector',
  ],
  default: [
    'Triage and scope the incident',
    'Assign incident commander',
    'Notify stakeholders per escalation matrix',
    'Collect and preserve evidence',
    'Contain the threat',
    'Eradicate root cause',
    'Recover and restore services',
    'Conduct post-incident review',
  ],
};

function detectPlaybook(incident: Incident): string {
  const text = (incident.title + ' ' + (incident.description || '')).toLowerCase();
  if (text.includes('ransom')) return 'ransomware';
  if (text.includes('phish') || text.includes('email')) return 'phishing';
  if (text.includes('breach') || text.includes('exfil') || text.includes('data loss')) return 'data_breach';
  if (text.includes('ddos') || text.includes('denial')) return 'ddos';
  return 'default';
}

const KpiCard: React.FC<{ label: string; value: number; color?: string }> = ({ label, value, color = 'text-primary-600 dark:text-primary-400' }) => (
  <div className="bg-white dark:bg-gray-800 rounded-lg p-5 shadow-sm border border-gray-200 dark:border-gray-700">
    <p className="text-xs text-gray-500 dark:text-gray-400 uppercase tracking-wide mb-1">{label}</p>
    <p className={`text-3xl font-bold ${color}`}>{value}</p>
  </div>
);

export const IncidentResponseDashboard: React.FC = () => {
  const [incidents, setIncidents] = useState<Incident[]>([]);
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState<Incident | null>(null);
  const [completedSteps, setCompletedSteps] = useState<Set<number>>(new Set());
  const [creating, setCreating] = useState(false);
  const [form, setForm] = useState({ title: '', severity: 'High' as IncidentSeverity, description: '' });
  const [saving, setSaving] = useState(false);
  const [statusFilter, setStatusFilter] = useState<string>('All');

  useEffect(() => {
    loadIncidents();
  }, []);

  const loadIncidents = async () => {
    setLoading(true);
    try {
      const res = await authFetch(`${API_BASE}/security-cases`);
      if (res.ok) {
        const data = await res.json();
        const raw: any[] = Array.isArray(data) ? data : (data.cases || data.items || []);
        setIncidents(raw.map(normalise));
      }
    } catch (e) {
      console.error('Failed to load incidents', e);
      showToast('Failed to load incident data', 'error');
    } finally {
      setLoading(false);
    }
  };

  function normalise(c: any): Incident {
    return {
      id: c.id || c._id || crypto.randomUUID(),
      title: c.title || c.name || c.summary || 'Untitled Incident',
      severity: (c.severity || 'Medium') as IncidentSeverity,
      status: (c.status || 'Open') as IncidentStatus,
      assignee: c.assignee || c.assignedTo || c.owner,
      createdAt: c.createdAt || c.created_at || new Date().toISOString(),
      updatedAt: c.updatedAt || c.updated_at,
      description: c.description || c.summary,
      affectedAssets: c.affectedAssets || c.assets || [],
      playbook: c.playbook,
    };
  }

  const handleCreate = async () => {
    if (!form.title.trim()) return;
    setSaving(true);
    try {
      const res = await authFetch(`${API_BASE}/security-cases`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ title: form.title, severity: form.severity, description: form.description, status: 'Open' }),
      });
      if (res.ok) {
        await loadIncidents();
        setCreating(false);
        setForm({ title: '', severity: 'High', description: '' });
      }
    } catch (e) {
      console.error('Failed to create incident', e);
    } finally {
      setSaving(false);
    }
  };

  const handleStatusChange = async (incident: Incident, newStatus: IncidentStatus) => {
    try {
      await authFetch(`${API_BASE}/security-cases/${incident.id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ status: newStatus }),
      });
      setIncidents(prev => prev.map(i => i.id === incident.id ? { ...i, status: newStatus } : i));
      if (selected?.id === incident.id) setSelected(s => s ? { ...s, status: newStatus } : s);
    } catch (e) {
      console.error('Failed to update status', e);
    }
  };

  const openIncident = (i: Incident) => {
    setSelected(i);
    setCompletedSteps(new Set());
  };

  const toggleStep = (idx: number) => {
    setCompletedSteps(prev => {
      const next = new Set(prev);
      next.has(idx) ? next.delete(idx) : next.add(idx);
      return next;
    });
  };

  const filtered = statusFilter === 'All' ? incidents : incidents.filter(i => i.status === statusFilter);

  const counts = incidents.reduce((acc, i) => {
    acc[i.status] = (acc[i.status] || 0) + 1;
    acc[i.severity] = (acc[i.severity] || 0) + 1;
    return acc;
  }, {} as Record<string, number>);

  const playbookKey = selected ? detectPlaybook(selected) : 'default';
  const steps = PLAYBOOK_STEPS[playbookKey];

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Incident Response</h1>
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">Manage, triage, and resolve security incidents with guided playbooks</p>
        </div>
        <button
          onClick={() => setCreating(true)}
          className="px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 text-sm font-medium"
        >
          + New Incident
        </button>
      </div>

      {/* KPI Row */}
      <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-4">
        <KpiCard label="Total" value={incidents.length} />
        <KpiCard label="Open" value={counts['Open'] || 0} color="text-red-600 dark:text-red-400" />
        <KpiCard label="In Progress" value={counts['In Progress'] || 0} color="text-blue-600 dark:text-blue-400" />
        <KpiCard label="Contained" value={counts['Contained'] || 0} color="text-purple-600 dark:text-purple-400" />
        <KpiCard label="Critical" value={counts['Critical'] || 0} color="text-red-600 dark:text-red-400" />
        <KpiCard label="Resolved" value={counts['Resolved'] || 0} color="text-green-600 dark:text-green-400" />
      </div>

      <div className="flex gap-6">
        {/* Incident List */}
        <div className="flex-1 min-w-0 bg-white dark:bg-gray-800 rounded-lg shadow-sm border border-gray-200 dark:border-gray-700">
          <div className="p-4 border-b border-gray-200 dark:border-gray-700 flex items-center justify-between flex-wrap gap-2">
            <h2 className="text-base font-semibold text-gray-800 dark:text-white">Active Incidents</h2>
            <div className="flex gap-1 flex-wrap">
              {(['All', 'Open', 'In Progress', 'Contained', 'Resolved', 'Closed'] as const).map(s => (
                <button
                  key={s}
                  onClick={() => setStatusFilter(s)}
                  className={`px-2.5 py-1 rounded-full text-xs font-medium transition-colors ${statusFilter === s ? 'bg-primary-600 text-white' : 'bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-600'}`}
                >
                  {s}
                </button>
              ))}
            </div>
          </div>

          {loading ? (
            <div className="p-8 text-center text-gray-500 dark:text-gray-400">Loading incidents...</div>
          ) : filtered.length === 0 ? (
            <div className="p-8 text-center text-gray-400 dark:text-gray-500">
              <p className="text-4xl mb-3">✓</p>
              <p className="font-medium">No incidents found</p>
              <p className="text-sm mt-1">Create a new incident or adjust the filter</p>
            </div>
          ) : (
            <div className="divide-y divide-gray-200 dark:divide-gray-700">
              {filtered.map((incident, idx) => (
                <div
                  key={`${incident.id}-${idx}`}
                  onClick={() => openIncident(incident)}
                  className={`p-4 cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-700/50 transition-colors ${selected?.id === incident.id ? 'bg-primary-50 dark:bg-primary-900/20 border-l-4 border-primary-500' : ''}`}
                >
                  <div className="flex items-start justify-between gap-2">
                    <div className="min-w-0 flex-1">
                      <p className="text-sm font-medium text-gray-900 dark:text-white truncate">{incident.title}</p>
                      <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">
                        {new Date(incident.createdAt).toLocaleString()}
                        {incident.assignee && ` · ${incident.assignee}`}
                      </p>
                    </div>
                    <div className="flex gap-1.5 flex-shrink-0 flex-wrap justify-end">
                      <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${SEVERITY_COLOR[incident.severity]}`}>{incident.severity}</span>
                      <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${STATUS_COLOR[incident.status]}`}>{incident.status}</span>
                    </div>
                  </div>
                  {incident.description && (
                    <p className="text-xs text-gray-500 dark:text-gray-400 mt-1.5 line-clamp-2">{incident.description}</p>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Detail + Playbook Panel */}
        {selected && (
          <div className="w-80 flex-shrink-0 space-y-4">
            {/* Detail Card */}
            <div className="bg-white dark:bg-gray-800 rounded-lg shadow-sm border border-gray-200 dark:border-gray-700 p-4">
              <div className="flex items-start justify-between mb-3">
                <h3 className="text-sm font-semibold text-gray-900 dark:text-white">{selected.title}</h3>
                <button onClick={() => setSelected(null)} className="text-gray-400 hover:text-gray-600 dark:hover:text-gray-200 text-lg leading-none">×</button>
              </div>
              <div className="space-y-2 text-xs">
                <div className="flex justify-between">
                  <span className="text-gray-500 dark:text-gray-400">Severity</span>
                  <span className={`px-1.5 py-0.5 rounded text-xs font-medium ${SEVERITY_COLOR[selected.severity]}`}>{selected.severity}</span>
                </div>
                <div className="flex justify-between items-center">
                  <span className="text-gray-500 dark:text-gray-400">Status</span>
                  <select
                    value={selected.status}
                    onChange={e => handleStatusChange(selected, e.target.value as IncidentStatus)}
                    className="text-xs border border-gray-300 dark:border-gray-600 rounded px-1 py-0.5 bg-white dark:bg-gray-700 text-gray-800 dark:text-gray-200"
                  >
                    {(['Open', 'In Progress', 'Contained', 'Resolved', 'Closed'] as IncidentStatus[]).map(s => (
                      <option key={s} value={s}>{s}</option>
                    ))}
                  </select>
                </div>
                {selected.assignee && (
                  <div className="flex justify-between">
                    <span className="text-gray-500 dark:text-gray-400">Assignee</span>
                    <span className="text-gray-800 dark:text-gray-200">{selected.assignee}</span>
                  </div>
                )}
                <div className="flex justify-between">
                  <span className="text-gray-500 dark:text-gray-400">Opened</span>
                  <span className="text-gray-800 dark:text-gray-200">{new Date(selected.createdAt).toLocaleDateString()}</span>
                </div>
                {selected.affectedAssets && selected.affectedAssets.length > 0 && (
                  <div>
                    <span className="text-gray-500 dark:text-gray-400">Affected Assets</span>
                    <div className="mt-1 flex flex-wrap gap-1">
                      {selected.affectedAssets.slice(0, 4).map(a => (
                        <span key={a} className="px-1.5 py-0.5 bg-gray-100 dark:bg-gray-700 rounded text-gray-700 dark:text-gray-300 text-xs">{a}</span>
                      ))}
                      {selected.affectedAssets.length > 4 && <span className="text-gray-500 text-xs">+{selected.affectedAssets.length - 4}</span>}
                    </div>
                  </div>
                )}
                {selected.description && (
                  <div className="pt-1 border-t border-gray-200 dark:border-gray-700">
                    <p className="text-gray-600 dark:text-gray-400">{selected.description}</p>
                  </div>
                )}
              </div>
            </div>

            {/* Playbook */}
            <div className="bg-white dark:bg-gray-800 rounded-lg shadow-sm border border-gray-200 dark:border-gray-700 p-4">
              <div className="flex items-center justify-between mb-3">
                <h3 className="text-sm font-semibold text-gray-900 dark:text-white">Response Playbook</h3>
                <span className="text-xs px-2 py-0.5 bg-primary-100 dark:bg-primary-900/40 text-primary-700 dark:text-primary-300 rounded-full capitalize">{playbookKey.replace('_', ' ')}</span>
              </div>
              <div className="space-y-2">
                {steps.map((step, idx) => (
                  <div
                    key={idx}
                    onClick={() => toggleStep(idx)}
                    className={`flex items-start gap-2 p-2 rounded cursor-pointer transition-colors ${completedSteps.has(idx) ? 'bg-green-50 dark:bg-green-900/20' : 'hover:bg-gray-50 dark:hover:bg-gray-700/50'}`}
                  >
                    <div className={`flex-shrink-0 w-4 h-4 mt-0.5 rounded border-2 flex items-center justify-center ${completedSteps.has(idx) ? 'bg-green-500 border-green-500' : 'border-gray-400 dark:border-gray-500'}`}>
                      {completedSteps.has(idx) && (
                        <svg className="w-2.5 h-2.5 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={3} d="M5 13l4 4L19 7" />
                        </svg>
                      )}
                    </div>
                    <span className={`text-xs ${completedSteps.has(idx) ? 'line-through text-gray-400 dark:text-gray-500' : 'text-gray-700 dark:text-gray-300'}`}>{step}</span>
                  </div>
                ))}
              </div>
              <div className="mt-3 pt-3 border-t border-gray-200 dark:border-gray-700">
                <div className="flex items-center justify-between text-xs text-gray-500 dark:text-gray-400">
                  <span>{completedSteps.size}/{steps.length} steps completed</span>
                  <div className="w-24 h-1.5 bg-gray-200 dark:bg-gray-700 rounded-full overflow-hidden">
                    <div className="h-full bg-green-500 rounded-full transition-all" style={{ width: `${(completedSteps.size / steps.length) * 100}%` }} />
                  </div>
                </div>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Create Incident Modal */}
      {creating && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
          <div className="bg-white dark:bg-gray-800 rounded-xl shadow-xl w-full max-w-md p-6">
            <div className="flex justify-between items-center mb-4">
              <h2 className="text-lg font-bold text-gray-900 dark:text-white">Create Incident</h2>
              <button onClick={() => setCreating(false)} className="text-gray-400 hover:text-gray-600 dark:hover:text-gray-200">✕</button>
            </div>
            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Title *</label>
                <input
                  value={form.title}
                  onChange={e => setForm(f => ({ ...f, title: e.target.value }))}
                  placeholder="e.g. Ransomware detected on DESKTOP-01"
                  className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white text-sm focus:ring-2 focus:ring-primary-500 outline-none"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Severity</label>
                <select
                  value={form.severity}
                  onChange={e => setForm(f => ({ ...f, severity: e.target.value as IncidentSeverity }))}
                  className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white text-sm"
                >
                  {(['Critical', 'High', 'Medium', 'Low'] as IncidentSeverity[]).map(s => <option key={s}>{s}</option>)}
                </select>
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Description</label>
                <textarea
                  value={form.description}
                  onChange={e => setForm(f => ({ ...f, description: e.target.value }))}
                  rows={3}
                  placeholder="Brief description of the incident..."
                  className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white text-sm resize-none focus:ring-2 focus:ring-primary-500 outline-none"
                />
              </div>
            </div>
            <div className="mt-6 flex justify-end gap-3">
              <button onClick={() => setCreating(false)} className="px-4 py-2 text-sm text-gray-600 dark:text-gray-300 border border-gray-300 dark:border-gray-600 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-700">
                Cancel
              </button>
              <button
                onClick={handleCreate}
                disabled={saving || !form.title.trim()}
                className="px-4 py-2 text-sm bg-primary-600 text-white rounded-lg hover:bg-primary-700 disabled:opacity-50"
              >
                {saving ? 'Creating...' : 'Create Incident'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};